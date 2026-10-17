"""قاعدة وهمية في الذاكرة تحاكي الاستعلامات التي تستخدمها دوال العمليات (حجز/سحب/إرجاع)."""
from contextlib import contextmanager


class FakeDB:
    def __init__(self, items=None, trainers=(1, 2)):
        self.items = dict(items or {1: 10})        # item_id -> quantity
        self.trainers = set(trainers)
        self.transactions = []                      # (item_id, trainer_id, action, qty)
        self.commits = 0
        self.rollbacks = 0

    def reserved(self, item_id, trainer_id=None):
        total = 0
        for i, t, a, q in self.transactions:
            if i == item_id and (trainer_id is None or t == trainer_id):
                total += q if a == "Reserve" else -q if a == "CancelReserve" else 0
        return total

    def outstanding(self, item_id, trainer_id):
        return sum(q if a == "Withdraw" else -q if a == "Return" else 0
                   for i, t, a, q in self.transactions if i == item_id and t == trainer_id)

    def actions(self):
        return [(a, q) for _, _, a, q in self.transactions]

    @contextmanager
    def cursor_ctx(self):
        cur = FakeCursor(self)
        try:
            yield cur
            self.commits += 1
        except Exception:
            self.rollbacks += 1
            raise


class FakeCursor:
    def __init__(self, db):
        self.db, self._row = db, None

    def execute(self, sql, params=()):
        sql = " ".join(sql.split())
        db, p = self.db, tuple(params)
        if "FROM Items WITH (UPDLOCK" in sql:
            self._row = (db.items[p[0]], 1) if p[0] in db.items else None
        elif "SELECT IsActive FROM Trainers" in sql:
            self._row = (1,) if p[0] in db.trainers else None
        elif "FROM vw_Reservations WHERE ItemID = ? AND TrainerID = ?" in sql:
            self._row = (db.reserved(p[0], p[1]),)
        elif "FROM vw_Reservations WHERE ItemID = ?" in sql:
            self._row = (db.reserved(p[0]),)
        elif "WHEN 'Withdraw'" in sql and "ItemID = ? AND TrainerID = ?" in sql:
            self._row = (db.outstanding(p[0], p[1]),)
        elif sql.startswith("UPDATE Items SET Quantity = Quantity -"):
            db.items[p[1]] -= p[0]
        elif sql.startswith("UPDATE Items SET Quantity = Quantity +"):
            db.items[p[1]] += p[0]
        elif sql.startswith("INSERT INTO Transactions"):
            db.transactions.append((p[0], p[1], p[2], p[3]))
        else:
            raise AssertionError(f"استعلام غير متوقع في القاعدة الوهمية: {sql}")
        return self

    def fetchone(self):
        return self._row
