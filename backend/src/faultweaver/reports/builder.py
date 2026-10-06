"""Build the single export representation; never read live HTTP/Identity payloads."""

import json
import re
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from faultweaver import __version__
from faultweaver.assessments.models import AssessmentRun
from faultweaver.attack_chains.models import (
    AttackChain,
    AttackChainStep,
    attack_chain_evidence,
    attack_chain_step_evidence,
)
from faultweaver.engagements.models import Engagement
from faultweaver.findings.models import Evidence, Finding, Retest, retest_evidence
from faultweaver.redaction import (
    REDACTED,
    is_sensitive_key,
    redact_body,
    redact_mapping,
    redact_url,
)
from faultweaver.reports.models import Report
from faultweaver.reports.schemas import ReportContent, ReportDocument
from faultweaver.scope.models import ScopeRule

SEVERITIES = ("Critical", "High", "Medium", "Low", "Informational")
RETEST_STATUSES = ("Still Vulnerable", "Partially Fixed", "Fixed", "Unable to Retest")
_URL = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
MAX_DOCUMENT_BYTES = 10_000_000


def safe_text(value: str) -> str:
    value = _URL.sub(lambda match: redact_url(match.group()), value)
    if value.startswith("/") and "?" in value:
        value = redact_url(value)
    return redact_body(value) or ""


def safe_data(value):
    """Defense-in-depth at the report boundary, after ordinary domain redaction."""
    if isinstance(value, dict):
        value = redact_mapping(value)
        if (
            isinstance(value.get("name"), str)
            and "value" in value
            and is_sensitive_key(value["name"])
        ):
            value = {**value, "value": REDACTED}
        return {key: safe_data(item) for key, item in value.items()}
    if isinstance(value, list):
        return [safe_data(item) for item in value]
    return safe_text(value) if isinstance(value, str) else value


def canonical_json(document: ReportDocument) -> str:
    return (
        json.dumps(document.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, indent=2)
        + "\n"
    )


def _selected(session, model, engagement_id, ids):
    statement = select(model).where(model.engagement_id == engagement_id)
    if ids is not None:
        statement = statement.where(model.id.in_(ids))
    records = list(session.scalars(statement.order_by(model.sequence_number).limit(1001)))
    if len(records) > 1000:
        raise HTTPException(422, "Select at most 1000 report records")
    if ids is not None and {item.id for item in records} != set(ids):
        raise HTTPException(422, "Every selected record must exist in this Engagement")
    return records


def _excerpt(label, text, limit=3000):
    safe = safe_text(str(text))
    return {
        "label": label,
        "text": safe[:limit] + ("\n[Excerpt truncated]" if len(safe) > limit else ""),
        "truncated": len(safe) > limit,
    }


def evidence_document(item: Evidence) -> dict:
    # Only the immutable snapshot is used. No fallback to its mutable source.
    snapshot = safe_data(item.snapshot)
    excerpts = []
    for name in ("exchange", "replay_a", "replay_b"):
        exchange = snapshot.get(name)
        if not isinstance(exchange, dict):
            continue
        excerpts.append(
            _excerpt(f"{name}: request", f"{exchange.get('method', '')} {exchange.get('url', '')}")
        )
        for direction in ("request", "response"):
            # Authentication/session headers are deliberately not report material.
            headers = [
                f"{h.get('name', '')}: {h.get('value', '')}"
                for h in exchange.get(direction + "_headers", [])
                if h.get("name", "").lower() in {"content-type", "cache-control", "location"}
            ]
            body = exchange.get(direction + "_body")
            if direction == "response":
                headers.insert(0, f"HTTP status: {exchange.get('response_status', 'unavailable')}")
            if headers:
                excerpts.append(_excerpt(f"{name}: {direction} metadata", "\n".join(headers)))
            if body:
                excerpts.append(_excerpt(f"{name}: {direction} body", body))
    if "result" in snapshot:
        excerpts.append(
            _excerpt(
                "Comparison summary",
                json.dumps(snapshot["result"], ensure_ascii=False, sort_keys=True, indent=2),
            )
        )
    if "text" in snapshot:
        excerpts.append(_excerpt("Preserved text", snapshot["text"]))
    return {
        "display_id": item.display_id,
        "title": item.title,
        "evidence_type": item.evidence_type,
        "captured_at": item.captured_at,
        "excerpts": excerpts,
    }


