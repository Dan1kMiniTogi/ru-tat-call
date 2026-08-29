"""REST /v1 request and response bodies."""

from typing import Optional

from ru_tat_call_shared.contracts.common import ApiModel


class LoginRequest(ApiModel):
    """POST /v1/auth/login body.

    Args:
        identifier: Email or login.
        password: User password.

    Example:
        LoginRequest(identifier="user@example.com", password="secret")
    """

    identifier: str
    password: str


class LoginResponse(ApiModel):
    """POST /v1/auth/login response."""

    user_id: str
    access_token: str
    refresh_token: str
    expires_in: int


class UserProfile(ApiModel):
    """GET /v1/users/me."""

    user_id: str
    display_name: str
    avatar_url: Optional[str] = None


class ContactItem(ApiModel):
    """One contact in GET /v1/contacts."""

    user_id: str
    display_name: str
    status: str


class ContactsListResponse(ApiModel):
    """GET /v1/contacts."""

    items: list[ContactItem]


class AddContactRequest(ApiModel):
    """POST /v1/contacts."""

    target_user_id: str


class CreateGroupRequest(ApiModel):
    """POST /v1/groups."""

    name: str


class GroupItem(ApiModel):
    """Group row for GET /v1/groups."""

    group_id: str
    name: str


class GroupsListResponse(ApiModel):
    """GET /v1/groups."""

    items: list[GroupItem]


class AddGroupMemberRequest(ApiModel):
    """POST /v1/groups/{group_id}/members."""

    user_id: str


class TranscriptionSettings(ApiModel):
    """GET/PATCH /v1/transcription/settings."""

    enabled: bool
    store_transcripts: bool
    show_speaker_labels: bool


class TranscriptSegment(ApiModel):
    """One stored line from GET /v1/calls/{call_id}/transcript."""

    subtitle_id: str
    speaker_id: str
    speaker_name: str
    text: str
    start_time_ms: Optional[int] = None
    end_time_ms: Optional[int] = None


class TranscriptResponse(ApiModel):
    """GET /v1/calls/{call_id}/transcript when persistence is on."""

    items: list[TranscriptSegment]
