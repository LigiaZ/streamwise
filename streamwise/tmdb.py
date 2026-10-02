"""Thin client for The Movie Database (TMDB) API.

Only the two things StreamWise needs: search for a title, and get its runtime,
upcoming episodes and which services stream it in a given country.

The HTTP call is injectable (``fetch``) so the parsing can be tested offline.
"""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from typing import Callable, Optional

from .catalog import match_service

API = "https://api.themoviedb.org/3"
POSTER = "https://image.tmdb.org/t/p/w185"
DEFAULT_EPISODE_MINUTES = 45


class NotConfigured(Exception):
    """Raised when no TMDB token is available."""


def _http_fetch(path: str, params: dict) -> dict:
    token = os.environ.get("TMDB_READ_TOKEN", "").strip()
    if not token:
        raise NotConfigured("TMDB_READ_TOKEN is not set")
    url = f"{API}{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    })
    with urllib.request.urlopen(req, timeout=8) as resp:
        return json.load(resp)


Fetch = Callable[[str, dict], dict]


def _year(date: Optional[str]) -> Optional[int]:
    return int(date[:4]) if date and len(date) >= 4 and date[:4].isdigit() else None


def _poster(path: Optional[str]) -> Optional[str]:
    return f"{POSTER}{path}" if path else None


def search(query: str, fetch: Fetch = _http_fetch) -> list:
    data = fetch("/search/multi", {"query": query, "include_adult": "false", "language": "en-US"})
    results = []
    for r in data.get("results", []):
        kind = r.get("media_type")
        if kind not in ("movie", "tv"):
            continue
        results.append({
            "id": r["id"],
            "kind": kind,
            "title": r.get("title") or r.get("name") or "Untitled",
            "year": _year(r.get("release_date") or r.get("first_air_date")),
            "poster": _poster(r.get("poster_path")),
        })
    return results[:12]


def providers(data: dict, country: str) -> list:
    """Subscription services (not rent/buy) streaming this title in ``country``."""
    region = (data.get("watch/providers") or {}).get("results", {}).get(country, {})
    seen, out = set(), []
    for p in sorted(region.get("flatrate", []), key=lambda p: p.get("display_priority", 99)):
        name = p.get("provider_name", "")
        if "channel" in name.lower():  # add-ons billed through another store
            continue
        sid = match_service(name)
        key = sid or name
        if key in seen:
            continue
        seen.add(key)
        out.append({"service": sid, "name": name})
    return out


def _episode_minutes(data: dict) -> int:
    for value in data.get("episode_run_time") or []:
        if value:
            return int(value)
    for key in ("last_episode_to_air", "next_episode_to_air"):
        runtime = (data.get(key) or {}).get("runtime")
        if runtime:
            return int(runtime)
    return DEFAULT_EPISODE_MINUTES


def title(kind: str, tmdb_id: int, country: str, fetch: Fetch = _http_fetch) -> dict:
    data = fetch(f"/{kind}/{tmdb_id}", {"append_to_response": "watch/providers", "language": "en-US"})
    base = {
        "id": tmdb_id,
        "kind": kind,
        "poster": _poster(data.get("poster_path")),
        "providers": providers(data, country),
    }
    if kind == "movie":
        base.update({
            "title": data.get("title") or "Untitled",
            "year": _year(data.get("release_date")),
            "minutes": int(data.get("runtime") or 0) or None,
        })
        return base

    nxt = data.get("next_episode_to_air") or None
    base.update({
        "title": data.get("name") or "Untitled",
        "year": _year(data.get("first_air_date")),
        "episode_minutes": _episode_minutes(data),
        "status": data.get("status"),
        "seasons": [
            {"number": s["season_number"], "episodes": s.get("episode_count") or 0, "air_date": s.get("air_date")}
            for s in data.get("seasons", []) if s.get("season_number", 0) > 0
        ],
        "next_episode": {
            "air_date": nxt.get("air_date"),
            "season": nxt.get("season_number"),
            "episode": nxt.get("episode_number"),
        } if nxt else None,
    })
    return base
