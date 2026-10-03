from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import partial

import httpx
from fastapi import FastAPI, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from faultweaver import __version__
from faultweaver.analysis.router import router as analysis_router
from faultweaver.config import Settings
from faultweaver.database import create_session_factory, get_session, session_dependency
from faultweaver.engagements.router import router as engagements_router
from faultweaver.http_traffic.router import router as http_traffic_router
from faultweaver.identities.router import router as identities_router
from faultweaver.migrations.runner import upgrade_database
from faultweaver.redaction import install_log_redaction, sanitize_for_log
from faultweaver.scope.router import router as scope_router


def create_app(
    settings: Settings | None = None,
    *,
    http_transport: httpx.BaseTransport | None = None,
) -> FastAPI:
    resolved_settings = settings or Settings.from_environment()
    session_factory = create_session_factory(resolved_settings.database_url)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        upgrade_database(resolved_settings.database_url)
        install_log_redaction()
        yield

    app = FastAPI(
        title="Faultweaver API",
        description="Local-first Web/API penetration-testing workspace",
        version=__version__,
        lifespan=lifespan,
    )
    app.state.settings = resolved_settings
    app.state.session_factory = session_factory
    app.state.http_transport = http_transport
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
        errors = sanitize_for_log(jsonable_encoder(error.errors()))
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content={"detail": errors},
        )

    @app.get("/api/health", tags=["system"])
    def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    app.include_router(engagements_router)
    app.include_router(scope_router)
    app.include_router(http_traffic_router)
    app.include_router(identities_router)
    app.include_router(analysis_router)

    return app


app = create_app()
