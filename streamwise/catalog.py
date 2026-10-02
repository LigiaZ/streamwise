"""Streaming services StreamWise knows about, and their plans and monthly prices per country.

There is no public API for streaming prices, so this table is maintained by hand from
local price comparisons (checked October 2026). A service only appears in a country where
we have at least one plan for it. Users pick their plan from a list; "Other amount" covers
promotions, bundles and price changes we haven't caught yet.
"""

PRICES_AS_OF = "2026-10"

# id -> display name, brand colour, and substrings that identify it in TMDB's
# watch-provider names (which vary: "Amazon Prime Video", "Amazon Video", ...).
SERVICES = {
    "netflix":     {"name": "Netflix",     "color": "#e50914", "match": ["netflix"]},
    "prime":       {"name": "Prime Video", "color": "#00a8e1", "match": ["amazon prime", "prime video"]},
    "disney":      {"name": "Disney+",     "color": "#113ccf", "match": ["disney"]},
    "hbo":         {"name": "HBO Max",     "color": "#5822b4", "match": ["hbo"]},
    "apple":       {"name": "Apple TV+",   "color": "#1d1d1f", "match": ["apple tv"]},
    "paramount":   {"name": "Paramount+",  "color": "#0064ff", "match": ["paramount"]},
    "crunchyroll": {"name": "Crunchyroll", "color": "#f47521", "match": ["crunchyroll"]},
    "skyshowtime": {"name": "SkyShowtime", "color": "#0f1d4a", "match": ["skyshowtime"]},
    "videoland":   {"name": "Videoland",   "color": "#e4007c", "match": ["videoland"]},
    "npo":         {"name": "NPO Plus",    "color": "#ff6d00", "match": ["npo"]},
    "peacock":     {"name": "Peacock",     "color": "#000000", "match": ["peacock"]},
}

# Crunchyroll's euro-zone tiers (same in each euro country we cover).
_CR_EUR = [("Fan", 6.99), ("Mega Fan", 9.99), ("Ultimate Fan", 14.99)]

