from __future__ import annotations

import argparse
import json
import os
import re
from collections import deque
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from ipaddress import ip_address
from urllib.parse import parse_qs, urlsplit

USERS = {
    "alice": {"id": "alice", "name": "Alice North", "role": "member"},
    "bob": {"id": "bob", "name": "Bob South", "role": "member"},
    "admin": {"id": "admin", "name": "Demo Administrator", "role": "admin"},
}
TOKENS = {
    "demo-alice-token": "alice",
    "demo-bob-token": "bob",
    "demo-admin-token": "admin",
}
PASSWORDS = {
    "alice": "demo-alice",
    "bob": "demo-bob",
    "admin": "demo-admin",
}
INVOICES = {
    1001: {"id": 1001, "owner_id": "alice", "amount": 1250, "currency": "USD"},
    2002: {"id": 2002, "owner_id": "bob", "amount": 840, "currency": "EUR"},
}
AUDIT_2026 = {
    "year": 2026,
    "entries": [
        {"action": "invoice.export", "actor": "admin"},
        {"action": "tenant.review", "actor": "admin"},
    ],
}
_SAFE_AUTHORITY = re.compile(r"^[A-Za-z0-9.:[\]-]{1,255}$")


class DemoServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, server_address: tuple[str, int]) -> None:
        super().__init__(server_address, DemoHandler)
        self.request_log: deque[tuple[str, str]] = deque(maxlen=10_000)


