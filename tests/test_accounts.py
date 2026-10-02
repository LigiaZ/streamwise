"""Accounts, sync and alerts. Run with: python3 -m unittest discover tests"""

import os
import sys
import unittest
from datetime import date
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from streamwise import accounts, alerts, db as dbmod  # noqa: E402
from streamwise.web import Request, handle  # noqa: E402

accounts.PBKDF2_ITERATIONS = 1000  # keep tests fast; production uses 600k
PASSWORD = "correct horse battery"


def post(name, action=None, body=None, cookie=None, csrf=True, ip="1.2.3.4"):
    headers = {"x-streamwise": "1"} if csrf else {}
    return handle(name, Request(method="POST", params={"action": action} if action else {}, body=body or {},
                                cookies={"sw_session": cookie} if cookie else {}, headers=headers, ip=ip))


def get(name, params=None, cookie=None):
    return handle(name, Request(method="GET", params=params or {}, cookies={"sw_session": cookie} if cookie else {}))


def session_from(res):
    return res.cookies[0].split(";")[0].split("=", 1)[1]


class Base(unittest.TestCase):
    def setUp(self):
        self.env = mock.patch.dict(os.environ, {"SETUP_SECRET": "letmein", "SESSION_SECRET": "test-secret"}, clear=False)
        self.env.start()
        os.environ.pop("VERCEL", None)
        dbmod.use(dbmod.SQLite(":memory:"))

    def tearDown(self):
        dbmod.use(None)
        self.env.stop()

    def owner(self):
        res = post("account", "register", {"email": "Ligia@Example.com", "password": PASSWORD, "setup": "letmein"})
        self.assertEqual(res.status, 200, res.payload)
        return res.payload["user"], session_from(res)


class Passwords(unittest.TestCase):
    def test_hash_roundtrip_and_salted(self):
        h1, h2 = accounts.hash_password("pw-123456789", 1000), accounts.hash_password("pw-123456789", 1000)
        self.assertNotEqual(h1, h2)
        self.assertTrue(accounts.verify_password("pw-123456789", h1))
        self.assertFalse(accounts.verify_password("wrong", h1))
        self.assertFalse(accounts.verify_password("x", "garbage"))

    def test_session_signature_and_tampering(self):
        with mock.patch.dict(os.environ, {"SESSION_SECRET": "s"}):
            token = accounts.sign_session("abc")
            self.assertEqual(accounts.verify_session(token), "abc")
            uid, issued, sig = token.split(".")
            self.assertIsNone(accounts.verify_session(f"other.{issued}.{sig}"))
            self.assertIsNone(accounts.verify_session(accounts.sign_session("abc", issued=1)))  # expired


class Registration(Base):
    def test_first_account_needs_setup_secret_and_becomes_owner(self):
        bad = post("account", "register", {"email": "a@b.co", "password": PASSWORD, "setup": "nope"})
        self.assertEqual(bad.status, 403)
        user, _ = self.owner()
        self.assertTrue(user["is_owner"])
        self.assertEqual(user["email"], "ligia@example.com")

    def test_after_owner_signup_needs_a_one_time_invite(self):
        _, cookie = self.owner()
        self.assertEqual(post("account", "register", {"email": "x@y.co", "password": PASSWORD}).status, 403)
        token = post("account", "invite", cookie=cookie).payload["token"]
        ok = post("account", "register", {"email": "friend@y.co", "password": PASSWORD, "invite": token})
        self.assertEqual(ok.status, 200)
        self.assertFalse(ok.payload["user"]["is_owner"])
        again = post("account", "register", {"email": "other@y.co", "password": PASSWORD, "invite": token})
        self.assertEqual(again.status, 403)

    def test_only_owner_can_invite(self):
        _, cookie = self.owner()
        token = post("account", "invite", cookie=cookie).payload["token"]
        friend = post("account", "register", {"email": "friend@y.co", "password": PASSWORD, "invite": token})
        self.assertEqual(post("account", "invite", cookie=session_from(friend)).status, 403)

    def test_password_rules(self):
        res = post("account", "register", {"email": "a@b.co", "password": "short", "setup": "letmein"})
        self.assertEqual(res.status, 400)


class Login(Base):
    def test_login_sets_httponly_cookie_and_me_works(self):
        self.owner()
        res = post("account", "login", {"email": "ligia@example.com", "password": PASSWORD})
        self.assertEqual(res.status, 200)
        self.assertIn("HttpOnly", res.cookies[0])
        self.assertIn("SameSite=Lax", res.cookies[0])
        me = get("account", {"action": "me"}, cookie=session_from(res))
        self.assertEqual(me.payload["user"]["email"], "ligia@example.com")
        self.assertIsNone(get("account", {"action": "me"}).payload["user"])

    def test_wrong_password_and_unknown_email_look_the_same(self):
        self.owner()
        a = post("account", "login", {"email": "ligia@example.com", "password": "wrong-password"})
        b = post("account", "login", {"email": "nobody@example.com", "password": "wrong-password"})
        self.assertEqual((a.status, a.payload), (b.status, b.payload))

    def test_lockout_after_five_failures(self):
        self.owner()
        for _ in range(5):
            self.assertEqual(post("account", "login", {"email": "ligia@example.com", "password": "nope-nope"}).status, 401)
        locked = post("account", "login", {"email": "ligia@example.com", "password": PASSWORD})
        self.assertEqual(locked.status, 429)

    def test_post_without_csrf_header_is_rejected(self):
        self.owner()
        res = post("account", "login", {"email": "ligia@example.com", "password": PASSWORD}, csrf=False)
        self.assertEqual(res.status, 403)


