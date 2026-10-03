from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import partial

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from faultweaver import __version__
from faultweaver.config import Settings
from faultweaver.database import Base, create_session_factory, session_dependency


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or Settings.from_environment()
    session_factory = create_session_factory(resolved_settings.database_url)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        Base.metadata.create_all(session_factory.kw["bind"])
        yield

    app = FastAPI(
        title="Faultweaver API",
        description="Local-first Web/API penetration-testing workspace",
        version=__version__,
        lifespan=lifespan,
    )
    app.state.session_factory = session_factory
    app.dependency_overrides[session_dependency] = partial(session_dependency, session_factory)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(resolved_settings.allowed_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health", tags=["system"])
    def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    return app


app = create_app()
