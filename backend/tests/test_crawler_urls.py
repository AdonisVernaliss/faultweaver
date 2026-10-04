import pytest

from faultweaver.assessments.urls import InvalidCrawlUrl, canonicalize_url, resolve_url


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("HTTPS://Example.COM:443", "https://example.com/"),
        ("http://example.com:80/a/../b/", "http://example.com/b/"),
        ("https://example.com/a#section", "https://example.com/a"),
        ("https://example.com/%7euser?q=%7e", "https://example.com/~user?q=~"),
        ("https://example.com/path?b=2&a=1", "https://example.com/path?b=2&a=1"),
        ("https://[2001:db8::1]:443/a", "https://[2001:db8::1]/a"),
        ("https://BÜCHER.example/", "https://xn--bcher-kva.example/"),
    ],
)
def test_canonicalize_url(value: str, expected: str) -> None:
    assert canonicalize_url(value) == expected


def test_canonicalize_preserves_meaningful_trailing_slash() -> None:
    assert canonicalize_url("https://example.test/docs") != canonicalize_url(
        "https://example.test/docs/"
    )


@pytest.mark.parametrize(
    "value",
    [
        "javascript:alert(1)",
        "file:///etc/passwd",
        "https://user:secret@example.test/",
        "https://example.test/%00",
    ],
)
def test_canonicalize_rejects_unsafe_urls(value: str) -> None:
    with pytest.raises(InvalidCrawlUrl):
        canonicalize_url(value)


def test_resolve_url_removes_fragment_and_resolves_relative_reference() -> None:
    assert resolve_url("https://example.test/docs/start", "../api/items#rows") == (
        "https://example.test/api/items"
    )
