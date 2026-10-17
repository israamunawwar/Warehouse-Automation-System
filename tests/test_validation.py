import pytest

from functions import ValidationError, _clean_item_fields, parse_int, parse_optional_id, require_text


@pytest.mark.parametrize("value", ["", "abc", "1.5", None, "  "])
def test_parse_int_rejects_non_numbers(value):
    with pytest.raises(ValidationError):
        parse_int(value, "الكمية")


@pytest.mark.parametrize("value", ["0", "-5"])
def test_parse_int_positive_required(value):
    with pytest.raises(ValidationError):
        parse_int(value, "الكمية", minimum=1)


def test_parse_int_accepts_spaces_and_zero_when_allowed():
    assert parse_int(" 7 ", "x", minimum=1) == 7
    assert parse_int("0", "x", minimum=0) == 0


def test_negative_quantity_rejected_for_items():
    with pytest.raises(ValidationError):
        _clean_item_fields("Laptop", "Electronics", "-1", "", 1, None)


def test_optional_id():
    assert parse_optional_id("", "الصندوق") is None
    assert parse_optional_id(None, "الصندوق") is None
    assert parse_optional_id("3", "الصندوق") == 3


def test_non_numeric_box_is_an_error_not_silently_ignored():
    with pytest.raises(ValidationError):
        parse_optional_id("abc", "الصندوق")


def test_require_text():
    assert require_text("  pc ", "الاسم") == "pc"
    with pytest.raises(ValidationError):
        require_text("   ", "الاسم")
    with pytest.raises(ValidationError):
        require_text("x" * 101, "الاسم")


def test_clean_item_fields_ok():
    f = _clean_item_fields(" Laptop ", "Electronics", "5", None, "2", "")
    assert f == {"name": "Laptop", "mtype": "Electronics", "quantity": 5, "description": "",
                 "shelf_id": 2, "box_id": None}
