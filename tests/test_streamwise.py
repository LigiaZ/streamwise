"""Run with: python3 -m unittest discover tests"""

import os
import sys
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from streamwise import tmdb  # noqa: E402
from streamwise.catalog import catalog, match_service  # noqa: E402
from streamwise.report import build_report  # noqa: E402
from streamwise.web import report_endpoint, search_endpoint, title_endpoint  # noqa: E402

TODAY = date(2026, 10, 2)


def days_ago(n):
    return (TODAY - timedelta(days=n)).isoformat()


class MatchService(unittest.TestCase):
    def test_common_provider_names(self):
        cases = {
            "Netflix": "netflix", "Netflix basic with Ads": "netflix",
            "Amazon Prime Video": "prime", "Amazon Prime Video with Ads": "prime",
            "Disney Plus": "disney", "HBO Max": "hbo", "Max": "hbo",
            "Apple TV Plus": "apple", "Apple TV+": "apple", "SkyShowtime": "skyshowtime",
            "Videoland": "videoland", "NPO Plus": "npo", "Crunchyroll": "crunchyroll",
            "Paramount Plus": "paramount", "Peacock Premium": "peacock",
        }
        for name, sid in cases.items():
            self.assertEqual(match_service(name), sid, name)

    def test_store_channels_and_unknowns_are_ignored(self):
        for name in ["HBO Max Amazon Channel", "Paramount Plus Apple TV Channel", "Pathé Thuis", "Maxdome"]:
            self.assertIsNone(match_service(name), name)

    def test_catalog_lists_plans_per_country(self):
        nl = {s["id"]: s for s in catalog("NL")["services"]}
        self.assertEqual([p["name"] for p in nl["netflix"]["plans"]], ["Basic", "Standard", "Premium"])
        self.assertEqual(nl["netflix"]["default"], {"name": "Standard", "price": 15.99})
        self.assertEqual(nl["npo"]["default"]["price"], 3.49)  # single plan -> that plan
        self.assertIn("crunchyroll", nl)

    def test_catalog_only_lists_services_sold_there(self):
        nl = {s["id"] for s in catalog("NL")["services"]}
        us = {s["id"] for s in catalog("US")["services"]}
        self.assertIn("videoland", nl)
        self.assertNotIn("videoland", us)
        self.assertIn("peacock", us)
        self.assertNotIn("peacock", nl)

    def test_every_country_has_prices_in_its_currency(self):
        from streamwise.catalog import COUNTRIES
        for code in COUNTRIES:
            c = catalog(code)
            self.assertGreaterEqual(len(c["services"]), 5, code)
            for s in c["services"]:
                prices = [p["price"] for p in s["plans"]]
                self.assertTrue(prices and all(p > 0 for p in prices), (code, s["id"]))
                self.assertEqual(prices, sorted(prices), (code, s["id"]))  # cheapest first
        self.assertEqual(catalog("BR")["currency"], "BRL")


MOVIE = {
    "id": 120, "title": "The Lord of the Rings: The Fellowship of the Ring", "release_date": "2001-12-18",
    "runtime": 179, "poster_path": "/x.jpg",
    "watch/providers": {"results": {"NL": {"flatrate": [
        {"provider_name": "Amazon Prime Video", "display_priority": 1},
        {"provider_name": "HBO Max Amazon Channel", "display_priority": 5},
        {"provider_name": "Pathé Thuis", "display_priority": 9},
    ], "rent": [{"provider_name": "Apple TV"}]}}},
}

SHOW = {
    "id": 1399, "name": "Some Show", "first_air_date": "2019-04-01", "status": "Returning Series",
    "episode_run_time": [], "last_episode_to_air": {"runtime": 52},
    "next_episode_to_air": {"air_date": "2027-01-10", "season_number": 3, "episode_number": 1},
    "seasons": [{"season_number": 0, "episode_count": 4}, {"season_number": 1, "episode_count": 8, "air_date": "2019-04-01"},
                {"season_number": 2, "episode_count": 10, "air_date": "2022-04-01"}],
    "watch/providers": {"results": {"NL": {"flatrate": [{"provider_name": "Max", "display_priority": 2}]}}},
}


class Tmdb(unittest.TestCase):
    def test_movie_runtime_and_subscription_providers_only(self):
        t = tmdb.title("movie", 120, "NL", fetch=lambda path, params: MOVIE)
        self.assertEqual(t["minutes"], 179)
        self.assertEqual(t["year"], 2001)
        self.assertEqual([p["service"] for p in t["providers"]], ["prime", None])
        self.assertTrue(t["poster"].endswith("/x.jpg"))

    def test_show_episode_runtime_seasons_and_next_episode(self):
        t = tmdb.title("tv", 1399, "NL", fetch=lambda path, params: SHOW)
        self.assertEqual(t["episode_minutes"], 52)
        self.assertEqual([s["number"] for s in t["seasons"]], [1, 2])
        self.assertEqual(t["next_episode"]["season"], 3)
        self.assertEqual(t["providers"][0]["service"], "hbo")

    def test_other_country_has_no_providers(self):
        t = tmdb.title("movie", 120, "BR", fetch=lambda path, params: MOVIE)
        self.assertEqual(t["providers"], [])

    def test_search_keeps_movies_and_shows_only(self):
        data = {"results": [
            {"id": 1, "media_type": "movie", "title": "A", "release_date": "2001-01-01"},
            {"id": 2, "media_type": "person", "name": "Someone"},
            {"id": 3, "media_type": "tv", "name": "B", "first_air_date": ""},
        ]}
        res = tmdb.search("x", fetch=lambda path, params: data)
        self.assertEqual([(r["kind"], r["title"], r["year"]) for r in res], [("movie", "A", 2001), ("tv", "B", None)])


