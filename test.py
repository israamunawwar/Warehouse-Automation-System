from database import get_connection

try:
    conn = get_connection()
    print("✅ CONNECTED")
    conn.close()
except Exception as e:
    print("❌ ERROR:", e)
