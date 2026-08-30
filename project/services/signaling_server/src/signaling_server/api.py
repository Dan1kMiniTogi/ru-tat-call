"""REST /v1 routes: auth, profile, contacts, groups, transcription settings."""

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from ru_tat_call_shared.contracts.common import ErrorCode
from ru_tat_call_shared.contracts.rest import (
    AddContactRequest,
    AddGroupMemberRequest,
    ContactItem,
    ContactsListResponse,
    CreateGroupRequest,
    GroupItem,
    GroupsListResponse,
    LoginRequest,
    LoginResponse,
    TranscriptionSettings,
    TranscriptResponse,
    UserProfile,
    ClientConfigResponse,
)

from signaling_server.db import Database
from signaling_server.errors import api_error
from signaling_server.public_urls import public_asr_ws_url

router = APIRouter(prefix="/v1")
_bearer = HTTPBearer(auto_error=False)


def _db(request: Request) -> Database:
    return request.app.state.db


def current_user_id(
    request: Request,
    creds: Annotated[Optional[HTTPAuthorizationCredentials], Depends(_bearer)],
) -> str:
    """Require a valid Bearer access token.

    Returns:
        user_id for the session.

    Raises:
        HTTPException: 401 INVALID_TOKEN or TOKEN_EXPIRED.
    """
    if creds is None or creds.scheme.lower() != "bearer":
        raise api_error(401, ErrorCode.INVALID_TOKEN, "Access token is missing")
    user_id = _db(request).user_id_for_token(creds.credentials)
    if user_id is None:
        raise api_error(401, ErrorCode.INVALID_TOKEN, "Access token is invalid or expired")
    return user_id


@router.get("/client-config", response_model=ClientConfigResponse)
def client_config(request: Request) -> ClientConfigResponse:
    """Public bootstrap for the SPA (ASR WebSocket URL).

    Same origin as the page (`/v1/asr-stream`), so one HTTPS tunnel covers UI,
    signaling, and ASR. Override with `ASR_PUBLIC_WS_URL` if ASR is on another host.

    Example:
        GET /v1/client-config → {"asr_ws_url": "wss://host/v1/asr-stream"}
    """
    settings = request.app.state.settings
    return ClientConfigResponse(asr_ws_url=public_asr_ws_url(settings, request))


@router.post("/auth/login", response_model=LoginResponse)
def login(body: LoginRequest, request: Request) -> LoginResponse:
    """Issue tokens for a seeded or existing user."""
    db = _db(request)
    user = db.authenticate(body.identifier, body.password)
    if user is None:
        raise api_error(401, ErrorCode.UNAUTHORIZED, "Invalid identifier or password")
    access, refresh, expires_in = db.create_session(user["user_id"])
    return LoginResponse(
        user_id=user["user_id"],
        access_token=access,
        refresh_token=refresh,
        expires_in=expires_in,
    )


@router.get("/users/me", response_model=UserProfile)
def me(request: Request, user_id: Annotated[str, Depends(current_user_id)]) -> UserProfile:
    """Return the authenticated profile."""
    user = _db(request).get_user(user_id)
    if user is None:
        raise api_error(401, ErrorCode.UNAUTHORIZED, "User no longer exists")
    return UserProfile(
        user_id=user["user_id"],
        display_name=user["display_name"],
        avatar_url=user["avatar_url"],
    )


@router.get("/contacts", response_model=ContactsListResponse)
def list_contacts(
    request: Request, user_id: Annotated[str, Depends(current_user_id)]
) -> ContactsListResponse:
    """List contacts. Presence is `offline` until WebSocket signaling exists."""
    items = [
        ContactItem(user_id=row["user_id"], display_name=row["display_name"], status="offline")
        for row in _db(request).list_contacts(user_id)
    ]
    return ContactsListResponse(items=items)


@router.post("/contacts", response_model=ContactsListResponse)
def add_contact(
    body: AddContactRequest,
    request: Request,
    user_id: Annotated[str, Depends(current_user_id)],
) -> ContactsListResponse:
    """Add a contact by user_id and return the updated list."""
    ok = _db(request).add_contact(user_id, body.target_user_id)
    if not ok:
        raise api_error(404, ErrorCode.INTERNAL_ERROR, "Target user not found")
    return list_contacts(request, user_id)


@router.get("/groups", response_model=GroupsListResponse)
def list_groups(
    request: Request, user_id: Annotated[str, Depends(current_user_id)]
) -> GroupsListResponse:
    """List groups the user can see."""
    items = [
        GroupItem(group_id=row["group_id"], name=row["name"])
        for row in _db(request).list_groups(user_id)
    ]
    return GroupsListResponse(items=items)


@router.post("/groups", response_model=GroupItem)
def create_group(
    body: CreateGroupRequest,
    request: Request,
    user_id: Annotated[str, Depends(current_user_id)],
) -> GroupItem:
    """Create a family group."""
    group_id = _db(request).create_group(user_id, body.name)
    return GroupItem(group_id=group_id, name=body.name)


@router.post("/groups/{group_id}/members")
def add_member(
    group_id: str,
    body: AddGroupMemberRequest,
    request: Request,
    user_id: Annotated[str, Depends(current_user_id)],
) -> dict:
    """Add a member to a group the caller can access (any member for MVP)."""
    db = _db(request)
    groups = {row["group_id"] for row in db.list_groups(user_id)}
    if group_id not in groups:
        raise api_error(404, ErrorCode.ROOM_NOT_FOUND, "Group not found")
    result = db.add_group_member(group_id, body.user_id)
    if result == "missing_user":
        raise api_error(404, ErrorCode.INTERNAL_ERROR, "User not found")
    if result == "missing_group":
        raise api_error(404, ErrorCode.ROOM_NOT_FOUND, "Group not found")
    return {"ok": True}


@router.get("/transcription/settings", response_model=TranscriptionSettings)
def get_transcription_settings(
    request: Request, user_id: Annotated[str, Depends(current_user_id)]
) -> TranscriptionSettings:
    """Return subtitle preferences."""
    row = _db(request).get_settings(user_id)
    return TranscriptionSettings(
        enabled=bool(row["enabled"]),
        store_transcripts=bool(row["store_transcripts"]),
        show_speaker_labels=bool(row["show_speaker_labels"]),
    )


@router.patch("/transcription/settings", response_model=TranscriptionSettings)
def patch_transcription_settings(
    body: TranscriptionSettings,
    request: Request,
    user_id: Annotated[str, Depends(current_user_id)],
) -> TranscriptionSettings:
    """Replace subtitle preferences."""
    row = _db(request).patch_settings(
        user_id, body.enabled, body.store_transcripts, body.show_speaker_labels
    )
    return TranscriptionSettings(
        enabled=bool(row["enabled"]),
        store_transcripts=bool(row["store_transcripts"]),
        show_speaker_labels=bool(row["show_speaker_labels"]),
    )


@router.get("/calls/{call_id}/transcript", response_model=TranscriptResponse)
def get_transcript(
    call_id: str,
    request: Request,
    user_id: Annotated[str, Depends(current_user_id)],
) -> TranscriptResponse:
    """Transcript history is empty until persistence is enabled in a later step."""
    _ = call_id, user_id, request
    return TranscriptResponse(items=[])
