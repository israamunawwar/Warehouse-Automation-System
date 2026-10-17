import configparser
import os
from contextlib import contextmanager

import pyodbc

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.ini")

# يمكن تجاوز أي قيمة بمتغير بيئة: WAREHOUSE_DB_SERVER, WAREHOUSE_DB_NAME, ...
_DEFAULTS = {
    "driver": "ODBC Driver 17 for SQL Server",
    "server": "localhost",
    "database": "WarehouseDB",
    "trusted_connection": "yes",
    "user": "",
    "password": "",
}
_ENV_KEYS = {
    "driver": "WAREHOUSE_DB_DRIVER",
    "server": "WAREHOUSE_DB_SERVER",
    "database": "WAREHOUSE_DB_NAME",
    "trusted_connection": "WAREHOUSE_DB_TRUSTED",
    "user": "WAREHOUSE_DB_USER",
    "password": "WAREHOUSE_DB_PASSWORD",
}


def load_settings():
    settings = dict(_DEFAULTS)
    parser = configparser.ConfigParser()
    if parser.read(CONFIG_PATH, encoding="utf-8") and parser.has_section("database"):
        settings.update({k: v for k, v in parser["database"].items() if k in settings})
    for key, env in _ENV_KEYS.items():
        if os.environ.get(env):
            settings[key] = os.environ[env]
    return settings


def build_connection_string(settings=None):
    s = settings or load_settings()
    parts = [
        f"DRIVER={{{s['driver']}}}",
        f"SERVER={s['server']}",
        f"DATABASE={s['database']}",
    ]
    if s["user"]:
        parts += [f"UID={s['user']}", f"PWD={s['password']}"]
    elif s["trusted_connection"].lower() in ("yes", "true", "1"):
        parts.append("Trusted_Connection=yes")
    parts.append("TrustServerCertificate=yes")
    return ";".join(parts) + ";"


def get_connection():
    return pyodbc.connect(build_connection_string())


@contextmanager
def db_cursor():
    """مؤشر ضمن معاملة واحدة: commit عند النجاح، rollback عند أي خطأ، وإغلاق الاتصال دائمًا."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        yield cursor
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
