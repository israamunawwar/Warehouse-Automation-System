import functools
import logging
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox, simpledialog, ttk

import auth
import functions as fn
from functions import WarehouseError

log = logging.getLogger("warehouse")

FONT = "Segoe UI"
DARK, GREEN, YELLOW, RED, BLUE, ORANGE, GRAY = (
    "#2c3e50", "#27ae60", "#f39c12", "#e74c3c", "#3498db", "#e67e22", "#95a5a6")


def show_error(message, parent=None):
    messagebox.showerror("خطأ", message, parent=parent)


def guarded(method):
    """يمنع انهيار الحدث: أخطاء النظام تُعرض للمستخدم، وغيرها تُسجَّل برسالة عامة."""
    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        try:
            return method(self, *args, **kwargs)
        except WarehouseError as e:
            show_error(str(e), getattr(self, "root", None))
        except Exception:
            log.exception("Unexpected error in %s", method.__name__)
            show_error("حدث خطأ غير متوقع. راجع ملف app.log للتفاصيل.")
    return wrapper


class IdCombo(ttk.Combobox):
    """Combobox يربط النص المعروض بمعرّف حقيقي بدل تحليل النص."""

    def __init__(self, master, **kw):
        kw.setdefault("state", "readonly")
        super().__init__(master, **kw)
        self._ids = []

    def set_items(self, items, none_label=None):
        keep = self.selected_id()
        self._ids = ([None] if none_label else []) + [i for i, _ in items]
        self["values"] = ([none_label] if none_label else []) + [label for _, label in items]
        if keep in self._ids:
            self.select_id(keep)
        elif none_label:
            self.current(0)
        else:
            self.set("")

    def selected_id(self):
        idx = self.current()
        return self._ids[idx] if 0 <= idx < len(self._ids) else None

    def has_selection(self):
        return self.current() >= 0

    def select_id(self, item_id):
        if item_id in self._ids:
            self.current(self._ids.index(item_id))
        else:
            self.set("")


def labeled(parent, text, row, widget, col_label=1, col_widget=0, pady=8):
    tk.Label(parent, text=text, bg="white", font=(FONT, 10), anchor="e").grid(
        row=row, column=col_label, pady=pady, sticky="e", padx=(10, 0))
    widget.grid(row=row, column=col_widget, padx=10, pady=pady, sticky="w")
    return widget


def make_tree(parent, columns, widths=None, **kw):
    frame = tk.Frame(parent, bg="white")
    tree = ttk.Treeview(frame, columns=columns, show="headings", **kw)
    sb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=sb.set)
    for col in columns:
        tree.heading(col, text=col)
        tree.column(col, anchor="center", width=(widths or {}).get(col, 100))
    tree.pack(side="left", fill="both", expand=True)
    sb.pack(side="right", fill="y")
    return frame, tree


def button(parent, text, command, color, **kw):
    return tk.Button(parent, text=text, command=command, bg=color, fg="white", relief="flat",
                     font=(FONT, 10, "bold"), padx=kw.pop("padx", 14), pady=kw.pop("pady", 4),
                     activebackground=color, cursor="hand2", **kw)


