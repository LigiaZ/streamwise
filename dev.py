"""Local development server: static files + the same /api endpoints Vercel runs.

    python3 dev.py            # http://localhost:3000
"""

import os
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from streamwise.web import ENDPOINTS, serve  # noqa: E402


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        key, sep, value = line.partition("=")
        if sep and not key.strip().startswith("#") and value.strip():
            os.environ.setdefault(key.strip(), value.strip())


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def _api(self):
        path = self.path.split("?")[0]
        name = path[len("/api/"):].strip("/") if path.startswith("/api/") else ""
        if name in ENDPOINTS:
            serve(self, name)
            return True
        return False

    def do_GET(self):
        if not self._api():
            super().do_GET()

    def do_POST(self):
        if not self._api():
            self.send_error(404)


if __name__ == "__main__":
    load_env(ROOT / ".env.local")
    port = int(os.environ.get("PORT", 3000))
    print(f"StreamWise on http://localhost:{port}  (TMDB {'on' if os.environ.get('TMDB_READ_TOKEN') else 'off'})")
    ThreadingHTTPServer(("", port), Handler).serve_forever()
