from __future__ import annotations

import os
from html.parser import HTMLParser
from urllib.parse import urlsplit

import httpx


class _TokenParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.token: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "input":
            return
        values = dict(attrs)
        if values.get("name") == "user_token" and values.get("value"):
            self.token = values["value"]


def main() -> None:
    base_url = os.environ["FAULTWEAVER_DVWA_URL"].rstrip("/")
    parsed = urlsplit(base_url)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"}:
        raise SystemExit("DVWA preparation requires an HTTP loopback target")

    with httpx.Client(base_url=base_url, follow_redirects=False, timeout=15) as client:
        setup = client.get("/setup.php")
        setup.raise_for_status()
        parser = _TokenParser()
        parser.feed(setup.text)
        if not parser.token:
            raise SystemExit("DVWA setup token was not present")
        created = client.post(
            "/setup.php",
            data={"create_db": "Create / Reset Database", "user_token": parser.token},
        )
        if created.status_code not in {200, 302}:
            created.raise_for_status()

    print("DVWA database initialized")


if __name__ == "__main__":
    main()
