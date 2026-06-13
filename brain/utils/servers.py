# utils/servers.py
# Small HTTP servers for memory/goals endpoints serving static SPAs

from __future__ import annotations
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from typing import Callable, Any
import json
import threading

def start_memory_server(dist_dir: str, port: int, memory_health_provider: Callable[[], dict]):
    """Serve static SPA from dist_dir and expose GET /memory"""
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=dist_dir, **kwargs)

        def do_GET(self):
            if self.path == "/memory":
                try:
                    data = memory_health_provider() or {}
                    body = json.dumps(data).encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                except Exception as e:
                    msg = json.dumps({"error": str(e)}).encode("utf-8")
                    self.send_response(500)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(msg)))
                    self.end_headers()
                    self.wfile.write(msg)
                return
            return super().do_GET()

    httpd = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    t = threading.Thread(target=httpd.serve_forever, name=f"memory-ui:{port}", daemon=True)
    t.start()
    url = f"http://127.0.0.1:{port}/"
    return t, httpd, url

def start_goals_server(dist_dir: str, port: int, goals_provider: Callable[[], Any]):
    """Serve static SPA from dist_dir and expose GET /goals and /goals.json"""
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=dist_dir, **kwargs)

        def _send_json(self, obj, code=200):
            body = json.dumps(obj).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = self.path.split("?", 1)[0]
            if path in ("/goals", "/goals.json"):
                try:
                    data = goals_provider() or []
                    self._send_json(data, 200)
                except Exception as e:
                    self._send_json({"error": str(e)}, 500)
                return
            return super().do_GET()

    httpd = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    t = threading.Thread(target=httpd.serve_forever, name=f"goals-ui:{port}", daemon=True)
    t.start()
    url = f"http://127.0.0.1:{port}/"
    return t, httpd, url
