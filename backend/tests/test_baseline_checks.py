from faultweaver.assessments.checks import AnalysisContext, analyze_response


def test_html_checks_separate_observations_from_conservative_candidates() -> None:
    context = AnalysisContext(
        url="https://example.test/login",
        status=200,
        headers=[
            {"name": "content-type", "value": "text/html"},
            {"name": "server", "value": "ExampleServer/1.2.3"},
            {"name": "set-cookie", "value": "session=secret; Path=/"},
        ],
        body='<form action="http://example.test/session"><input type="password"></form>',
    )

    signals = analyze_response(context)

    by_check = {signal.check_id: signal for signal in signals}
    assert by_check["headers.content-security-policy"].classification == "Candidate"
    assert by_check["cookies.session-flags"].classification == "Candidate"
    assert by_check["disclosure.server-banner"].classification == "Informational"
    assert by_check["forms.insecure-transport"].suggested_severity == "Medium"
    assert all(signal.reason for signal in signals)


def test_hsts_is_not_expected_on_plain_http() -> None:
    signals = analyze_response(
        AnalysisContext(
            url="http://example.test/",
            status=200,
            headers=[{"name": "content-type", "value": "text/html"}],
            body="<html></html>",
        )
    )
    assert "headers.strict-transport-security" not in {item.check_id for item in signals}


def test_json_and_cache_checks_are_informational_and_do_not_copy_values() -> None:
    signals = analyze_response(
        AnalysisContext(
            url="https://example.test/account",
            status=200,
            headers=[{"name": "content-type", "value": "application/json"}],
            body='{"api_token":"do-not-copy","profile":{"password":"also-secret"}}',
        )
    )
    by_check = {item.check_id: item for item in signals}
    assert by_check["cache.auth-sensitive"].classification == "Informational"
    content = by_check["content.sensitive-field-names"]
    assert content.classification == "Informational"
    assert "api_token" in content.reason and "password" in content.reason
    assert "do-not-copy" not in content.reason and "also-secret" not in content.reason


def test_internal_path_disclosure_remains_informational() -> None:
    signals = analyze_response(
        AnalysisContext(
            url="https://example.test/error",
            status=500,
            headers=[{"name": "content-type", "value": "text/plain"}],
            body="Template failed at /srv/app/templates/account.html",
        )
    )
    signal = next(item for item in signals if item.check_id == "disclosure.internal-path")
    assert signal.classification == "Informational"
    assert "/srv/app/templates/account.html" not in signal.reason
