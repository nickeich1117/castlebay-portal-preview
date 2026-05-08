"""Tiny SQLite layer — users + sessions only. Independent from prod portal."""
import os
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.config import DB_PATH, SESSION_TTL_HOURS

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  email TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  display_name TEXT,
  role TEXT NOT NULL DEFAULT 'cb_internal',
  active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sessions (
  token TEXT PRIMARY KEY,
  user_id INTEGER NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  expires_at TEXT NOT NULL,
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
"""


def _conn() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(os.path.abspath(DB_PATH)), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def cursor():
    c = _conn()
    try:
        yield c
        c.commit()
    finally:
        c.close()


def init_db() -> None:
    with cursor() as c:
        c.executescript(SCHEMA)


def create_user(
    email: str,
    password_hash: str,
    display_name: str = "",
    role: str = "cb_internal",
) -> dict:
    with cursor() as c:
        cur = c.execute(
            "INSERT INTO users (email, password_hash, display_name, role) VALUES (?, ?, ?, ?)",
            (email.lower().strip(), password_hash, display_name, role),
        )
        uid = cur.lastrowid
        return get_user_by_id(uid)


def get_user_by_email(email: str) -> Optional[dict]:
    with cursor() as c:
        row = c.execute(
            "SELECT * FROM users WHERE email = ?", (email.lower().strip(),)
        ).fetchone()
        return dict(row) if row else None


def get_user_by_id(user_id: int) -> Optional[dict]:
    with cursor() as c:
        row = c.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return dict(row) if row else None


def list_users() -> list[dict]:
    with cursor() as c:
        rows = c.execute("SELECT * FROM users ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]


def create_session(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(hours=SESSION_TTL_HOURS)
    with cursor() as c:
        c.execute(
            "INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)",
            (token, user_id, expires.isoformat()),
        )
    return token


def validate_session(token: str) -> Optional[dict]:
    with cursor() as c:
        row = c.execute(
            """
            SELECT u.*, s.expires_at AS session_expires_at
            FROM sessions s JOIN users u ON s.user_id = u.id
            WHERE s.token = ?
            """,
            (token,),
        ).fetchone()
        if not row:
            return None
        d = dict(row)
        # Manual expiry check
        try:
            exp = datetime.fromisoformat(d["session_expires_at"])
            if exp < datetime.now(timezone.utc):
                return None
        except Exception:
            return None
        if not d.get("active"):
            return None
        return d


def delete_session(token: str) -> None:
    with cursor() as c:
        c.execute("DELETE FROM sessions WHERE token = ?", (token,))