# country -> service -> [(plan, monthly price in local currency)], cheapest first.
PLANS = {
    "NL": {
        "netflix": [("Basic", 9.99), ("Standard", 15.99), ("Premium", 20.99)],
        "prime": [("Prime Video", 4.99)],
        "disney": [("Standard with ads", 6.99), ("Standard", 10.99), ("Premium", 15.99)],
        "hbo": [("Basic with ads", 5.99), ("Standard", 11.99), ("Premium", 16.99)],
        "apple": [("Apple TV+", 9.99)],
        "crunchyroll": _CR_EUR,
        "skyshowtime": [("With ads", 6.99), ("Standard", 9.99), ("Premium", 13.99)],
        "videoland": [("Basis with ads", 6.99), ("Plus", 11.99), ("Premium", 14.99)],
        "npo": [("NPO Plus", 3.49)],
    },
    "BE": {
        "netflix": [("Basic", 10.99), ("Standard", 16.99), ("Premium", 21.99)],
        "prime": [("Prime", 2.99)],
        "disney": [("Standard", 10.99), ("Premium", 15.99)],
        "hbo": [("Basic with ads", 6.99), ("Standard", 10.99), ("Premium", 15.99)],
        "apple": [("Apple TV+", 9.99)],
        "crunchyroll": _CR_EUR,
    },
    "DE": {
        "netflix": [("Standard with ads", 6.99), ("Standard", 15.99), ("Premium", 21.99)],
        "prime": [("Prime", 8.99), ("Prime, ad-free", 11.98)],
        "disney": [("Standard with ads", 6.99), ("Standard", 10.99), ("Premium", 15.99)],
        "apple": [("Apple TV+", 9.99)],
        "paramount": [("Basic with ads", 5.99)],
        "crunchyroll": _CR_EUR,
    },
    "FR": {
        "netflix": [("Standard with ads", 7.99), ("Standard", 14.99), ("Premium", 21.99)],
        "prime": [("Prime", 6.99)],
        "disney": [("Standard with ads", 6.99), ("Standard", 10.99), ("Premium", 15.99)],
        "hbo": [("Basic with ads", 6.99)],
        "apple": [("Apple TV+", 9.99)],
        "paramount": [("Standard", 7.99)],
        "crunchyroll": _CR_EUR,
    },
    "ES": {
        "netflix": [("Standard with ads", 8.99), ("Standard", 14.99), ("Premium", 21.99)],
        "prime": [("Prime", 4.99)],
        "disney": [("Standard with ads", 6.99), ("Standard", 10.99), ("Premium", 15.99)],
        "hbo": [("Basic with ads", 6.99)],
        "apple": [("Apple TV+", 9.99)],
        "skyshowtime": [("With ads", 5.99)],
        "crunchyroll": _CR_EUR,
    },
    "PT": {
        "netflix": [("Basic", 8.99), ("Standard", 12.99), ("Premium", 17.99)],
        "prime": [("Prime", 4.99)],
        "disney": [("Standard with ads", 6.99), ("Standard", 10.99), ("Premium", 15.99)],
        "hbo": [("Basic with ads", 5.99), ("Standard", 9.99), ("Premium", 13.99)],
        "apple": [("Apple TV+", 9.99)],
        "skyshowtime": [("SkyShowtime", 4.99)],
        "crunchyroll": _CR_EUR,
    },
    "IT": {
        "netflix": [("Standard with ads", 5.99), ("Standard", 13.99), ("Premium", 17.99)],
        "prime": [("Prime", 4.99), ("Prime, ad-free", 6.98)],
        "disney": [("Standard with ads", 5.99), ("Standard", 11.99), ("Premium", 13.99)],
        "hbo": [("Basic with ads", 5.99)],
        "apple": [("Apple TV+", 9.99)],
        "paramount": [("Paramount+", 7.99)],
        "crunchyroll": _CR_EUR,
    },
    "IE": {
        "netflix": [("Basic", 11.99), ("Standard", 18.99), ("Premium", 25.99)],
        "prime": [("Prime", 6.99)],
        "disney": [("Standard with ads", 9.99), ("Premium", 15.99)],
        "hbo": [("Standard with ads", 6.99), ("Standard", 10.99), ("Premium", 15.99)],
        "apple": [("Apple TV+", 9.99)],
        "paramount": [("Basic", 5.99), ("Standard", 8.99), ("Premium", 11.99)],
        "crunchyroll": _CR_EUR,
    },
    "GB": {
        "netflix": [("Standard with ads", 7.99), ("Standard", 13.99), ("Premium", 20.99)],
        "prime": [("Prime", 8.99)],
        "disney": [("Standard with ads", 5.99), ("Standard", 9.99), ("Premium", 14.99)],
        "hbo": [("Basic with ads", 4.99), ("Standard with ads", 5.99), ("Standard", 9.99), ("Premium", 14.99)],
        "apple": [("Apple TV+", 9.99)],
        "paramount": [("Basic with ads", 5.99), ("Standard", 9.99), ("Premium", 12.99)],
        "crunchyroll": [("Fan", 5.99), ("Mega Fan", 6.99)],
    },
    "US": {
        "netflix": [("Standard with ads", 8.99), ("Standard", 19.99), ("Premium", 26.99)],
        "prime": [("Prime Video", 8.99), ("Prime Video, ad-free", 13.98)],
        "disney": [("Standard with ads", 9.99), ("Premium", 18.99)],
        "hbo": [("Basic with ads", 10.99), ("Standard", 18.49), ("Premium", 22.99)],
        "apple": [("Apple TV+", 12.99)],
        "paramount": [("Essential", 8.99), ("Premium", 13.99)],
        "crunchyroll": [("Fan", 9.99), ("Mega Fan", 13.99), ("Ultimate Fan", 17.99)],
        "peacock": [("Select", 7.99), ("Premium", 10.99), ("Premium Plus", 16.99)],
    },
    "CA": {
        "netflix": [("Standard with ads", 7.99), ("Standard", 18.99), ("Premium", 23.99)],
        "prime": [("Prime ($99/year)", 8.25)],
        "disney": [("Standard with ads", 8.99), ("Standard", 15.99), ("Premium", 16.99)],
        "apple": [("Apple TV+", 14.99)],
        "paramount": [("Basic with ads", 6.99), ("Standard", 10.99), ("Premium", 13.99)],
        "crunchyroll": [("Fan", 9.99), ("Mega Fan", 12.49)],
    },
    "BR": {
        "netflix": [("Standard with ads", 20.90), ("Standard", 44.90), ("Premium", 59.90)],
        "prime": [("Prime Video", 19.90), ("Prime Video, ad-free", 29.90)],
        "disney": [("Standard with ads", 27.99), ("Standard", 46.90)],
        "hbo": [("Basic with ads", 29.90), ("Standard", 44.90)],
        "apple": [("Apple TV+", 29.90)],
        "paramount": [("Standard", 34.90), ("Premium", 44.90)],
        "crunchyroll": [("Fan", 19.90), ("Mega Fan", 24.90)],
    },
}

COUNTRIES = {
    "NL": "Netherlands", "BE": "Belgium", "DE": "Germany", "FR": "France",
    "ES": "Spain", "PT": "Portugal", "IT": "Italy", "IE": "Ireland",
    "GB": "United Kingdom", "US": "United States", "CA": "Canada", "BR": "Brazil",
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


def default_plan(plans: list) -> dict:
    """The plan to preselect: plain "Standard" if there is one, else the cheapest."""
    for name, price in plans:
        if name == "Standard":
            return {"name": name, "price": price}
    name, price = plans[0]
    return {"name": name, "price": price}


def catalog(country: str) -> dict:
    plans = PLANS.get(country, {})
    return {
        "country": country,
        "currency": currency(country),
        "prices_as_of": PRICES_AS_OF,
        "services": [
            {
                "id": sid, "name": s["name"], "color": s["color"],
                "plans": [{"name": n, "price": p} for n, p in plans[sid]],
                "default": default_plan(plans[sid]),
            }
            for sid, s in SERVICES.items() if sid in plans
        ],
        "countries": [{"code": c, "name": n} for c, n in COUNTRIES.items()],
        "all": {sid: {"name": s["name"], "color": s["color"]} for sid, s in SERVICES.items()},
    }
