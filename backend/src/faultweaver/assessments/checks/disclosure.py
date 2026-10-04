import re

from faultweaver.assessments.checks.types import AnalysisContext, AnalysisSignal

_VERSION = re.compile(r"\b\d+(?:\.\d+)+\b")
_STACK_TRACE = re.compile(
    r"(?i)(traceback \(most recent call|stack trace|exception at|/app/[^\s:]+:\d+)"
)


def check_disclosure(context: AnalysisContext) -> list[AnalysisSignal]:
    signals: list[AnalysisSignal] = []
    for name in ("server", "x-powered-by"):
        value = next(iter(context.header_map.get(name, [])), "")
        if value and _VERSION.search(value):
            signals.append(
                AnalysisSignal(
                    check_id="disclosure.server-banner",
                    title="Version-bearing server banner observed",
                    description="Technology banners can help an operator focus manual validation.",
                    reason=f"The {name} header included a version-like value.",
                    confidence="High",
                    classification="Informational",
                    suggested_severity="Informational",
                )
            )
            break
    if context.status >= 500 and _STACK_TRACE.search(context.body):
        signals.append(
            AnalysisSignal(
                check_id="disclosure.verbose-error",
                title="Verbose application error observed",
                description=(
                    "A naturally occurring error response exposed stack-like "
                    "implementation detail."
                ),
                reason="The response was a server error and contained a stack-trace marker.",
                confidence="High",
                classification="Candidate",
                suggested_severity="Medium",
            )
        )
    return signals
