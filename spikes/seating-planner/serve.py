"""Serve only this synthetic static experiment on an ephemeral loopback origin."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path

ROOT = Path(__file__).parent
FILES = {"/": ("index.html", "text/html; charset=utf-8"), "/style.css": ("style.css", "text/css"),
         "/app.mjs": ("app.mjs", "text/javascript"), "/solver.mjs": ("solver.mjs", "text/javascript")}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_GET(self):
        if self.headers.get("Host") != f"127.0.0.1:{self.server.server_port}":
            self.send_error(421)
            return
        if self.path not in FILES:
            self.send_error(404)
            return
        name, content_type = FILES[self.path]
        payload = (ROOT / name).read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'none'; script-src 'self'; style-src 'self'; img-src data:; connect-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'")
        self.end_headers()
        self.wfile.write(payload)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8766)
    args = parser.parse_args()
    with ThreadingHTTPServer(("127.0.0.1", args.port), Handler) as server:
        print(json.dumps({"url": f"http://127.0.0.1:{server.server_port}/"}), flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
