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
