import openpyxl
import pytest

from src.lookups import default_frequency, parse_hrms_export


def _export(tmp_path, header, rows):
    """Builds a file shaped like the HRMS admin exports: title, header, data."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["\n                HRMS            "])
    ws.append(header)
    for r in rows:
        ws.append(r)
    path = tmp_path / "export.xlsx"
    wb.save(path)
    return path


def test_parses_categories(tmp_path):
    path = _export(tmp_path, ["Action", "Category ID", "Category Name", "Status", "Control Options"],
                   [[None, 2, "Armed Forces", "Active", "ShowonBoth"],
                    [None, 16, " Civil rights ", "Inactive", "ShowonReport"]])
    kind, rows = parse_hrms_export(path)
    assert kind == "category"
    assert [(r["hrms_id"], r["name"], r["active"], r["control"]) for r in rows] == [
        (2, "Armed Forces", True, "ShowonBoth"),
        (16, "Civil rights", False, "ShowonReport"),
    ]


def test_parses_newspapers_with_city_language_and_frequency(tmp_path):
    path = _export(tmp_path, ["Action", "Newspaper ID", "Newspaper Name", "City Name", "Language", "Status"],
                   [[None, 2, "Aaj", "Peshawar", "Urdu", "Active"],
                    [None, 9, "Dawn Magazine", "Lahore", "English", "Active"],
                    [None, 3, "Aaj Kal", None, None, "Inactive"]])
    kind, rows = parse_hrms_export(path)
    assert kind == "newspaper"
    assert rows[0]["city"] == "Peshawar" and rows[0]["language"] == "Urdu"
    assert [r["frequency"] for r in rows] == ["Daily", "Weekly", "Daily"]
    assert rows[2]["city"] is None and rows[2]["active"] is False


def test_keywords_have_no_frequency(tmp_path):
    path = _export(tmp_path, ["Action", "Keywords ID", "Keywords", "Status"], [[None, 112, "(CPWB)", "Active"]])
    kind, rows = parse_hrms_export(path)
    assert kind == "keyword" and rows[0]["frequency"] is None and rows[0]["name"] == "(CPWB)"


def test_skips_blank_rows(tmp_path):
    path = _export(tmp_path, ["Action", "Keywords ID", "Keywords", "Status"],
                   [[None, None, None, None], [None, 5, None, "Active"], [None, 6, "kept", "Active"]])
    assert [r["hrms_id"] for r in parse_hrms_export(path)[1]] == [6]


def test_rejects_unknown_files(tmp_path):
    path = _export(tmp_path, ["Name", "Value"], [["a", 1]])
    with pytest.raises(ValueError):
        parse_hrms_export(path)


@pytest.mark.parametrize("name, expected", [
    ("Dawn", "Daily"), ("Dawn Magazine", "Weekly"), ("Dawn Prism", "Weekly"), ("Jang - Magazine", "Weekly"),
])
def test_default_frequency(name, expected):
    assert default_frequency(name) == expected


# --- dashboard validation ---------------------------------------------------

from src.lookups import clean_lookup


def test_clean_keeps_only_fields_the_kind_uses():
    out = clean_lookup("keyword", {"name": " storms ", "hrms_id": "334", "url": "http://x", "language": "Urdu"})
    assert out["name"] == "storms" and out["hrms_id"] == 334
    assert out["url"] is None and out["language"] is None and out["active"] is True


def test_feed_needs_newspaper_and_http_url():
    with pytest.raises(ValueError, match="Parent"):
        clean_lookup("feed", {"name": "Dawn home", "url": "https://dawn.com/feed"})
    with pytest.raises(ValueError, match="http"):
        clean_lookup("feed", {"name": "Dawn home", "parent": "Dawn", "url": "javascript:alert(1)"})
    ok = clean_lookup("feed", {"name": "Dawn home", "parent": "Dawn", "url": "https://www.dawn.com/feeds/home"})
    assert ok["parent"] == "Dawn"


@pytest.mark.parametrize("data, message", [
    ({"name": ""}, "Name is required"),
    ({"name": "x" * 301}, "too long"),
    ({"name": "a", "hrms_id": "abc"}, "whole number"),
    ({"name": "a", "hrms_id": "-4"}, "positive"),
])
def test_bad_input_is_rejected(data, message):
    with pytest.raises(ValueError, match=message):
        clean_lookup("category", data)


def test_unknown_kind_is_rejected():
    with pytest.raises(ValueError, match="Unknown"):
        clean_lookup("users", {"name": "x"})


def test_partial_update_touches_only_given_fields():
    assert clean_lookup("newspaper", {"active": False}, partial=True) == {"active": False}
    assert clean_lookup("newspaper", {"frequency": "Weekly"}, partial=True) == {"frequency": "Weekly"}
