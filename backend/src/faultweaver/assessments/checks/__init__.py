from faultweaver.assessments.checks.content import check_content
from faultweaver.assessments.checks.cookies import check_cookies
from faultweaver.assessments.checks.disclosure import check_disclosure
from faultweaver.assessments.checks.forms import check_forms
from faultweaver.assessments.checks.headers import check_headers
from faultweaver.assessments.checks.types import AnalysisContext, AnalysisSignal


def analyze_response(context: AnalysisContext) -> list[AnalysisSignal]:
    return [
        *check_headers(context),
        *check_cookies(context),
        *check_content(context),
        *check_disclosure(context),
        *check_forms(context),
    ]


__all__ = ["AnalysisContext", "AnalysisSignal", "analyze_response"]
