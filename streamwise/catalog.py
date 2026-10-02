"""Streaming services StreamWise knows about, and their usual monthly prices.

Prices are the standard ad-free plan in each country. There is no public API for
streaming prices, so this table is maintained by hand. Users can always type in
what they actually pay.
"""

PRICES_AS_OF = "2026-10"

# id -> display name, brand colour, and substrings that identify it in TMDB's
# watch-provider names (which vary: "Amazon Prime Video", "Amazon Video", ...).
SERVICES = {
    "netflix":     {"name": "Netflix",          "color": "#e50914", "match": ["netflix"]},
    "prime":       {"name": "Prime Video",      "color": "#00a8e1", "match": ["amazon prime", "prime video"]},
    "disney":      {"name": "Disney+",          "color": "#113ccf", "match": ["disney"]},
    "hbo":         {"name": "HBO Max",          "color": "#5822b4", "match": ["hbo"]},
    "apple":       {"name": "Apple TV+",        "color": "#1d1d1f", "match": ["apple tv"]},
    "skyshowtime": {"name": "SkyShowtime",      "color": "#0f1d4a", "match": ["skyshowtime"]},
    "videoland":   {"name": "Videoland",        "color": "#e4007c", "match": ["videoland"]},
    "npo":         {"name": "NPO Plus",         "color": "#ff6d00", "match": ["npo"]},
}

# Netherlands, standard ad-free plans, EUR per month.
PRICES = {
    "NL": {
        "netflix": 15.99,
        "prime": 4.99,
        "disney": 10.99,
        "hbo": 11.99,
        "apple": 9.99,
        "skyshowtime": 9.99,
        "videoland": 11.99,
        "npo": 3.49,
    },
}

COUNTRIES = {
    "NL": "Netherlands", "BE": "Belgium", "DE": "Germany", "FR": "France",
    "ES": "Spain", "PT": "Portugal", "IT": "Italy", "GB": "United Kingdom",
    "IE": "Ireland", "US": "United States", "CA": "Canada", "BR": "Brazil",
}

NON_EURO = {"GB": "GBP", "US": "USD", "CA": "CAD", "BR": "BRL"}


def currency(country: str) -> str:
    return NON_EURO.get(country, "EUR")


def match_service(provider_name: str):
    """Map a TMDB provider name to one of our service ids, or None.

    Add-on "channels" sold through another store (e.g. "HBO Max Amazon Channel")
    are skipped: they are billed by the store, not the service.
    """
    name = provider_name.lower()
    if "channel" in name:
        return None
    if name == "max" or name.startswith("max "):
        return "hbo"
    for sid, svc in SERVICES.items():
        if any(needle in name for needle in svc["match"]):
            return sid
    return None


def catalog(country: str) -> dict:
    prices = PRICES.get(country, {})
    return {
        "country": country,
        "currency": currency(country),
        "prices_as_of": PRICES_AS_OF if prices else None,
        "services": [
            {"id": sid, "name": s["name"], "color": s["color"], "price": prices.get(sid)}
            for sid, s in SERVICES.items()
        ],
        "countries": [{"code": c, "name": n} for c, n in COUNTRIES.items()],
    }