class WarehouseApp:
    def __init__(self, root, role="admin", user_id=None, setup_mode=False):
        self.root = root
        self.role = role
        self.user_id = user_id
        self.setup_mode = setup_mode
        self.is_admin = role == "admin"
        self.history = []
        self._search_job = None

        root.title("نظام إدارة المستودع الذكي - معهد دمشق المتوسط")
        root.geometry("1200x800")
        root.minsize(900, 600)
        root.configure(bg="#f8f9fa")
        root.report_callback_exception = self._on_tk_exception

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Treeview", rowheight=32, font=(FONT, 10))
        style.configure("Treeview.Heading", font=(FONT, 11, "bold"), background=DARK, foreground="white")
        style.map("Treeview.Heading", background=[("active", "#34495e")], foreground=[("active", "white")])

        self.setup_ui()
        self.refresh_all()

    def _on_tk_exception(self, exc_type, exc, tb):
        if issubclass(exc_type, WarehouseError):
            show_error(str(exc))
        else:
            log.error("Unhandled Tk exception", exc_info=(exc_type, exc, tb))
            show_error("حدث خطأ غير متوقع. راجع ملف app.log للتفاصيل.")

    # ------------------------------------------------------------ بناء الواجهة
    def setup_ui(self):
        header = tk.Frame(self.root, bg=DARK, height=60)
        header.pack(fill="x")
        tk.Label(header, text="📦 لوحة إدارة المستودع الاحترافية", font=(FONT, 18, "bold"),
                 fg="white", bg=DARK).pack(pady=10)
        if self.user_id is not None:
            tk.Label(header, text=f"الدور: {'مدير' if self.is_admin else 'مشاهد'}", fg="#bdc3c7",
                     bg=DARK, font=(FONT, 9)).place(relx=0.01, rely=0.35)

        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=20, pady=20)

        def tab(title):
            frame = tk.Frame(self.notebook, bg="white")
            self.notebook.add(frame, text=f"  {title}  ")
            return frame

        self.tab_inv = tab("المخزن الحالي")
        self.create_inventory_ui()
        if self.is_admin:
            self.tab_ops = tab("سحب وحجز وإرجاع")
            self.create_operations_ui()
        self.tab_rep = tab("التقارير والسجلات")
        self.create_reports_ui()
        if self.is_admin:
            self.tab_trainers = tab("المدربون")
            self.create_trainers_ui()
            self.tab_loc = tab("الخزائن والرفوف")
            self.create_locations_ui()
            self.tab_users = tab("المستخدمون")
            self.create_users_ui()

    # -- المخزن
    def create_inventory_ui(self):
        toolbar = tk.Frame(self.tab_inv, bg="white")
        toolbar.pack(fill="x", padx=10, pady=12)
        if self.is_admin:
            button(toolbar, "🗑️ حذف المادة", self.handle_delete, RED).pack(side="right", padx=5)
            button(toolbar, "📝 تعديل البيانات", self.show_edit_win, YELLOW).pack(side="right", padx=5)
            button(toolbar, "+ إضافة مادة جديدة", self.show_add_win, GREEN).pack(side="right", padx=5)
        tk.Label(toolbar, text="🔍 بحث:", bg="white", font=(FONT, 10)).pack(side="left", padx=(0, 5))
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", self._on_search_changed)
        tk.Entry(toolbar, textvariable=self.search_var, width=30, font=(FONT, 10)).pack(side="left")

        cols = ("ID", "الاسم", "النوع", "الكمية", "المحجوز", "المتاح", "الخزانة", "الرف", "الصندوق")
        frame, self.tree = make_tree(self.tab_inv, cols, {"ID": 50, "الاسم": 180})
        frame.pack(fill="both", expand=True, padx=10, pady=10)
        self.tree.tag_configure("out", foreground=RED)

    def _on_search_changed(self, *_):
        if self._search_job:
            self.root.after_cancel(self._search_job)
        self._search_job = self.root.after(300, self._run_search)

    @guarded
    def _run_search(self):
        self._search_job = None
        self.refresh_inventory()

    # -- العمليات
    def create_operations_ui(self):
        frame = tk.LabelFrame(self.tab_ops, text=" إجراء عملية ", bg="white", font=(FONT, 12, "bold"),
                              padx=30, pady=30)
        frame.place(relx=0.5, rely=0.4, anchor="center")

        self.cb_items = labeled(frame, "اختر المادة:", 0, IdCombo(frame, width=38))
        self.cb_items.bind("<<ComboboxSelected>>", lambda e: self._show_availability())
        self.cb_trainers = labeled(frame, "اختر المدرب:", 1, IdCombo(frame, width=38))
        self.ent_qty = labeled(frame, "الكمية المطلوبة:", 2, tk.Entry(frame, width=40))
        self.lbl_avail = tk.Label(frame, text="", bg="white", fg="#7f8c8d", font=(FONT, 9))
        self.lbl_avail.grid(row=3, column=0, columnspan=2)

        btns = tk.Frame(frame, bg="white")
        btns.grid(row=4, column=0, columnspan=2, pady=15)
        for text, op, color in (("إرجاع", "return", GREEN), ("سحب (خصم من المخزن)", "withdraw", ORANGE),
                                ("إلغاء حجز", "cancel", GRAY), ("حجز (يقلل المتاح)", "reserve", BLUE)):
            button(btns, text, lambda o=op: self.process_op(o), color, width=18).pack(side="right", padx=4)

    @guarded
    def _show_availability(self):
        item_id = self.cb_items.selected_id()
        if item_id is None:
            self.lbl_avail.config(text="")
            return
        info = next((m for m in self.materials if m["id"] == item_id), None)
        if info:
            self.lbl_avail.config(
                text=f"الكمية: {info['quantity']}   |   المحجوز: {info['reserved']}   |   المتاح: {info['available']}")

    # -- التقارير
    def create_reports_ui(self):
        ff = tk.LabelFrame(self.tab_rep, text=" أدوات البحث والفلترة ", bg="white", font=(FONT, 11, "bold"),
                           padx=15, pady=15)
        ff.pack(fill="x", padx=20, pady=10)
        tk.Label(ff, text="فلترة مادة:", bg="white").grid(row=0, column=0, padx=5)
        self.cb_filter_item = IdCombo(ff, width=22)
        self.cb_filter_item.grid(row=0, column=1, padx=5)
        tk.Label(ff, text="فلترة مدرب:", bg="white").grid(row=0, column=2, padx=5)
        self.cb_filter_trainer = IdCombo(ff, width=22)
        self.cb_filter_trainer.grid(row=0, column=3, padx=5)
        button(ff, "🔍 عرض التقرير", self.apply_filter, "#34495e").grid(row=0, column=4, padx=8)
        button(ff, "🔄 الكل", self.reset_filter, GRAY).grid(row=0, column=5, padx=4)
        button(ff, "💾 حفظ TXT", lambda: self.save_report_to_disk("txt"), GREEN).grid(row=0, column=6, padx=4)
        button(ff, "📄 حفظ PDF", lambda: self.save_report_to_disk("pdf"), "#c0392b").grid(row=0, column=7, padx=4)

        cols = ("ID", "التاريخ", "المدرب", "نوع العملية", "الكمية", "المادة")
        frame, self.report_tree = make_tree(self.tab_rep, cols, {"ID": 60, "التاريخ": 150})
        frame.pack(fill="both", expand=True, padx=20, pady=10)

    # -- المدربون
    def create_trainers_ui(self):
        bar = tk.Frame(self.tab_trainers, bg="white")
        bar.pack(fill="x", padx=10, pady=12)
        button(bar, "🗑️ حذف", self.delete_trainer, RED).pack(side="right", padx=5)
        button(bar, "📝 تعديل الاسم", self.rename_trainer, YELLOW).pack(side="right", padx=5)
        button(bar, "+ إضافة مدرب", self.add_trainer, GREEN).pack(side="right", padx=5)
        frame, self.trainers_tree = make_tree(self.tab_trainers, ("ID", "اسم المدرب"), {"ID": 60})
        frame.pack(fill="both", expand=True, padx=10, pady=10)

    @guarded
    def add_trainer(self):
        name = simpledialog.askstring("مدرب جديد", "اسم المدرب:", parent=self.root)
        if name is not None:
            fn.add_trainer(name)
            self.refresh_all()

    @guarded
    def rename_trainer(self):
        tid = self._selected_id(self.trainers_tree, "اختر مدربًا")
        if tid is None:
            return
        old = self.trainers_tree.item(str(tid))["values"][1]
        name = simpledialog.askstring("تعديل الاسم", "الاسم الجديد:", initialvalue=old, parent=self.root)
        if name is not None:
            fn.rename_trainer(tid, name)
            self.refresh_all()

    @guarded
    def delete_trainer(self):
        tid = self._selected_id(self.trainers_tree, "اختر مدربًا")
        if tid is not None and messagebox.askyesno("تأكيد", "حذف المدرب؟", parent=self.root):
            fn.delete_trainer(tid)
            self.refresh_all()

    # -- الخزائن والرفوف والصناديق
    def create_locations_ui(self):
        bar = tk.Frame(self.tab_loc, bg="white")
        bar.pack(fill="x", padx=10, pady=12)
        button(bar, "🗑️ حذف", self.delete_location, RED).pack(side="right", padx=5)
        button(bar, "📝 تعديل الاسم", self.rename_location, YELLOW).pack(side="right", padx=5)
        button(bar, "+ صندوق", lambda: self.add_location("box"), BLUE).pack(side="right", padx=5)
        button(bar, "+ رف", lambda: self.add_location("shelf"), BLUE).pack(side="right", padx=5)
        button(bar, "+ خزانة", lambda: self.add_location("cabinet"), GREEN).pack(side="right", padx=5)
        frame = tk.Frame(self.tab_loc, bg="white")
        frame.pack(fill="both", expand=True, padx=10, pady=10)
        self.loc_tree = ttk.Treeview(frame, show="tree")
        self.loc_tree.pack(fill="both", expand=True)

    def _selected_location(self):
        sel = self.loc_tree.selection()
        if not sel:
            return None, None
        kind, _, raw = sel[0].partition(":")
        return kind, int(raw)

    @guarded
    def add_location(self, kind):
        sel_kind, sel_id = self._selected_location()
        titles = {"cabinet": "اسم الخزانة:", "shelf": "اسم الرف:", "box": "اسم الصندوق:"}
        if kind == "shelf":
            if sel_kind == "shelf":
                sel_kind, sel_id = "cabinet", next(s[2] for s in fn.get_shelves() if s[0] == sel_id)
            if sel_kind != "cabinet":
                return messagebox.showwarning("تنبيه", "اختر الخزانة التي سيضاف إليها الرف.", parent=self.root)
        elif kind == "box" and sel_kind != "shelf":
            return messagebox.showwarning("تنبيه", "اختر الرف الذي سيضاف إليه الصندوق.", parent=self.root)
        name = simpledialog.askstring("إضافة", titles[kind], parent=self.root)
        if name is None:
            return
        {"cabinet": lambda: fn.add_cabinet(name), "shelf": lambda: fn.add_shelf(name, sel_id),
         "box": lambda: fn.add_box(name, sel_id)}[kind]()
        self.refresh_locations()

    @guarded
    def rename_location(self):
        kind, loc_id = self._selected_location()
        if kind is None:
            return messagebox.showwarning("تنبيه", "اختر عنصرًا أولًا.", parent=self.root)
        old = self.loc_tree.item(f"{kind}:{loc_id}")["text"].strip()
        name = simpledialog.askstring("تعديل الاسم", "الاسم الجديد:", initialvalue=old, parent=self.root)
        if name is not None:
            fn.rename_location(kind, loc_id, name)
            self.refresh_all()

    @guarded
    def delete_location(self):
        kind, loc_id = self._selected_location()
        if kind is None:
            return messagebox.showwarning("تنبيه", "اختر عنصرًا أولًا.", parent=self.root)
        if messagebox.askyesno("تأكيد", "حذف العنصر المحدد؟", parent=self.root):
            fn.delete_location(kind, loc_id)
            self.refresh_all()

    # -- المستخدمون
    def create_users_ui(self):
        if self.setup_mode:
            tk.Label(self.tab_users, bg="#fff3cd", fg="#856404", font=(FONT, 10), pady=6,
                     text="لا يوجد مستخدمون بعد: التطبيق يعمل بدون تسجيل دخول. "
                          "أنشئ حساب مدير ليُفعَّل تسجيل الدخول في المرة القادمة.").pack(fill="x")
        bar = tk.Frame(self.tab_users, bg="white")
        bar.pack(fill="x", padx=10, pady=12)
        button(bar, "🗑️ حذف", self.delete_user, RED).pack(side="right", padx=5)
        button(bar, "+ مستخدم جديد", self.add_user, GREEN).pack(side="right", padx=5)
        frame, self.users_tree = make_tree(self.tab_users, ("ID", "اسم المستخدم", "الدور"), {"ID": 60})
        frame.pack(fill="both", expand=True, padx=10, pady=10)

    @guarded
    def add_user(self):
        win = tk.Toplevel(self.root)
        win.title("مستخدم جديد")
        win.transient(self.root)
        win.grab_set()
        body = tk.Frame(win, bg="white", padx=20, pady=15)
        body.pack(fill="both", expand=True)
        user = labeled(body, "اسم المستخدم:", 0, tk.Entry(body, width=28))
        pw = labeled(body, "كلمة السر:", 1, tk.Entry(body, width=28, show="•"))
        role = labeled(body, "الدور:", 2, ttk.Combobox(body, width=26, state="readonly",
                                                        values=["admin", "viewer"]))
        role.current(0 if self.setup_mode else 1)

        def save():
            try:
                auth.create_user(user.get(), pw.get(), role.get())
            except WarehouseError as e:
                return show_error(str(e), win)
            win.destroy()
            self.refresh_users()
        button(body, "حفظ", save, DARK, width=18).grid(row=3, column=0, columnspan=2, pady=12)

    @guarded
    def delete_user(self):
        uid = self._selected_id(self.users_tree, "اختر مستخدمًا")
        if uid is not None and messagebox.askyesno("تأكيد", "حذف المستخدم؟", parent=self.root):
            auth.delete_user(uid, self.user_id)
            self.refresh_users()

    # ------------------------------------------------------------ تحديث البيانات
    def _selected_id(self, tree, warning):
        sel = tree.selection()
        if not sel:
            messagebox.showwarning("تنبيه", warning, parent=self.root)
            return None
        return int(sel[0])

    @guarded
    def refresh_all(self):
        self.refresh_inventory()
        self.refresh_lookups()
        self.apply_filter()
        if self.is_admin:
            self.refresh_trainers()
            self.refresh_locations()
            self.refresh_users()

    def refresh_inventory(self):
        self.materials = fn.get_materials_status(self.search_var.get())
        self.tree.delete(*self.tree.get_children())
        for m in self.materials:
            self.tree.insert("", "end", iid=str(m["id"]), tags=("out",) if m["available"] <= 0 else (),
                             values=(m["id"], m["name"], m["type"], m["quantity"], m["reserved"],
                                     m["available"], m["cab"], m["shelf"], m["box"]))

    def refresh_lookups(self):
        items = [(i, f"{name} (#{i})") for i, name in fn.get_all_items_list()]
        trainers = [(t, f"{name} (#{t})") for t, name in fn.get_all_trainers()]
        if self.is_admin:
            self.cb_items.set_items(items)
            self.cb_trainers.set_items(trainers)
            self._show_availability()
        self.cb_filter_item.set_items(
            [(i, f"{name} (#{i})") for i, name in fn.get_all_items_list(include_inactive=True)], "الكل")
        self.cb_filter_trainer.set_items(
            [(t, f"{name} (#{t})") for t, name in fn.get_all_trainers(include_inactive=True)], "الكل")

    def refresh_trainers(self):
        self.trainers_tree.delete(*self.trainers_tree.get_children())
        for tid, name in fn.get_all_trainers():
            self.trainers_tree.insert("", "end", iid=str(tid), values=(tid, name))

    def refresh_locations(self):
        self.loc_tree.delete(*self.loc_tree.get_children())
        shelves, boxes = fn.get_shelves(), fn.get_boxes()
        for cid, cname in fn.get_cabinets():
            self.loc_tree.insert("", "end", iid=f"cabinet:{cid}", text=f"🗄️ {cname}", open=True)
        for sid, sname, cid in shelves:
            self.loc_tree.insert(f"cabinet:{cid}", "end", iid=f"shelf:{sid}", text=f"📚 {sname}", open=True)
        for bid, bname, sid in boxes:
            self.loc_tree.insert(f"shelf:{sid}", "end", iid=f"box:{bid}", text=f"📦 {bname}")

    def refresh_users(self):
        self.users_tree.delete(*self.users_tree.get_children())
        for uid, name, role in auth.list_users():
            self.users_tree.insert("", "end", iid=str(uid), values=(uid, name, role))

    # ------------------------------------------------------------ التقارير
    @guarded
    def apply_filter(self):
        self.history = fn.get_filtered_history(self.cb_filter_item.selected_id(),
                                               self.cb_filter_trainer.selected_id())
        self.report_tree.delete(*self.report_tree.get_children())
        for h in self.history:
            self.report_tree.insert("", "end", values=(h["id"], h["date"], h["trainer"],
                                                       h["action_label"], h["qty"], h["item"]))

    @guarded
    def reset_filter(self):
        self.cb_filter_item.current(0)
        self.cb_filter_trainer.current(0)
        self.apply_filter()

    @guarded
    def save_report_to_disk(self, file_type):
        if not self.history:
            return messagebox.showwarning("تنبيه", "لا توجد بيانات في الجدول لتصديرها!", parent=self.root)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = filedialog.asksaveasfilename(
            defaultextension=f".{file_type}", initialfile=f"تقرير_العمليات_{stamp}",
            filetypes=[("Text files", "*.txt")] if file_type == "txt" else [("PDF files", "*.pdf")])
        if not path:
            return
        (fn.export_to_txt if file_type == "txt" else fn.export_to_pdf)(path, self.history)
        messagebox.showinfo("نجاح", "تم حفظ التقرير بنجاح", parent=self.root)

    # ------------------------------------------------------------ العمليات
    @guarded
    def process_op(self, op):
        item_id, trainer_id = self.cb_items.selected_id(), self.cb_trainers.selected_id()
        if item_id is None or trainer_id is None:
            return show_error("يجب اختيار المادة والمدرب", self.root)
        actions = {
            "reserve": (fn.reserve_material, "تم تسجيل الحجز"),
            "cancel": (fn.cancel_reservation, "تم إلغاء الحجز"),
            "withdraw": (fn.withdraw_material, "تم السحب"),
            "return": (fn.return_material, "تم الإرجاع"),
        }
        func, done = actions[op]
        func(item_id, trainer_id, self.ent_qty.get())
        messagebox.showinfo("تم", done, parent=self.root)
        self.ent_qty.delete(0, "end")
        self.refresh_all()

    # ------------------------------------------------------------ إدارة المواد
    @guarded
    def handle_delete(self):
        item_id = self._selected_id(self.tree, "اختر مادة")
        if item_id is None:
            return
        name = self.tree.item(str(item_id))["values"][1]
        if messagebox.askyesno("تأكيد", f"حذف المادة «{name}»؟\nسيبقى سجل عملياتها محفوظًا.", parent=self.root):
            fn.delete_material(item_id)
            self.refresh_all()

    def show_add_win(self):
        self.show_editor("add")

    def show_edit_win(self):
        item_id = self._selected_id(self.tree, "اختر مادة")
        if item_id is not None:
            self.show_editor("edit", next(m for m in self.materials if m["id"] == item_id))

    def show_editor(self, mode, item=None):
        win = tk.Toplevel(self.root)
        win.title("إضافة مادة" if mode == "add" else "تعديل مادة")
        win.transient(self.root)
        win.grab_set()
        win.resizable(False, False)
        body = tk.Frame(win, bg="white", padx=25, pady=20)
        body.pack(fill="both", expand=True)

        name = labeled(body, "اسم المادة:", 0, tk.Entry(body, width=34))
        mtype = labeled(body, "النوع:", 1, tk.Entry(body, width=34))
        qty = labeled(body, "الكمية:", 2, tk.Entry(body, width=34))
        desc = labeled(body, "وصف المادة:", 3, tk.Entry(body, width=34))
        cab = labeled(body, "الخزانة:", 4, IdCombo(body, width=32))
        shelf = labeled(body, "الرف:", 5, IdCombo(body, width=32))
        box = labeled(body, "الصندوق:", 6, IdCombo(body, width=32))

        all_shelves = fn.get_shelves()
        cab.set_items(fn.get_cabinets())
        box.set_items([], "بدون صندوق")

        def on_cabinet(_=None):
            shelf.set("")
            shelf.set_items([(s[0], s[1]) for s in all_shelves if s[2] == cab.selected_id()])
            box.set_items([], "بدون صندوق")

        def on_shelf(_=None):
            box.set_items([(b[0], b[1]) for b in fn.get_boxes(shelf.selected_id())], "بدون صندوق")

        cab.bind("<<ComboboxSelected>>", on_cabinet)
        shelf.bind("<<ComboboxSelected>>", on_shelf)

        if mode == "edit":
            name.insert(0, item["name"])
            mtype.insert(0, item["type"])
            qty.insert(0, item["quantity"])
            desc.insert(0, item["desc"])
            cab_id = next((s[2] for s in all_shelves if s[0] == item["shelf_id"]), None)
            cab.select_id(cab_id)
            on_cabinet()
            shelf.select_id(item["shelf_id"])
            on_shelf()
            box.select_id(item["box_id"])
        else:
            qty.insert(0, "0")

        def save():
            args = (name.get(), mtype.get(), qty.get(), desc.get(), shelf.selected_id(), box.selected_id())
            try:
                if mode == "add":
                    fn.add_material(*args)
                else:
                    fn.update_material(item["id"], *args)
            except WarehouseError as e:
                return show_error(str(e), win)  # النافذة تبقى مفتوحة ليصحح المستخدم المدخلات
            win.destroy()
            self.refresh_all()

        button(body, "حفظ", save, DARK, width=20).grid(row=7, column=0, columnspan=2, pady=15)


