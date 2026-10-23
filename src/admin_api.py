"""Login and editable lists for the dashboard (ADR-029, ADR-031).

Everything here except /auth/login needs a signed-in user. Changing lists
needs the admin role; reviewers can read them.
"""
from fastapi import APIRouter, Body, Depends, Header, HTTPException, Request
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from src import auth, db, lookups

router = APIRouter()
limiter = auth.LoginLimiter()

MAX_UPLOAD_BYTES = 5 * 1024 * 1024


def find_user_by_name(username: str):
    with db.connection() as conn:
        return conn.execute("SELECT id, username, role, active, password_hash FROM users "
                            "WHERE lower(username) = lower(%s)", (username,)).fetchone()


def find_user_by_id(user_id: int):
    with db.connection() as conn:
        return conn.execute("SELECT id, username, role, active FROM users WHERE id = %s", (user_id,)).fetchone()


def current_user(authorization: str = Header(default="")) -> dict:
    """Any signed-in, active user. The row is re-read every request, so a
    disabled account or a changed role applies immediately."""
    scheme, _, token = authorization.partition(" ")
    user_id = auth.verify_token(token) if scheme.lower() == "bearer" and token else None
    user = find_user_by_id(user_id) if user_id is not None else None
    if not user or not user["active"]:
        raise HTTPException(status_code=401, detail="Please sign in.")
    return {"id": user["id"], "username": user["username"], "role": user["role"]}


def require_admin(user: dict = Depends(current_user)) -> dict:
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Only admins can do this.")
    return user


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/auth/login")
def login(body: LoginRequest):
    username = body.username.strip()
    wait = limiter.locked_for(username)
    if wait:
        raise HTTPException(status_code=429, detail=f"Too many failed attempts. Try again in {wait // 60 + 1} minutes.")

    user = find_user_by_name(username)
    if user is None:
        auth.dummy_check(body.password)  # same time cost as a wrong password
    ok = user is not None and auth.verify_password(body.password, user["password_hash"]) and user["active"]
    if not ok:
        limiter.failed(username)
        # One message for every failure, so it never confirms a username exists.
        raise HTTPException(status_code=401, detail="Wrong username or password.")

    limiter.succeeded(username)
    token, expires = auth.create_token(user["id"])
    return {"token": token, "expires_at": expires, "user": {"username": user["username"], "role": user["role"]}}


@router.get("/auth/me")
def me(user: dict = Depends(current_user)):
    return user


@router.get("/lookups/summary")
def lookups_summary(user: dict = Depends(current_user)):
    return lookups.summary()


@router.get("/lookups")
def lookups_list(kind: str, user: dict = Depends(current_user)):
    try:
        return lookups.list_kind(kind)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/lookups", status_code=201)
def lookups_create(body: dict = Body(...), user: dict = Depends(require_admin)):
    try:
        return lookups.create(str(body.get("kind", "")), body)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.patch("/lookups/{lookup_id}")
def lookups_update(lookup_id: int, body: dict = Body(...), user: dict = Depends(require_admin)):
    try:
        return lookups.update(lookup_id, body)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/lookups/import")
async def lookups_import(request: Request, user: dict = Depends(require_admin)):
    """Takes an HRMS Excel export as the raw request body (no multipart
    library needed) and upserts it by the client's IDs."""
    data = await request.body()
    if not data:
        raise HTTPException(status_code=400, detail="No file received.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File is larger than 5 MB.")

    def run():
        import io
        kind, rows = lookups.parse_hrms_export(io.BytesIO(data))
        return {"kind": kind, **lookups.import_rows(rows)}

    try:
        return await run_in_threadpool(run)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:  # a corrupt or non-Excel file
        print(f"ERROR: import failed: {e}")
        raise HTTPException(status_code=400, detail="Could not read this file. Upload an HRMS Excel export (.xlsx).")