class Report(unittest.TestCase):
    def report(self, services, log):
        return build_report(services, log, TODAY)

    def by_id(self, rep):
        return {r["id"]: r for r in rep["services"]}

    def test_cost_per_hour_and_verdicts(self):
        services = [
            {"id": "netflix", "price": 15.99, "since": "2025-01-01"},
            {"id": "prime", "price": 4.99, "since": "2025-01-01"},
            {"id": "disney", "price": 10.99, "since": "2025-01-01"},
        ]
        log = [
            {"date": days_ago(2), "service": "netflix", "minutes": 20 * 60, "title": "Show A"},   # 20 h -> €0.80/h
            {"date": days_ago(5), "service": "prime", "minutes": 120, "title": "Film"},           # 2 h -> €2.50/h
            {"date": days_ago(3), "service": "disney", "minutes": 60, "title": "Short"},          # 1 h -> €10.99/h
        ]
        r = self.by_id(self.report(services, log))
        self.assertEqual((r["netflix"]["verdict"], r["netflix"]["cost_per_hour"]), ("great", 0.8))
        self.assertEqual((r["prime"]["verdict"], r["prime"]["cost_per_hour"]), ("ok", 2.5))
        self.assertEqual(r["disney"]["verdict"], "poor")
        self.assertIn("4 hours", r["disney"]["reason"])

    def test_idle_service_is_paused_and_savings_counted(self):
        services = [{"id": "hbo", "price": 11.99, "since": "2025-01-01"}]
        log = [{"date": days_ago(45), "service": "hbo", "minutes": 300, "title": "Old show"}]
        rep = self.report(services, log)
        row = rep["services"][0]
        self.assertEqual((row["verdict"], row["idle_days"], row["hours_30d"]), ("pause", 45, 0))
        self.assertEqual(rep["yearly_savings"], 143.88)
        self.assertIn("HBO Max hasn’t been used lately", rep["summary"])

    def test_never_watched_old_subscription_is_paused(self):
        rep = self.report([{"id": "apple", "price": 9.99, "since": days_ago(90)}], [])
        self.assertEqual(rep["services"][0]["verdict"], "pause")

    def test_brand_new_subscription_is_not_judged(self):
        rep = self.report([{"id": "apple", "price": 9.99, "since": days_ago(5)}], [])
        self.assertEqual(rep["services"][0]["verdict"], "new")

    def test_monthly_history_and_window(self):
        services = [{"id": "netflix", "price": 15.99, "since": "2025-01-01"}]
        log = [
            {"date": "2026-10-01", "service": "netflix", "minutes": 60, "title": "A"},
            {"date": "2026-09-02", "service": "netflix", "minutes": 30, "title": "B"},   # outside 30-day window
            {"date": "2026-05-15", "service": "netflix", "minutes": 90, "title": "C"},
            {"date": "2027-01-01", "service": "netflix", "minutes": 999, "title": "Future"},
        ]
        row = self.report(services, log)["services"][0]
        self.assertEqual(row["minutes_30d"], 60)
        self.assertEqual([m["month"] for m in row["monthly"]], ["2026-05", "2026-06", "2026-07", "2026-08", "2026-09", "2026-10"])
        self.assertEqual([m["minutes"] for m in row["monthly"]], [90, 0, 0, 0, 30, 60])

    def test_bad_entries_are_ignored(self):
        services = [{"id": "netflix", "price": 15.99, "since": "2025-01-01"}]
        log = [{"date": "not a date", "service": "netflix", "minutes": 60},
               {"date": days_ago(1), "service": "netflix", "minutes": -5},
               {"date": days_ago(1), "minutes": 60}]
        self.assertEqual(self.report(services, log)["services"][0]["minutes_30d"], 0)

    def test_empty(self):
        rep = self.report([], [])
        self.assertEqual(rep["monthly_total"], 0)
        self.assertIn("Add the services", rep["summary"])


class Endpoints(unittest.TestCase):
    def test_search_validates_query(self):
        self.assertEqual(search_endpoint({"q": "a"})[0], 400)

    def test_title_validates_params(self):
        self.assertEqual(title_endpoint({"kind": "person", "id": "1"})[0], 400)
        self.assertEqual(title_endpoint({"kind": "movie", "id": "1;drop"})[0], 400)

    def test_missing_token_is_a_friendly_503(self):
        old = os.environ.pop("TMDB_READ_TOKEN", None)
        try:
            status, payload, _ = search_endpoint({"q": "lord of the rings"})
            self.assertEqual(status, 503)
            self.assertIn("manually", payload["error"])
        finally:
            if old is not None:
                os.environ["TMDB_READ_TOKEN"] = old

    def test_report_endpoint_uses_country_currency(self):
        status, payload, _ = report_endpoint({}, {"country": "GB", "services": [], "log": [], "today": "2026-10-02"})
        self.assertEqual((status, payload["currency"]), (200, "GBP"))
        self.assertEqual(report_endpoint({}, {"services": "nope"})[0], 400)


if __name__ == "__main__":
    unittest.main()
