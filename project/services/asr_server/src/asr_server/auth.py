"""Validate ASR access tokens against the shared signaling SQLite sessions table."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


def user_id_for_token(sqlite_path: Path, access_token: str) -> Optional[str]:
    """Return user_id if the access token is present and not expired.

    Args:
        sqlite_path: Same DB as signaling (`SQLITE_PATH`).
        access_token: Bearer token from the query string.

    Returns:
        user_id or None.

    Example:
        uid = user_id_for_token(Path("data/app.db"), token)
    """
    if not sqlite_path.is_file():
        return None
    conn = sqlite3.connect(str(sqlite_path))
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT user_id, expires_at FROM sessions WHERE access_token = ?",
            (access_token,),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    expires = datetime.fromisoformat(row["expires_at"])
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires < datetime.now(timezone.utc):
        return None
    return row["user_id"]
