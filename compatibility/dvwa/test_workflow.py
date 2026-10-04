from __future__ import annotations

import os
from html.parser import HTMLParser
from urllib.parse import urlsplit

import httpx
import pytest


class _TokenParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.token: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "input" and values.get("name") == "user_token":
            self.token = values.get("value")


def _target_url() -> str:
    target = os.environ.get("FAULTWEAVER_DVWA_URL")
    if not target:
        pytest.skip("set FAULTWEAVER_DVWA_URL to run this external-lab test")
    parsed = urlsplit(target)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"}:
        pytest.fail("DVWA compatibility tests require an HTTP loopback target")
    return target.rstrip("/")


def _credential(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        pytest.fail(f"{name} must be supplied by the compatibility runner")
    return value


def test_expected_dvwa_application_and_synthetic_login() -> None:
    base_url = _target_url()
    with httpx.Client(base_url=base_url, follow_redirects=False, timeout=15) as target:
        setup = target.get("/setup.php")
        setup.raise_for_status()
        assert "Damn Vulnerable Web Application (DVWA)" in setup.text
        assert "Database Setup" in setup.text

        login_page = target.get("/login.php")
        login_page.raise_for_status()
        parser = _TokenParser()
        parser.feed(login_page.text)
        assert parser.token
        login = target.post(
            "/login.php",
            data={
                "username": _credential("FAULTWEAVER_DVWA_USERNAME"),
                "password": _credential("FAULTWEAVER_DVWA_PASSWORD"),
                "Login": "Login",
                "user_token": parser.token,
            },
        )
        assert login.status_code == 302
        assert login.headers["location"].endswith("index.php")
        assert target.cookies.get("PHPSESSID")
