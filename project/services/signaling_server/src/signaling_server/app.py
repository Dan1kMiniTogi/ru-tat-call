"""FastAPI application factory for the signaling HTTP API."""

from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from ru_tat_call_shared.config import Settings, get_settings

from signaling_server.api import router
from signaling_server.db import Database
from signaling_server.internal import internal_router
from signaling_server.rooms import RoomManager
from signaling_server.static_site import mount_web_client
from signaling_server.ws import ws_router


def create_app(settings: Optional[Settings] = None) -> FastAPI:
    """Build the signaling app with CORS and SQLite.

    Args:
        settings: Override for tests (temp sqlite path). Default: `get_settings()`.

    Returns:
        Configured FastAPI app. Uvicorn target: `signaling_server.app:app`.

    Example:
        from ru_tat_call_shared.config import Settings
        app = create_app(Settings(_env_file=None, sqlite_path=":memory:"))
    """
    cfg = settings or get_settings()
    db = Database(cfg.sqlite_path)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        db.init_schema()
        db.seed_family_if_empty()
        app.state.db = db
        app.state.settings = cfg
        app.state.rooms = RoomManager(max_participants=cfg.max_participants)
        yield
        db.close()

    app = FastAPI(title="ru-tat-call signaling", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router)
    app.include_router(internal_router)
    app.include_router(ws_router)

    @app.get("/health")
    def health() -> dict:
        """Liveness probe for local run and later Docker."""
        return {"ok": True}

    mount_web_client(app, cfg.web_client_dir)

    return app


app = create_app()
