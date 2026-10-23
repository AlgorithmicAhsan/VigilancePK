"""Editable lists: newspapers, feeds, categories, keywords... (ADR-028).

The client manages these from the dashboard; the pipeline reads the active
rows at the start of every sync, so a change applies on the next run with no
code change.
"""
from urllib.parse import urlparse

import openpyxl
from psycopg import errors
from src import db

# HRMS admin exports: a title row, then a header row, then data. The ID
# column's header tells us which list a file holds.
HRMS_LISTS = {
    "Category ID": ("category", "Category Name"),
    "Sub-Category ID": ("sub_category", "Sub-Category Name"),
    "Keywords ID": ("keyword", "Keywords"),
    "Newspaper ID": ("newspaper", "Newspaper Name"),
}

# Lists the client did not supply. Our assumptions, seeded once and editable
# from the dashboard afterwards (ADR-028).
DEFAULTS = {
    "province": ["Punjab", "Sindh", "Khyber Pakhtunkhwa", "Balochistan", "Islamabad",
                 "Gilgit-Baltistan", "Azad Jammu and Kashmir", "International"],
    "news_type": ["News", "Editorial", "Column", "Article", "Letter", "Feature"],
}


def _text(value):
    text = str(value).strip() if value is not None else ""
    return text or None


def default_frequency(newspaper_name: str) -> str:
    """HRMS exports have no frequency. Magazines are weekly, the rest daily;
    the client can correct any of them in the dashboard."""
    return "Weekly" if "magazine" in newspaper_name.lower() or "prism" in newspaper_name.lower() else "Daily"


def parse_hrms_export(file) -> tuple[str, list[dict]]:
    """Reads one HRMS Excel export. Returns (kind, rows)."""
    sheet = openpyxl.load_workbook(file, read_only=True, data_only=True).worksheets[0]
    rows = sheet.iter_rows(values_only=True)

    for header in rows:
        cells = [_text(c) for c in header]
        match = next((h for h in HRMS_LISTS if h in cells), None)
        if match:
            break
    else:
        raise ValueError("Not an HRMS export: no known ID column found.")

    kind, name_header = HRMS_LISTS[match]
    col = {name: i for i, name in enumerate(cells) if name}
    if name_header not in col:
        raise ValueError(f"Missing column '{name_header}'.")

    def cell(row, header):
        i = col.get(header)
        return _text(row[i]) if i is not None and i < len(row) else None

    parsed = []
    for row in rows:
        hrms_id, name = cell(row, match), cell(row, name_header)
        if hrms_id is None or name is None:
            continue
        parsed.append({
            "kind": kind,
            "hrms_id": int(float(hrms_id)),
            "name": name,
            "active": (cell(row, "Status") or "Active").lower() == "active",
            "control": cell(row, "Control Options"),
            "language": cell(row, "Language"),
            "city": cell(row, "City Name"),
            "frequency": default_frequency(name) if kind == "newspaper" else None,
        })
    return kind, parsed


UPSERT = """
INSERT INTO lookups (kind, hrms_id, name, language, city, frequency, control, active)
VALUES (%(kind)s, %(hrms_id)s, %(name)s, %(language)s, %(city)s, %(frequency)s, %(control)s, %(active)s)
ON CONFLICT (kind, hrms_id) WHERE hrms_id IS NOT NULL DO UPDATE SET
    name = EXCLUDED.name,
    language = COALESCE(EXCLUDED.language, lookups.language),
    city = COALESCE(EXCLUDED.city, lookups.city),
    -- Frequency is ours, not HRMS's: never overwrite a value someone set.
    frequency = COALESCE(lookups.frequency, EXCLUDED.frequency),
    control = EXCLUDED.control,
    active = EXCLUDED.active,
    updated_at = now()
RETURNING (xmax = 0) AS inserted
"""


def import_rows(rows: list[dict]) -> dict:
    """Upserts by the client's ID. Rows missing from a file are left as they
    are (never deleted). Returns counts plus any rows that failed."""
    result = {"inserted": 0, "updated": 0, "failed": []}

    # The client's own lists contain the same name under two IDs. Which ID is
    # meant can't be known, so the first one wins and the rest are reported.
    seen, unique = set(), []
    for row in rows:
        if row["name"].lower() in seen:
            result["failed"].append(f"{row['name']} (ID {row['hrms_id']}): duplicate name in this file")
        else:
            seen.add(row["name"].lower())
            unique.append(row)

    # Fast path: the whole file in one round trip. Neon is far away, and one
    # trip per row took minutes for the keyword list.
    try:
        with db.connection() as conn, conn.cursor() as cur:
            cur.executemany(UPSERT, unique, returning=True)
            while True:
                result["inserted" if cur.fetchone()["inserted"] else "updated"] += 1
                if not cur.nextset():
                    break
        return result
    except errors.UniqueViolation:
        result["inserted"] = result["updated"] = 0  # rolled back; redo row by row

    # Slow path, only when a name clashes with a different ID already stored.
    with db.connection() as conn:
        for row in unique:
            try:
                # A savepoint per row, so one bad row doesn't undo the rest.
                with conn.transaction():
                    inserted = conn.execute(UPSERT, row).fetchone()["inserted"]
                result["inserted" if inserted else "updated"] += 1
            except errors.UniqueViolation:
                result["failed"].append(f"{row['name']} (ID {row['hrms_id']}): another entry already uses this name")
    return result


