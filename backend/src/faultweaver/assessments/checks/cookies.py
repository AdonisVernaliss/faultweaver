from urllib.parse import urlsplit

from faultweaver.assessments.checks.types import AnalysisContext, AnalysisSignal


def check_cookies(context: AnalysisContext) -> list[AnalysisSignal]:
    insecure: list[str] = []
    is_https = urlsplit(context.url).scheme == "https"
    for value in context.header_map.get("set-cookie", []):
        name = value.split("=", 1)[0].strip()
        lowered = value.lower()
        session_like = any(token in name.lower() for token in ("session", "auth", "sid"))
        if session_like and "httponly" not in lowered:
            insecure.append(f"{name} lacks HttpOnly")
        if is_https and "secure" not in lowered:
            insecure.append(f"{name} lacks Secure")
    if not insecure:
        return []
    return [
        AnalysisSignal(
            check_id="cookies.session-flags",
            title="Cookie security attributes may be incomplete",
            description="Session-like cookies should use context-appropriate security attributes.",
            reason="; ".join(insecure),
            confidence="Medium",
            classification="Candidate",
            suggested_severity="Low",
        )
    ]
