"""طبقة البيانات ومنطق العمل لنظام إدارة المستودع.

كل دالة تعمل داخل معاملة واحدة (db_cursor) وتُرجع بيانات بسيطة، وترمي WarehouseError
(أو إحدى فئاتها) برسالة عربية مفهومة بدل استثناءات pyodbc الخام.
"""
import functools
import logging
import os
from datetime import datetime

import pyodbc

from database import db_cursor

log = logging.getLogger(__name__)

ACTION_LABELS = {
    "Reserve": "حجز",
    "CancelReserve": "إلغاء حجز",
    "Withdraw": "سحب",
    "Return": "إرجاع",
}


# ---------------------------------------------------------------- الاستثناءات
class WarehouseError(Exception):
    """أساس كل أخطاء النظام؛ رسالتها صالحة للعرض للمستخدم."""


class ValidationError(WarehouseError):
    """مدخلات غير صالحة."""


class InsufficientStock(WarehouseError):
    """الكمية المتاحة لا تكفي."""


class DatabaseError(WarehouseError):
    """خطأ في الاتصال بقاعدة البيانات أو تنفيذ الاستعلام."""


_CONNECTION_STATES = {"08001", "08S01", "28000", "HYT00", "HYT01", "IM002"}


def _friendly_db_message(err):
    state = str(err.args[0]) if err.args else ""
    if state in _CONNECTION_STATES:
        return "تعذر الاتصال بقاعدة البيانات. تحقق من الخادم وملف config.ini."
    if state.startswith("23"):
        return "العملية تخالف قيود قاعدة البيانات (قد يكون العنصر مرتبطًا ببيانات أخرى)."
    return "حدث خطأ في قاعدة البيانات."


