from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import partial

import httpx
from fastapi import FastAPI, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DatabaseError
from sqlalchemy.orm import sessionmaker

from faultweaver import __version__
from faultweaver.analysis.router import router as analysis_router
from faultweaver.assessments.router import router as assessments_router
from faultweaver.assessments.runner import AssessmentManager
from faultweaver.attack_chains.router import router as attack_chains_router
from faultweaver.config import Settings
from faultweaver.database import create_storage_engine, get_session, session_dependency
from faultweaver.engagements.router import router as engagements_router
from faultweaver.findings.router import router as findings_router
from faultweaver.http_traffic.router import router as http_traffic_router
from faultweaver.identities.router import router as identities_router
from faultweaver.imports.router import router as imports_router
from faultweaver.redaction import install_log_redaction
from faultweaver.reports.router import router as reports_router
from faultweaver.scope.router import router as scope_router
from faultweaver.storage.configuration import database_path, key_provider_for
from faultweaver.storage.keys import SecretKeyProvider, StorageError
from faultweaver.storage.lifecycle import prepare_storage
from faultweaver.storage.locking import storage_lock


def create_app(
    settings: Settings | None = None,
    *,
    http_transport: httpx.BaseTransport | None = None,
    key_provider: SecretKeyProvider | None = None,
) -> FastAPI:
    resolved_settings = settings or Settings.from_environment()
    session_factory = sessionmaker(autoflush=False, expire_on_commit=False)
    assessment_manager = AssessmentManager(session_factory, transport=http_transport)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        install_log_redaction()
        key = (key_provider or key_provider_for(resolved_settings)).load()
        engine = create_storage_engine(resolved_settings.database_url, key)
        with storage_lock(database_path(resolved_settings.database_url)):
            try:
                prepare_storage(engine, resolved_settings.database_url, key)
                session_factory.configure(bind=engine)
                assessment_manager.recover_stale()
                yield
            finally:
                assessment_manager.shutdown()
                engine.dispose()

    app = FastAPI(
        title="Faultweaver API",
        description="Local-first Web/API penetration-testing workspace",
        version=__version__,
        lifespan=lifespan,
    )
    app.state.settings = resolved_settings
    app.state.session_factory = session_factory
    app.state.http_transport = http_transport
    app.state.assessment_manager = assessment_manager
    app.dependency_overrides[get_session] = partial(session_dependency, session_factory)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(resolved_settings.allowed_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(_: object, error: RequestValidationError) -> JSONResponse:
        # Validation input/context can contain arbitrary credentials, including
        # malformed ones that recognition-based redaction cannot identify.
        errors = [
            {"loc": item["loc"], "type": item["type"], "msg": "Invalid request value"}
            for item in error.errors()
        ]
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content={"detail": errors},
        )

    @app.exception_handler(StorageError)
    @app.exception_handler(DatabaseError)
    async def storage_error_handler(_: object, error: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "detail": "Protected storage is unavailable; check the key and database integrity"
            },
        )

    @app.get("/api/health", tags=["system"])
    def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    app.include_router(engagements_router)
    app.include_router(scope_router)
    app.include_router(http_traffic_router)
    app.include_router(identities_router)
    app.include_router(analysis_router)
    app.include_router(findings_router)
    app.include_router(attack_chains_router)
    app.include_router(imports_router)
    app.include_router(assessments_router)
    app.include_router(reports_router)

    return app


app = create_app()
