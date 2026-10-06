import hashlib
import re
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session, load_only

from faultweaver.attack_chains.models import AttackChain
from faultweaver.database import get_session
from faultweaver.engagements.models import utc_now
from faultweaver.engagements.router import get_engagement_or_404
from faultweaver.findings.models import Evidence, Finding
from faultweaver.findings.service import allocate_display_id
from faultweaver.reports.builder import build_document, canonical_json, safe_data
from faultweaver.reports.models import Report, ReportRevision
from faultweaver.reports.rendering import REPORT_CSP, render_document
from faultweaver.reports.schemas import (
    GenerateRequest,
    ReportContent,
    ReportDocument,
    ReportResponse,
    ReportSummary,
    ReportUpdate,
    RevisionSummary,
)

router = APIRouter(tags=["reports"])
SessionDep = Annotated[Session, Depends(get_session)]
PREFIX = "/api/engagements/{engagement_id}/reports"


def _transaction(session: Session, *, write: bool = False) -> None:
    # Legacy SQLite transaction control otherwise leaves SELECTs outside a
    # transaction. All source reads for a report must share one consistent view.
    connection = session.connection()
    if not connection.connection.driver_connection.in_transaction:
        connection.exec_driver_sql("BEGIN IMMEDIATE" if write else "BEGIN")


def _report(session: Session, engagement_id: str, report_id: str) -> Report:
    get_engagement_or_404(session, engagement_id)
    report = session.scalar(
        select(Report).where(Report.id == report_id, Report.engagement_id == engagement_id)
    )
    if report is None:
        raise HTTPException(404, "Report not found")
    return report


def _public(report: Report) -> ReportResponse:
    return ReportResponse(**ReportSummary.model_validate(report).model_dump(), **report.content)


def _check_version(report: Report, version: int) -> None:
    if report.version != version:
        raise HTTPException(409, "Report changed; reload it before saving or generating")


@router.get("/api/report-schema")
def report_schema() -> dict:
    return ReportDocument.model_json_schema()


@router.post(PREFIX, response_model=ReportResponse, status_code=201)
def create_report(engagement_id: str, payload: ReportContent, session: SessionDep):
    _transaction(session, write=True)
    get_engagement_or_404(session, engagement_id)
    display_id, _ = allocate_display_id(session, engagement_id, "report")
    content = safe_data(payload.model_dump())
    report = Report(
        engagement_id=engagement_id,
        display_id=display_id,
        title=content.pop("title"),
        content=content,
    )
    session.add(report)
    session.flush()
    build_document(session, report, require_scope=False)
    session.commit()
    return _public(report)


@router.get(PREFIX, response_model=list[ReportSummary])
def list_reports(engagement_id: str, session: SessionDep, include_archived: bool = Query(False)):
    get_engagement_or_404(session, engagement_id)
    query = (
        select(Report)
        .where(Report.engagement_id == engagement_id)
        .options(
            load_only(
                *(getattr(Report, field) for field in ReportSummary.model_fields), raiseload=True
            )
        )
    )
    if not include_archived:
        query = query.where(Report.status != "Archived")
    return list(session.scalars(query.order_by(Report.created_at.desc(), Report.id)))


@router.get(PREFIX + "/options")
def report_options(engagement_id: str, session: SessionDep):
    get_engagement_or_404(session, engagement_id)
    findings = session.execute(
        select(
            Finding.id,
            Finding.display_id,
            Finding.title,
            Finding.severity,
            Finding.status,
            Finding.archived_at,
            func.length(Finding.description).label("description_length"),
            func.length(Finding.impact).label("impact_length"),
            func.length(Finding.remediation).label("remediation_length"),
            func.json_array_length(Finding.reproduction_steps).label("step_count"),
        )
        .where(Finding.engagement_id == engagement_id)
        .order_by(Finding.sequence_number)
    ).mappings()
    with_evidence = set(
        session.scalars(select(Evidence.finding_id).where(Evidence.engagement_id == engagement_id))
    )
    options = []
    for item in findings:
        gaps = [
            label
            for field, label in [
                ("description_length", "Description"),
                ("impact_length", "Impact"),
                ("remediation_length", "Remediation"),
                ("step_count", "Reproduction steps"),
            ]
            if not item[field]
        ]
        if item["id"] not in with_evidence:
            gaps.append("Evidence")
        options.append(
            {
                **{
                    name: item[name]
                    for name in ("id", "display_id", "title", "severity", "status", "archived_at")
                },
                "gaps": gaps,
            }
        )
    chains = session.execute(
        select(AttackChain.id, AttackChain.display_id, AttackChain.title, AttackChain.status)
        .where(AttackChain.engagement_id == engagement_id)
        .order_by(AttackChain.sequence_number)
    ).mappings()
    return safe_data({"findings": options, "attack_chains": [dict(item) for item in chains]})


