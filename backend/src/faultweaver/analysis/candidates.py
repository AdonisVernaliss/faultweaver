import re
from urllib.parse import parse_qsl

from faultweaver.analysis.models import Candidate, ResponseComparison
from faultweaver.http_traffic.models import HttpExchange

_OBJECT_SEGMENT = re.compile(r"^(?:\d+|[0-9a-f]{24}|[0-9a-f]{8}-[0-9a-f-]{27,})$", re.IGNORECASE)


def authorization_candidate(
    *,
    original: HttpExchange,
    comparison: ResponseComparison,
    replay_a: HttpExchange,
    replay_b: HttpExchange,
) -> Candidate | None:
    result = comparison.result["diff"]
    json_diff = result["json"]
    if comparison.identity_a_id == comparison.identity_b_id:
        return None
    if not _has_object_reference(original):
        return None
    if replay_a.response_status is None or replay_b.response_status is None:
        return None
    if not (200 <= replay_a.response_status < 300 and 200 <= replay_b.response_status < 300):
        return None
    if replay_a.response_status != replay_b.response_status:
        return None
    if not replay_a.response_body or not replay_b.response_body:
        return None
    if result["content_type"]["changed"]:
        return None
    if result["normalized_similarity"] < 0.95:
        return None
    if json_diff["structural_similarity"] < 0.95:
        return None

    return Candidate(
        engagement_id=original.engagement_id,
        comparison_id=comparison.id,
        original_exchange_id=original.id,
        title="Potential authorization inconsistency",
        category="authorization",
        confidence="medium",
        status="candidate",
        reasoning=[
            (
                "Two distinct identity contexts received successful responses "
                "for the same object reference."
            ),
            "Response status and content type matched.",
            (
                "Normalized response similarity was "
                f"{result['normalized_similarity']:.2f}; structural similarity was "
                f"{json_diff['structural_similarity']:.2f}."
            ),
            "This is a conservative candidate and requires manual authorization review.",
        ],
        supporting_replays=[replay_a, replay_b],
    )


def _has_object_reference(exchange: HttpExchange) -> bool:
    if any(_OBJECT_SEGMENT.fullmatch(segment) for segment in exchange.path.split("/") if segment):
        return True
    return any(
        (key.lower() == "id" or key.lower().endswith("_id")) and bool(value)
        for key, value in parse_qsl(exchange.query, keep_blank_values=True)
    )