def build_document(
    session: Session,
    report: Report,
    *,
    revision: int | None = None,
    generated_at: datetime | None = None,
    require_scope: bool = True,
) -> ReportDocument:
    engagement = session.get(Engagement, report.engagement_id)
    if engagement is None:
        raise HTTPException(404, "Engagement not found")
    content = ReportContent.model_validate({**report.content, "title": report.title})
    warnings = []
    scopes = list(
        session.scalars(
            select(ScopeRule)
            .where(ScopeRule.engagement_id == engagement.id)
            .order_by(ScopeRule.scheme, ScopeRule.hostname, ScopeRule.port, ScopeRule.path_prefix)
        )
    )
    if not any(scope.active for scope in scopes):
        if require_scope:
            raise HTTPException(422, "Add an active authorized scope before generating this report")
        warnings.append("No active authorized scope is configured.")
    if engagement.status not in {"reporting", "complete"}:
        warnings.append(
            "Engagement is not in Reporting or Complete state; verify assessment readiness."
        )
    for field in ("executive_summary", "methodology", "limitations", "conclusion"):
        if not getattr(content, field).strip():
            warnings.append(f"Report: missing {field.replace('_', ' ')}.")
    findings = _selected(session, Finding, engagement.id, content.finding_ids)
    findings = [
        f
        for f in findings
        if (content.include_archived or not f.archived_at)
        and (content.include_informational or f.severity != "Informational")
    ]
    findings.sort(key=lambda item: (SEVERITIES.index(item.severity), item.sequence_number))
    by_id = {f.id: f for f in findings}
    chains = _selected(session, AttackChain, engagement.id, content.attack_chain_ids)
    chains = [
        c
        for c in chains
        if (content.include_archived or not c.archived_at)
        and (c.status != "Draft" or content.include_draft_chains)
    ]
    retests = list(
        session.scalars(
            select(Retest)
            .where(Retest.engagement_id == engagement.id, Retest.finding_id.in_(by_id))
            .order_by(Retest.tested_at, Retest.sequence_number)
        )
    )
    latest = {item.finding_id: item for item in retests}
    retest_links = list(
        session.execute(
            select(retest_evidence).where(retest_evidence.c.retest_id.in_([r.id for r in retests]))
        )
    )
    # A snapshot can support both the initial Finding and later Retests. Retest
    # links must never remove it from the Finding's preserved evidence history.
    finding_evidence = list(
        session.scalars(
            select(Evidence)
            .where(
                Evidence.engagement_id == engagement.id,
                Evidence.finding_id.in_(by_id),
            )
            .order_by(Evidence.sequence_number)
        )
    )
    evidence_ids = {e.id for e in finding_evidence}
    shown_retests = retests if content.include_retest_history else list(latest.values())
    evidence_ids.update(
        row.evidence_id for row in retest_links if row.retest_id in {r.id for r in shown_retests}
    )
    document_chains = []
    for chain in chains:
        steps = list(
            session.scalars(
                select(AttackChainStep)
                .where(AttackChainStep.attack_chain_id == chain.id)
                .order_by(AttackChainStep.position)
            )
        )
        if any(step.finding_id and step.finding_id not in by_id for step in steps):
            if content.attack_chain_ids is not None:
                raise HTTPException(
                    422, "Include all Findings referenced by each selected Attack Chain"
                )
            warnings.append(
                f"{chain.display_id}: excluded because a related Finding is not included."
            )
            continue
        chain_links = list(
            session.scalars(
                select(attack_chain_evidence.c.evidence_id).where(
                    attack_chain_evidence.c.attack_chain_id == chain.id
                )
            )
        )
        document_steps = []
        for step in steps:
            links = list(
                session.scalars(
                    select(attack_chain_step_evidence.c.evidence_id).where(
                        attack_chain_step_evidence.c.step_id == step.id
                    )
                )
            )
            evidence_ids.update(links)
            finding = by_id.get(step.finding_id)
            document_steps.append(
                {
                    "position": step.position,
                    "kind": step.step_type,
                    "finding_id": finding.display_id if finding else None,
                    "title": finding.title if finding else step.title,
                    "description": step.description,
                    "evidence_ids": links,
                }
            )
        evidence_ids.update(chain_links)
        document_chains.append(
            {
                "display_id": chain.display_id,
                "title": chain.title,
                "status": chain.status,
                "description": chain.description,
                "resulting_impact": chain.resulting_impact,
                "steps": document_steps,
                "evidence_ids": chain_links,
            }
        )
    evidence = list(
        session.scalars(
            select(Evidence)
            .where(Evidence.engagement_id == engagement.id, Evidence.id.in_(evidence_ids))
            .order_by(Evidence.sequence_number)
        )
    )
    if {e.id for e in evidence} != evidence_ids:
        raise HTTPException(422, "Report Evidence must exist in the same Engagement")
    if len(evidence) > 2000 or len(shown_retests) > 2000:
        raise HTTPException(
            422, "Reduce report selection; at most 2000 Evidence and Retest records are supported"
        )
    evidence_names = {e.id: e.display_id for e in evidence}
    for chain in document_chains:
        chain["evidence_ids"] = sorted(evidence_names[e] for e in chain["evidence_ids"])
        for step in chain["steps"]:
            step["evidence_ids"] = sorted(evidence_names[e] for e in step["evidence_ids"])
    document_findings = []
    for finding in findings:
        for field in ("description", "impact", "reproduction_steps", "remediation"):
            if not getattr(finding, field):
                warnings.append(f"{finding.display_id}: missing {field.replace('_', ' ')}.")
        linked_ids = [e.display_id for e in finding_evidence if e.finding_id == finding.id]
        if not linked_ids:
            warnings.append(f"{finding.display_id}: no immutable Finding Evidence selected.")
        fields = (
            "display_id",
            "title",
            "severity",
            "status",
            "affected_asset",
            "affected_endpoints",
            "description",
            "impact",
            "reproduction_steps",
            "remediation",
            "references",
            "confirmed_at",
        )
        document_findings.append(
            {
                **{field: getattr(finding, field) for field in fields},
                "archived": finding.archived_at is not None,
                "finding_evidence_ids": linked_ids,
                "latest_retest": latest[finding.id].status
                if finding.id in latest
                else "Not Retested",
            }
        )
    document_retests = [
        {
            "display_id": r.display_id,
            "finding_id": by_id[r.finding_id].display_id,
            "status": r.status,
            "tested_at": r.tested_at,
            "operator_notes": r.operator_notes,
            "latest": latest[r.finding_id].id == r.id,
            "evidence_ids": sorted(
                evidence_names[row.evidence_id] for row in retest_links if row.retest_id == r.id
            ),
        }
        for r in shown_retests
    ]
    assessments = session.execute(
        select(
            AssessmentRun.display_id,
            AssessmentRun.target_url,
            AssessmentRun.status,
            AssessmentRun.request_count,
            AssessmentRun.started_at,
            AssessmentRun.finished_at,
        )
        .where(AssessmentRun.engagement_id == engagement.id)
        .order_by(AssessmentRun.sequence_number)
    ).mappings()
    document = ReportDocument.model_validate(
        safe_data(
            {
                "application_version": __version__,
                "report": {
                    "id": report.id,
                    "display_id": report.display_id,
                    "title": report.title,
                    "revision": revision,
                    "generated_at": generated_at,
                    **{
                        name: getattr(content, name)
                        for name in (
                            "executive_summary",
                            "methodology",
                            "limitations",
                            "conclusion",
                        )
                    },
                },
                "engagement": {
                    "id": engagement.id,
                    "name": engagement.name,
                    "description": engagement.description,
                    "status": engagement.status,
                    "created_at": engagement.created_at,
                },
                "scope": [
                    {
                        "scheme": s.scheme,
                        "host": s.hostname,
                        "port": s.port,
                        "path_prefix": s.path_prefix,
                        "active": s.active,
                    }
                    for s in scopes
                ],
                "summary": {
                    "finding_count": len(findings),
                    "severity": {s: sum(f.severity == s for f in findings) for s in SEVERITIES},
                    "attack_chain_count": len(document_chains),
                    "retested_findings": len(latest),
                    "latest_retest_results": {
                        s: sum(r.status == s for r in latest.values()) for s in RETEST_STATUSES
                    },
                },
                "findings": document_findings,
                "evidence": [evidence_document(e) for e in evidence],
                "attack_chains": document_chains,
                "retests": document_retests,
                "assessments": [dict(item) for item in assessments],
                "warnings": warnings,
            }
        )
    )
    if len(canonical_json(document).encode()) > MAX_DOCUMENT_BYTES:
        raise HTTPException(422, "Report exceeds 10 MB; reduce the selected content")
    return document
