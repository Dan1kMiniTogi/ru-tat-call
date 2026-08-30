"""HTTP API tests for signaling REST (step 1.1)."""

from pathlib import Path

from fastapi.testclient import TestClient
from ru_tat_call_shared.config import Settings

from signaling_server.app import create_app


def _client(tmp_path: Path) -> TestClient:
    settings = Settings(_env_file=None, sqlite_path=tmp_path / "api.db")
    return TestClient(create_app(settings))


def test_health(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        assert client.get("/health").json() == {"ok": True}


def test_login_me_contacts(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        bad = client.post(
            "/v1/auth/login", json={"identifier": "you", "password": "wrong"}
        )
        assert bad.status_code == 401
        login = client.post(
            "/v1/auth/login", json={"identifier": "you", "password": "family"}
        )
        assert login.status_code == 200
        body = login.json()
        token = body["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        me = client.get("/v1/users/me", headers=headers)
        assert me.status_code == 200
        assert me.json()["user_id"] == "u_you"
        contacts = client.get("/v1/contacts", headers=headers)
        assert contacts.status_code == 200
        ids = {item["user_id"] for item in contacts.json()["items"]}
        assert ids == {"u_mama", "u_sister"}


def test_missing_token(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        assert client.get("/v1/users/me").status_code == 401


def test_groups_and_settings(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        token = client.post(
            "/v1/auth/login", json={"identifier": "you", "password": "family"}
        ).json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        created = client.post("/v1/groups", json={"name": "Family"}, headers=headers)
        assert created.status_code == 200
        group_id = created.json()["group_id"]
        listed = client.get("/v1/groups", headers=headers)
        assert any(g["group_id"] == group_id for g in listed.json()["items"])
        add = client.post(
            f"/v1/groups/{group_id}/members",
            json={"user_id": "u_mama"},
            headers=headers,
        )
        assert add.status_code == 200
        settings = client.get("/v1/transcription/settings", headers=headers)
        assert settings.json()["enabled"] is True
        patched = client.patch(
            "/v1/transcription/settings",
            json={"enabled": False, "store_transcripts": True, "show_speaker_labels": True},
            headers=headers,
        )
        assert patched.json()["enabled"] is False
        assert patched.json()["store_transcripts"] is True
        transcript = client.get("/v1/calls/call_1/transcript", headers=headers)
        assert transcript.status_code == 200
        assert transcript.json()["items"] == []
