from faultweaver.assessments.discovery import discover_html, discover_sitemap


def test_html_discovery_classifies_links_resources_and_forms_without_submitting() -> None:
    document = """
    <html><head><link rel="stylesheet" href="/app.css"><script src="/app.js"></script></head>
    <body>
      <a href="/users?page=2#list">Users</a><img src="/logo.png">
      <iframe src="/frame"></iframe><source src="/movie.mp4">
      <form action="/session" method="post" enctype="application/x-www-form-urlencoded">
        <input name="email" type="email"><input name="csrf" type="hidden" value="secret">
      </form>
    </body></html>
    """

    result = discover_html(document, "https://example.test/start")

    assert {(item.kind, item.url) for item in result.links} == {
        ("navigation", "https://example.test/users?page=2"),
        ("stylesheet", "https://example.test/app.css"),
        ("script", "https://example.test/app.js"),
        ("image", "https://example.test/logo.png"),
        ("iframe", "https://example.test/frame"),
        ("media", "https://example.test/movie.mp4"),
        ("form", "https://example.test/session"),
    }
    assert result.forms[0].method == "POST"
    assert [(field.name, field.input_type) for field in result.forms[0].fields] == [
        ("email", "email"),
        ("csrf", "hidden"),
    ]
    assert result.forms[0].fields[1].has_value is True


def test_sitemap_is_bounded_and_ignores_non_http_locations() -> None:
    xml = """<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <url><loc>https://example.test/a</loc></url>
      <url><loc>javascript:alert(1)</loc></url>
      <url><loc>https://example.test/b</loc></url>
    </urlset>"""
    assert discover_sitemap(xml, limit=1) == ["https://example.test/a"]
