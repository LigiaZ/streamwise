"""Database access: Turso (libSQL over HTTP) in production, plain SQLite locally and in tests.

Both speak the same SQLite dialect, so the rest of the app just calls ``db().execute(sql, args)``
and gets back a list of dict rows. Turso is reached with its HTTP "pipeline" API using only
the standard library — no driver needed.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import urllib.request
from pathlib import Path
from typing import Optional

SCHEMA = [
    """CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        email TEXT NOT NULL UNIQUE,
        name TEXT NOT NULL,
        password_hash TEXT NOT NULL,
        is_owner INTEGER NOT NULL DEFAULT 0,
        email_alerts INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS invites (
        token TEXT PRIMARY KEY,
        created_by TEXT NOT NULL,
        created_at TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        used_by TEXT,
        used_at TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS user_data (
        user_id TEXT PRIMARY KEY,
        data TEXT NOT NULL,
        version INTEGER NOT NULL,
        updated_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS login_attempts (
        key TEXT PRIMARY KEY,
        failures INTEGER NOT NULL,
        window_start TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS notifications (
        user_id TEXT NOT NULL,
        key TEXT NOT NULL,
        sent_at TEXT NOT NULL,
        PRIMARY KEY (user_id, key)
    )""",
]


class NotConfigured(Exception):
    """Raised when sync is requested but no database is available."""


class SQLite:
    def __init__(self, path: str):
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.lock = threading.Lock()

    def execute(self, sql: str, args: tuple = ()) -> list:
        with self.lock:
            cur = self.conn.execute(sql, args)
            rows = [dict(r) for r in cur.fetchall()]
            self.conn.commit()
            return rows


class Turso:
    def __init__(self, url: str, token: str):
        self.endpoint = url.replace("libsql://", "https://").rstrip("/") + "/v2/pipeline"
        self.token = token

    @staticmethod
    def _arg(value):
        if value is None:
            return {"type": "null"}
        if isinstance(value, bool):
            return {"type": "integer", "value": str(int(value))}
        if isinstance(value, int):
            return {"type": "integer", "value": str(value)}
        if isinstance(value, float):
            return {"type": "float", "value": value}
        return {"type": "text", "value": str(value)}

    def execute(self, sql: str, args: tuple = ()) -> list:
        body = json.dumps({"requests": [
            {"type": "execute", "stmt": {"sql": sql, "args": [self._arg(a) for a in args]}},
            {"type": "close"},
        ]}).encode()
        req = urllib.request.Request(self.endpoint, data=body, method="POST", headers={
            "Authorization": f"Bearer {self.token}", "Content-Type": "application/json",
        })
        with urllib.request.urlopen(req, timeout=10) as resp:
            out = json.load(resp)
        first = out["results"][0]
        if first.get("type") == "error":
            raise RuntimeError(first["error"].get("message", "database error"))
        result = first["response"]["result"]
        cols = [c["name"] for c in result["cols"]]
        rows = []
        for row in result["rows"]:
            values = []
            for cell in row:
                v = cell.get("value")
                if cell.get("type") == "integer" and v is not None:
                    v = int(v)
                values.append(v)
            rows.append(dict(zip(cols, values)))
        return rows


_db = None
_lock = threading.Lock()


def db():
    """The configured database, created (and schema-migrated) on first use."""
    global _db
    with _lock:
        if _db is None:
            _db = _connect()
            for stmt in SCHEMA:
                _db.execute(stmt)
        return _db


def _connect():
    url, token = os.environ.get("TURSO_DATABASE_URL"), os.environ.get("TURSO_AUTH_TOKEN")
    if url and token:
        return Turso(url, token)
    if os.environ.get("VERCEL"):
        # Vercel's filesystem is ephemeral: never silently fall back to a local file there.
        raise NotConfigured("TURSO_DATABASE_URL / TURSO_AUTH_TOKEN are not set")
    return SQLite(os.environ.get("STREAMWISE_SQLITE", str(Path(__file__).parent.parent / ".data" / "dev.db")))


def use(database: Optional[object]) -> None:
    """Swap the database (tests use an in-memory SQLite)."""
    global _db
    with _lock:
        _db = database
        if database is not None:
            for stmt in SCHEMA:
                database.execute(stmt)
