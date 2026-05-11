import sqlite3
from contextlib import contextmanager

import os
import sys

# Ensure DB is in a writable location
if hasattr(sys, '_MEIPASS'):
    # Running as bundled EXE
    app_data_dir = os.path.join(os.environ.get('APPDATA', os.path.expanduser('~')), "HealthAssist")
    os.makedirs(app_data_dir, exist_ok=True)
    DB_PATH = os.path.join(app_data_dir, "medications.db")
else:
    # Running as normal script
    DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "medications.db")

DB_NAME = DB_PATH


def get_connection():
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def managed_connection():
    """Context manager that guarantees the connection is closed even if an
    exception is raised mid-route. Use this for new code; the bare
    get_connection() is kept for backward compatibility with existing routes
    that already manage their own close() calls."""
    conn = get_connection()
    try:
        yield conn
    finally:
        conn.close()


def get_db():
    """FastAPI dependency that provides a database connection."""
    conn = get_connection()
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    # =========================
    # USERS TABLE
    # =========================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            is_admin BOOLEAN DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Migrate existing databases
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN is_admin BOOLEAN DEFAULT 0")
    except Exception:
        pass
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN created_at TEXT")
        cursor.execute("UPDATE users SET created_at = CURRENT_TIMESTAMP WHERE created_at IS NULL")
    except Exception:
        pass

    # =========================
    # MEDICATIONS TABLE
    # =========================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS medications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            dosage TEXT,
            frequency TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
        )
    """)

    # =========================
    # CONVERSATIONS TABLE
    # =========================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT DEFAULT '',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
        )
    """)

    # =========================
    # MESSAGES TABLE
    # =========================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER NOT NULL,
            sender TEXT NOT NULL,
            content TEXT NOT NULL,
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (conversation_id) REFERENCES conversations (id) ON DELETE CASCADE
        )
    """)

    # =========================
    # HEALTH PROFILE TABLE
    # =========================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS health_profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE NOT NULL,
            allergies TEXT,
            conditions TEXT,
            age INTEGER,
            FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
        )
    """)

    # =========================
    # DOCUMENTS (PDF) TABLE
    # =========================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            uploaded_by INTEGER NOT NULL,
            chunk_count INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (uploaded_by) REFERENCES users (id)
        )
    """)

    conn.commit()
    conn.close()


if __name__ == "__main__":
    init_db()
