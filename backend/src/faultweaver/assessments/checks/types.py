from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AnalysisContext:
    url: str
    status: int
    headers: list[dict[str, str]]
    body: str

    @property
    def header_map(self) -> dict[str, list[str]]:
        result: dict[str, list[str]] = {}
        for header in self.headers:
            result.setdefault(header["name"].lower(), []).append(header["value"])
        return result


@dataclass(frozen=True, slots=True)
class AnalysisSignal:
    check_id: str
    title: str
    description: str
    reason: str
    confidence: str
    classification: str
    suggested_severity: str
