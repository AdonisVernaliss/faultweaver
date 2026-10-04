from urllib.parse import urljoin, urlsplit

from faultweaver.assessments.checks.types import AnalysisContext, AnalysisSignal


def check_forms(context: AnalysisContext) -> list[AnalysisSignal]:
    lowered = context.body.lower()
    if (
        "<form" not in lowered
        or 'type="password"' not in lowered
        and "type='password'" not in lowered
    ):
        return []
    action = context.url
    marker = "action="
    position = lowered.find(marker)
    if position >= 0:
        remainder = context.body[position + len(marker) :].lstrip()
        if remainder and remainder[0] in {'"', "'"}:
            quote = remainder[0]
            action = urljoin(context.url, remainder[1:].split(quote, 1)[0])
    if urlsplit(action).scheme != "http":
        return []
    return [
        AnalysisSignal(
            check_id="forms.insecure-transport",
            title="Password form uses unencrypted transport",
            description=(
                "The form metadata indicates that credentials could be sent over plain HTTP."
            ),
            reason=f"A password field submits to {urlsplit(action).scheme.upper()}.",
            confidence="High",
            classification="Candidate",
            suggested_severity="Medium",
        )
    ]
