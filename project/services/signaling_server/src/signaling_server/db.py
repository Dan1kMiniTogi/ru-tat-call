"""SQLite persistence for users, sessions, contacts, groups and transcription settings."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from signaling_server.security import hash_password, new_token, verify_password

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    identifier TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    display_name TEXT NOT NULL,
    avatar_url TEXT
);

CREATE TABLE IF NOT EXISTS sessions (
    access_token TEXT PRIMARY KEY,
    refresh_token TEXT NOT NULL UNIQUE,
    user_id TEXT NOT NULL REFERENCES users(user_id),
    expires_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS contacts (
    owner_id TEXT NOT NULL REFERENCES users(user_id),
    target_id TEXT NOT NULL REFERENCES users(user_id),
    PRIMARY KEY (owner_id, target_id)
);

CREATE TABLE IF NOT EXISTS groups (
    group_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    owner_id TEXT NOT NULL REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS group_members (
    group_id TEXT NOT NULL REFERENCES groups(group_id),
    user_id TEXT NOT NULL REFERENCES users(user_id),
    PRIMARY KEY (group_id, user_id)
);

CREATE TABLE IF NOT EXISTS transcription_settings (
    user_id TEXT PRIMARY KEY REFERENCES users(user_id),
    enabled INTEGER NOT NULL DEFAULT 1,
    store_transcripts INTEGER NOT NULL DEFAULT 0,
    show_speaker_labels INTEGER NOT NULL DEFAULT 1
);
"""

_SEED_USERS = (
    ("u_you", "you", "family", "Ты"),
    ("u_mama", "mama", "family", "Mama"),
    ("u_sister", "sister", "family", "Сестра"),
)

TOKEN_TTL_SECONDS = 3600


