from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from threading import Event, Lock, Thread
from time import monotonic
from urllib.parse import urljoin, urlsplit

import httpx
from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session, sessionmaker

from faultweaver.analysis.models import Candidate
from faultweaver.assessments.checks import AnalysisContext, AnalysisSignal, analyze_response
from faultweaver.assessments.discovery import discover_html, discover_sitemap
from faultweaver.assessments.frontier import CrawlFrontier, FrontierItem
from faultweaver.assessments.models import (
    AssessmentRun,
    BaselineObservation,
    CrawlDiscovery,
    CrawlForm,
)
from faultweaver.assessments.scheduler import RateLimiter
from faultweaver.assessments.urls import InvalidCrawlUrl, canonicalize_url, resolve_url
from faultweaver.engagements.models import utc_now
from faultweaver.http_traffic.models import HttpExchange
from faultweaver.http_traffic.replay import REDIRECT_STATUSES, _read_limited
from faultweaver.imports.service import attach_exchange_endpoint, upsert_discovered_endpoint
from faultweaver.redaction import redact_body, redact_url
from faultweaver.scope.models import ScopeRule
from faultweaver.scope.rules import ScopeRuleValue, is_url_in_scope

_TEXT_TYPES = ("text/", "application/json", "+json", "application/xml", "+xml")
_FETCHABLE_KINDS = {"seed", "navigation", "iframe", "redirect", "robots", "sitemap"}
_REQUEST_HEADERS = [
    {"name": "User-Agent", "value": "Faultweaver-Baseline/1.0"},
    {
        "name": "Accept",
        "value": "text/html,application/json,application/xml,text/plain;q=0.9,*/*;q=0.1",
    },
]


@dataclass(frozen=True, slots=True)
class FetchResult:
    item: FrontierItem
    status: int | None
    response_headers: list[dict[str, str]]
    body: str | None
    content_type: str
    elapsed_ms: float | None
    truncated: bool
    error: str | None = None


