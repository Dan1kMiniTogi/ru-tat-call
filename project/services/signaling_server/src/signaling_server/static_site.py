"""Serve the mobile-first HTML/JS client from `WEB_CLIENT_DIR`."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles


def mount_web_client(app: FastAPI, web_client_dir: Path) -> None:
    """Mount static files at `/` after API/WS routes so they keep priority.

    Args:
        app: Signaling FastAPI app.
        web_client_dir: Directory with `index.html` (usually `project/web_client`).

    Example:
        mount_web_client(app, settings.web_client_dir)
    """
    if not (web_client_dir / "index.html").is_file():
        return
    app.mount(
        "/",
        StaticFiles(directory=str(web_client_dir), html=True),
        name="web_client",
    )
