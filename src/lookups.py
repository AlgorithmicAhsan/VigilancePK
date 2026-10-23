"""Editable lists: newspapers, feeds, categories, keywords... (ADR-028).

The client manages these from the dashboard; the pipeline reads the active
rows at the start of every sync, so a change applies on the next run with no
code change.
"""
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