class Database:
    """Thin sqlite3 wrapper used by the signaling REST API.

    Args:
        path: File path or `:memory:`. Parent dirs are created for file DBs.

    Example:
        db = Database(Path("/tmp/app.db"))
        db.init_schema()
        db.seed_family_if_empty()
    """

    def __init__(self, path: Path | str) -> None:
        raw = str(path)
        if raw == ":memory:":
            self.path = ":memory:"
            uri = ":memory:"
        else:
            self.path = Path(path)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            uri = str(self.path)
        self._conn = sqlite3.connect(uri, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")

    def init_schema(self) -> None:
        """Create tables if they do not exist."""
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def seed_family_if_empty(self) -> None:
        """Insert demo family users and mutual contacts when the DB is empty.

        Logins: `you` / `mama` / `sister`, password `family`.
        """
        count = self._conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]
        if count:
            return
        for user_id, identifier, password, display_name in _SEED_USERS:
            self._conn.execute(
                "INSERT INTO users (user_id, identifier, password_hash, display_name) VALUES (?, ?, ?, ?)",
                (user_id, identifier, hash_password(password), display_name),
            )
            self._conn.execute(
                """INSERT INTO transcription_settings
                   (user_id, enabled, store_transcripts, show_speaker_labels)
                   VALUES (?, 1, 0, 1)""",
                (user_id,),
            )
        pairs = (("u_you", "u_mama"), ("u_you", "u_sister"), ("u_mama", "u_you"), ("u_sister", "u_you"))
        for owner, target in pairs:
            self._conn.execute(
                "INSERT INTO contacts (owner_id, target_id) VALUES (?, ?)",
                (owner, target),
            )
        self._conn.commit()

    def get_user_by_identifier(self, identifier: str) -> Optional[sqlite3.Row]:
        """Look up a user by login/email."""
        return self._conn.execute(
            "SELECT * FROM users WHERE identifier = ?", (identifier,)
        ).fetchone()

    def get_user(self, user_id: str) -> Optional[sqlite3.Row]:
        """Look up a user by id."""
        return self._conn.execute(
            "SELECT * FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()

    def authenticate(self, identifier: str, password: str) -> Optional[sqlite3.Row]:
        """Return the user row if identifier and password match."""
        user = self.get_user_by_identifier(identifier)
        if user is None or not verify_password(password, user["password_hash"]):
            return None
        return user

    def create_session(self, user_id: str) -> tuple[str, str, int]:
        """Store a new access/refresh pair.

        Returns:
            (access_token, refresh_token, expires_in_seconds)
        """
        access = new_token()
        refresh = new_token()
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=TOKEN_TTL_SECONDS)
        self._conn.execute(
            "INSERT INTO sessions (access_token, refresh_token, user_id, expires_at) VALUES (?, ?, ?, ?)",
            (access, refresh, user_id, expires_at.isoformat()),
        )
        self._conn.commit()
        return access, refresh, TOKEN_TTL_SECONDS

    def user_id_for_token(self, access_token: str) -> Optional[str]:
        """Resolve a still-valid access token to a user_id."""
        row = self._conn.execute(
            "SELECT user_id, expires_at FROM sessions WHERE access_token = ?",
            (access_token,),
        ).fetchone()
        if row is None:
            return None
        expires = datetime.fromisoformat(row["expires_at"])
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if expires < datetime.now(timezone.utc):
            return None
        return row["user_id"]

    def list_contacts(self, owner_id: str) -> list[sqlite3.Row]:
        """Contacts of owner with display names (status is always offline until signaling WS)."""
        return list(
            self._conn.execute(
                """SELECT u.user_id, u.display_name
                   FROM contacts c JOIN users u ON u.user_id = c.target_id
                   WHERE c.owner_id = ? ORDER BY u.display_name""",
                (owner_id,),
            ).fetchall()
        )

    def add_contact(self, owner_id: str, target_id: str) -> bool:
        """Add a contact. Returns False if target does not exist.

        Args:
            owner_id: Current user.
            target_id: User to add.
        """
        if owner_id == target_id:
            return False
        if self.get_user(target_id) is None:
            return False
        self._conn.execute(
            "INSERT OR IGNORE INTO contacts (owner_id, target_id) VALUES (?, ?)",
            (owner_id, target_id),
        )
        self._conn.commit()
        return True

    def list_groups(self, user_id: str) -> list[sqlite3.Row]:
        """Groups the user owns or belongs to."""
        return list(
            self._conn.execute(
                """SELECT DISTINCT g.group_id, g.name
                   FROM groups g
                   LEFT JOIN group_members m ON m.group_id = g.group_id
                   WHERE g.owner_id = ? OR m.user_id = ?
                   ORDER BY g.name""",
                (user_id, user_id),
            ).fetchall()
        )

    def create_group(self, owner_id: str, name: str) -> str:
        """Create a group, add owner as member, return group_id."""
        group_id = f"g_{new_token()[:12]}"
        self._conn.execute(
            "INSERT INTO groups (group_id, name, owner_id) VALUES (?, ?, ?)",
            (group_id, name, owner_id),
        )
        self._conn.execute(
            "INSERT INTO group_members (group_id, user_id) VALUES (?, ?)",
            (group_id, owner_id),
        )
        self._conn.commit()
        return group_id

    def add_group_member(self, group_id: str, user_id: str) -> str:
        """Add a member. Returns ok | missing_group | missing_user."""
        group = self._conn.execute(
            "SELECT group_id FROM groups WHERE group_id = ?", (group_id,)
        ).fetchone()
        if group is None:
            return "missing_group"
        if self.get_user(user_id) is None:
            return "missing_user"
        self._conn.execute(
            "INSERT OR IGNORE INTO group_members (group_id, user_id) VALUES (?, ?)",
            (group_id, user_id),
        )
        self._conn.commit()
        return "ok"

    def get_settings(self, user_id: str) -> sqlite3.Row:
        """Transcription settings, inserting defaults if missing."""
        row = self._conn.execute(
            "SELECT * FROM transcription_settings WHERE user_id = ?", (user_id,)
        ).fetchone()
        if row is not None:
            return row
        self._conn.execute(
            """INSERT INTO transcription_settings
               (user_id, enabled, store_transcripts, show_speaker_labels)
               VALUES (?, 1, 0, 1)""",
            (user_id,),
        )
        self._conn.commit()
        return self._conn.execute(
            "SELECT * FROM transcription_settings WHERE user_id = ?", (user_id,)
        ).fetchone()

    def patch_settings(
        self,
        user_id: str,
        enabled: bool,
        store_transcripts: bool,
        show_speaker_labels: bool,
    ) -> sqlite3.Row:
        """Replace transcription settings for the user."""
        self.get_settings(user_id)
        self._conn.execute(
            """UPDATE transcription_settings
               SET enabled = ?, store_transcripts = ?, show_speaker_labels = ?
               WHERE user_id = ?""",
            (int(enabled), int(store_transcripts), int(show_speaker_labels), user_id),
        )
        self._conn.commit()
        return self.get_settings(user_id)

    def close(self) -> None:
        """Close the connection."""
        self._conn.close()