def seed_defaults() -> dict:
    """Adds our default lists, only for kinds that are still empty."""
    added = {}
    with db.connection() as conn:
        for kind, names in DEFAULTS.items():
            if conn.execute("SELECT 1 FROM lookups WHERE kind = %s LIMIT 1", (kind,)).fetchone():
                continue
            for name in names:
                conn.execute("INSERT INTO lookups (kind, name) VALUES (%s, %s)", (kind, name))
            added[kind] = len(names)
    return added


# --- Editing from the dashboard ------------------------------------------

KINDS = ("newspaper", "feed", "category", "sub_category", "keyword", "news_type", "province", "city")

# Which optional fields each kind uses; the rest are stored as NULL.
FIELDS = {
    "newspaper": ("hrms_id", "language", "city", "frequency"),
    "feed": ("parent", "url"),
    "category": ("hrms_id", "control"),
    "sub_category": ("hrms_id", "control"),
    "keyword": ("hrms_id",),
    "news_type": (),
    "province": (),
    "city": ("parent",),
}
# A feed belongs to a newspaper; a city belongs to a province.
PARENT_KIND = {"feed": "newspaper", "city": "province"}
REQUIRED = {"feed": ("parent", "url"), "city": ("parent",)}
OPTIONAL = ("hrms_id", "parent", "url", "language", "city", "frequency", "control")


def clean_lookup(kind: str, data: dict, partial: bool = False) -> dict:
    """Checks one entry from the dashboard. Returns only the columns this
    kind uses, cleaned. Raises ValueError with a message for the user."""
    if kind not in KINDS:
        raise ValueError(f"Unknown list '{kind}'.")
    out = {}

    if "name" in data or not partial:
        name = _text(data.get("name"))
        if not name:
            raise ValueError("Name is required.")
        if len(name) > 300:
            raise ValueError("Name is too long (300 characters max).")
        out["name"] = name

    for field in OPTIONAL:
        if field not in data and partial:
            continue
        value = _text(data.get(field)) if field in FIELDS[kind] else None
        if field == "hrms_id" and value is not None:
            try:
                value = int(value)
            except ValueError:
                raise ValueError("HRMS ID must be a whole number.")
            if not 0 < value < 10 ** 9:
                raise ValueError("HRMS ID must be a positive number.")
        if field == "url" and value is not None:
            parsed = urlparse(value)
            if parsed.scheme not in ("http", "https") or not parsed.netloc:
                raise ValueError("Feed URL must start with http:// or https://.")
        if isinstance(value, str) and len(value) > 1000:
            raise ValueError(f"{field} is too long.")
        if field in REQUIRED.get(kind, ()) and value is None:
            raise ValueError(f"{field.capitalize()} is required for a {kind.replace('_', ' ')}.")
        out[field] = value

    if "active" in data or not partial:
        out["active"] = bool(data.get("active", True))
    return out


def _resolve_parent(conn, kind: str, entry: dict) -> None:
    """Replaces the typed parent with the stored name, or rejects it."""
    if not entry.get("parent") or kind not in PARENT_KIND:
        return
    row = conn.execute("SELECT name FROM lookups WHERE kind = %s AND lower(name) = lower(%s)",
                       (PARENT_KIND[kind], entry["parent"])).fetchone()
    if not row:
        raise ValueError(f"No {PARENT_KIND[kind]} called '{entry['parent']}'.")
    entry["parent"] = row["name"]


COLUMNS = "id, kind, hrms_id, name, parent, url, language, city, frequency, control, active, updated_at"


def summary() -> dict:
    with db.connection() as conn:
        rows = conn.execute("SELECT kind, count(*) AS total, count(*) FILTER (WHERE active) AS active "
                            "FROM lookups GROUP BY kind").fetchall()
    found = {r["kind"]: {"total": r["total"], "active": r["active"]} for r in rows}
    return {kind: found.get(kind, {"total": 0, "active": 0}) for kind in KINDS}


def list_kind(kind: str) -> list[dict]:
    if kind not in KINDS:
        raise ValueError(f"Unknown list '{kind}'.")
    with db.connection() as conn:
        return conn.execute(f"SELECT {COLUMNS} FROM lookups WHERE kind = %s ORDER BY active DESC, lower(name)",
                            (kind,)).fetchall()


def create(kind: str, data: dict) -> dict:
    entry = clean_lookup(kind, data)
    with db.connection() as conn:
        _resolve_parent(conn, kind, entry)
        try:
            return conn.execute(
                f"INSERT INTO lookups (kind, {', '.join(entry)}) VALUES (%s, {', '.join(['%s'] * len(entry))}) "
                f"RETURNING {COLUMNS}", (kind, *entry.values())).fetchone()
        except errors.UniqueViolation:
            raise ValueError("An entry with this name or HRMS ID already exists in this list.")


def update(lookup_id: int, data: dict) -> dict:
    with db.connection() as conn:
        current = conn.execute("SELECT kind FROM lookups WHERE id = %s", (lookup_id,)).fetchone()
        if not current:
            raise LookupError("Entry not found.")
        entry = clean_lookup(current["kind"], data, partial=True)
        if not entry:
            raise ValueError("Nothing to change.")
        _resolve_parent(conn, current["kind"], entry)
        sets = ", ".join(f"{field} = %s" for field in entry)
        try:
            return conn.execute(f"UPDATE lookups SET {sets}, updated_at = now() WHERE id = %s RETURNING {COLUMNS}",
                                (*entry.values(), lookup_id)).fetchone()
        except errors.UniqueViolation:
            raise ValueError("An entry with this name or HRMS ID already exists in this list.")
