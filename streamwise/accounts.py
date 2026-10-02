"""Accounts, sessions and per-user data for the signed-in version of StreamWise.

Security choices, in short:
  * passwords: PBKDF2-HMAC-SHA256, 600k iterations, random salt (OWASP 2023 guidance);
  * sessions: HMAC-signed, httpOnly + Secure + SameSite=Lax cookie, 30-day expiry;
  * sign-up: the first account needs SETUP_SECRET; everyone after needs a one-time invite;
  * brute force: 5 failed logins per email (and 20 per IP) per 15 minutes, then a lockout.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

from .db import db

PBKDF2_ITERATIONS = 600_000
SESSION_DAYS = 30
INVITE_DAYS = 7
MAX_FAILURES_EMAIL = 5
MAX_FAILURES_IP = 20
LOCKOUT_MINUTES = 15
MAX_DATA_BYTES = 400_000
EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,255}\.[^@\s]{2,}$")


class AuthError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


def now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


# ---------------------------------------------------------------- passwords

def hash_password(password: str, iterations: Optional[int] = None) -> str:
    iterations = iterations or PBKDF2_ITERATIONS
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    return f"pbkdf2_sha256${iterations}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iterations, salt, digest = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        check = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(iterations))
        return hmac.compare_digest(check.hex(), digest)
    except (ValueError, TypeError):
        return False


# A real hash to compare against when the email doesn't exist, so a wrong email and a
# wrong password take the same time (no account enumeration by timing).
_DUMMY_HASH = None


def _dummy_hash() -> str:
    global _DUMMY_HASH
    if _DUMMY_HASH is None:
        _DUMMY_HASH = hash_password(secrets.token_hex(8))
    return _DUMMY_HASH


# ---------------------------------------------------------------- sessions

def _secret() -> bytes:
    secret = os.environ.get("SESSION_SECRET", "")
    if not secret:
        if os.environ.get("VERCEL"):
            raise AuthError(503, "Sign-in isn’t set up on this server yet.")
        secret = "dev-only-session-secret"
    return secret.encode()


def sign_session(user_id: str, issued: Optional[int] = None) -> str:
    payload = f"{user_id}.{issued or int(time.time())}"
    sig = hmac.new(_secret(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{sig}"


def verify_session(token: Optional[str]) -> Optional[str]:
    if not token or token.count(".") != 2:
        return None
    user_id, issued, sig = token.split(".")
    expected = hmac.new(_secret(), f"{user_id}.{issued}".encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        return None
    if not issued.isdigit() or time.time() - int(issued) > SESSION_DAYS * 86400:
        return None
    return user_id


def session_cookie(token: str, secure: bool) -> str:
    return (f"sw_session={token}; Path=/; HttpOnly; SameSite=Lax; Max-Age={SESSION_DAYS * 86400}"
            + ("; Secure" if secure else ""))


def clear_cookie(secure: bool) -> str:
    return "sw_session=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0" + ("; Secure" if secure else "")


# ---------------------------------------------------------------- users

def public_user(row: dict) -> dict:
    return {"id": row["id"], "email": row["email"], "name": row["name"],
            "is_owner": bool(row["is_owner"]), "email_alerts": bool(row["email_alerts"])}


def get_user(user_id: str) -> Optional[dict]:
    rows = db().execute("SELECT * FROM users WHERE id = ?", (user_id,))
    return rows[0] if rows else None


def _validate(email: str, password: str, name: str) -> tuple:
    email = (email or "").strip().lower()
    name = (name or "").strip()[:60]
    if not EMAIL_RE.match(email):
        raise AuthError(400, "That email address doesn’t look right.")
    if len(password or "") < 10:
        raise AuthError(400, "Use a password of at least 10 characters.")
    if len(password) > 200:
        raise AuthError(400, "That password is too long.")
    return email, name or email.split("@")[0]


def register(email: str, password: str, name: str, invite: Optional[str], setup_secret: Optional[str]) -> dict:
    email, name = _validate(email, password, name)
    has_users = bool(db().execute("SELECT 1 AS x FROM users LIMIT 1"))
    is_owner = 0
    invite_row = None

    if not has_users:
        expected = os.environ.get("SETUP_SECRET", "")
        if os.environ.get("VERCEL") and not expected:
            raise AuthError(503, "Set SETUP_SECRET on the server to create the first account.")
        if expected and not hmac.compare_digest(setup_secret or "", expected):
            raise AuthError(403, "The setup code is wrong.")
        is_owner = 1
    else:
        if not invite:
            raise AuthError(403, "Sign-up is by invitation only.")
        rows = db().execute("SELECT * FROM invites WHERE token = ?", (invite,))
        invite_row = rows[0] if rows else None
        if not invite_row or invite_row["used_at"] or _parse(invite_row["expires_at"]) < now():
            raise AuthError(403, "This invite link is invalid, used or expired.")

    if db().execute("SELECT 1 AS x FROM users WHERE email = ?", (email,)):
        raise AuthError(409, "There’s already an account with that email. Sign in instead.")

    user_id = secrets.token_hex(12)
    db().execute(
        "INSERT INTO users (id, email, name, password_hash, is_owner, email_alerts, created_at) VALUES (?, ?, ?, ?, ?, 1, ?)",
        (user_id, email, name, hash_password(password), is_owner, _iso(now())),
    )
    if invite_row:
        db().execute("UPDATE invites SET used_by = ?, used_at = ? WHERE token = ? AND used_at IS NULL",
                     (user_id, _iso(now()), invite))
    return get_user(user_id)


def _throttle_check(key: str, limit: int) -> None:
    rows = db().execute("SELECT failures, window_start FROM login_attempts WHERE key = ?", (key,))
    if rows and rows[0]["failures"] >= limit:
        if _parse(rows[0]["window_start"]) + timedelta(minutes=LOCKOUT_MINUTES) > now():
            raise AuthError(429, f"Too many attempts. Try again in {LOCKOUT_MINUTES} minutes.")


def _throttle_fail(key: str) -> None:
    rows = db().execute("SELECT failures, window_start FROM login_attempts WHERE key = ?", (key,))
    if rows and _parse(rows[0]["window_start"]) + timedelta(minutes=LOCKOUT_MINUTES) > now():
        db().execute("UPDATE login_attempts SET failures = failures + 1 WHERE key = ?", (key,))
    else:
        db().execute("INSERT OR REPLACE INTO login_attempts (key, failures, window_start) VALUES (?, 1, ?)",
                     (key, _iso(now())))


def login(email: str, password: str, ip: str) -> dict:
    email = (email or "").strip().lower()
    keys = [(f"email:{email}", MAX_FAILURES_EMAIL), (f"ip:{ip}", MAX_FAILURES_IP)]
    for key, limit in keys:
        _throttle_check(key, limit)
    rows = db().execute("SELECT * FROM users WHERE email = ?", (email,))
    user = rows[0] if rows else None
    ok = verify_password(password or "", user["password_hash"] if user else _dummy_hash())
    if not (user and ok):
        for key, _ in keys:
            _throttle_fail(key)
        raise AuthError(401, "Wrong email or password.")
    db().execute("DELETE FROM login_attempts WHERE key = ?", (f"email:{email}",))
    return user


def create_invite(user: dict) -> str:
    if not user["is_owner"]:
        raise AuthError(403, "Only the owner can invite people.")
    token = secrets.token_urlsafe(18)
    db().execute("INSERT INTO invites (token, created_by, created_at, expires_at) VALUES (?, ?, ?, ?)",
                 (token, user["id"], _iso(now()), _iso(now() + timedelta(days=INVITE_DAYS))))
    return token


def set_alerts(user: dict, enabled: bool) -> dict:
    db().execute("UPDATE users SET email_alerts = ? WHERE id = ?", (1 if enabled else 0, user["id"]))
    return get_user(user["id"])


# ---------------------------------------------------------------- data sync

def load_data(user_id: str) -> dict:
    rows = db().execute("SELECT data, version, updated_at FROM user_data WHERE user_id = ?", (user_id,))
    if not rows:
        return {"data": None, "version": 0, "updated_at": None}
    return {"data": json.loads(rows[0]["data"]), "version": rows[0]["version"], "updated_at": rows[0]["updated_at"]}


def save_data(user_id: str, data: dict, base_version: int) -> dict:
    """Optimistic concurrency: the write only lands if nobody saved since ``base_version``."""
    if not isinstance(data, dict) or not isinstance(data.get("log"), list) or not isinstance(data.get("services"), dict):
        raise AuthError(400, "Expected {services: {...}, log: [...]}.")
    clean = {"country": str(data.get("country") or "NL")[:2], "services": data["services"], "log": data["log"],
             "follows": data.get("follows") if isinstance(data.get("follows"), list) else []}
    blob = json.dumps(clean, separators=(",", ":"))
    if len(blob) > MAX_DATA_BYTES:
        raise AuthError(413, "That’s more data than StreamWise can store for one person.")
    current = load_data(user_id)["version"]
    if base_version != current:
        raise AuthError(409, "Your data changed on another device. Reloading the latest version.")
    stamp = _iso(now())
    if current == 0:
        db().execute("INSERT INTO user_data (user_id, data, version, updated_at) VALUES (?, ?, 1, ?)", (user_id, blob, stamp))
    else:
        db().execute("UPDATE user_data SET data = ?, version = version + 1, updated_at = ? WHERE user_id = ? AND version = ?",
                     (blob, stamp, user_id, current))
    saved = load_data(user_id)
    if saved["version"] != current + 1:
        raise AuthError(409, "Your data changed on another device. Reloading the latest version.")
    return {"version": saved["version"], "updated_at": saved["updated_at"]}
