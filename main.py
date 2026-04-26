import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from functions import *
# حاول استيراد مكتبة fpdf في البداية
try:
    from fpdf import FPDF
except ImportError:
    pass

class WarehouseApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("نظام إدارة المستودع الذكي - معهد دمشق المتوسط")
        self.root.geometry("1200x800")
        self.root.configure(bg="#f8f9fa")
        
        # تنسيق الجداول والواجهة
        self.style = ttk.Style()
        self.style.theme_use('clam')
        self.style.configure("Treeview", rowheight=35, font=('Segoe UI', 10))
        self.style.configure("Treeview.Heading", font=('Segoe UI', 11, 'bold'), background="#2c3e50", foreground="white")
        
        self.setup_ui()
        self.load_materials()

    def setup_ui(self):
        # العنوان العلوي
        header = tk.Frame(self.root, bg="#2c3e50", height=60)
        header.pack(fill='x')
        tk.Label(header, text="📦 لوحة إدارة المستودع الاحترافية", font=('Segoe UI', 18, 'bold'), fg="white", bg="#2c3e50").pack(pady=10)

        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill='both', expand=True, padx=20, pady=20)
        
        self.tab_inv = tk.Frame(self.notebook, bg="white")
        self.tab_ops = tk.Frame(self.notebook, bg="white")
        self.tab_rep = tk.Frame(self.notebook, bg="white")

        self.notebook.add(self.tab_inv, text='  المخزن الحالي  ')
        self.notebook.add(self.tab_ops, text='  سحب وحجز مادة  ')
        self.notebook.add(self.tab_rep, text='  التقارير والسجلات  ')
        
        self.create_inventory_ui()
        self.create_operations_ui()
        self.create_reports_ui()

    def create_inventory_ui(self):
        toolbar = tk.Frame(self.tab_inv, bg="white")
        toolbar.pack(fill='x', padx=10, pady=15)
        
        tk.Button(toolbar, text="+ إضافة مادة جديدة", command=self.show_add_win, bg="#27ae60", fg="white", font=('Segoe UI', 10, 'bold'), padx=15).pack(side='left', padx=5)
        tk.Button(toolbar, text="📝 تعديل البيانات", command=self.show_edit_win, bg="#f1c40f", fg="white", font=('Segoe UI', 10, 'bold'), padx=15).pack(side='left', padx=5)
        tk.Button(toolbar, text="🗑️ حذف المادة", command=self.handle_delete, bg="#e74c3c", fg="white", font=('Segoe UI', 10, 'bold'), padx=15).pack(side='left', padx=5)

        cols = ('ID', 'الاسم', 'النوع', 'الكمية', 'الخزانة', 'الرف', 'الصندوق')
        self.tree = ttk.Treeview(self.tab_inv, columns=cols, show='headings')
        for col in cols: 
            self.tree.heading(col, text=col)
            self.tree.column(col, anchor='center')
        self.tree.pack(fill='both', expand=True, padx=10, pady=10)

    def create_operations_ui(self):
        frame = tk.LabelFrame(self.tab_ops, text=" إجراء عملية (سحب / حجز) ", bg="white", font=('Segoe UI', 12, 'bold'), padx=30, pady=30)
        frame.place(relx=0.5, rely=0.4, anchor='center')

        tk.Label(frame, text="اختر المادة:", bg="white", font=('Segoe UI', 10)).grid(row=0, column=1, pady=10, sticky='e')
        self.cb_items = ttk.Combobox(frame, width=35, state="readonly")
        self.cb_items.grid(row=0, column=0, padx=10)

        tk.Label(frame, text="اختر المدرب:", bg="white", font=('Segoe UI', 10)).grid(row=1, column=1, pady=10, sticky='e')
        self.cb_trainers = ttk.Combobox(frame, width=35, state="readonly")
        self.cb_trainers.grid(row=1, column=0, padx=10)

        tk.Label(frame, text="الكمية المطلوبة:", bg="white", font=('Segoe UI', 10)).grid(row=2, column=1, pady=10, sticky='e')
        self.ent_qty = tk.Entry(frame, width=37)
        self.ent_qty.grid(row=2, column=0)

        btn_f = tk.Frame(frame, bg="white")
        btn_f.grid(row=3, columnspan=2, pady=20)
        tk.Button(btn_f, text="حجز (لا ينقص الكمية)", command=lambda: self.process_op('reserve'), bg="#3498db", fg="white", width=20, font=('Segoe UI', 9, 'bold')).pack(side='left', padx=5)
        tk.Button(btn_f, text="سحب (خصم من المخزن)", command=lambda: self.process_op('withdraw'), bg="#e67e22", fg="white", width=20, font=('Segoe UI', 9, 'bold')).pack(side='left', padx=5)

    def create_reports_ui(self):
        filter_frame = tk.LabelFrame(self.tab_rep, text=" أدوات البحث والفلترة ", bg="white", font=('Segoe UI', 11, 'bold'), padx=15, pady=15)
        filter_frame.pack(fill='x', padx=20, pady=10)

        tk.Label(filter_frame, text="فلترة مادة:", bg="white").grid(row=0, column=0, padx=5)
        self.cb_filter_item = ttk.Combobox(filter_frame, width=20, state="readonly")
        self.cb_filter_item.grid(row=0, column=1, padx=5)

        tk.Label(filter_frame, text="فلترة مدرب:", bg="white").grid(row=0, column=2, padx=5)
        self.cb_filter_trainer = ttk.Combobox(filter_frame, width=20, state="readonly")
        self.cb_filter_trainer.grid(row=0, column=3, padx=5)

        tk.Button(filter_frame, text="🔍 عرض التقرير", command=self.apply_filter, bg="#34495e", fg="white", padx=15).grid(row=0, column=4, padx=10)
        tk.Button(filter_frame, text="🔄 الكل", command=self.reset_filter, bg="#95a5a6", fg="white", padx=10).grid(row=0, column=5, padx=5)
        
        # أزرار التصدير (استدعاء الدوال من داخل الكلاس)
        tk.Button(filter_frame, text="💾 حفظ TXT", command=lambda: self.save_report_to_disk("txt"), 
                  bg="#27ae60", fg="white", font=('Segoe UI', 9, 'bold'), padx=10).grid(row=0, column=6, padx=5)
        
        tk.Button(filter_frame, text="📄 حفظ PDF", command=lambda: self.save_report_to_disk("pdf"), 
                  bg="#c0392b", fg="white", font=('Segoe UI', 9, 'bold'), padx=10).grid(row=0, column=7, padx=5)

        cols = ('ID', 'التاريخ', 'المدرب', 'نوع العملية', 'الكمية', 'المادة')
        self.report_tree = ttk.Treeview(self.tab_rep, columns=cols, show='headings')
        for col in cols:
            self.report_tree.heading(col, text=col)
            self.report_tree.column(col, anchor='center')
        self.report_tree.pack(fill='both', expand=True, padx=20, pady=10)

    # --- الدوال البرمجية داخل الكلاس ---

    def save_report_to_disk(self, file_type):
        try:
            rows = self.report_tree.get_children()
            if not rows:
                messagebox.showwarning("تنبيه", "لا توجد بيانات في الجدول لتصديرها!")
                return

            if file_type == "txt":
                file_path = filedialog.asksaveasfilename(defaultextension=".txt", 
                                                         filetypes=[("Text files", "*.txt")])
                if not file_path: return
                
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(f"{'التاريخ':<20} | {'المدرب':<15} | {'العملية':<12} | {'الكمية':<5} | {'المادة'}\n")
                    f.write("-" * 90 + "\n")
                    for row_id in rows:
                        v = self.report_tree.item(row_id)['values']
                        f.write(f"{str(v[1]):<20} | {str(v[2]):<15} | {str(v[3]):<12} | {str(v[4]):<5} | {str(v[5])}\n")
                messagebox.showinfo("نجاح", f"تم حفظ التقرير النصي بنجاح")

            elif file_type == "pdf":
                try:
                    from fpdf import FPDF
                except ImportError:
                    messagebox.showerror("خطأ", "مكتبة fpdf غير مثبتة! يرجى تثبيتها عبر: pip install fpdf")
                    return

                file_path = filedialog.asksaveasfilename(defaultextension=".pdf", 
                                                         filetypes=[("PDF files", "*.pdf")])
                if not file_path: return
                
                pdf = FPDF()
                pdf.add_page()
                pdf.set_font("Arial", 'B', 14)
                pdf.cell(200, 10, txt="Warehouse Transactions Report", ln=True, align='C')
                pdf.ln(10)
                
                pdf.set_font("Arial", 'B', 10)
                headers = [("Date", 45), ("Trainer", 35), ("Action", 25), ("Qty", 15), ("Item", 70)]
                for title, width in headers:
                    pdf.cell(width, 10, title, 1)
                pdf.ln()
                
                pdf.set_font("Arial", size=9)
                for row_id in rows:
                    v = self.report_tree.item(row_id)['values']
                    pdf.cell(45, 10, str(v[1]), 1)
                    pdf.cell(35, 10, str(v[2]), 1)
                    pdf.cell(25, 10, str(v[3]), 1)
                    pdf.cell(15, 10, str(v[4]), 1)
                    pdf.cell(70, 10, str(v[5]), 1)
                    pdf.ln()
                
                pdf.output(file_path)
                messagebox.showinfo("نجاح", "تم حفظ ملف PDF بنجاح")

        except Exception as e:
            messagebox.showerror("خطأ", f"حدث خطأ: {str(e)}")

    def load_materials(self):
        self.tree.delete(*self.tree.get_children())
        for m in get_materials_status():
            self.tree.insert('', 'end', values=(m['id'], m['name'], m['type'], m['quantity'], m['cab'], m['shelf'], m['box']))
        
        self.items_data = get_all_items_list()
        self.trainers_data = get_all_trainers()
        
        names_items = [f"{i[0]} - {i[1]}" for i in self.items_data]
        names_trainers = [f"{t[0]} - {t[1]}" for t in self.trainers_data]

        self.cb_items['values'] = names_items
        self.cb_trainers['values'] = names_trainers
        self.cb_filter_item['values'] = ["الكل"] + names_items
        self.cb_filter_trainer['values'] = ["الكل"] + names_trainers
        self.cb_filter_item.current(0)
        self.cb_filter_trainer.current(0)
        self.apply_filter()

    def apply_filter(self):
        item_sel = self.cb_filter_item.get()
        trainer_sel = self.cb_filter_trainer.get()
        item_id = item_sel.split(" - ")[0] if item_sel != "الكل" else None
        trainer_id = trainer_sel.split(" - ")[0] if trainer_sel != "الكل" else None
        history = get_filtered_history(item_id, trainer_id)
        self.report_tree.delete(*self.report_tree.get_children())
        for h in history:
            self.report_tree.insert('', 'end', values=(h['id'], h['date'], h['trainer'], h['action'], h['qty'], h['item']))

    def reset_filter(self):
        self.cb_filter_item.current(0)
        self.cb_filter_trainer.current(0)
        self.apply_filter()

    def process_op(self, op_type):
        try:
            item_idx = self.cb_items.current()
            trainer_idx = self.cb_trainers.current()
            qty = int(self.ent_qty.get())
            if item_idx < 0 or trainer_idx < 0: raise Exception("يجب اختيار المادة والمدرب")
            item_id = self.items_data[item_idx][0]
            trainer_id = self.trainers_data[trainer_idx][0]
            if op_type == 'reserve':
                reserve_material(item_id, trainer_id, qty)
                messagebox.showinfo("تم", "تم تسجيل الحجز")
            else:
                success = withdraw_material(item_id, trainer_id, qty)
                if success: messagebox.showinfo("تم", "تم السحب")
                else: messagebox.showerror("خطأ", "الكمية غير كافية")
            self.load_materials()
        except Exception as e:
            messagebox.showerror("خطأ", str(e))

    def handle_delete(self):
        sel = self.tree.selection()
        if not sel: return
        if messagebox.askyesno("تأكيد", "حذف المادة؟"):
            delete_material(self.tree.item(sel[0])['values'][0])
            self.load_materials()

    def show_add_win(self): self.show_editor("add")
    def show_edit_win(self):
        sel = self.tree.selection()
        if sel: self.show_editor("edit", self.tree.item(sel[0])['values'])
        else: messagebox.showwarning("تنبيه", "اختر مادة")

    def show_editor(self, mode, data=None):
        win = tk.Toplevel(self.root)
        win.title("المحرر")
        win.geometry("380x580")
        fields = ['اسم المادة', 'النوع', 'الكمية', 'وصف المادة', 'الرف', 'الصندوق']
        entries = {}
        for i, f in enumerate(fields):
            tk.Label(win, text=f).pack(pady=5)
            e = tk.Entry(win, width=35)
            if mode == "edit" and data: e.insert(0, data[i+1] if i < 3 else "")
            e.pack()
            entries[f] = e
        def save():
            vals = [entries[f].get() for f in fields]
            if mode == "add": add_material(*vals)
            else: update_material(data[0], *vals)
            win.destroy()
            self.load_materials()
        tk.Button(win, text="حفظ", command=save, bg="#2c3e50", fg="white", width=20).pack(pady=20)

if __name__ == "__main__":
    app = WarehouseApp()
    app.root.mainloop()