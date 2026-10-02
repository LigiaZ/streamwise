<p align="center"><img src="img/streamwise-logo.png" width="260" alt="StreamWise"></p>

# StreamWise

[![tests](https://github.com/LigiaZ/streamwise/actions/workflows/tests.yml/badge.svg)](https://github.com/LigiaZ/streamwise/actions/workflows/tests.yml)

**Is your streaming worth what you pay for it?**

Log what you watch, and StreamWise works out what each subscription really costs per hour, which ones are poor value, and which ones to pause until there's something new to watch.

- 🔎 **Search any film or series.** Runtime and where it streams in your country are filled in for you (via TMDB).
- 💶 **Cost per hour, per service.** Prices for the Netherlands are pre-filled and editable for anywhere else.
- ⏸️ **Pause suggestions.** Nothing watched in 30 days? It tells you, and what pausing would save over a year.
- 📅 **What's coming.** For series, it shows when the next episode or season arrives.
- 📱 **Install it like an app.** On iPhone: Share → *Add to Home Screen*.
- 🔒 **Private by design.** Use it without an account and your log never leaves your browser.
- 🔄 **Or sign in to sync** (invite-only): your data follows you across devices, and a daily job emails you when a service sits unused or a show you follow gets a new season, with a nudge to resubscribe if you've paused that service.

## How it decides

| Verdict | Rule |
|---|---|
| **Great value** | under €1.00 per hour watched in the last 30 days |
| **Worth it** | under €2.50 per hour, cheaper than renting what you watched (≈ €4.99 per 2-hour film) |
| **Poor value** | above €2.50 per hour, so renting would have cost less |
| **Pause it** | nothing watched for 30+ days |
| **Too new to tell** | subscribed less than 14 days ago |

## Two modes, one app

| | Signed out (default) | Signed in |
|---|---|---|
| Where your data lives | `localStorage` in this browser only | your account in a Turso (libSQL) database, plus a local copy |
| Works across devices | no (export/import a backup) | yes |
| Email reminders | no | yes: pause suggestions and new seasons of shows you follow |
| Who can use it | anyone | invite-only: the first account needs `SETUP_SECRET`, then the owner creates invite links |

### Security notes

- Passwords: PBKDF2-HMAC-SHA256, 600,000 iterations, per-user salt. Wrong-email and wrong-password take the same time and give the same error.
- Sessions: HMAC-signed, `HttpOnly; Secure; SameSite=Lax` cookie, 30-day expiry.
- Brute force: 5 failed logins per email (20 per IP) locks sign-in for 15 minutes.
- CSRF: state-changing requests need a custom `X-StreamWise` header, which cross-site forms can't send.
- Sync uses optimistic versioning, so two devices can't silently overwrite each other.
- All secrets come from environment variables. None are in the repo.

## Architecture

```
index.html, app.js, app.css     mobile-first web app (installable, no build step)
api/*.py                        Vercel Python serverless functions
streamwise/
  catalog.py                    services, brand colours, prices per country
  tmdb.py                       TMDB client: search, runtime, providers, next episode
  report.py                     cost-per-hour, verdicts, savings, monthly history
  web.py                        endpoint logic shared by Vercel and the dev server
  db.py                         Turso over HTTP in production, SQLite locally (stdlib only)
  accounts.py                   passwords, sessions, invites, rate limiting, data sync
  alerts.py                     the daily job: pause + new-season emails via Resend
tests/                          unit tests (no network needed)
dev.py                          local server that mirrors Vercel
```

The browser sends the log to `/api/report` only to compute the numbers. Nothing is stored server-side. The TMDB token lives in a server environment variable and never reaches the browser.

## Run it locally

```bash
cp .env.example .env.local      # paste your TMDB "API Read Access Token"
python3 dev.py                  # http://localhost:3000
python3 -m unittest discover tests
```

Python 3.9+ and no dependencies. Without a TMDB token, everything except title search still works: use *Add it manually* or *Try it with sample data*.

Locally, sign-in uses a SQLite file in `.data/` (git-ignored). Open `/?setup` to create the first account.

## Deploy

Import the repo in Vercel (no build settings needed), then add these under **Settings → Environment Variables**:

| Variable | Needed for | Value |
|---|---|---|
| `TMDB_READ_TOKEN` | title search | TMDB "API Read Access Token" |
| `TURSO_DATABASE_URL` | sign-in + sync | `libsql://<db>-<org>.turso.io` |
| `TURSO_AUTH_TOKEN` | sign-in + sync | `turso db tokens create <db>` |
| `SESSION_SECRET` | sign-in | a long random string (`openssl rand -hex 32`) |
| `SETUP_SECRET` | creating the first account | any code you choose; open `/?setup` and enter it |
| `CRON_SECRET` | the daily job | a long random string (Vercel sends it to `/api/cron` automatically) |
| `RESEND_API_KEY` | reminder emails | from resend.com |
| `ALERTS_FROM` | optional | e.g. `StreamWise <hello@yourdomain>` once your domain is verified in Resend |
| `APP_URL` | optional | the app's URL, linked from emails |

Without the Turso variables the app runs in signed-out mode only.

## Credits

Title data and where-to-watch from [TMDB](https://www.themoviedb.org/) and JustWatch. This product uses the TMDB API but is not endorsed or certified by TMDB. Illustration by Lígia Zanchet.

MIT licensed. Built by [Lígia Zanchet](https://www.zanchet.eu).
