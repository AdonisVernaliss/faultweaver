from __future__ import annotations

from hashlib import sha256
from pathlib import PurePosixPath
from urllib.parse import urlsplit

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from faultweaver.config import Settings
from faultweaver.findings.service import allocate_display_id
from faultweaver.http_traffic.models import HttpExchange
from faultweaver.imports.canonical import (
    CanonicalHttpRecord,
    DeclaredEndpoint,
    ParseResult,
    ParserLimits,
)
from faultweaver.imports.models import AttackSurfaceEndpoint, ImportBatch
from faultweaver.imports.schemas import ImportBatchResponse, ImportResultResponse
from faultweaver.redaction import redact_body
from faultweaver.scope.rules import ScopeRuleValue, is_url_in_scope


def parser_limits(settings: Settings) -> ParserLimits:
    return ParserLimits(
        max_document_bytes=settings.max_import_bytes,
        max_entries=settings.max_import_entries,
        max_request_body_bytes=settings.max_import_request_body_bytes,
        max_response_body_bytes=settings.max_import_response_body_bytes,
    )


def content_digest(content: str) -> str:
    return sha256(content.encode("utf-8")).hexdigest()


def safe_filename(filename: str | None) -> str | None:
    if not filename:
        return None
    normalized = filename.replace("\\", "/").replace("\x00", "")
    basename = PurePosixPath(normalized).name[:255]
    return redact_body(basename) or None


def persist_observed_import(
    session: Session,
    *,
    engagement_id: str,
    import_format: str,
    filename: str | None,
    content: str,
    parsed: ParseResult,
    scopes: list[ScopeRuleValue],
) -> ImportResultResponse:
    warnings = list(parsed.warnings)
    duplicate = session.scalar(
        select(ImportBatch)
        .where(
            ImportBatch.engagement_id == engagement_id,
            ImportBatch.content_digest == content_digest(content),
            ImportBatch.import_format == import_format,
        )
        .order_by(ImportBatch.created_at.desc())
    )
    if duplicate is not None:
        warnings.append(
            f"Probable duplicate of {duplicate.display_id}; transactions were preserved"
        )

    batch = _new_batch(
        session,
        engagement_id=engagement_id,
        import_format=import_format,
        filename=filename,
        content=content,
        total_records=parsed.total_records,
    )
    request_ids: list[str] = []
    endpoint_ids: list[str] = []
    new_endpoint_ids: set[str] = set()
    known_endpoint_ids: set[str] = set()
    skipped_count = parsed.skipped_count
    response_count = 0
    for record in parsed.records:
        if not is_url_in_scope(record.url, scopes):
            skipped_count += 1
            warnings.append(
                f"Entry {record.source_entry_index}: request was skipped because it is out of scope"
            )
            continue
        endpoint, created = endpoint_for_record(
            session, engagement_id=engagement_id, record=record, source=import_format
        )
        if created:
            new_endpoint_ids.add(endpoint.id)
        elif endpoint.id not in new_endpoint_ids:
            known_endpoint_ids.add(endpoint.id)
        method, host, path, query = record.validated_parts()
        exchange = HttpExchange(
            engagement_id=engagement_id,
            import_batch_id=batch.id,
            endpoint_id=endpoint.id,
            source_entry_index=record.source_entry_index,
            source=import_format,
            method=method,
            url=record.url,
            host=host,
            path=path,
            query=query,
            request_headers=record.request_headers,
            request_body=record.request_body,
            response_status=record.response_status,
            response_headers=record.response_headers,
            response_body=record.response_body,
            response_elapsed_ms=record.response_elapsed_ms,
            response_truncated=record.response_truncated,
            redirect_chain=record.redirect_chain,
            **({"created_at": record.observed_at} if record.observed_at is not None else {}),
        )
        session.add(exchange)
        session.flush()
        request_ids.append(exchange.id)
        endpoint_ids.append(endpoint.id)
        if record.response_status is not None:
            response_count += 1

    batch.imported_count = len(request_ids)
    batch.response_count = response_count
    batch.skipped_count = skipped_count
    batch.new_endpoint_count = len(new_endpoint_ids)
    batch.known_endpoint_count = len(known_endpoint_ids)
    batch.warnings = _redacted_warnings(warnings)
    batch.warning_count = len(batch.warnings)
    batch.status = "partial" if skipped_count else "completed"
    session.commit()
    session.refresh(batch)
    return ImportResultResponse(
        batch=public_batch(batch),
        request_ids=request_ids,
        endpoint_ids=list(dict.fromkeys(endpoint_ids)),
    )


