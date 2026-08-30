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
        mesh = client.get("/js/call.js")
        assert mesh.status_code == 200
        assert "webrtc.offer" in mesh.text
        assert "RTCPeerConnection" in mesh.text
        assert "sdpMid" in mesh.text
        assert "onRoomReady" in mesh.text
        assert "subtitle.update" in mesh.text
        subs = client.get("/js/subtitles.js")
        assert subs.status_code == 200
        assert "SubtitleStore" in subs.text
        assert "subtitle-panel" in page.text
        assert "subtitle-list" in css.text
        assert "subtitles.js" in page.text
        pcm = client.get("/js/pcm.js")
        assert pcm.status_code == 200
        assert "downsampleTo16k" in pcm.text
        worklet = client.get("/js/pcm-worklet.js")
        assert worklet.status_code == 200
        assert "pcm-capture" in worklet.text
        asr_js = client.get("/js/asr.js")
        assert asr_js.status_code == 200
        assert "asr.audio" in asr_js.text
        capture = client.get("/js/pcm-capture.js")
        assert capture.status_code == 200
        assert "audioWorklet" in capture.text
        assert "pcm.js" in page.text
        assert "asr.js" in page.text
        cfg = client.get("/v1/client-config")
        assert cfg.status_code == 200
        url = cfg.json()["asr_ws_url"]
        assert url.endswith("/v1/stream")
        assert ":8001/" in url or url.endswith(":8001/v1/stream")
        assert client.get("/health").json() == {"ok": True}
        assert client.get("/v1/users/me").status_code == 401
