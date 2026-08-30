"""Docker Compose wiring for signaling + ASR (step 5.3)."""

from __future__ import annotations

import shutil
import subprocess

import pytest
from ru_tat_call_shared.config import PROJECT_ROOT


def test_compose_and_dockerfile_exist() -> None:
    """Compose file wires Docker DNS; Dockerfile syncs the uv workspace."""
    compose = (PROJECT_ROOT / "infra" / "docker-compose.yml").read_text(encoding="utf-8")
    dockerfile = (PROJECT_ROOT / "infra" / "Dockerfile").read_text(encoding="utf-8")
    dockerignore = (PROJECT_ROOT / ".dockerignore").read_text(encoding="utf-8")
    assert "ASR_UPSTREAM_WS_URL: ws://asr:8001/v1/stream" in compose
    assert "SIGNALING_INTERNAL_URL: http://signaling:8000" in compose
    assert "SQLITE_PATH: /data/app.db" in compose
    assert "8000:8000" in compose
    assert "uv sync --frozen --no-dev --all-packages" in dockerfile
    assert "signaling_server.app:app" in dockerfile
    assert ".venv" in dockerignore
    assert "tests" in dockerignore


def test_docker_compose_config() -> None:
    """`docker compose config` validates the file when Docker is installed."""
    if shutil.which("docker") is None:
        pytest.skip("docker is not installed")
    compose = PROJECT_ROOT / "infra" / "docker-compose.yml"
    result = subprocess.run(
        ["docker", "compose", "-f", str(compose), "config"],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
    )
    err = (result.stderr or "") + (result.stdout or "")
    if result.returncode != 0 and (
        "Cannot connect" in err
        or "daemon" in err.lower()
        or "permission denied" in err.lower()
    ):
        pytest.skip(err.strip() or "docker daemon is not running")
    assert result.returncode == 0, err