def persist_openapi_import(
    session: Session,
    *,
    engagement_id: str,
    filename: str | None,
    content: str,
    parsed: ParseResult,
) -> ImportResultResponse:
    warnings = list(parsed.warnings)
    duplicate = session.scalar(
        select(ImportBatch)
        .where(
            ImportBatch.engagement_id == engagement_id,
            ImportBatch.content_digest == content_digest(content),
            ImportBatch.import_format == "openapi",
        )
        .order_by(ImportBatch.created_at.desc())
    )
    if duplicate is not None:
        warnings.append(
            f"Probable duplicate of {duplicate.display_id}; endpoints were deduplicated"
        )
    batch = _new_batch(
        session,
        engagement_id=engagement_id,
        import_format="openapi",
        filename=filename,
        content=content,
        total_records=parsed.total_records,
    )
    endpoint_ids: list[str] = []
    new_endpoint_ids: set[str] = set()
    known_endpoint_ids: set[str] = set()
    for endpoint_input in parsed.endpoints:
        endpoint, created = upsert_declared_endpoint(
            session, engagement_id=engagement_id, declared=endpoint_input
        )
        endpoint_ids.append(endpoint.id)
        if created:
            new_endpoint_ids.add(endpoint.id)
        elif endpoint.id not in new_endpoint_ids:
            known_endpoint_ids.add(endpoint.id)
    batch.imported_count = len(parsed.endpoints)
    batch.skipped_count = parsed.skipped_count
    batch.new_endpoint_count = len(new_endpoint_ids)
    batch.known_endpoint_count = len(known_endpoint_ids)
    batch.warnings = _redacted_warnings(warnings)
    batch.warning_count = len(batch.warnings)
    batch.status = "partial" if parsed.skipped_count else "completed"
    session.commit()
    session.refresh(batch)
    return ImportResultResponse(
        batch=public_batch(batch), request_ids=[], endpoint_ids=list(dict.fromkeys(endpoint_ids))
    )


def endpoint_for_record(
    session: Session,
    *,
    engagement_id: str,
    record: CanonicalHttpRecord,
    source: str,
) -> tuple[AttackSurfaceEndpoint, bool]:
    method, host, path, _ = record.validated_parts()
    parsed_url = urlsplit(record.url)
    scheme = parsed_url.scheme.lower()
    port = _effective_port(parsed_url)
    declared = list(
        session.scalars(
            select(AttackSurfaceEndpoint).where(
                AttackSurfaceEndpoint.engagement_id == engagement_id,
                AttackSurfaceEndpoint.method == method,
                AttackSurfaceEndpoint.declared_by_openapi.is_(True),
            )
        )
    )
    matches = [
        item
        for item in declared
        if _endpoint_origin_matches(item, scheme, host, port)
        and _path_matches_template(path, item.path_template)
    ]
    if matches:
        matches.sort(key=lambda item: (item.host is None, item.path_template.count("{")))
        endpoint = matches[0]
        _add_source(endpoint, source)
        return endpoint, False
    key = canonical_key(method, scheme, host, port, path)
    endpoint = session.scalar(
        select(AttackSurfaceEndpoint).where(
            AttackSurfaceEndpoint.engagement_id == engagement_id,
            AttackSurfaceEndpoint.canonical_key == key,
        )
    )
    if endpoint is not None:
        _add_source(endpoint, source)
        return endpoint, False
    endpoint = AttackSurfaceEndpoint(
        engagement_id=engagement_id,
        canonical_key=key,
        method=method,
        scheme=scheme,
        host=host,
        port=port,
        path_template=path,
        sources=[source],
        declared_by_openapi=False,
        details={},
    )
    session.add(endpoint)
    session.flush()
    return endpoint, True


def upsert_declared_endpoint(
    session: Session, *, engagement_id: str, declared: DeclaredEndpoint
) -> tuple[AttackSurfaceEndpoint, bool]:
    scheme, host, port, path = _declared_parts(declared)
    key = canonical_key(declared.method, scheme, host, port, path)
    endpoint = session.scalar(
        select(AttackSurfaceEndpoint).where(
            AttackSurfaceEndpoint.engagement_id == engagement_id,
            AttackSurfaceEndpoint.canonical_key == key,
        )
    )
    created = endpoint is None
    if endpoint is None:
        endpoint = AttackSurfaceEndpoint(
            engagement_id=engagement_id,
            canonical_key=key,
            method=declared.method,
            scheme=scheme,
            host=host,
            port=port,
            path_template=path,
            sources=["openapi"],
            declared_by_openapi=True,
            details=_json_safe(declared.details),
        )
        session.add(endpoint)
        session.flush()
    else:
        endpoint.declared_by_openapi = True
        endpoint.details = _json_safe(declared.details)
        _add_source(endpoint, "openapi")
    _merge_matching_observed_endpoints(session, endpoint)
    return endpoint, created


def attach_exchange_endpoint(
    session: Session, exchange: HttpExchange, *, source: str
) -> AttackSurfaceEndpoint:
    record = CanonicalHttpRecord(method=exchange.method, url=exchange.url)
    endpoint, _ = endpoint_for_record(
        session, engagement_id=exchange.engagement_id, record=record, source=source
    )
    exchange.endpoint_id = endpoint.id
    return endpoint


