"""The daily job: email each signed-in user about things worth acting on.

  * a subscription they pay for but haven't used in 30 days  -> "pause it"
  * a new season of a show they follow starting within a week -> "it's back" (and, if they've
    paused the service it streams on, "resubscribe on <date>")

Each alert is sent once (tracked in the notifications table). Vercel Cron calls /api/cron
every morning; email goes out through Resend's HTTP API.
"""

from __future__ import annotations

import html
import json
import os
import urllib.request
from datetime import date, timedelta
from typing import Callable, Optional

from . import tmdb
from .accounts import _iso, load_data, now
from .catalog import SERVICES, currency
from .db import db
from .report import build_report

LOOKAHEAD_DAYS = 7


def _active_services(data: dict) -> list:
    return [{"id": sid, "name": SERVICES.get(sid, {}).get("name", sid), "price": s.get("price") or 0, "since": s.get("since")}
            for sid, s in (data.get("services") or {}).items() if s.get("on")]


def alerts_for(data: dict, today: date, title_lookup: Callable) -> list:
    """Pure function: what should this user hear about today? Returns [{key, subject, text}]."""
    out = []
    active = _active_services(data)
    active_ids = {s["id"] for s in active}
    country = data.get("country") or "NL"

    report = build_report(active, data.get("log") or [], today, currency(country))
    for s in report["services"]:
        if s["verdict"] == "pause":
            out.append({
                "key": f"pause:{s['id']}:{today:%Y-%m}",
                "subject": f"Pause {s['name']}?",
                "text": f"You haven’t watched anything on {s['name']} in {s['idle_days']} days. "
                        f"Pausing it saves {s['price']:.2f} a month.",
            })

    for follow in data.get("follows") or []:
        tmdb_id = follow.get("tmdbId")
        if not isinstance(tmdb_id, int):
            continue
        try:
            show = title_lookup(tmdb_id, country)
        except Exception:  # noqa: BLE001 — one bad lookup shouldn't stop the others
            continue
        nxt = show.get("next_episode") or {}
        if not nxt.get("air_date") or nxt.get("episode") != 1:
            continue  # only new seasons, not every weekly episode
        air = date.fromisoformat(nxt["air_date"])
        if not today <= air <= today + timedelta(days=LOOKAHEAD_DAYS):
            continue
        where = [p for p in show.get("providers", []) if p.get("service")]
        on = where[0]["service"] if where else None
        name = SERVICES.get(on, {}).get("name") if on else None
        text = f"Season {nxt['season']} of {show['title']} starts on {air:%A %d %B}"
        text += f" on {name}." if name else "."
        if on and on not in active_ids:
            text += f" You’re not subscribed to {name} right now: resubscribe on {air:%d %B} and pause again when you’re done."
        out.append({"key": f"season:{tmdb_id}:{nxt['season']}", "subject": f"{show['title']} is back", "text": text})
    return out


def send_email(to: str, subject: str, lines: list) -> bool:
    key = os.environ.get("RESEND_API_KEY", "")
    if not key:
        return False
    sender = os.environ.get("ALERTS_FROM", "StreamWise <onboarding@resend.dev>")
    app_url = os.environ.get("APP_URL", "")
    body_html = ("<div style=\"font-family:system-ui,sans-serif;max-width:520px\">"
                 + "".join(f"<p>{html.escape(l)}</p>" for l in lines)
                 + (f"<p><a href=\"{html.escape(app_url)}\">Open StreamWise</a></p>" if app_url else "")
                 + "<p style=\"color:#888;font-size:12px\">You can turn these emails off under Services in the app.</p></div>")
    req = urllib.request.Request("https://api.resend.com/emails", method="POST",
                                 data=json.dumps({"from": sender, "to": [to], "subject": subject, "html": body_html,
                                                  "text": "\n\n".join(lines)}).encode(),
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return 200 <= resp.status < 300


def run_daily(today: Optional[date] = None, title_lookup: Optional[Callable] = None,
              sender: Callable = send_email) -> dict:
    today = today or date.today()
    cache = {}

    def lookup(tmdb_id: int, country: str) -> dict:
        if (tmdb_id, country) not in cache:
            cache[(tmdb_id, country)] = (title_lookup or (lambda i, c: tmdb.title("tv", i, c)))(tmdb_id, country)
        return cache[(tmdb_id, country)]

    stats = {"users": 0, "alerts": 0, "emails": 0}
    for user in db().execute("SELECT id, email FROM users WHERE email_alerts = 1"):
        data = load_data(user["id"])["data"]
        if not data:
            continue
        stats["users"] += 1
        sent_keys = {r["key"] for r in db().execute("SELECT key FROM notifications WHERE user_id = ?", (user["id"],))}
        fresh = [a for a in alerts_for(data, today, lookup) if a["key"] not in sent_keys]
        if not fresh:
            continue
        stats["alerts"] += len(fresh)
        subject = fresh[0]["subject"] if len(fresh) == 1 else f"StreamWise: {len(fresh)} things worth a look"
        if sender(user["email"], subject, [a["text"] for a in fresh]):
            stats["emails"] += 1
            for a in fresh:
                db().execute("INSERT OR IGNORE INTO notifications (user_id, key, sent_at) VALUES (?, ?, ?)",
                             (user["id"], a["key"], _iso(now())))
    return stats
