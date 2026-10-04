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
