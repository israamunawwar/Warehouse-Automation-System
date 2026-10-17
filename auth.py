"""مستخدمو التطبيق وصلاحياتهم (admin / viewer). كلمات السر تُخزَّن مشفّرة بـ bcrypt.

إذا لم يوجد أي مستخدم في الجدول يعمل التطبيق بدون تسجيل دخول بصلاحية admin،
وينشئ المدير أول حساب من تبويب «المستخدمون».
"""
from database import db_cursor
from functions import ValidationError, WarehouseError, _db, require_text

ROLES = ("admin", "viewer")
MIN_PASSWORD_LEN = 6


def _bcrypt():
    try:
        import bcrypt
    except ImportError:
        raise WarehouseError("مكتبة bcrypt غير مثبتة. ثبّتها عبر: pip install bcrypt") from None
    return bcrypt


@_db
def has_users():
    with db_cursor() as cur:
        return cur.execute("SELECT COUNT(*) FROM Users").fetchone()[0] > 0


@_db
def list_users():
    with db_cursor() as cur:
        return [tuple(r) for r in cur.execute("SELECT UserID, Username, Role FROM Users ORDER BY Username")]


@_db
def create_user(username, password, role):
    username = require_text(username, "اسم المستخدم", 50)
    if role not in ROLES:
        raise ValidationError("الدور غير صالح.")
    if len(password or "") < MIN_PASSWORD_LEN:
        raise ValidationError(f"كلمة السر يجب ألا تقل عن {MIN_PASSWORD_LEN} أحرف.")
    bcrypt = _bcrypt()
    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("ascii")
    with db_cursor() as cur:
        if cur.execute("SELECT 1 FROM Users WHERE Username = ?", (username,)).fetchone():
            raise ValidationError("اسم المستخدم مستخدم مسبقًا.")
        cur.execute("INSERT INTO Users (Username, PasswordHash, Role) VALUES (?, ?, ?)", (username, hashed, role))


@_db
def authenticate(username, password):
    """يعيد (user_id, role) عند النجاح وإلا None."""
    with db_cursor() as cur:
        row = cur.execute(
            "SELECT UserID, PasswordHash, Role FROM Users WHERE Username = ?", ((username or "").strip(),)
        ).fetchone()
    if row is None:
        return None
    ok = _bcrypt().checkpw((password or "").encode("utf-8"), row[1].encode("ascii"))
    return (row[0], row[2]) if ok else None


@_db
def delete_user(user_id, current_user_id=None):
    if user_id == current_user_id:
        raise ValidationError("لا يمكنك حذف حسابك الحالي.")
    with db_cursor() as cur:
        row = cur.execute("SELECT Role FROM Users WHERE UserID = ?", (user_id,)).fetchone()
        if row is None:
            return
        if row[0] == "admin" and cur.execute("SELECT COUNT(*) FROM Users WHERE Role = 'admin'").fetchone()[0] <= 1:
            raise ValidationError("لا يمكن حذف آخر مدير في النظام.")
        cur.execute("DELETE FROM Users WHERE UserID = ?", (user_id,))
