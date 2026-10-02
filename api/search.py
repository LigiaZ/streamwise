import os
import sys
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from streamwise.web import serve  # noqa: E402


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        serve(self, "search")

    def do_POST(self):
        serve(self, "search")
