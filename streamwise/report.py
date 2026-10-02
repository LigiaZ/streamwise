"""The money part: is each subscription worth what you pay?

Given the services someone pays for and a log of what they watched, work out
for each service:

  * hours watched in the last 30 days, and the cost per hour that implies;
  * how long it has been idle;
  * a verdict — great / ok / poor value, unused lately, or too new to judge;
  * how much pausing the idle ones would save over a year.

The benchmark for "poor value" is renting: a film costs about 4.99 for two
hours, so if a subscription costs more than ~2.50 per hour you watched, renting
would have been cheaper.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import Optional

from .catalog import SERVICES

WINDOW_DAYS = 30
IDLE_DAYS = 30            # nothing watched for this long -> suggest pausing
NEW_DAYS = 14             # don't judge a subscription younger than this
GREAT_PER_HOUR = 1.00
RENTAL_PER_HOUR = 2.50    # above this, renting would have been cheaper
HISTORY_MONTHS = 6
SYMBOLS = {"EUR": "€", "GBP": "£", "USD": "$", "CAD": "CA$", "BRL": "R$"}

VERDICTS = {
    "great": "Great value",
    "ok": "Worth it",
    "poor": "Poor value",
    "pause": "Unused lately",
    "new": "Too new to tell",
}


def _d(value) -> Optional[date]:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _month_keys(today: date, n: int) -> list:
    keys, y, m = [], today.year, today.month
    for _ in range(n):
        keys.append(f"{y:04d}-{m:02d}")
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return list(reversed(keys))


def _money(x: Optional[float]) -> Optional[float]:
    return None if x is None else round(x + 1e-9, 2)


def _verdict(price: float, hours: float, idle_days: int, age_days: Optional[int], cur: str = "€") -> tuple:
    if idle_days >= IDLE_DAYS:
        return "pause", f"Nothing watched in {idle_days} days. You could pause it until something new comes out."
    if age_days is not None and age_days < NEW_DAYS and hours < 2:
        return "new", "Give it a couple of weeks before judging."
    if price <= 0:
        return "great", "Free with something you already pay for."
    per_hour = price / hours if hours else float("inf")
    if per_hour <= GREAT_PER_HOUR:
        return "great", f"Under {cur}{GREAT_PER_HOUR:.2f} per hour watched."
    if per_hour <= RENTAL_PER_HOUR:
        return "ok", "Cheaper than renting what you watched."
    needed = price / RENTAL_PER_HOUR
    return "poor", f"Renting would have been cheaper. It pays off at about {needed:.0f} hours a month."


def build_report(services: list, log: list, today=None, currency: str = "EUR") -> dict:
    cur = SYMBOLS.get(currency, currency + " ")
    today = _d(today) or date.today()
    window_start = today - timedelta(days=WINDOW_DAYS - 1)
    months = _month_keys(today, HISTORY_MONTHS)

    by_service = defaultdict(list)
    for entry in log:
        when = _d(entry.get("date"))
        sid = entry.get("service")
        minutes = entry.get("minutes") or 0
        if when is None or when > today or not sid or minutes <= 0:
            continue
        by_service[sid].append((when, int(minutes), entry.get("title") or ""))

    rows = []
    for svc in services:
        sid = svc.get("id")
        price = float(svc.get("price") or 0)
        since = _d(svc.get("since"))
        entries = sorted(by_service.get(sid, []))

        recent = [e for e in entries if e[0] >= window_start]
        minutes_30d = sum(m for _, m, _ in recent)
        hours = minutes_30d / 60
        last = entries[-1][0] if entries else None
        idle_from = last or since or window_start
        idle_days = (today - idle_from).days
        age_days = (today - since).days if since else None

        verdict, reason = _verdict(price, hours, idle_days, age_days, cur)

        monthly = defaultdict(int)
        for when, m, _ in entries:
            monthly[f"{when.year:04d}-{when.month:02d}"] += m
        titles = defaultdict(int)
        for _, m, t in recent:
            titles[t] += m

        rows.append({
            "id": sid,
            "name": svc.get("name") or SERVICES.get(sid, {}).get("name", sid),
            "price": _money(price),
            "minutes_30d": minutes_30d,
            "hours_30d": round(hours, 1),
            "cost_per_hour": _money(price / hours) if hours else None,
            "last_watched": last.isoformat() if last else None,
            "idle_days": idle_days,
            "verdict": verdict,
            "verdict_label": VERDICTS[verdict],
            "reason": reason,
            "monthly": [{"month": k, "minutes": monthly.get(k, 0)} for k in months],
            "top_titles": [t for t, _ in sorted(titles.items(), key=lambda kv: -kv[1])[:3] if t],
        })

    order = {"pause": 0, "poor": 1, "ok": 2, "great": 3, "new": 4}
    rows.sort(key=lambda r: (order[r["verdict"]], -(r["price"] or 0)))

    monthly_total = sum(r["price"] or 0 for r in rows)
    pause = [r for r in rows if r["verdict"] == "pause"]
    poor = [r for r in rows if r["verdict"] == "poor"]
    yearly_savings = sum(r["price"] for r in pause) * 12
    hours_total = sum(r["hours_30d"] for r in rows)

    return {
        "today": today.isoformat(),
        "currency": currency,
        "window_days": WINDOW_DAYS,
        "monthly_total": _money(monthly_total),
        "yearly_total": _money(monthly_total * 12),
        "hours_30d": round(hours_total, 1),
        "cost_per_hour": _money(monthly_total / hours_total) if hours_total else None,
        "yearly_savings": _money(yearly_savings),
        "yearly_savings_with_poor": _money(yearly_savings + sum(r["price"] for r in poor) * 12),
        "services": rows,
        "summary": _summary(rows, pause, poor, yearly_savings, cur),
    }


def _names(rows: list) -> str:
    names = [r["name"] for r in rows]
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def _summary(rows: list, pause: list, poor: list, savings: float, cur: str = "€") -> str:
    if not rows:
        return "Add the services you pay for to get started."
    if pause:
        s = f"{_names(pause)} {'hasn’t' if len(pause) == 1 else 'haven’t'} been used lately. Pausing would save {cur}{savings:,.0f} a year."
        if poor:
            s += f" {_names(poor)} {'is' if len(poor) == 1 else 'are'} also costing more than renting."
        return s
    if poor:
        return f"{_names(poor)} {'is' if len(poor) == 1 else 'are'} costing more per hour than renting would."
    return "Every subscription is earning its keep this month. Nice."
