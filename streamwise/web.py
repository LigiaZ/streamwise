"""HTTP layer shared by the Vercel functions in /api and the local dev server.

Each endpoint is a plain function: Request -> Response. Keeping HTTP details here means
the logic modules (report, tmdb, accounts) stay easy to test.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
from dataclasses import dataclass, field
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler
from typing import Optional

from . import accounts, tmdb
from .accounts import AuthError
from .catalog import COUNTRIES, catalog, currency
from .db import NotConfigured
from .report import build_report

MAX_BODY = 512 * 1024
MAX_LOG = 5000


@dataclass
class Request:
    method: str = "GET"
    params: dict = field(default_factory=dict)
    body: object = None
    cookies: dict = field(default_factory=dict)
    headers: dict = field(default_factory=dict)
    ip: str = ""
    secure: bool = False


@dataclass
class Response:
    status: int
    payload: dict
    cache: int = 0
    cookies: list = field(default_factory=list)


def _country(value: Optional[str]) -> str:
    c = (value or "NL").upper()
    return c if c in COUNTRIES else "NL"


def _error(status: int, message: str) -> Response:
    return Response(status, {"error": message})


def _tmdb_error(exc: Exception) -> Response:
    if isinstance(exc, tmdb.NotConfigured):
        return _error(503, "Title search isn’t set up yet. You can still add things manually.")
    if isinstance(exc, urllib.error.HTTPError) and exc.code == 404:
        return _error(404, "Title not found.")
    return _error(502, "Couldn’t reach the movie database. Try again in a moment.")


# ---------------------------------------------------------------- public endpoints

def catalog_endpoint(req: Request) -> Response:
    return Response(200, catalog(_country(req.params.get("country"))), 86400)


def search_endpoint(req: Request) -> Response:
    q = (req.params.get("q") or "").strip()
    if len(q) < 2 or len(q) > 100:
        return _error(400, "Search for 2 to 100 characters.")
    try:
        return Response(200, {"results": tmdb.search(q)}, 3600)
    except Exception as exc:  # noqa: BLE001 — every failure becomes a friendly message
        return _tmdb_error(exc)


def title_endpoint(req: Request) -> Response:
    kind, tmdb_id = req.params.get("kind"), req.params.get("id") or ""
    if kind not in ("movie", "tv") or not re.fullmatch(r"\d{1,9}", tmdb_id):
        return _error(400, "Expected kind=movie|tv and a numeric id.")
    try:
        return Response(200, tmdb.title(kind, int(tmdb_id), _country(req.params.get("country"))), 86400)
    except Exception as exc:  # noqa: BLE001
        return _tmdb_error(exc)


def report_endpoint(req: Request) -> Response:
    body = req.body
    if not isinstance(body, dict):
        return _error(400, "Send JSON with services and log.")
    services, log = body.get("services") or [], body.get("log") or []
    if not isinstance(services, list) or not isinstance(log, list) or len(log) > MAX_LOG:
        return _error(400, "services and log must be lists (log up to 5000 entries).")
    country = _country(body.get("country"))
    return Response(200, build_report(services, log, body.get("today"), currency(country)))


# ---------------------------------------------------------------- signed-in endpoints

def _current_user(req: Request) -> Optional[dict]:
    user_id = accounts.verify_session(req.cookies.get("sw_session"))
    return accounts.get_user(user_id) if user_id else None


def _require_user(req: Request) -> dict:
    user = _current_user(req)
    if not user:
        raise AuthError(401, "Please sign in.")
    return user


def account_endpoint(req: Request) -> Response:
    action = req.params.get("action") or ""
    body = req.body if isinstance(req.body, dict) else {}

    if action == "me":
        user = _current_user(req)
        return Response(200, {"user": accounts.public_user(user) if user else None})

    if req.method != "POST":
        return _error(405, "Use POST.")

    if action == "register":
        user = accounts.register(body.get("email"), body.get("password"), body.get("name"),
                                 body.get("invite"), body.get("setup"))
        return Response(200, {"user": accounts.public_user(user)},
                        cookies=[accounts.session_cookie(accounts.sign_session(user["id"]), req.secure)])
    if action == "login":
        user = accounts.login(body.get("email"), body.get("password"), req.ip)
        return Response(200, {"user": accounts.public_user(user)},
                        cookies=[accounts.session_cookie(accounts.sign_session(user["id"]), req.secure)])
    if action == "logout":
        return Response(200, {"ok": True}, cookies=[accounts.clear_cookie(req.secure)])
    if action == "invite":
        return Response(200, {"token": accounts.create_invite(_require_user(req))})
    if action == "alerts":
        user = accounts.set_alerts(_require_user(req), bool(body.get("enabled")))
        return Response(200, {"user": accounts.public_user(user)})
    return _error(400, "Unknown action.")


def sync_endpoint(req: Request) -> Response:
    user = _require_user(req)
    if req.method == "GET":
        return Response(200, accounts.load_data(user["id"]))
    body = req.body if isinstance(req.body, dict) else {}
    version = body.get("version")
    if not isinstance(version, int):
        return _error(400, "Send the version you started from.")
    return Response(200, accounts.save_data(user["id"], body.get("data"), version))


def cron_endpoint(req: Request) -> Response:
    from . import alerts  # imported lazily: only the daily job needs it
    expected = os.environ.get("CRON_SECRET", "")
    if not expected or req.headers.get("authorization") != f"Bearer {expected}":
        return _error(401, "Unauthorized.")
    return Response(200, alerts.run_daily())


ENDPOINTS = {
    "catalog": catalog_endpoint,
    "search": search_endpoint,
    "title": title_endpoint,
    "report": report_endpoint,
    "account": account_endpoint,
    "sync": sync_endpoint,
    "cron": cron_endpoint,
}

# Endpoints that change state need this header. Browsers can't add custom headers to
# cross-site form posts, so together with SameSite=Lax cookies this blocks CSRF.
CSRF_HEADER = "x-streamwise"


def handle(name: str, req: Request) -> Response:
    if req.method == "POST" and name in ("account", "sync") and req.headers.get(CSRF_HEADER) != "1":
        return _error(403, "Missing request header.")
    try:
        return ENDPOINTS[name](req)
    except AuthError as exc:
        return _error(exc.status, str(exc))
    except NotConfigured:
        return _error(503, "Sign-in and sync aren’t set up on this server yet.")


# ---------------------------------------------------------------- BaseHTTPRequestHandler glue

def serve(handler: BaseHTTPRequestHandler, name: str) -> None:
    parsed = urllib.parse.urlparse(handler.path)
    headers = {k.lower(): v for k, v in handler.headers.items()}
    req = Request(
        method=handler.command,
        params={k: v[0] for k, v in urllib.parse.parse_qs(parsed.query).items()},
        headers=headers,
        ip=(headers.get("x-forwarded-for", "").split(",")[0].strip() or handler.client_address[0]),
        secure=headers.get("x-forwarded-proto", "") == "https",
    )
    cookie = SimpleCookie()
    try:
        cookie.load(headers.get("cookie", ""))
    except Exception:  # noqa: BLE001 — a malformed cookie header just means "no cookies"
        pass
    req.cookies = {k: m.value for k, m in cookie.items()}

    if handler.command == "POST":
        length = int(headers.get("content-length") or 0)
        if length > MAX_BODY:
            return _send(handler, Response(413, {"error": "Request too large."}))
        try:
            req.body = json.loads(handler.rfile.read(length) or b"null")
        except ValueError:
            return _send(handler, Response(400, {"error": "Invalid JSON."}))
    _send(handler, handle(name, req))


def _send(handler: BaseHTTPRequestHandler, res: Response) -> None:
    data = json.dumps(res.payload).encode()
    handler.send_response(res.status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(data)))
    private = bool(res.cookies) or "user" in res.payload or "data" in res.payload
    handler.send_header("Cache-Control", "private, no-store" if private or not res.cache
                        else f"public, s-maxage={res.cache}, max-age=300")
    for c in res.cookies:
        handler.send_header("Set-Cookie", c)
    handler.end_headers()
    handler.wfile.write(data)