@router.get(PREFIX + "/{report_id}", response_model=ReportResponse)
def get_report(engagement_id: str, report_id: str, session: SessionDep):
    return _public(_report(session, engagement_id, report_id))


@router.patch(PREFIX + "/{report_id}", response_model=ReportResponse)
def update_report(engagement_id: str, report_id: str, payload: ReportUpdate, session: SessionDep):
    _transaction(session, write=True)
    report = _report(session, engagement_id, report_id)
    _check_version(report, payload.version)
    updates = payload.model_dump(exclude_unset=True, exclude={"version", "status"})
    if report.status == "Archived" and (updates or payload.status != "Draft"):
        raise HTTPException(409, "Restore this archived report to Draft before editing")
    updates = safe_data(updates)
    if "title" in updates:
        report.title = updates.pop("title")
    report.content = {**report.content, **updates}
    report.status = payload.status or "Draft"
    build_document(session, report, require_scope=report.status == "Ready")
    report.version += 1
    report.updated_at = utc_now()
    session.commit()
    return _public(report)


@router.get(PREFIX + "/{report_id}/preview", response_model=ReportDocument)
def preview_report(engagement_id: str, report_id: str, session: SessionDep):
    _transaction(session)
    return build_document(session, _report(session, engagement_id, report_id), require_scope=False)


@router.get(PREFIX + "/{report_id}/preview/html")
def preview_html(engagement_id: str, report_id: str, session: SessionDep):
    _transaction(session)
    document = build_document(
        session, _report(session, engagement_id, report_id), require_scope=False
    )
    return Response(
        render_document(document, "html"),
        media_type="text/html",
        headers={
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": REPORT_CSP + "; sandbox",
        },
    )


@router.post(PREFIX + "/{report_id}/generate", response_model=RevisionSummary, status_code=201)
def generate_report(
    engagement_id: str, report_id: str, payload: GenerateRequest, session: SessionDep
):
    _transaction(session, write=True)
    report = _report(session, engagement_id, report_id)
    _check_version(report, payload.version)
    if report.status == "Archived":
        raise HTTPException(409, "Restore this report to Draft before generating a new revision")
    timestamp = utc_now()
    number = report.revision_count + 1
    document = build_document(session, report, revision=number, generated_at=timestamp)
    revision = ReportRevision(
        report_id=report.id,
        revision=number,
        generated_at=timestamp,
        schema_version=document.report_schema_version,
        document_sha256=hashlib.sha256(canonical_json(document).encode()).hexdigest(),
        document=document.model_dump(mode="json"),
    )
    session.add(revision)
    report.revision_count = number
    report.version += 1
    report.generated_at = timestamp
    report.updated_at = timestamp
    report.status = "Generated"
    session.commit()
    return revision


@router.get(PREFIX + "/{report_id}/revisions", response_model=list[RevisionSummary])
def list_revisions(engagement_id: str, report_id: str, session: SessionDep):
    _report(session, engagement_id, report_id)
    return list(
        session.scalars(
            select(ReportRevision)
            .where(ReportRevision.report_id == report_id)
            .options(
                load_only(
                    *(getattr(ReportRevision, field) for field in RevisionSummary.model_fields),
                    raiseload=True,
                )
            )
            .order_by(ReportRevision.revision.desc())
        )
    )


def _revision(session, engagement_id, report_id, number):
    _report(session, engagement_id, report_id)
    revision = session.scalar(
        select(ReportRevision).where(
            ReportRevision.report_id == report_id, ReportRevision.revision == number
        )
    )
    if revision is None:
        raise HTTPException(404, "Report revision not found")
    return ReportDocument.model_validate(revision.document)


@router.get(PREFIX + "/{report_id}/revisions/{number}", response_model=ReportDocument)
def get_revision(engagement_id: str, report_id: str, number: int, session: SessionDep):
    return _revision(session, engagement_id, report_id, number)


def export_filename(display_id: str, revision: int, extension: str) -> str:
    if (
        not re.fullmatch(r"REP-[0-9]+", display_id)
        or revision < 1
        or extension not in {"html", "md", "json"}
    ):
        raise HTTPException(422, "Invalid report export identifier or format")
    return f"faultweaver-{display_id}-r{revision}.{extension}"


@router.get(PREFIX + "/{report_id}/revisions/{number}/export/{format_name}")
def export_report(
    engagement_id: str,
    report_id: str,
    number: int,
    format_name: Literal["html", "md", "json"],
    session: SessionDep,
):
    document = _revision(session, engagement_id, report_id, number)
    filename = export_filename(document.report.display_id, number, format_name)
    output = (
        canonical_json(document)
        if format_name == "json"
        else render_document(document, format_name)
    )
    return Response(
        output,
        media_type={"json": "application/json", "html": "text/html", "md": "text/markdown"}[
            format_name
        ],
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": REPORT_CSP + "; sandbox",
        },
    )
