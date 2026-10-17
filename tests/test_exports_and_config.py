import pytest

import functions as fn
from database import build_connection_string

DATA = [
    {"id": 1, "date": "2026-01-19 09:00", "trainer": "أحمد", "action": "Withdraw",
     "action_label": "سحب", "qty": 2, "item": "Laptop"},
    {"id": 2, "date": "2026-01-19 10:00", "trainer": "Sarah", "action": "Reserve",
     "action_label": "حجز", "qty": 1, "item": "جهاز عرض"},
]


def test_txt_export_roundtrip(tmp_path):
    path = tmp_path / "r.txt"
    assert fn.export_to_txt(str(path), DATA)
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    assert lines[0].split("\t") == ["التاريخ", "المدرب", "العملية", "الكمية", "المادة"]
    assert lines[1].split("\t") == ["2026-01-19 09:00", "أحمد", "سحب", "2", "Laptop"]


def test_txt_export_bad_path_raises_friendly_error(tmp_path):
    with pytest.raises(fn.WarehouseError):
        fn.export_to_txt(str(tmp_path / "missing" / "r.txt"), DATA)


def test_pdf_export_creates_file(tmp_path):
    pytest.importorskip("fpdf")
    path = tmp_path / "r.pdf"
    assert fn.export_to_pdf(str(path), DATA)
    assert path.read_bytes().startswith(b"%PDF")


def test_connection_string_windows_auth():
    s = build_connection_string({"driver": "D", "server": "S", "database": "DB",
                                 "trusted_connection": "yes", "user": "", "password": ""})
    assert "SERVER=S" in s and "Trusted_Connection=yes" in s and "UID" not in s


def test_connection_string_sql_login():
    s = build_connection_string({"driver": "D", "server": "S", "database": "DB",
                                 "trusted_connection": "no", "user": "u", "password": "p"})
    assert "UID=u" in s and "PWD=p" in s and "Trusted_Connection" not in s
