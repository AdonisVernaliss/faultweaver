from __future__ import annotations

from difflib import SequenceMatcher
from typing import Any

from faultweaver.analysis.normalization import NormalizedResponse


def compare_responses(first: NormalizedResponse, second: NormalizedResponse) -> dict[str, object]:
    first_paths = set(first.json_fields)
    second_paths = set(second.json_fields)
    first_structure = set(first.json_structure)
    second_structure = set(second.json_structure)
    shared_paths = sorted(first_paths & second_paths)
    changed_fields = [
        {"path": path, "a": first.json_fields[path], "b": second.json_fields[path]}
        for path in shared_paths
        if first.json_fields[path] != second.json_fields[path]
    ]
    header_names = sorted(set(first.selected_headers) | set(second.selected_headers))
    header_differences = [
        {
            "name": name,
            "a": first.selected_headers.get(name),
            "b": second.selected_headers.get(name),
        }
        for name in header_names
        if first.selected_headers.get(name) != second.selected_headers.get(name)
    ]

    return {
        "status": _pair(first.status, second.status),
        "content_type": _pair(first.content_type, second.content_type),
        "body_size": {
            "a": first.body_length,
            "b": second.body_length,
            "delta": second.body_length - first.body_length,
        },
        "normalized_similarity": round(
            SequenceMatcher(
                None, first.normalized_text, second.normalized_text, autojunk=False
            ).ratio(),
            4,
        ),
        "json": {
            "present_a": first.json_value is not None,
            "present_b": second.json_value is not None,
            "added_fields": sorted(second_paths - first_paths),
            "removed_fields": sorted(first_paths - second_paths),
            "changed_fields": changed_fields,
            "structural_similarity": round(_jaccard(first_structure, second_structure), 4),
        },
        "redirects": {
            "a": first.redirect_chain,
            "b": second.redirect_chain,
            "changed": first.redirect_chain != second.redirect_chain,
        },
        "header_differences": header_differences,
    }


def _pair(first: Any, second: Any) -> dict[str, Any]:
    return {"a": first, "b": second, "changed": first != second}


def _jaccard(first: set[str], second: set[str]) -> float:
    if not first and not second:
        return 1.0
    return len(first & second) / len(first | second)
