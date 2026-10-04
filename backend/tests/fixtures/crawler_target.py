"""Deterministic local-only target for assessment integration and browser QA.

This is test infrastructure, not Faultweaver's deliberately vulnerable demo SaaS.
"""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class TargetHandler(BaseHTTPRequestHandler):
    server_version = "FaultweaverSynthetic/1.0"

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        path = self.path.split("?", 1)[0]
        if path == "/":
            self._send(
                "text/html",
                """<!doctype html><html><body>
                <a href="/catalog">Catalog</a>
                <a href="/api/status">Status API</a>
                <a href="/redirect-local">Local redirect</a>
                <a href="http://127.0.0.1:9/external">External service</a>
                <script src="/assets/app.js"></script>
                <img src="/assets/logo.png" alt="Synthetic logo">
                <form method="post" action="/login">
                  <input name="username"><input name="password" type="password">
                  <input name="csrf" type="hidden" value="synthetic">
                </form></body></html>""",
                headers=[("Set-Cookie", "session=synthetic; Path=/")],
            )
        elif path == "/catalog":
            self._send(
                "text/html",
                '<!doctype html><html><body><a href="/catalog?page=2">Next</a></body></html>',
            )
        elif path == "/api/status":
            self._send(
                "application/json",
                json.dumps({"status": "ok", "api_token": "synthetic-placeholder"}),
            )
        elif path == "/redirect-local":
            self.send_response(302)
            self.send_header("Location", "/catalog")
            self.end_headers()
        elif path == "/robots.txt":
            host = self.headers.get("Host", "127.0.0.1")
            self._send(
                "text/plain",
                f"User-agent: *\nDisallow: /private\nSitemap: http://{host}/sitemap.xml\n",
            )
        elif path == "/sitemap.xml":
            host = self.headers.get("Host", "127.0.0.1")
            self._send(
                "application/xml",
                '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
                f"<url><loc>http://{host}/catalog</loc></url>"
                f"<url><loc>http://{host}/api/status</loc></url>"
                "</urlset>",
            )
        else:
            self._send("text/plain", "Not found", status=404)

    def do_POST(self) -> None:  # noqa: N802 - records accidental form submission as failure
        self._send("application/json", '{"error":"forms must not be submitted"}', status=405)

    def log_message(self, format: str, *args: object) -> None:
        print(f"synthetic-target {self.address_string()} {format % args}", flush=True)

    def _send(
        self,
        content_type: str,
        body: str,
        *,
        status: int = 200,
        headers: list[tuple[str, str]] | None = None,
    ) -> None:
        encoded = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        for name, value in headers or []:
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(encoded)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18080)
    args = parser.parse_args()
    ThreadingHTTPServer((args.host, args.port), TargetHandler).serve_forever()


if __name__ == "__main__":
    main()
