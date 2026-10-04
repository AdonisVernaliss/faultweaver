from urllib.parse import urlsplit

from faultweaver.assessments.checks.types import AnalysisContext, AnalysisSignal


def check_headers(context: AnalysisContext) -> list[AnalysisSignal]:
    headers = context.header_map
    content_type = ";".join(headers.get("content-type", [])).lower()
    if "text/html" not in content_type:
        return []
    signals: list[AnalysisSignal] = []
    expected = [
        (
            "content-security-policy",
            "headers.content-security-policy",
            "Content Security Policy is absent",
            "Candidate",
            "Low",
        ),
        (
            "x-content-type-options",
            "headers.x-content-type-options",
            "MIME sniffing protection is absent",
            "Informational",
            "Informational",
        ),
    ]
    if urlsplit(context.url).scheme == "https":
        expected.append(
            (
                "strict-transport-security",
                "headers.strict-transport-security",
                "HSTS is absent on an HTTPS response",
                "Informational",
                "Informational",
            )
        )
    for name, check_id, title, classification, severity in expected:
        if name not in headers:
            signals.append(
                AnalysisSignal(
                    check_id=check_id,
                    title=title,
                    description="A context-aware response header check found a missing defense.",
                    reason=f"The HTML response did not include {name}.",
                    confidence="Medium",
                    classification=classification,
                    suggested_severity=severity,
                )
            )
    return signals
