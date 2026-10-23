"""Login and permission rules, with an in-memory user store (no database)."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src import admin_api, auth, lookups


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "s" * 40)
    users = {
        1: {"id": 1, "username": "boss", "role": "admin", "active": True, "password_hash": auth.hash_password("admin password 1")},
        2: {"id": 2, "username": "rev", "role": "reviewer", "active": True, "password_hash": auth.hash_password("review password 1")},
        3: {"id": 3, "username": "gone", "role": "admin", "active": False, "password_hash": auth.hash_password("gone password 1")},
    }
    monkeypatch.setattr(admin_api, "find_user_by_name",
                        lambda name: next((u for u in users.values() if u["username"] == name.lower()), None))
    monkeypatch.setattr(admin_api, "find_user_by_id", lambda uid: users.get(uid))
    monkeypatch.setattr(admin_api, "limiter", auth.LoginLimiter(max_failures=3, lockout=600))
    monkeypatch.setattr(lookups, "summary", lambda: {"keyword": {"total": 1, "active": 1}})
    monkeypatch.setattr(lookups, "create", lambda kind, body: {"id": 9, "kind": kind, "name": body["name"]})
    app = FastAPI()
    app.include_router(admin_api.router)
    return TestClient(app)


def login(client, username, password):
    return client.post("/auth/login", json={"username": username, "password": password})


def bearer(client, username, password):
    return {"Authorization": "Bearer " + login(client, username, password).json()["token"]}


def test_login_returns_token_and_role(client):
    res = login(client, "Boss", "admin password 1")
    assert res.status_code == 200
    assert res.json()["user"] == {"username": "boss", "role": "admin"}


@pytest.mark.parametrize("username, password", [("boss", "wrong password"), ("nobody", "admin password 1"), ("gone", "gone password 1")])
def test_failed_logins_share_one_message(client, username, password):
    res = login(client, username, password)
    assert res.status_code == 401 and res.json()["detail"] == "Wrong username or password."


def test_lockout_after_repeated_failures(client):
    for _ in range(3):
        login(client, "boss", "wrong password")
    res = login(client, "boss", "admin password 1")
    assert res.status_code == 429


def test_routes_need_a_valid_token(client):
    assert client.get("/lookups/summary").status_code == 401
    assert client.get("/lookups/summary", headers={"Authorization": "Bearer junk"}).status_code == 401
    assert client.get("/lookups/summary", headers=bearer(client, "rev", "review password 1")).status_code == 200


def test_reviewers_can_read_but_not_edit(client):
    headers = bearer(client, "rev", "review password 1")
    assert client.post("/lookups", json={"kind": "keyword", "name": "x"}, headers=headers).status_code == 403
    assert client.post("/lookups/import", content=b"x", headers=headers).status_code == 403


def test_admins_can_edit(client):
    res = client.post("/lookups", json={"kind": "keyword", "name": "x"}, headers=bearer(client, "boss", "admin password 1"))
    assert res.status_code == 201 and res.json()["name"] == "x"


def test_import_rejects_non_excel(client):
    res = client.post("/lookups/import", content=b"not a spreadsheet", headers=bearer(client, "boss", "admin password 1"))
    assert res.status_code == 400 and "Excel" in res.json()["detail"]