class AssessmentManager:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        transport: httpx.BaseTransport | None,
    ) -> None:
        self._session_factory = session_factory
        self._transport = transport
        self._workers: dict[str, tuple[Event, Thread]] = {}
        self._lock = Lock()

    def recover_stale(self) -> None:
        with self._session_factory() as session:
            stale = list(
                session.scalars(
                    select(AssessmentRun).where(AssessmentRun.status.in_(["Pending", "Running"]))
                )
            )
            for run in stale:
                run.status = "Stopped"
                run.stop_requested = True
                run.stop_reason = "Interrupted by application restart"
                run.finished_at = utc_now()
            session.commit()

    def start(self, run_id: str) -> None:
        stop = Event()
        thread = Thread(target=self._run, args=(run_id, stop), daemon=True)
        with self._lock:
            self._workers[run_id] = (stop, thread)
        thread.start()

    def stop(self, run_id: str) -> None:
        with self._lock:
            worker = self._workers.get(run_id)
        if worker is not None:
            worker[0].set()

    def shutdown(self) -> None:
        with self._lock:
            workers = list(self._workers.values())
        for stop, _ in workers:
            stop.set()
        for _, thread in workers:
            thread.join(timeout=2)

    def _run(self, run_id: str, stop: Event) -> None:
        try:
            with self._session_factory() as session:
                run = session.get(AssessmentRun, run_id)
                if run is None:
                    return
                self._execute(session, run, stop)
        finally:
            with self._lock:
                self._workers.pop(run_id, None)

    def _execute(self, session: Session, run: AssessmentRun, stop: Event) -> None:
        run.status = "Running"
        run.started_at = utc_now()
        run.stop_requested = False
        session.commit()
        scopes = _scope_values(session, run.engagement_id)
        frontier = CrawlFrontier(
            max_depth=run.max_depth,
            max_query_variants_per_path=run.max_query_variants_per_path,
        )
        discovery_rows: dict[str, CrawlDiscovery] = {}
        try:
            self._discover(
                session,
                run,
                frontier,
                discovery_rows,
                scopes,
                run.target_url,
                depth=0,
                kind="seed",
                parent_exchange_id=None,
            )
            if run.inspect_site_metadata:
                parsed = urlsplit(run.target_url)
                origin = f"{parsed.scheme}://{parsed.netloc}"
                for path, kind in (("/robots.txt", "robots"), ("/sitemap.xml", "sitemap")):
                    self._discover(
                        session,
                        run,
                        frontier,
                        discovery_rows,
                        scopes,
                        urljoin(origin, path),
                        depth=0,
                        kind=kind,
                        parent_exchange_id=None,
                    )
            limiter = RateLimiter(run.requests_per_second)
            with (
                httpx.Client(
                    transport=self._transport,
                    timeout=run.request_timeout_seconds,
                    follow_redirects=False,
                ) as client,
                ThreadPoolExecutor(max_workers=run.concurrency) as pool,
            ):
                while frontier and run.request_count < run.max_requests:
                    session.refresh(run)
                    if stop.is_set() or run.stop_requested:
                        break
                    batch: list[FrontierItem] = []
                    remaining = run.max_requests - run.request_count
                    for _ in range(min(run.concurrency, remaining)):
                        item = frontier.pop()
                        if item is None:
                            break
                        row = discovery_rows[item.canonical_url]
                        row.state = "queued"
                        batch.append(item)
                    run.queued_count = frontier.queued_count
                    session.commit()
                    futures: list[Future[FetchResult]] = []
                    for item in batch:
                        if stop.is_set():
                            break
                        limiter.wait()
                        futures.append(
                            pool.submit(self._fetch, client, item, run.max_response_bytes, scopes)
                        )
                    for future in futures:
                        result = future.result()
                        self._persist_result(
                            session,
                            run,
                            frontier,
                            discovery_rows,
                            scopes,
                            result,
                        )
                    if run.page_count >= run.max_pages:
                        run.stop_reason = "Maximum page limit reached"
                        break
            if stop.is_set() or run.stop_requested:
                run.status = "Stopped"
                run.stop_reason = "Stopped by operator"
            else:
                run.status = "Completed"
                if run.request_count >= run.max_requests and frontier:
                    run.stop_reason = "Maximum request limit reached"
        except (
            Exception
        ) as error:  # Fundamental runner failure; request failures are handled below.
            run.status = "Failed"
            run.stop_reason = redact_body(str(error)) or type(error).__name__
            self._warn(run, f"Assessment failed: {type(error).__name__}")
        finally:
            self._finalize(session, run, frontier)

    def _fetch(
        self,
        client: httpx.Client,
        item: FrontierItem,
        max_response_bytes: int,
        scopes: list[ScopeRuleValue],
    ) -> FetchResult:
        if not is_url_in_scope(item.canonical_url, scopes):
            return FetchResult(item, None, [], None, "", None, False, "outside authorized scope")
        started = monotonic()
        try:
            with client.stream(
                "GET",
                item.canonical_url,
                headers={entry["name"]: entry["value"] for entry in _REQUEST_HEADERS},
            ) as response:
                content, truncated = _read_limited(response, max_response_bytes)
                content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
                textual = any(token in content_type for token in _TEXT_TYPES)
                body = (
                    content.decode(response.encoding or "utf-8", errors="replace")
                    if textual
                    else None
                )
                return FetchResult(
                    item=item,
                    status=response.status_code,
                    response_headers=[
                        {"name": name, "value": value}
                        for name, value in response.headers.multi_items()
                    ],
                    body=body,
                    content_type=content_type,
                    elapsed_ms=round((monotonic() - started) * 1_000, 3),
                    truncated=truncated,
                )
        except httpx.HTTPError as error:
            return FetchResult(
                item,
                None,
                [],
                None,
                "",
                round((monotonic() - started) * 1_000, 3),
                False,
                redact_body(str(error)) or type(error).__name__,
            )

    def _persist_result(
        self,
        session: Session,
        run: AssessmentRun,
        frontier: CrawlFrontier,
        discovery_rows: dict[str, CrawlDiscovery],
        scopes: list[ScopeRuleValue],
        result: FetchResult,
    ) -> None:
        item = result.item
        row = discovery_rows[item.canonical_url]
        exchange = HttpExchange(
            engagement_id=run.engagement_id,
            assessment_run_id=run.id,
            discovered_from_exchange_id=item.parent_exchange_id,
            crawl_depth=item.depth,
            discovery_kind=item.kind,
            source="crawler",
            method="GET",
            url=item.canonical_url,
            host=urlsplit(item.canonical_url).hostname or "",
            path=urlsplit(item.canonical_url).path or "/",
            query=urlsplit(item.canonical_url).query,
            request_headers=_REQUEST_HEADERS,
            response_status=result.status,
            response_headers=result.response_headers,
            response_body=result.body,
            response_elapsed_ms=result.elapsed_ms,
            response_truncated=result.truncated,
            redirect_chain=[],
            crawl_error=result.error,
        )
        session.add(exchange)
        session.flush()
        attach_exchange_endpoint(session, exchange, source="crawler")
        run.request_count += 1
        run.current_depth = item.depth
        run.current_url = item.canonical_url
        row.requested_exchange_id = exchange.id
        row.state = "failed" if result.error else "requested"
        row.reason = result.error
        if result.error:
            run.failed_request_count += 1
            self._warn(run, f"Request failed for {redact_url(item.canonical_url)}")
            session.commit()
            return
        if result.content_type == "text/html":
            run.page_count += 1
        else:
            run.resource_count += 1
        signals = analyze_response(
            AnalysisContext(
                url=item.canonical_url,
                status=result.status or 0,
                headers=result.response_headers,
                body=result.body or "",
            )
        )
        self._persist_signals(session, run, exchange, signals)
        self._discover_from_response(
            session,
            run,
            frontier,
            discovery_rows,
            scopes,
            exchange,
            result,
        )
        run.queued_count = frontier.queued_count
        session.commit()

    def _discover_from_response(
        self,
        session: Session,
        run: AssessmentRun,
        frontier: CrawlFrontier,
        discovery_rows: dict[str, CrawlDiscovery],
        scopes: list[ScopeRuleValue],
        exchange: HttpExchange,
        result: FetchResult,
    ) -> None:
        location = _header(result.response_headers, "location")
        if result.status in REDIRECT_STATUSES and location:
            try:
                destination = resolve_url(exchange.url, location)
            except InvalidCrawlUrl:
                self._warn(run, "A redirect contained an invalid or unsupported URL")
                return
            signal = _redirect_signal(exchange.url, destination)
            if signal:
                self._persist_signals(session, run, exchange, [signal])
            self._discover(
                session,
                run,
                frontier,
                discovery_rows,
                scopes,
                destination,
                depth=exchange.crawl_depth or 0,
                kind="redirect",
                parent_exchange_id=exchange.id,
            )
            return
        body = result.body or ""
        if result.content_type == "text/html":
            discovered = discover_html(body, exchange.url)
            for form in discovered.forms:
                session.add(
                    CrawlForm(
                        assessment_run_id=run.id,
                        exchange_id=exchange.id,
                        action_url=form.action_url,
                        method=form.method,
                        enctype=form.enctype,
                        fields=[
                            {
                                "name": field.name,
                                "type": field.input_type,
                                "hidden": field.input_type == "hidden",
                                "has_value": field.has_value,
                            }
                            for field in form.fields
                        ],
                    )
                )
                if _origin(form.action_url) != _origin(exchange.url):
                    self._persist_signals(
                        session,
                        run,
                        exchange,
                        [_cross_origin_form_signal()],
                    )
            for link in discovered.links:
                if urlsplit(exchange.url).scheme == "https" and urlsplit(link.url).scheme == "http":
                    self._persist_signals(
                        session, run, exchange, [_mixed_content_signal(link.kind)]
                    )
                self._discover(
                    session,
                    run,
                    frontier,
                    discovery_rows,
                    scopes,
                    link.url,
                    depth=(exchange.crawl_depth or 0) + 1,
                    kind=link.kind,
                    parent_exchange_id=exchange.id,
                    method=_form_method(discovered.forms, link.url),
                )
        elif exchange.discovery_kind == "sitemap" or "xml" in result.content_type:
            for url in discover_sitemap(body, limit=run.max_requests):
                self._discover(
                    session,
                    run,
                    frontier,
                    discovery_rows,
                    scopes,
                    url,
                    depth=(exchange.crawl_depth or 0) + 1,
                    kind="sitemap",
                    parent_exchange_id=exchange.id,
                )
        elif exchange.discovery_kind == "robots":
            for line in body.splitlines():
                name, separator, value = line.partition(":")
                if not separator:
                    continue
                if name.strip().lower() == "sitemap":
                    kind = "sitemap"
                elif name.strip().lower() == "disallow" and value.strip():
                    kind = "robots-rule"
                else:
                    continue
                try:
                    url = resolve_url(exchange.url, value.strip())
                except InvalidCrawlUrl:
                    continue
                self._discover(
                    session,
                    run,
                    frontier,
                    discovery_rows,
                    scopes,
                    url,
                    depth=(exchange.crawl_depth or 0) + 1,
                    kind=kind,
                    parent_exchange_id=exchange.id,
                )

    def _discover(
        self,
        session: Session,
        run: AssessmentRun,
        frontier: CrawlFrontier,
        discovery_rows: dict[str, CrawlDiscovery],
        scopes: list[ScopeRuleValue],
        url: str,
        *,
        depth: int,
        kind: str,
        parent_exchange_id: str | None,
        method: str = "GET",
    ) -> None:
        try:
            canonical = canonicalize_url(url)
        except InvalidCrawlUrl:
            self._warn(run, f"Skipped unsupported discovered URL from {kind}")
            return
        if canonical in discovery_rows:
            return
        in_scope = is_url_in_scope(canonical, scopes)
        enqueue = in_scope and kind in _FETCHABLE_KINDS
        reason = (
            None if enqueue else "outside authorized scope" if not in_scope else "metadata only"
        )
        item = frontier.discover(
            canonical,
            depth=depth,
            kind=kind,
            parent_exchange_id=parent_exchange_id,
            enqueue=enqueue,
            skip_reason=reason,
        )
        if item is None:
            return
        row = CrawlDiscovery(
            assessment_run_id=run.id,
            parent_exchange_id=parent_exchange_id,
            url=canonical,
            canonical_url=canonical,
            depth=depth,
            kind=kind,
            state=item.state,
            reason=item.reason,
        )
        session.add(row)
        session.flush()
        discovery_rows[canonical] = row
        upsert_discovered_endpoint(
            session,
            engagement_id=run.engagement_id,
            method=method,
            url=canonical,
            kind=kind,
            assessment_run_id=run.id,
        )
        if kind in {"stylesheet", "script", "image", "media"}:
            run.resource_count += 1
        if not in_scope:
            self._warn(run, f"Skipped out-of-scope {kind}: {redact_url(canonical)}")

    def _persist_signals(
        self,
        session: Session,
        run: AssessmentRun,
        exchange: HttpExchange,
        signals: list[AnalysisSignal],
    ) -> None:
        host = exchange.host
        for signal in signals:
            fingerprint = f"{signal.check_id}|{host}"[:200]
            observation = session.scalar(
                select(BaselineObservation).where(
                    BaselineObservation.assessment_run_id == run.id,
                    BaselineObservation.fingerprint == fingerprint,
                )
            )
            if observation is not None:
                observation.occurrence_count += 1
                if exchange.id not in observation.affected_exchange_ids:
                    observation.affected_exchange_ids = [
                        *observation.affected_exchange_ids,
                        exchange.id,
                    ]
                if observation.candidate_id:
                    candidate = session.get(Candidate, observation.candidate_id)
                    if candidate and exchange.id not in candidate.affected_exchange_ids:
                        candidate.affected_exchange_ids = [
                            *candidate.affected_exchange_ids,
                            exchange.id,
                        ]
                continue
            candidate: Candidate | None = None
            if signal.classification == "Candidate":
                candidate = Candidate(
                    engagement_id=run.engagement_id,
                    comparison_id=None,
                    original_exchange_id=exchange.id,
                    assessment_run_id=run.id,
                    endpoint_id=exchange.endpoint_id,
                    check_id=signal.check_id,
                    suggested_severity=signal.suggested_severity,
                    affected_exchange_ids=[exchange.id],
                    title=signal.title,
                    category="Baseline Assessment",
                    confidence=signal.confidence,
                    status="candidate",
                    reasoning=[signal.description, signal.reason],
                    notes="",
                )
                session.add(candidate)
                session.flush()
            session.add(
                BaselineObservation(
                    assessment_run_id=run.id,
                    exchange_id=exchange.id,
                    endpoint_id=exchange.endpoint_id,
                    candidate_id=candidate.id if candidate else None,
                    check_id=signal.check_id,
                    title=signal.title,
                    description=signal.description,
                    reason=signal.reason,
                    confidence=signal.confidence,
                    classification=signal.classification,
                    suggested_severity=signal.suggested_severity,
                    fingerprint=fingerprint,
                    occurrence_count=1,
                    affected_exchange_ids=[exchange.id],
                    details={},
                )
            )

    def _finalize(self, session: Session, run: AssessmentRun, frontier: CrawlFrontier) -> None:
        run.queued_count = frontier.queued_count
        run.current_url = None
        run.observation_count = (
            session.scalar(
                select(func.count())
                .select_from(BaselineObservation)
                .where(BaselineObservation.assessment_run_id == run.id)
            )
            or 0
        )
        run.candidate_count = (
            session.scalar(
                select(func.count())
                .select_from(Candidate)
                .where(Candidate.assessment_run_id == run.id)
            )
            or 0
        )
        run.endpoint_count = (
            session.scalar(
                select(func.count(distinct(CrawlDiscovery.canonical_url))).where(
                    CrawlDiscovery.assessment_run_id == run.id,
                    CrawlDiscovery.kind.not_in(
                        ["stylesheet", "script", "image", "media", "robots-rule"]
                    ),
                )
            )
            or 0
        )
        run.finished_at = utc_now()
        session.commit()

    @staticmethod
    def _warn(run: AssessmentRun, message: str) -> None:
        safe = redact_body(message) or "Assessment warning"
        if safe not in run.warnings and len(run.warnings) < 100:
            run.warnings = [*run.warnings, safe]


