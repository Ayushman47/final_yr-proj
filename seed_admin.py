"""
seed_admin.py — Promote an existing user to admin.

Usage:
    python seed_admin.py <username>

Example:
    python seed_admin.py ayush

The user must already exist in the database (i.e. they must have signed up first).
Run this once from the project root directory.
"""

import sys
import sqlite3

DB_NAME = "medications.db"


def seed_admin(username: str) -> None:
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT id, is_admin FROM users WHERE username = ?", (username,))
        row = cursor.fetchone()

        if not row:
            print(f"[ERROR] User '{username}' does not exist. Sign up first.")
            sys.exit(1)

        if row["is_admin"]:
            print(f"[INFO] User '{username}' is already an admin. Nothing to do.")
            return

        cursor.execute(
            "UPDATE users SET is_admin = 1 WHERE username = ?",
            (username,)
        )
        conn.commit()
        print(f"[OK] User '{username}' has been promoted to admin.")

    finally:
        conn.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python seed_admin.py <username>")
        sys.exit(1)

    seed_admin(sys.argv[1])
