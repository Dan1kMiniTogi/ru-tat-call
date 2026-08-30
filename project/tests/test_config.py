"""Settings load from env and resolve paths under project/."""

from pathlib import Path

from ru_tat_call_shared.config import PROJECT_ROOT, Settings, clear_settings_cache, get_settings


def test_default_ports_and_cors() -> None:
    """Defaults match .env.example without requiring a real .env file."""
    settings = Settings(_env_file=None)
    assert settings.signaling_port == 8000
    assert settings.asr_port == 8001
    assert "http://localhost:8000" in settings.cors_origin_list
    assert settings.max_participants == 4
    assert settings.asr_engine == "mock"
    assert settings.asr_remote_token == ""
    assert settings.asr_onnx_path == ""
    assert settings.asr_vad == "silero"
    assert settings.signaling_internal_url == "http://127.0.0.1:8000"
    assert settings.web_client_dir == PROJECT_ROOT / "web_client"
    assert settings.sqlite_path == PROJECT_ROOT / "data" / "app.db"


def test_env_overrides_port(monkeypatch) -> None:
    """SIGNALING_PORT from the environment wins over the default."""
    monkeypatch.setenv("SIGNALING_PORT", "9000")
    settings = Settings(_env_file=None)
    assert settings.signaling_port == 9000


def test_relative_sqlite_path() -> None:
    """Relative SQLITE_PATH is joined to the workspace root."""
    settings = Settings(_env_file=None, sqlite_path="tmp/test.db")
    assert settings.sqlite_path == PROJECT_ROOT / "tmp" / "test.db"
    assert settings.sqlite_path.is_absolute()


def test_get_settings_cache(monkeypatch) -> None:
    """get_settings caches; clear_settings_cache allows a fresh load."""
    clear_settings_cache()
    monkeypatch.setenv("ASR_PORT", "8111")
    first = get_settings()
    monkeypatch.setenv("ASR_PORT", "8222")
    assert get_settings().asr_port == first.asr_port
    clear_settings_cache()
    assert get_settings().asr_port == 8222
    clear_settings_cache()


def test_project_root_is_workspace() -> None:
    """PROJECT_ROOT is the directory that holds the workspace pyproject.toml."""
    assert (PROJECT_ROOT / "pyproject.toml").is_file()
    assert Path(PROJECT_ROOT.name) == Path("project")
