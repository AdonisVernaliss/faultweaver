from urllib.parse import urlsplit

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from faultweaver.config import Settings
from faultweaver.http_traffic.models import HttpExchange
from faultweaver.http_traffic.replay import apply_identity, execute_replay
from faultweaver.http_traffic.schemas import HeaderEntry, ReplayCreate
from faultweaver.identities.models import Identity
from faultweaver.scope.rules import ScopeRuleValue, split_http_url


def build_replay_exchange(
    session: Session,
    *,
    original: HttpExchange,
    payload: ReplayCreate,
    settings: Settings,
    transport: httpx.BaseTransport | None,
    scopes: list[ScopeRuleValue],
) -> HttpExchange:
    method = payload.method or original.method
    url = str(payload.url) if payload.url is not None else original.url
    headers = (
        payload.headers
        if payload.headers is not None
        else [HeaderEntry.model_validate(item) for item in original.request_headers]
    )
    body = payload.body if "body" in payload.model_fields_set else original.request_body
    identity: Identity | None = None
    auth_source = "original"
    if payload.identity_id is not None:
        identity = session.scalar(
            select(Identity).where(
                Identity.id == payload.identity_id,
                Identity.engagement_id == original.engagement_id,
                Identity.archived_at.is_(None),
            )
        )
        if identity is None:
            raise LookupError("Identity not found")
        engagement_identities = session.scalars(
            select(Identity).where(
                Identity.engagement_id == original.engagement_id,
                Identity.archived_at.is_(None),
            )
        )
        managed_header_names = {
            name.lower()
            for item in engagement_identities
            for name in (
                *[header["name"] for header in item.custom_headers],
                *([item.api_key_header] if item.api_key_header else []),
            )
        }
        headers = apply_identity(headers, identity, managed_header_names=managed_header_names)
        auth_source = "identity"

    with httpx.Client(
        transport=transport,
        timeout=settings.request_timeout_seconds,
    ) as client:
        result = execute_replay(
            client,
            method=method,
            url=url,
            headers=headers,
            body=body,
            scopes=scopes,
            max_redirects=settings.max_redirects,
            max_response_bytes=settings.max_response_bytes,
        )
    _, host, _, path = split_http_url(result.url)
    return HttpExchange(
        engagement_id=original.engagement_id,
        parent_exchange_id=original.id,
        identity_id=identity.id if identity is not None else None,
        endpoint_id=original.endpoint_id,
        auth_source=auth_source,
        operator_modified=bool(
            {"method", "url", "headers", "body"}.intersection(payload.model_fields_set)
        ),
        source="replay",
        method=result.method,
        url=result.url,
        host=host,
        path=path,
        query=urlsplit(result.url).query,
        request_headers=result.request_headers,
        request_body=result.request_body,
        response_status=result.status,
        response_headers=result.response_headers,
        response_body=result.response_body,
        response_elapsed_ms=result.elapsed_ms,
        response_truncated=result.response_truncated,
        redirect_chain=result.redirect_chain,
    )
