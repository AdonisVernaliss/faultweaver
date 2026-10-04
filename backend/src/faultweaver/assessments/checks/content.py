from __future__ import annotations

import json
import re
from urllib.parse import urlsplit

from faultweaver.assessments.checks.types import AnalysisContext, AnalysisSignal
from faultweaver.redaction import is_sensitive_key

_INTERNAL_PATH = re.compile(r"(?i)(?:/var/www|/srv/app|/home/[\w.-]+|[a-z]:\\[^\r\n]{3,})")
_AUTH_PATH = re.compile(r"(?i)/(?:login|session|account|profile|admin|auth)(?:/|$)")


def check_content(context: AnalysisContext) -> list[AnalysisSignal]:
    signals: list[AnalysisSignal] = []
    headers = context.header_map
    content_type = ";".join(headers.get("content-type", [])).lower()
    cache_control = ";".join(headers.get("cache-control", [])).lower()
    if (_AUTH_PATH.search(urlsplit(context.url).path) or "set-cookie" in headers) and (
        "no-store" not in cache_control
    ):
        signals.append(
            AnalysisSignal(
                check_id="cache.auth-sensitive",
                title="Cache policy merits review",
                description=(
                    "An authentication-sensitive response did not explicitly prohibit storage."
                ),
                reason="The response context appears sensitive and Cache-Control lacks no-store.",
                confidence="Low",
                classification="Informational",
                suggested_severity="Informational",
            )
        )
    if _INTERNAL_PATH.search(context.body):
        signals.append(
            AnalysisSignal(
                check_id="disclosure.internal-path",
                title="Internal filesystem path observed",
                description="Response text contained a path-like implementation detail.",
                reason="A local filesystem path pattern appeared in the captured response.",
                confidence="Medium",
                classification="Informational",
                suggested_severity="Informational",
            )
        )
    if "json" in content_type:
        names = _sensitive_names(context.body)
        if names:
            signals.append(
                AnalysisSignal(
                    check_id="content.sensitive-field-names",
                    title="Sensitive-looking response fields observed",
                    description=(
                        "Field names can guide manual review; values were not copied into "
                        "reasoning."
                    ),
                    reason=f"Sensitive-looking field names: {', '.join(names[:8])}.",
                    confidence="Low",
                    classification="Informational",
                    suggested_severity="Informational",
                )
            )
    return signals


def _sensitive_names(body: str) -> list[str]:
    try:
        value = json.loads(body)
    except (json.JSONDecodeError, TypeError):
        return []
    names: set[str] = set()
    pending: list[object] = [value]
    visited = 0
    while pending and visited < 1_000:
        item = pending.pop()
        visited += 1
        if isinstance(item, dict):
            for key, child in list(item.items())[:100]:
                if is_sensitive_key(str(key)):
                    names.add(str(key))
                pending.append(child)
        elif isinstance(item, list):
            pending.extend(item[:100])
    return sorted(names)
