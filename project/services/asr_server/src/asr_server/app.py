"""FastAPI application factory for the ASR streaming server."""

from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from ru_tat_call_shared.config import Settings, get_settings

from asr_server.ws import ws_router


def create_app(settings: Optional[Settings] = None) -> FastAPI:
    """Build the ASR app. Uvicorn target: `asr_server.app:app` on port 8001.

    Args:
        settings: Test override (same sqlite as signaling for tokens).

    Example:
        create_app(Settings(_env_file=None, sqlite_path=tmp / "app.db"))
    """
    cfg = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.settings = cfg
        yield

    app = FastAPI(title="ru-tat-call asr", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(ws_router)

    @app.get("/health")
    def health() -> dict:
        """Liveness probe."""
        return {"ok": True, "role": "asr"}

    return app


app = create_app()