def _scope_values(session: Session, engagement_id: str) -> list[ScopeRuleValue]:
    return [
        ScopeRuleValue(
            scheme=rule.scheme,
            hostname=rule.hostname,
            port=rule.port,
            path_prefix=rule.path_prefix,
        )
        for rule in session.scalars(
            select(ScopeRule).where(
                ScopeRule.engagement_id == engagement_id,
                ScopeRule.active.is_(True),
            )
        )
    ]


def _header(headers: list[dict[str, str]], name: str) -> str | None:
    return next((item["value"] for item in headers if item["name"].lower() == name), None)


def _redirect_signal(source: str, destination: str) -> AnalysisSignal | None:
    source_parts = urlsplit(source)
    destination_parts = urlsplit(destination)
    if source_parts.scheme == "https" and destination_parts.scheme == "http":
        return AnalysisSignal(
            "redirect.downgrade",
            "HTTPS redirect downgrades to HTTP",
            "A natural redirect moved navigation from encrypted to unencrypted transport.",
            "The redirect target uses HTTP.",
            "High",
            "Candidate",
            "Low",
        )
    if (source_parts.scheme, source_parts.hostname, source_parts.port) != (
        destination_parts.scheme,
        destination_parts.hostname,
        destination_parts.port,
    ):
        return AnalysisSignal(
            "redirect.external",
            "External redirect observed",
            "The response redirects to another origin; this is not an open-redirect claim.",
            "The destination origin differs from the requested origin.",
            "High",
            "Informational",
            "Informational",
        )
    if canonicalize_url(source) == canonicalize_url(destination):
        return AnalysisSignal(
            "redirect.loop",
            "Self-redirect observed",
            "The response redirected to its own canonical URL.",
            "The source and destination normalize to the same URL.",
            "High",
            "Informational",
            "Informational",
        )
    return None


def _mixed_content_signal(kind: str) -> AnalysisSignal:
    return AnalysisSignal(
        "transport.mixed-content",
        "HTTP resource referenced by HTTPS page",
        "An HTTPS document referenced a resource using unencrypted HTTP.",
        f"The discovered {kind} reference uses HTTP.",
        "High",
        "Candidate",
        "Low",
    )


def _cross_origin_form_signal() -> AnalysisSignal:
    return AnalysisSignal(
        "forms.cross-origin-action",
        "Cross-origin form action observed",
        "A form action targets a different origin and warrants manual review.",
        "The resolved form action origin differs from the document origin.",
        "High",
        "Informational",
        "Informational",
    )


def _origin(url: str) -> tuple[str, str | None, int | None]:
    parsed = urlsplit(url)
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    return parsed.scheme, parsed.hostname, port


def _form_method(forms: list[object], url: str) -> str:
    for form in forms:
        if getattr(form, "action_url", None) == url:
            return str(getattr(form, "method", "GET")).upper()
    return "GET"
