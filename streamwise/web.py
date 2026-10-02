"""HTTP layer shared by the Vercel functions in /api and the local dev server.

Each endpoint is a plain function: (query params, JSON body) -> (status, payload, cache seconds).
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
from http.server import BaseHTTPRequestHandler

from . import tmdb
from .catalog import COUNTRIES, catalog, currency
from .report import build_report

MAX_BODY = 512 * 1024
MAX_LOG = 5000


def _country(params: dict) -> str:
    c = (params.get("country") or "NL").upper()
    return c if c in COUNTRIES else "NL"


def _tmdb_error(exc: Exception):
    if isinstance(exc, tmdb.NotConfigured):
        return 503, {"error": "Title search isn’t set up yet. You can still add things manually."}, 0
    if isinstance(exc, urllib.error.HTTPError) and exc.code == 404:
        return 404, {"error": "Title not found."}, 0
    return 502, {"error": "Couldn’t reach the movie database. Try again in a moment."}, 0


def catalog_endpoint(params: dict, body=None):
    return 200, catalog(_country(params)), 86400


def search_endpoint(params: dict, body=None):
    q = (params.get("q") or "").strip()
    if len(q) < 2 or len(q) > 100:
        return 400, {"error": "Search for 2 to 100 characters."}, 0
    try:
        return 200, {"results": tmdb.search(q)}, 3600
    except Exception as exc:  # noqa: BLE001 — every failure becomes a friendly message
        return _tmdb_error(exc)


def title_endpoint(params: dict, body=None):
    kind = params.get("kind")
    tmdb_id = params.get("id") or ""
    if kind not in ("movie", "tv") or not re.fullmatch(r"\d{1,9}", tmdb_id):
        return 400, {"error": "Expected kind=movie|tv and a numeric id."}, 0
    try:
        return 200, tmdb.title(kind, int(tmdb_id), _country(params)), 86400
    except Exception as exc:  # noqa: BLE001
        return _tmdb_error(exc)


def report_endpoint(params: dict, body=None):
    if not isinstance(body, dict):
        return 400, {"error": "Send JSON with services and log."}, 0
    services = body.get("services") or []
    log = body.get("log") or []
    if not isinstance(services, list) or not isinstance(log, list) or len(log) > MAX_LOG:
        return 400, {"error": "services and log must be lists (log up to 5000 entries)."}, 0
    country = _country({"country": body.get("country")})
    return 200, build_report(services, log, body.get("today"), currency(country)), 0


ENDPOINTS = {
    "catalog": catalog_endpoint,
    "search": search_endpoint,
    "title": title_endpoint,
    "report": report_endpoint,
}


def serve(handler: BaseHTTPRequestHandler, name: str) -> None:
    """Run endpoint ``name`` for a request held by a BaseHTTPRequestHandler."""
    parsed = urllib.parse.urlparse(handler.path)
    params = {k: v[0] for k, v in urllib.parse.parse_qs(parsed.query).items()}
    body = None
    if handler.command == "POST":
        length = int(handler.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            return _send(handler, 413, {"error": "Request too large."}, 0)
        try:
            body = json.loads(handler.rfile.read(length) or b"null")
        except ValueError:
            return _send(handler, 400, {"error": "Invalid JSON."}, 0)
    status, payload, cache = ENDPOINTS[name](params, body)
    _send(handler, status, payload, cache)


def _send(handler: BaseHTTPRequestHandler, status: int, payload: dict, cache: int) -> None:
    data = json.dumps(payload).encode()
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(data)))
    handler.send_header("Cache-Control", f"public, s-maxage={cache}, max-age=300" if cache else "no-store")
    handler.end_headers()
    handler.wfile.write(data)