class DemoHandler(BaseHTTPRequestHandler):
    server_version = "FaultweaverDemo/1.0"
    protocol_version = "HTTP/1.1"

    @property
    def demo_server(self) -> DemoServer:
        return self.server  # type: ignore[return-value]

    def do_GET(self) -> None:
        path = urlsplit(self.path).path
        self.demo_server.request_log.append(("GET", path))
        if path == "/":
            self._html(HTTPStatus.OK, _landing_page(), cookie="session=guest; Path=/")
        elif path == "/login":
            self._html(HTTPStatus.OK, _login_page())
        elif path == "/dashboard":
            self._dashboard()
        elif path == "/api/me":
            self._api_me()
        elif path == "/api/invoices":
            self._invoice_list()
        elif path.startswith("/api/invoices/"):
            self._invoice_detail(path)
        elif path == "/api/admin/audit/2026":
            self._admin_audit()
        elif path == "/api/public-config":
            self._json(
                HTTPStatus.OK,
                {"environment": "demo", "api_token": "synthetic-placeholder"},
            )
        elif path == "/debug/error":
            self._text(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                "Traceback (most recent call last):\n"
                '  File "/srv/app/demo.py", line 173, in demo_error\n'
                "RuntimeError: deterministic demonstration failure\n",
            )
        elif path == "/robots.txt":
            self._text(
                HTTPStatus.OK,
                "User-agent: *\nDisallow: /api/admin/\nSitemap: "
                f"http://{self._authority()}/sitemap.xml\n",
            )
        elif path == "/sitemap.xml":
            host = self._authority()
            urls = ("/", "/login", "/api/public-config", "/debug/error")
            body = (
                '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
                + "".join(f"<url><loc>http://{host}{item}</loc></url>" for item in urls)
            )
            self._send(HTTPStatus.OK, "application/xml; charset=utf-8", body.encode())
        elif path == "/assets/app.css":
            self._send(HTTPStatus.OK, "text/css; charset=utf-8", _STYLES.encode())
        elif path == "/health":
            self._json(HTTPStatus.OK, {"status": "ok", "service": "faultweaver-demo"})
        else:
            self._json(HTTPStatus.NOT_FOUND, {"detail": "not found"})

    def do_POST(self) -> None:
        path = urlsplit(self.path).path
        self.demo_server.request_log.append(("POST", path))
        if path != "/session":
            self._json(HTTPStatus.METHOD_NOT_ALLOWED, {"detail": "method not allowed"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length < 0 or length > 4096:
            self._json(
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"detail": "request too large"}
            )
            return
        form = parse_qs(self.rfile.read(length).decode("utf-8", errors="replace"))
        username = form.get("username", [""])[0]
        password = form.get("password", [""])[0]
        if PASSWORDS.get(username) != password:
            self._html(
                HTTPStatus.UNAUTHORIZED, _login_page(error="Invalid demo credentials")
            )
            return
        self._send(
            HTTPStatus.SEE_OTHER,
            "text/plain; charset=utf-8",
            b"Continue to dashboard",
            headers=[
                ("Location", "/dashboard"),
                ("Set-Cookie", f"session={username}; Path=/"),
            ],
        )

    def log_message(self, format: str, *args: object) -> None:
        return

    def _dashboard(self) -> None:
        user = self._identity()
        if user is None:
            self._html(
                HTTPStatus.UNAUTHORIZED, _login_page(error="Sign in to continue")
            )
            return
        invoices = [
            item for item in INVOICES.values() if item["owner_id"] == user["id"]
        ]
        rows = "".join(
            f'<li><a href="/api/invoices/{item["id"]}">Invoice {item["id"]}</a></li>'
            for item in invoices
        )
        self._html(
            HTTPStatus.OK,
            _page(
                "Tenant dashboard",
                f'<p class="eyebrow">Signed in as {user["name"]}</p>'
                f"<h1>{user['role'].title()} workspace</h1><ul>{rows}</ul>",
            ),
        )

    def _api_me(self) -> None:
        user = self._require_identity()
        if user is not None:
            self._json(HTTPStatus.OK, user)

    def _invoice_list(self) -> None:
        user = self._require_identity()
        if user is None:
            return
        self._json(
            HTTPStatus.OK,
            {
                "invoices": [
                    item for item in INVOICES.values() if item["owner_id"] == user["id"]
                ]
            },
        )

    def _invoice_detail(self, path: str) -> None:
        if self._require_identity() is None:
            return
        try:
            invoice_id = int(path.rsplit("/", 1)[-1])
        except ValueError:
            self._json(HTTPStatus.NOT_FOUND, {"detail": "invoice not found"})
            return
        invoice = INVOICES.get(invoice_id)
        if invoice is None:
            self._json(HTTPStatus.NOT_FOUND, {"detail": "invoice not found"})
            return
        # Deliberate defect: ownership is not checked after authentication.
        self._json(HTTPStatus.OK, invoice)

    def _admin_audit(self) -> None:
        if self._require_identity() is None:
            return
        # Deliberate defect: the authenticated identity's role is not checked.
        self._json(HTTPStatus.OK, AUDIT_2026)

    def _identity(self) -> dict[str, str] | None:
        authorization = self.headers.get("Authorization", "")
        if authorization.startswith("Bearer "):
            user_id = TOKENS.get(authorization.removeprefix("Bearer "))
            return USERS.get(user_id or "")
        cookies = {}
        for pair in self.headers.get("Cookie", "").split(";"):
            name, separator, value = pair.strip().partition("=")
            if separator:
                cookies[name] = value
        return USERS.get(cookies.get("session", ""))

    def _authority(self) -> str:
        value = self.headers.get("Host", "")
        return value if _SAFE_AUTHORITY.fullmatch(value) else "127.0.0.1:8088"

    def _require_identity(self) -> dict[str, str] | None:
        identity = self._identity()
        if identity is None:
            self._json(HTTPStatus.UNAUTHORIZED, {"detail": "authentication required"})
        return identity

    def _html(
        self, status: HTTPStatus, body: str, *, cookie: str | None = None
    ) -> None:
        headers = [("Set-Cookie", cookie)] if cookie else None
        self._send(status, "text/html; charset=utf-8", body.encode(), headers=headers)

    def _json(self, status: HTTPStatus, value: object) -> None:
        body = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
        self._send(status, "application/json; charset=utf-8", body)

    def _text(self, status: HTTPStatus, body: str) -> None:
        self._send(status, "text/plain; charset=utf-8", body.encode())

    def _send(
        self,
        status: HTTPStatus,
        content_type: str,
        body: bytes,
        *,
        headers: list[tuple[str, str]] | None = None,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Faultweaver-Demo", "deliberately-vulnerable")
        for name, value in headers or []:
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)


def _landing_page() -> str:
    content = """
    <p class="eyebrow">Local training tenant</p>
    <h1>Northstar Billing</h1>
    <p class="lede">A deterministic, deliberately vulnerable SaaS for Faultweaver validation.</p>
    <div class="warning">Never expose this service to an untrusted network.</div>
    <section class="grid">
      <article><h2>Explore</h2>
        <a href="/login">Sign in</a><a href="/dashboard">Dashboard</a>
      </article>
      <article><h2>Tenant API</h2>
        <a href="/api/me">Current identity</a><a href="/api/invoices">Invoices</a>
        <a href="/api/invoices/1001">Invoice 1001</a>
      </article>
      <article><h2>Operations</h2>
        <a href="/api/admin/audit/2026">Audit 2026</a>
        <a href="/api/public-config">Public config</a>
        <a href="/debug/error">Debug failure</a>
      </article>
    </section>
    <form method="post" action="/session">
      <label>Username <input name="username" autocomplete="username"></label>
      <label>Password
        <input name="password" type="password" autocomplete="current-password">
      </label>
      <button type="submit">Open demo tenant</button>
    </form>
    <a class="external" href="http://127.0.0.1:9/outside">Out-of-scope service</a>
    """
    return _page("Northstar Billing", content)


def _login_page(*, error: str | None = None) -> str:
    error_markup = f'<p class="error">{error}</p>' if error else ""
    return _page(
        "Demo sign in",
        f"""
        <p class="eyebrow">Public synthetic identities</p>
        <h1>Sign in to a demo tenant</h1>{error_markup}
        <p>Alice: <code>alice / demo-alice</code></p>
        <p>Bob: <code>bob / demo-bob</code></p>
        <p>Administrator: <code>admin / demo-admin</code></p>
        <form method="post" action="/session">
          <label>Username <input name="username" autocomplete="username"></label>
          <label>Password <input name="password" type="password"></label>
          <button type="submit">Sign in</button>
        </form>
        """,
    )


def _page(title: str, content: str) -> str:
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>{title}</title><link rel="stylesheet" href="/assets/app.css"></head>
<body><main>{content}</main>
<footer>Faultweaver local demo · intentionally insecure</footer></body></html>"""


_STYLES = """
:root{font-family:Inter,ui-sans-serif,system-ui;color:#15231f;background:#e8eee9}
*{box-sizing:border-box}
body{margin:0}
main{width:min(72rem,calc(100% - 2rem));margin:2rem auto;padding:clamp(1.2rem,4vw,4rem)}
main{background:#f8faf7;border:1px solid #b8c3ba;border-radius:1.5rem}
main{box-shadow:0 2rem 5rem #253a2d1c}
.eyebrow{text-transform:uppercase;letter-spacing:.16em;font-size:.75rem;color:#536b5e}
.lede{font-size:1.2rem;max-width:48rem}
.warning,.error{padding:1rem;border-left:4px solid #b44a2a;background:#f7e8df}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(13rem,1fr));gap:1rem;margin:2rem 0}
.grid article,form{padding:1.2rem;background:#edf2ed;border:1px solid #c8d2ca;border-radius:1rem}
a{display:block;color:#285b48;margin:.55rem 0}
label{display:block;margin:.8rem 0}
input{width:100%;padding:.7rem;border:1px solid #9cac9f;border-radius:.45rem}
button{padding:.75rem 1rem;border:0;border-radius:999px;background:#285b48;color:white}
footer{padding:0 1rem 2rem;text-align:center;color:#64756b}
.external{margin-top:1rem}
@media(max-width:36rem){main{margin:1rem auto;padding:1rem;border-radius:1rem}}
"""


def validate_bind_host(host: str, *, allow_non_loopback: bool) -> None:
    if allow_non_loopback:
        return
    if host == "localhost":
        return
    try:
        loopback = ip_address(host).is_loopback
    except ValueError as error:
        raise ValueError("Demo host must be a loopback IP address") from error
    if not loopback:
        raise ValueError("Demo host must be loopback unless explicitly overridden")


def create_server(host: str, port: int) -> DemoServer:
    return DemoServer((host, port))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local Faultweaver demo SaaS")
    parser.add_argument(
        "--host", default=os.getenv("FAULTWEAVER_DEMO_HOST", "127.0.0.1")
    )
    parser.add_argument(
        "--port", type=int, default=int(os.getenv("FAULTWEAVER_DEMO_PORT", "8088"))
    )
    args = parser.parse_args()
    allow_non_loopback = os.getenv("FAULTWEAVER_DEMO_ALLOW_NON_LOOPBACK") == "1"
    try:
        validate_bind_host(args.host, allow_non_loopback=allow_non_loopback)
    except ValueError as error:
        parser.error(str(error))
    server = create_server(args.host, args.port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