def public_batch(batch: ImportBatch) -> ImportBatchResponse:
    return ImportBatchResponse(
        id=batch.id,
        engagement_id=batch.engagement_id,
        display_id=batch.display_id,
        import_format=batch.import_format,
        original_filename=batch.original_filename,
        status=batch.status,
        total_records=batch.total_records,
        imported_count=batch.imported_count,
        response_count=batch.response_count,
        skipped_count=batch.skipped_count,
        warning_count=batch.warning_count,
        new_endpoint_count=batch.new_endpoint_count,
        known_endpoint_count=batch.known_endpoint_count,
        warnings=batch.warnings,
        created_at=batch.created_at,
    )


def observed_count(session: Session, endpoint_id: str) -> int:
    return (
        session.scalar(
            select(func.count())
            .select_from(HttpExchange)
            .where(
                HttpExchange.endpoint_id == endpoint_id,
                HttpExchange.source != "replay",
            )
        )
        or 0
    )


def canonical_key(
    method: str, scheme: str | None, host: str | None, port: int | None, path: str
) -> str:
    return "|".join([method.upper(), scheme or "", host or "", str(port or ""), path])


def _new_batch(
    session: Session,
    *,
    engagement_id: str,
    import_format: str,
    filename: str | None,
    content: str,
    total_records: int,
) -> ImportBatch:
    display_id, number = allocate_display_id(session, engagement_id, "import")
    batch = ImportBatch(
        engagement_id=engagement_id,
        display_id=display_id,
        sequence_number=number,
        import_format=import_format,
        original_filename=safe_filename(filename),
        content_digest=content_digest(content),
        status="processing",
        total_records=total_records,
        imported_count=0,
        response_count=0,
        skipped_count=0,
        warning_count=0,
        new_endpoint_count=0,
        known_endpoint_count=0,
        warnings=[],
    )
    session.add(batch)
    session.flush()
    return batch


def _declared_parts(
    declared: DeclaredEndpoint,
) -> tuple[str | None, str | None, int | None, str]:
    if not declared.server_url:
        return None, None, None, declared.path_template
    parsed = urlsplit(declared.server_url)
    base = parsed.path.rstrip("/")
    path = f"{base}{declared.path_template}" or "/"
    return (
        parsed.scheme.lower(),
        parsed.hostname.lower() if parsed.hostname else None,
        _effective_port(parsed),
        path,
    )


def _effective_port(parsed: object) -> int | None:
    port = parsed.port  # type: ignore[attr-defined]
    if port is not None:
        return port
    if parsed.scheme == "http":  # type: ignore[attr-defined]
        return 80
    if parsed.scheme == "https":  # type: ignore[attr-defined]
        return 443
    return None


def _endpoint_origin_matches(
    endpoint: AttackSurfaceEndpoint, scheme: str, host: str, port: int | None
) -> bool:
    if endpoint.host is None:
        return True
    return endpoint.scheme == scheme and endpoint.host == host and endpoint.port == port


def _path_matches_template(path: str, template: str) -> bool:
    path_parts = path.strip("/").split("/")
    template_parts = template.strip("/").split("/")
    if len(path_parts) != len(template_parts):
        return False
    return all(
        template_part == path_part
        or (template_part.startswith("{") and template_part.endswith("}"))
        for path_part, template_part in zip(path_parts, template_parts, strict=True)
    )


def _merge_matching_observed_endpoints(session: Session, declared: AttackSurfaceEndpoint) -> None:
    if declared.host is None:
        return
    candidates = list(
        session.scalars(
            select(AttackSurfaceEndpoint).where(
                AttackSurfaceEndpoint.engagement_id == declared.engagement_id,
                AttackSurfaceEndpoint.method == declared.method,
                AttackSurfaceEndpoint.declared_by_openapi.is_(False),
                AttackSurfaceEndpoint.host == declared.host,
                AttackSurfaceEndpoint.scheme == declared.scheme,
                AttackSurfaceEndpoint.port == declared.port,
                AttackSurfaceEndpoint.id != declared.id,
            )
        )
    )
    for candidate in candidates:
        if not _path_matches_template(candidate.path_template, declared.path_template):
            continue
        for source in candidate.sources:
            _add_source(declared, source)
        session.query(HttpExchange).filter(HttpExchange.endpoint_id == candidate.id).update(
            {HttpExchange.endpoint_id: declared.id}, synchronize_session=False
        )
        session.delete(candidate)
    session.flush()


def _add_source(endpoint: AttackSurfaceEndpoint, source: str) -> None:
    if source not in endpoint.sources:
        endpoint.sources = [*endpoint.sources, source]


def _redacted_warnings(warnings: list[str]) -> list[str]:
    return [redact_body(item) or "Import warning" for item in warnings]


def _json_safe(value: object) -> object:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    return str(value)
