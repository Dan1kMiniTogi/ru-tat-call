"""Internal HTTP used by the ASR process (not the family client)."""

from typing import Annotated

from fastapi import APIRouter, Header, Request
from ru_tat_call_shared.contracts.common import ErrorCode
from ru_tat_call_shared.contracts.subtitles import SubtitleUpdateEvent

from signaling_server.errors import api_error
from signaling_server.security import tokens_match

internal_router = APIRouter(prefix="/v1/internal")


@internal_router.post("/subtitles")
async def push_subtitle(
    body: SubtitleUpdateEvent,
    request: Request,
    x_internal_token: Annotated[str | None, Header()] = None,
) -> dict:
    """Fan-out `subtitle.update` to members of `body.room_id`.

    Auth: header `X-Internal-Token` must equal `SECRET_KEY`. ASR failure to
    reach this endpoint must not drop the call; this handler never touches media.

    Args:
        body: Subtitle event (same JSON the client UI consumes).
        request: FastAPI request (rooms + settings).
        x_internal_token: Shared secret from the ASR publisher.

    Returns:
        `{ok, delivered}` where delivered is the number of live sockets sent to.

    Example:
        POST /v1/internal/subtitles
        X-Internal-Token: dev-only-change-me
    """
    expected = request.app.state.settings.secret_key
    if x_internal_token is None or not tokens_match(x_internal_token, expected):
        raise api_error(401, ErrorCode.UNAUTHORIZED, "Internal token is invalid")
    delivered = await request.app.state.rooms.broadcast_subtitle(body)
    return {"ok": True, "delivered": delivered}
