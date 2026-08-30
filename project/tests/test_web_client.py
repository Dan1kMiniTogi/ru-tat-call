"""Static web client is served from signaling on port 8000 (step 3.1)."""

from pathlib import Path

from fastapi.testclient import TestClient
from ru_tat_call_shared.config import PROJECT_ROOT, Settings

from signaling_server.app import create_app


def test_index_and_assets(tmp_path: Path) -> None:
    """GET / is the login SPA; CSS/JS are reachable; API still wins."""
    settings = Settings(_env_file=None, sqlite_path=tmp_path / "web.db")
    assert (PROJECT_ROOT / "web_client" / "index.html").is_file()
    with TestClient(create_app(settings)) as client:
        page = client.get("/")
        assert page.status_code == 200
        assert "text/html" in page.headers["content-type"]
        assert "Войти" in page.text
        assert "ru-tat-call" in page.text
        css = client.get("/css/app.css")
        assert css.status_code == 200
        assert "video-grid" in css.text
        js = client.get("/js/app.js")
        assert js.status_code == 200
        assert "apiLogin" in js.text
        assert client.get("/health").json() == {"ok": True}
        assert client.get("/v1/users/me").status_code == 401