def _db(func):
    """يحوّل أخطاء pyodbc إلى DatabaseError ويسجّل التفاصيل في السجل."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except pyodbc.Error as e:
            log.exception("Database error in %s", func.__name__)
            raise DatabaseError(_friendly_db_message(e)) from e
    return wrapper


# ---------------------------------------------------------------- التحقق من المدخلات
def parse_int(value, field, minimum=None):
    text = str(value).strip() if value is not None else ""
    try:
        number = int(text)
    except ValueError:
        raise ValidationError(f"«{field}» يجب أن يكون رقمًا صحيحًا.") from None
    if minimum is not None and number < minimum:
        limit = "أكبر من صفر" if minimum == 1 else f"لا يقل عن {minimum}"
        raise ValidationError(f"«{field}» يجب أن يكون {limit}.")
    return number


def parse_optional_id(value, field):
    text = str(value).strip() if value is not None else ""
    if text in ("", "None"):
        return None
    return parse_int(text, field, minimum=1)


def require_text(value, field, max_len=100):
    text = (value or "").strip()
    if not text:
        raise ValidationError(f"«{field}» مطلوب.")
    if len(text) > max_len:
        raise ValidationError(f"«{field}» أطول من {max_len} حرفًا.")
    return text


def _clean_item_fields(name, mtype, quantity, description, shelf_id, box_id):
    return {
        "name": require_text(name, "اسم المادة"),
        "mtype": require_text(mtype, "النوع"),
        "quantity": parse_int(quantity, "الكمية", minimum=0),
        "description": require_text_optional(description, "الوصف", 255),
        "shelf_id": parse_int(shelf_id, "الرف", minimum=1) if shelf_id not in (None, "") else None,
        "box_id": parse_optional_id(box_id, "الصندوق"),
    }


def require_text_optional(value, field, max_len):
    text = (value or "").strip()
    if len(text) > max_len:
        raise ValidationError(f"«{field}» أطول من {max_len} حرفًا.")
    return text


def _check_placement(cursor, shelf_id, box_id):
    if shelf_id is None:
        raise ValidationError("يجب اختيار الرف.")
    if cursor.execute("SELECT 1 FROM Shelves WHERE ShelfID = ?", (shelf_id,)).fetchone() is None:
        raise ValidationError("الرف المحدد غير موجود.")
    if box_id is not None:
        row = cursor.execute("SELECT ShelfID FROM Boxes WHERE BoxID = ?", (box_id,)).fetchone()
        if row is None:
            raise ValidationError("الصندوق المحدد غير موجود.")
        if row[0] != shelf_id:
            raise ValidationError("الصندوق المحدد لا ينتمي إلى هذا الرف.")


# ---------------------------------------------------------------- قوائم الاختيار
@_db
def get_all_trainers(include_inactive=False):
    sql = "SELECT TrainerID, TrainerName FROM Trainers"
    if not include_inactive:
        sql += " WHERE IsActive = 1"
    with db_cursor() as cur:
        return [tuple(r) for r in cur.execute(sql + " ORDER BY TrainerName").fetchall()]


@_db
def get_all_items_list(include_inactive=False):
    sql = "SELECT ItemID, ItemName FROM Items"
    if not include_inactive:
        sql += " WHERE IsActive = 1"
    with db_cursor() as cur:
        return [tuple(r) for r in cur.execute(sql + " ORDER BY ItemName").fetchall()]


# ---------------------------------------------------------------- المواد
@_db
def add_material(name, mtype, quantity, description, shelf_id, box_id):
    f = _clean_item_fields(name, mtype, quantity, description, shelf_id, box_id)
    with db_cursor() as cur:
        _check_placement(cur, f["shelf_id"], f["box_id"])
        cur.execute(
            "INSERT INTO Items (ItemName, ItemType, Quantity, Description, ShelfID, BoxID) "
            "OUTPUT INSERTED.ItemID VALUES (?, ?, ?, ?, ?, ?)",
            (f["name"], f["mtype"], f["quantity"], f["description"], f["shelf_id"], f["box_id"]),
        )
        return cur.fetchone()[0]


@_db
def update_material(item_id, name, mtype, quantity, description, shelf_id, box_id):
    f = _clean_item_fields(name, mtype, quantity, description, shelf_id, box_id)
    with db_cursor() as cur:
        _check_placement(cur, f["shelf_id"], f["box_id"])
        _lock_item(cur, item_id)
        reserved = _reserved_total(cur, item_id)
        if f["quantity"] < reserved:
            raise ValidationError(f"لا يمكن تقليل الكمية إلى أقل من المحجوز حاليًا ({reserved}).")
        cur.execute(
            "UPDATE Items SET ItemName=?, ItemType=?, Quantity=?, Description=?, ShelfID=?, BoxID=? "
            "WHERE ItemID=?",
            (f["name"], f["mtype"], f["quantity"], f["description"], f["shelf_id"], f["box_id"], item_id),
        )


@_db
def delete_material(item_id):
    """حذف ناعم: تبقى المادة في سجل العمليات لكنها تختفي من المخزن."""
    with db_cursor() as cur:
        _lock_item(cur, item_id)
        if _reserved_total(cur, item_id) > 0:
            raise ValidationError("لا يمكن حذف مادة عليها حجوزات قائمة. ألغِ الحجوزات أولًا.")
        cur.execute("UPDATE Items SET IsActive = 0 WHERE ItemID = ?", (item_id,))


@_db
def get_materials_status(search=None):
    sql = """
        SELECT I.ItemID, I.ItemName, I.ItemType, I.Quantity, I.Description,
               ISNULL(C.CabinetName, N'غير محدد'), ISNULL(S.ShelfName, N'غير محدد'), B.BoxName,
               I.ShelfID, I.BoxID, ISNULL(A.Reserved, 0), ISNULL(A.Available, I.Quantity)
        FROM Items I
        LEFT JOIN Shelves  S ON I.ShelfID = S.ShelfID
        LEFT JOIN Cabinets C ON S.CabinetID = C.CabinetID
        LEFT JOIN Boxes    B ON I.BoxID = B.BoxID
        LEFT JOIN vw_ItemAvailability A ON A.ItemID = I.ItemID
        WHERE I.IsActive = 1
    """
    params = []
    if search and search.strip():
        sql += " AND (I.ItemName LIKE ? OR I.ItemType LIKE ? OR I.Description LIKE ?)"
        params = [f"%{search.strip()}%"] * 3
    sql += " ORDER BY I.ItemName"
    with db_cursor() as cur:
        rows = cur.execute(sql, params).fetchall()
    return [
        {"id": r[0], "name": r[1], "type": r[2], "quantity": r[3], "desc": r[4] or "",
         "cab": r[5], "shelf": r[6], "box": r[7] or "N/A",
         "shelf_id": r[8], "box_id": r[9], "reserved": r[10], "available": r[11]}
        for r in rows
    ]


# ---------------------------------------------------------------- العمليات (حجز / سحب / إرجاع)
def _lock_item(cursor, item_id):
    """يقفل صف المادة حتى نهاية المعاملة؛ كل عملية تبدأ به فتتسلسل العمليات المتزامنة."""
    row = cursor.execute(
        "SELECT Quantity, IsActive FROM Items WITH (UPDLOCK, HOLDLOCK) WHERE ItemID = ?", (item_id,)
    ).fetchone()
    if row is None or not row[1]:
        raise ValidationError("المادة غير موجودة.")
    return row[0]


def _ensure_trainer(cursor, trainer_id):
    row = cursor.execute("SELECT IsActive FROM Trainers WHERE TrainerID = ?", (trainer_id,)).fetchone()
    if row is None or not row[0]:
        raise ValidationError("المدرب غير موجود.")


def _reserved_total(cursor, item_id):
    return cursor.execute(
        "SELECT ISNULL(SUM(Reserved), 0) FROM vw_Reservations WHERE ItemID = ?", (item_id,)
    ).fetchone()[0]


def _reserved_by(cursor, item_id, trainer_id):
    return cursor.execute(
        "SELECT ISNULL(SUM(Reserved), 0) FROM vw_Reservations WHERE ItemID = ? AND TrainerID = ?",
        (item_id, trainer_id),
    ).fetchone()[0]


def _outstanding(cursor, item_id, trainer_id):
    """ما سحبه المدرب ولم يُرجعه بعد."""
    return cursor.execute(
        "SELECT ISNULL(SUM(CASE ActionType WHEN 'Withdraw' THEN Quantity WHEN 'Return' THEN -Quantity ELSE 0 END), 0) "
        "FROM Transactions WHERE ItemID = ? AND TrainerID = ?",
        (item_id, trainer_id),
    ).fetchone()[0]


def _log_transaction(cursor, item_id, trainer_id, action, quantity):
    cursor.execute(
        "INSERT INTO Transactions (ItemID, TrainerID, ActionType, Quantity, ActionDate) VALUES (?, ?, ?, ?, ?)",
        (item_id, trainer_id, action, quantity, datetime.now()),
    )


@_db
def reserve_material(item_id, trainer_id, quantity):
    qty = parse_int(quantity, "الكمية", minimum=1)
    with db_cursor() as cur:
        stock = _lock_item(cur, item_id)
        _ensure_trainer(cur, trainer_id)
        available = stock - _reserved_total(cur, item_id)
        if qty > available:
            raise InsufficientStock(f"الكمية المتاحة للحجز {available} فقط.")
        _log_transaction(cur, item_id, trainer_id, "Reserve", qty)
    return True


@_db
def cancel_reservation(item_id, trainer_id, quantity):
    qty = parse_int(quantity, "الكمية", minimum=1)
    with db_cursor() as cur:
        _lock_item(cur, item_id)
        _ensure_trainer(cur, trainer_id)
        mine = _reserved_by(cur, item_id, trainer_id)
        if qty > mine:
            raise ValidationError(f"المدرب لديه {mine} محجوزة فقط من هذه المادة.")
        _log_transaction(cur, item_id, trainer_id, "CancelReserve", qty)
    return True


@_db
def withdraw_material(item_id, trainer_id, quantity):
    """السحب يستهلك أولًا حجز المدرب نفسه ثم المتاح العام."""
    qty = parse_int(quantity, "الكمية", minimum=1)
    with db_cursor() as cur:
        stock = _lock_item(cur, item_id)
        _ensure_trainer(cur, trainer_id)
        mine = _reserved_by(cur, item_id, trainer_id)
        allowed = stock - _reserved_total(cur, item_id) + mine
        if qty > allowed:
            raise InsufficientStock(f"الكمية المتاحة للسحب {allowed} فقط.")
        cur.execute("UPDATE Items SET Quantity = Quantity - ? WHERE ItemID = ?", (qty, item_id))
        _log_transaction(cur, item_id, trainer_id, "Withdraw", qty)
        consumed = min(mine, qty)
        if consumed > 0:
            _log_transaction(cur, item_id, trainer_id, "CancelReserve", consumed)
    return True


@_db
def return_material(item_id, trainer_id, quantity):
    qty = parse_int(quantity, "الكمية", minimum=1)
    with db_cursor() as cur:
        _lock_item(cur, item_id)
        _ensure_trainer(cur, trainer_id)
        held = _outstanding(cur, item_id, trainer_id)
        if qty > held:
            raise ValidationError(f"المدرب لم يسحب سوى {held} غير مُرجعة من هذه المادة.")
        cur.execute("UPDATE Items SET Quantity = Quantity + ? WHERE ItemID = ?", (qty, item_id))
        _log_transaction(cur, item_id, trainer_id, "Return", qty)
    return True


@_db
def get_available(item_id):
    with db_cursor() as cur:
        row = cur.execute("SELECT Available FROM vw_ItemAvailability WHERE ItemID = ?", (item_id,)).fetchone()
    return row[0] if row else 0


# ---------------------------------------------------------------- المدربون
@_db
def add_trainer(name):
    name = require_text(name, "اسم المدرب")
    with db_cursor() as cur:
        cur.execute("INSERT INTO Trainers (TrainerName) OUTPUT INSERTED.TrainerID VALUES (?)", (name,))
        return cur.fetchone()[0]


@_db
def rename_trainer(trainer_id, name):
    name = require_text(name, "اسم المدرب")
    with db_cursor() as cur:
        cur.execute("UPDATE Trainers SET TrainerName = ? WHERE TrainerID = ?", (name, trainer_id))


@_db
def delete_trainer(trainer_id):
    """حذف ناعم؛ يُمنع إذا كان لدى المدرب حجوزات أو عهدة غير مُرجعة."""
    with db_cursor() as cur:
        reserved = cur.execute(
            "SELECT ISNULL(SUM(Reserved), 0) FROM vw_Reservations WHERE TrainerID = ?", (trainer_id,)
        ).fetchone()[0]
        held = cur.execute(
            "SELECT ISNULL(SUM(CASE ActionType WHEN 'Withdraw' THEN Quantity WHEN 'Return' THEN -Quantity ELSE 0 END), 0) "
            "FROM Transactions WHERE TrainerID = ?", (trainer_id,)
        ).fetchone()[0]
        if reserved > 0 or held > 0:
            raise ValidationError("لا يمكن حذف مدرب لديه حجوزات قائمة أو مواد لم يُرجعها.")
        cur.execute("UPDATE Trainers SET IsActive = 0 WHERE TrainerID = ?", (trainer_id,))


# ---------------------------------------------------------------- الخزائن والرفوف والصناديق
@_db
def get_cabinets():
    with db_cursor() as cur:
        return [tuple(r) for r in cur.execute("SELECT CabinetID, CabinetName FROM Cabinets ORDER BY CabinetName")]


@_db
def get_shelves(cabinet_id=None):
    sql, params = "SELECT ShelfID, ShelfName, CabinetID FROM Shelves", []
    if cabinet_id is not None:
        sql, params = sql + " WHERE CabinetID = ?", [cabinet_id]
    with db_cursor() as cur:
        return [tuple(r) for r in cur.execute(sql + " ORDER BY ShelfName", params)]


@_db
def get_boxes(shelf_id=None):
    sql, params = "SELECT BoxID, BoxName, ShelfID FROM Boxes", []
    if shelf_id is not None:
        sql, params = sql + " WHERE ShelfID = ?", [shelf_id]
    with db_cursor() as cur:
        return [tuple(r) for r in cur.execute(sql + " ORDER BY BoxName", params)]


@_db
def add_cabinet(name):
    with db_cursor() as cur:
        cur.execute("INSERT INTO Cabinets (CabinetName) VALUES (?)", (require_text(name, "اسم الخزانة"),))


@_db
def add_shelf(name, cabinet_id):
    name = require_text(name, "اسم الرف")
    with db_cursor() as cur:
        if cur.execute("SELECT 1 FROM Cabinets WHERE CabinetID = ?", (cabinet_id,)).fetchone() is None:
            raise ValidationError("الخزانة المحددة غير موجودة.")
        cur.execute("INSERT INTO Shelves (ShelfName, CabinetID) VALUES (?, ?)", (name, cabinet_id))


@_db
def add_box(name, shelf_id):
    name = require_text(name, "اسم الصندوق")
    with db_cursor() as cur:
        if cur.execute("SELECT 1 FROM Shelves WHERE ShelfID = ?", (shelf_id,)).fetchone() is None:
            raise ValidationError("الرف المحدد غير موجود.")
        cur.execute("INSERT INTO Boxes (BoxName, ShelfID) VALUES (?, ?)", (name, shelf_id))


@_db
def rename_location(kind, loc_id, name):
    table, id_col, name_col = _LOCATION_TABLES[kind]
    name = require_text(name, "الاسم")
    with db_cursor() as cur:
        cur.execute(f"UPDATE {table} SET {name_col} = ? WHERE {id_col} = ?", (name, loc_id))


@_db
def delete_location(kind, loc_id):
    """يحذف خزانة/رف/صندوق فقط إذا كان فارغًا (بدون رفوف/صناديق/مواد داخله)."""
    table, id_col, _ = _LOCATION_TABLES[kind]
    child_checks = {
        "cabinet": ("SELECT COUNT(*) FROM Shelves WHERE CabinetID = ?", "رفوف"),
        "shelf": ("SELECT (SELECT COUNT(*) FROM Boxes WHERE ShelfID = ?) + "
                  "(SELECT COUNT(*) FROM Items WHERE ShelfID = ?)", "صناديق أو مواد"),
        "box": ("SELECT COUNT(*) FROM Items WHERE BoxID = ?", "مواد"),
    }
    sql, what = child_checks[kind]
    with db_cursor() as cur:
        params = (loc_id, loc_id) if kind == "shelf" else (loc_id,)
        if cur.execute(sql, params).fetchone()[0] > 0:
            raise ValidationError(f"لا يمكن الحذف: يحتوي على {what}.")
        cur.execute(f"DELETE FROM {table} WHERE {id_col} = ?", (loc_id,))


_LOCATION_TABLES = {
    "cabinet": ("Cabinets", "CabinetID", "CabinetName"),
    "shelf": ("Shelves", "ShelfID", "ShelfName"),
    "box": ("Boxes", "BoxID", "BoxName"),
}


# ---------------------------------------------------------------- التقارير
@_db
def get_filtered_history(item_id=None, trainer_id=None):
    sql = """
        SELECT T.TransactionID, I.ItemName, TR.TrainerName, T.ActionType, T.Quantity, T.ActionDate
        FROM Transactions T
        JOIN Items I ON T.ItemID = I.ItemID
        JOIN Trainers TR ON T.TrainerID = TR.TrainerID
        WHERE 1=1
    """
    params = []
    if item_id:
        sql += " AND T.ItemID = ?"
        params.append(item_id)
    if trainer_id:
        sql += " AND T.TrainerID = ?"
        params.append(trainer_id)
    sql += " ORDER BY T.ActionDate DESC, T.TransactionID DESC"
    with db_cursor() as cur:
        rows = cur.execute(sql, params).fetchall()
    return [
        {"id": r[0], "item": r[1], "trainer": r[2], "action": r[3],
         "action_label": ACTION_LABELS.get(r[3], r[3]), "qty": r[4],
         "date": r[5].strftime("%Y-%m-%d %H:%M")}
        for r in rows
    ]


def get_transaction_history():
    return get_filtered_history()


# ---------------------------------------------------------------- التصدير
def export_to_txt(file_path, data):
    """تصدير نصي بفواصل Tab: يفتح بسلاسة في Excel ولا تتأثر أعمدته بالنص العربي."""
    try:
        with open(file_path, "w", encoding="utf-8-sig") as f:
            f.write("\t".join(["التاريخ", "المدرب", "العملية", "الكمية", "المادة"]) + "\n")
            for h in data:
                f.write("\t".join([h["date"], h["trainer"], h["action_label"], str(h["qty"]), h["item"]]) + "\n")
    except OSError as e:
        raise WarehouseError(f"تعذر حفظ الملف: {e.strerror or e}") from e
    return True


_FONT_CANDIDATES = [
    r"C:\Windows\Fonts\arial.ttf",
    r"C:\Windows\Fonts\tahoma.ttf",
    r"C:\Windows\Fonts\segoeui.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]


def _find_font():
    custom = os.environ.get("WAREHOUSE_PDF_FONT")
    for path in ([custom] if custom else []) + _FONT_CANDIDATES:
        if path and os.path.exists(path):
            return path
    return None


def _shape(text):
    """تشكيل الحروف العربية واتجاه RTL للعرض الصحيح في PDF."""
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
        return get_display(arabic_reshaper.reshape(str(text)))
    except ImportError:
        return str(text)


def export_to_pdf(file_path, data):
    try:
        from fpdf import FPDF
    except ImportError:
        raise WarehouseError("مكتبة fpdf2 غير مثبتة. ثبّتها عبر: pip install fpdf2") from None

    font_path = _find_font()
    pdf = FPDF()
    pdf.add_page()
    if font_path:
        pdf.add_font("Report", "", font_path)
        font, title = "Report", _shape("تقرير حركة المستودع")
        headers = [("التاريخ", 40), ("المدرب", 38), ("العملية", 25), ("الكمية", 15), ("المادة", 72)]
        cell = lambda h: [h["date"], h["trainer"], h["action_label"], h["qty"], h["item"]]
    else:  # بدون خط يدعم العربية نستخدم الإنكليزية حتى لا يفشل التصدير
        font, title = "Helvetica", "Warehouse Transactions Report"
        headers = [("Date", 40), ("Trainer", 38), ("Action", 25), ("Qty", 15), ("Item", 72)]
        cell = lambda h: [h["date"], h["trainer"], h["action"], h["qty"], h["item"]]

    def txt(value):
        text = _shape(value) if font_path else str(value).encode("latin-1", "replace").decode("latin-1")
        return text

    pdf.set_font(font, size=14)
    pdf.cell(0, 10, title, align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    pdf.set_font(font, size=10)
    for name, width in headers:
        pdf.cell(width, 9, txt(name) if font_path else name, border=1, align="C")
    pdf.ln()
    pdf.set_font(font, size=9)
    for h in data:
        for (_, width), value in zip(headers, cell(h)):
            pdf.cell(width, 9, txt(value), border=1, align="C")
        pdf.ln()
    try:
        pdf.output(file_path)
    except OSError as e:
        raise WarehouseError(f"تعذر حفظ الملف: {e.strerror or e}") from e
    return True
