"""Runtime settings loaded from environment and optional `project/.env`.

Example:
    from ru_tat_call_shared.config import get_settings
    settings = get_settings()
    print(settings.signaling_port, settings.cors_origin_list)
"""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[3]
"""Directory that contains `pyproject.toml` of the uv workspace (`project/`)."""

_DEFAULT_CORS = "http://localhost:8000,http://127.0.0.1:8000"


class Settings(BaseSettings):
    """Process-wide config for signaling, ASR, CORS and static files.

    Values come from environment variables (and `project/.env` if present).
    Unknown keys are ignored so extra tools can share the same file.

    Attributes:
        signaling_host: Bind address for the signaling HTTP/WS server.
        signaling_port: Port for signaling (also serves `web_client` later).
        asr_host: Bind address for the ASR WebSocket server.
        asr_port: Port for ASR streaming.
        cors_origins: Comma-separated browser origins allowed by CORS.
        sqlite_path: SQLite file for users/contacts (created in step 1.x).
        web_client_dir: Directory with the HTML/JS client.
        secret_key: HMAC/session secret; override in `.env` before any deploy.
        asr_engine: `mock` until a real engine is wired (step 2/4).
        asr_remote_url: Optional Colab/ngrok base URL for remote ASR.
        signaling_internal_url: Base URL ASR uses to POST `subtitle.update` into rooms.
        max_participants: Hard cap for a room (product MVP: 4).
    """

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    signaling_host: str = "0.0.0.0"
    signaling_port: int = Field(default=8000, ge=1, le=65535)
    asr_host: str = "0.0.0.0"
    asr_port: int = Field(default=8001, ge=1, le=65535)
    cors_origins: str = _DEFAULT_CORS
    sqlite_path: Path = PROJECT_ROOT / "data" / "app.db"
    web_client_dir: Path = PROJECT_ROOT / "web_client"
    secret_key: str = "dev-only-change-me"
    asr_engine: str = "mock"
    asr_remote_url: str = ""
    signaling_internal_url: str = "http://127.0.0.1:8000"
    max_participants: int = Field(default=4, ge=2, le=4)

    @field_validator("sqlite_path", "web_client_dir", mode="before")
    @classmethod
    def _expand_path(cls, value: object) -> object:
        """Resolve `~` and relative paths against the workspace root.

        Args:
            value: Raw env string or Path.

        Returns:
            Absolute Path, or the original value if empty/non-string.
        """
        if value is None or value == "":
            return value
        path = Path(str(value)).expanduser()
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        return path

    @property
    def cors_origin_list(self) -> list[str]:
        """CORS origins as a list for FastAPI `CORSMiddleware`.

        Returns:
            Non-empty stripped origin URLs.

        Example:
            Settings(cors_origins="http://a,http://b").cors_origin_list
        """
        return [part.strip() for part in self.cors_origins.split(",") if part.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings instance.

    Returns:
        Process-wide settings. Call `clear_settings_cache` in tests after env changes.

    Example:
        port = get_settings().signaling_port
    """
    return Settings()


def clear_settings_cache() -> None:
    """Drop the cached settings (use in tests)."""
    get_settings.cache_clear()