def setup_logging():
    logging.basicConfig(filename="app.log", level=logging.INFO, encoding="utf-8",
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def ask_login(root):
    result = {}
    win = tk.Toplevel(root)
    win.title("تسجيل الدخول")
    win.resizable(False, False)
    body = tk.Frame(win, padx=25, pady=20)
    body.pack()
    tk.Label(body, text="🔐 تسجيل الدخول", font=(FONT, 14, "bold")).grid(row=0, column=0, columnspan=2, pady=(0, 10))
    user = tk.Entry(body, width=28)
    pw = tk.Entry(body, width=28, show="•")
    for r, (text, w) in enumerate((("اسم المستخدم:", user), ("كلمة السر:", pw)), start=1):
        tk.Label(body, text=text).grid(row=r, column=1, sticky="e", pady=6)
        w.grid(row=r, column=0, padx=8)

    def submit(_=None):
        try:
            found = auth.authenticate(user.get(), pw.get())
        except WarehouseError as e:
            return show_error(str(e), win)
        if found is None:
            return show_error("اسم المستخدم أو كلمة السر غير صحيحة.", win)
        result["user"] = found
        win.destroy()

    tk.Button(body, text="دخول", command=submit, bg=DARK, fg="white", width=18).grid(
        row=3, column=0, columnspan=2, pady=12)
    win.bind("<Return>", submit)
    win.protocol("WM_DELETE_WINDOW", win.destroy)
    win.grab_set()
    user.focus_set()
    root.wait_window(win)
    return result.get("user")


def main():
    setup_logging()
    root = tk.Tk()
    root.withdraw()
    try:
        users_exist = auth.has_users()
    except WarehouseError as e:
        show_error(f"{e}\nتأكد من تنفيذ DB.sql أو migration_01.sql على قاعدة البيانات.")
        return
    user_id, role = None, "admin"
    if users_exist:
        found = ask_login(root)
        if found is None:
            return
        user_id, role = found
    root.deiconify()
    WarehouseApp(root, role, user_id, setup_mode=not users_exist)
    root.mainloop()


if __name__ == "__main__":
    main()
