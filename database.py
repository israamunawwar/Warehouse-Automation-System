import pyodbc

def get_connection():
    conn = pyodbc.connect(
        "DRIVER={ODBC Driver 17 for SQL Server};"
        "SERVER=DESKTOP-Q8EHCGQ;"
        "DATABASE=WarehouseDB;"
        "Trusted_Connection=yes;"
        "TrustServerCertificate=yes;"
    )
    return conn
