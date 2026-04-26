from datetime import datetime
from database import get_connection

# جلب البيانات للقوائم المنسدلة
def get_all_trainers():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT TrainerID, TrainerName FROM Trainers")
    rows = cursor.fetchall()
    conn.close()
    return rows

def get_all_items_list():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT ItemID, ItemName FROM Items")
    rows = cursor.fetchall()
    conn.close()
    return rows

# إدارة المواد (إضافة، حذف، تعديل)
def add_material(name, mtype, quantity, description, shelf_id, box_id):
    conn = get_connection()
    cursor = conn.cursor()
    b_id = int(box_id) if box_id and str(box_id).isdigit() else None
    cursor.execute("""
        INSERT INTO Items (ItemName, ItemType, Quantity, Description, ShelfID, BoxID)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (name, mtype, int(quantity), description, int(shelf_id), b_id))
    conn.commit()
    conn.close()

def delete_material(item_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM Items WHERE ItemID = ?", (item_id,))
    conn.commit()
    conn.close()

def update_material(item_id, name, mtype, quantity, description, shelf_id, box_id):
    conn = get_connection()
    cursor = conn.cursor()
    b_id = int(box_id) if box_id and str(box_id).isdigit() else None
    cursor.execute("""
        UPDATE Items 
        SET ItemName=?, ItemType=?, Quantity=?, Description=?, ShelfID=?, BoxID=?
        WHERE ItemID=?
    """, (name, mtype, int(quantity), description, int(shelf_id), b_id, item_id))
    conn.commit()
    conn.close()

# العمليات (سحب وحجز)
def reserve_material(item_id, trainer_id, quantity):
    conn = get_connection()
    cursor = conn.cursor()
    # الحجز يسجل في السجل فقط ولا يغير كمية المخزن
    cursor.execute("""
        INSERT INTO Transactions (ItemID, TrainerID, ActionType, Quantity, ActionDate)
        VALUES (?, ?, 'reserve', ?, ?)
    """, (item_id, trainer_id, int(quantity), datetime.now()))
    conn.commit()
    conn.close()
    return True

def withdraw_material(item_id, trainer_id, quantity):
    conn = get_connection()
    cursor = conn.cursor()
    # التحقق من الكمية قبل السحب
    cursor.execute("SELECT Quantity FROM Items WHERE ItemID = ?", (item_id,))
    res = cursor.fetchone()
    
    if res and res[0] >= int(quantity):
        cursor.execute("""
            INSERT INTO Transactions (ItemID, TrainerID, ActionType, Quantity, ActionDate)
            VALUES (?, ?, 'withdraw', ?, ?)
        """, (item_id, trainer_id, int(quantity), datetime.now()))
        cursor.execute("UPDATE Items SET Quantity = Quantity - ? WHERE ItemID = ?", (int(quantity), item_id))
        conn.commit()
        conn.close()
        return True
    conn.close()
    return False

# عرض البيانات والتقارير
def get_materials_status():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT I.ItemID, I.ItemName, I.ItemType, I.Quantity, I.Description, C.CabinetName, S.ShelfName, B.BoxName
        FROM Items I
        JOIN Shelves S ON I.ShelfID = S.ShelfID
        JOIN Cabinets C ON S.CabinetID = C.CabinetID
        LEFT JOIN Boxes B ON I.BoxID = B.BoxID
    """)
    rows = cursor.fetchall()
    conn.close()
    return [{"id":r[0],"name":r[1],"type":r[2],"quantity":r[3],"desc":r[4],"cab":r[5],"shelf":r[6],"box":r[7] or "N/A"} for r in rows]

def get_transaction_history():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT T.TransactionID, I.ItemName, TR.TrainerName, T.ActionType, T.Quantity, T.ActionDate
        FROM Transactions T
        JOIN Items I ON T.ItemID = I.ItemID
        JOIN Trainers TR ON T.TrainerID = TR.TrainerID
        ORDER BY T.ActionDate DESC
    """)
    rows = cursor.fetchall()
    conn.close()
    return [{"id":r[0],"item":r[1],"trainer":r[2],"action":r[3],"qty":r[4],"date":r[5].strftime("%Y-%m-%d %H:%M")} for r in rows]

def export_report_to_file(file_path, history_data):
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(f"{'التاريخ':<20} | {'المدرب':<15} | {'العملية':<10} | {'الكمية':<5} | {'المادة'}\n")
            f.write("-" * 80 + "\n")
            for h in history_data:
                line = f"{h['date']:<20} | {h['trainer']:<15} | {h['action']:<10} | {h['qty']:<5} | {h['item']}\n"
                f.write(line)
        return True
    except:
        return False
def get_filtered_history(item_id=None, trainer_id=None):
    conn = get_connection()
    cursor = conn.cursor()
    
    query = """
    SELECT T.TransactionID, I.ItemName, TR.TrainerName, T.ActionType, T.Quantity, T.ActionDate
    FROM Transactions T
    JOIN Items I ON T.ItemID = I.ItemID
    JOIN Trainers TR ON T.TrainerID = TR.TrainerID
    WHERE 1=1
    """
    params = []
    if item_id:
        query += " AND T.ItemID = ?"
        params.append(item_id)
    if trainer_id:
        query += " AND T.TrainerID = ?"
        params.append(trainer_id)
        
    query += " ORDER BY T.ActionDate DESC"
    
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return [{"id":r[0],"item":r[1],"trainer":r[2],"action":r[3],"qty":r[4],"date":r[5].strftime("%Y-%m-%d %H:%M")} for r in rows]

from fpdf import FPDF

# دالة تصدير ملف نصي
def export_to_txt(file_path, data):
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(f"{'التاريخ':<20} | {'المدرب':<15} | {'العملية':<10} | {'الكمية':<5} | {'المادة'}\n")
            f.write("-" * 85 + "\n")
            for h in data:
                line = f"{h['date']:<20} | {h['trainer']:<15} | {h['action']:<10} | {h['qty']:<5} | {h['item']}\n"
                f.write(line)
        return True
    except:
        return False

# دالة تصدير PDF (بسيطة)
def export_to_pdf(file_path, data):
    try:
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", size=12)
        
        pdf.cell(200, 10, txt="Warehouse Transaction Report", ln=True, align='C')
        pdf.ln(10)
        
        # العناوين
        pdf.set_font("Arial", 'B', 10)
        pdf.cell(40, 10, "Date", 1)
        pdf.cell(40, 10, "Trainer", 1)
        pdf.cell(30, 10, "Action", 1)
        pdf.cell(20, 10, "Qty", 1)
        pdf.cell(60, 10, "Item", 1)
        pdf.ln()
        
        # البيانات
        pdf.set_font("Arial", size=9)
        for h in data:
            pdf.cell(40, 10, str(h['date']), 1)
            pdf.cell(40, 10, str(h['trainer']), 1)
            pdf.cell(30, 10, str(h['action']), 1)
            pdf.cell(20, 10, str(h['qty']), 1)
            pdf.cell(60, 10, str(h['item']), 1)
            pdf.ln()
            
        pdf.output(file_path)
        return True
    except Exception as e:
        print(e)
        return False