class Sync(Base):
    def test_save_load_and_conflict(self):
        _, cookie = self.owner()
        self.assertEqual(get("sync", cookie=cookie).payload["version"], 0)
        data = {"country": "NL", "services": {"netflix": {"on": True, "price": 15.99}}, "log": [], "follows": []}
        saved = post("sync", body={"data": data, "version": 0}, cookie=cookie)
        self.assertEqual(saved.payload["version"], 1)
        loaded = get("sync", cookie=cookie).payload
        self.assertEqual((loaded["version"], loaded["data"]["services"]["netflix"]["price"]), (1, 15.99))
        stale = post("sync", body={"data": data, "version": 0}, cookie=cookie)
        self.assertEqual(stale.status, 409)

    def test_users_cannot_see_each_others_data(self):
        _, owner = self.owner()
        post("sync", body={"data": {"services": {}, "log": [{"title": "secret"}]}, "version": 0}, cookie=owner)
        token = post("account", "invite", cookie=owner).payload["token"]
        friend = session_from(post("account", "register", {"email": "f@y.co", "password": PASSWORD, "invite": token}))
        self.assertIsNone(get("sync", cookie=friend).payload["data"])

    def test_sync_requires_sign_in(self):
        self.assertEqual(get("sync").status, 401)


class Alerts(Base):
    TODAY = date(2026, 10, 2)

    def data(self, **extra):
        d = {"country": "NL", "services": {
            "netflix": {"on": True, "price": 15.99, "since": "2025-01-01"},
            "disney": {"on": True, "price": 10.99, "since": "2025-01-01"},
        }, "log": [{"date": "2026-09-30", "service": "netflix", "minutes": 600, "title": "Show"}], "follows": []}
        d.update(extra)
        return d

    def show(self, air_date, episode=1, service="hbo"):
        return lambda tmdb_id, country: {"title": "The Last of Us", "providers": [{"service": service, "name": "HBO Max"}],
                                         "next_episode": {"air_date": air_date, "season": 3, "episode": episode}}

    def test_idle_service_gets_a_pause_alert(self):
        found = alerts.alerts_for(self.data(), self.TODAY, self.show("2027-01-01"))
        self.assertEqual([a["key"] for a in found], ["pause:disney:2026-10"])

    def test_new_season_on_a_paused_service_says_resubscribe(self):
        data = self.data(follows=[{"tmdbId": 100088, "title": "The Last of Us"}])
        found = alerts.alerts_for(data, self.TODAY, self.show("2026-10-05"))
        season = [a for a in found if a["key"].startswith("season:")][0]
        self.assertIn("resubscribe", season["text"])
        self.assertIn("Season 3", season["text"])

    def test_far_away_or_mid_season_episodes_are_ignored(self):
        data = self.data(follows=[{"tmdbId": 1, "title": "X"}])
        self.assertFalse([a for a in alerts.alerts_for(data, self.TODAY, self.show("2026-12-01")) if a["key"].startswith("season")])
        self.assertFalse([a for a in alerts.alerts_for(data, self.TODAY, self.show("2026-10-04", episode=5)) if a["key"].startswith("season")])

    def test_daily_run_sends_once_and_respects_opt_out(self):
        user, cookie = self.owner()
        post("sync", body={"data": self.data(), "version": 0}, cookie=cookie)
        sent = []
        sender = lambda to, subject, lines: sent.append((to, subject, lines)) or True
        stats = alerts.run_daily(self.TODAY, title_lookup=self.show("2027-01-01"), sender=sender)
        self.assertEqual((stats["emails"], sent[0][0]), (1, "ligia@example.com"))
        alerts.run_daily(self.TODAY, title_lookup=self.show("2027-01-01"), sender=sender)
        self.assertEqual(len(sent), 1)  # same alert isn't sent twice
        post("account", "alerts", {"enabled": False}, cookie=cookie)
        self.assertEqual(alerts.run_daily(date(2026, 11, 2), title_lookup=self.show("2027-01-01"), sender=sender)["users"], 0)

    def test_cron_endpoint_needs_secret(self):
        with mock.patch.dict(os.environ, {"CRON_SECRET": "c"}):
            self.assertEqual(handle("cron", Request(headers={})).status, 401)
            self.assertEqual(handle("cron", Request(headers={"authorization": "Bearer c"})).status, 200)


if __name__ == "__main__":
    unittest.main()
