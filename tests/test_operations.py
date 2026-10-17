import pytest

import functions as fn
from tests.fake_db import FakeDB


@pytest.fixture
def db(monkeypatch):
    db = FakeDB(items={1: 10})
    monkeypatch.setattr(fn, "db_cursor", db.cursor_ctx)
    return db


def test_reserve_reduces_available_but_not_stock(db):
    fn.reserve_material(1, 1, 4)
    assert db.items[1] == 10
    assert db.reserved(1) == 4
    with pytest.raises(fn.InsufficientStock):
        fn.reserve_material(1, 2, 7)          # المتاح 6 فقط


def test_cannot_reserve_more_than_stock(db):
    with pytest.raises(fn.InsufficientStock):
        fn.reserve_material(1, 1, 11)
    assert db.transactions == [] and db.rollbacks == 1


def test_withdraw_cannot_take_other_trainers_reservation(db):
    fn.reserve_material(1, 1, 8)
    with pytest.raises(fn.InsufficientStock):
        fn.withdraw_material(1, 2, 3)         # المتاح لمدرب 2 هو 2 فقط
    assert db.items[1] == 10


def test_withdraw_consumes_own_reservation(db):
    fn.reserve_material(1, 1, 5)
    fn.withdraw_material(1, 1, 5)
    assert db.items[1] == 5
    assert db.reserved(1) == 0
    assert db.actions() == [("Reserve", 5), ("Withdraw", 5), ("CancelReserve", 5)]


def test_withdraw_partially_uses_reservation_then_general_stock(db):
    fn.reserve_material(1, 1, 2)
    fn.withdraw_material(1, 1, 6)
    assert db.items[1] == 4 and db.reserved(1) == 0


@pytest.mark.parametrize("qty", ["0", "-5", "abc", ""])
def test_invalid_quantities_never_touch_stock(db, qty):
    for op in (fn.withdraw_material, fn.reserve_material, fn.return_material, fn.cancel_reservation):
        with pytest.raises(fn.ValidationError):
            op(1, 1, qty)
    assert db.items[1] == 10 and db.transactions == []


def test_negative_withdraw_cannot_increase_stock(db):
    with pytest.raises(fn.ValidationError):
        fn.withdraw_material(1, 1, -5)
    assert db.items[1] == 10


def test_return_restores_stock_and_is_limited_to_outstanding(db):
    fn.withdraw_material(1, 1, 3)
    with pytest.raises(fn.ValidationError):
        fn.return_material(1, 1, 4)           # سحب 3 فقط
    with pytest.raises(fn.ValidationError):
        fn.return_material(1, 2, 1)           # مدرب آخر لم يسحب
    fn.return_material(1, 1, 3)
    assert db.items[1] == 10


def test_cancel_reservation_limits(db):
    fn.reserve_material(1, 1, 3)
    with pytest.raises(fn.ValidationError):
        fn.cancel_reservation(1, 1, 4)
    with pytest.raises(fn.ValidationError):
        fn.cancel_reservation(1, 2, 1)
    fn.cancel_reservation(1, 1, 3)
    assert db.reserved(1) == 0


def test_unknown_item_or_trainer(db):
    with pytest.raises(fn.ValidationError):
        fn.withdraw_material(99, 1, 1)
    with pytest.raises(fn.ValidationError):
        fn.withdraw_material(1, 99, 1)


def test_failure_rolls_back_whole_transaction(db):
    with pytest.raises(fn.InsufficientStock):
        fn.withdraw_material(1, 1, 50)
    assert db.rollbacks == 1 and db.commits == 0
