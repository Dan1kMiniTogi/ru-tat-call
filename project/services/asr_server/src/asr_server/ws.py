"""ASR streaming WebSocket: `/v1/stream?token=ACCESS_TOKEN`."""

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from pydantic import ValidationError
from ru_tat_call_shared.contracts.asr import (
    AsrAudioEvent,
    AsrErrorEvent,
    AsrErrorPayload,
    AsrInfoEvent,
    AsrInfoPayload,
    AsrStartEvent,
    AsrStopEvent,
    parse_asr_message,
)
from ru_tat_call_shared.contracts.common import ErrorCode
from ru_tat_call_shared.config import Settings

from asr_server.auth import display_name_for_user, user_id_for_token
from asr_server.buffer import AudioFormatError, StreamSession
from asr_server.mock_engine import MockEngine, MockUtterance, to_asr_event, to_subtitle_event

ws_router = APIRouter()


def _dump(model) -> dict:
    return model.model_dump(mode="json")


def _error(session_id: str, code: ErrorCode, message: str) -> dict:
    return _dump(
        AsrErrorEvent(
            type="asr.error",
            session_id=session_id,
            payload=AsrErrorPayload(code=code, message=message),
        )
    )


def _info(
    session_id: str,
    message: str,
    *,
    model_name: str | None = None,
    version: str | None = None,
    chunk_bytes: int | None = None,
    buffered_bytes: int | None = None,
) -> dict:
    return _dump(
        AsrInfoEvent(
            type="asr.info",
            session_id=session_id,
            payload=AsrInfoPayload(
                message=message,
                model_name=model_name,
                version=version,
                chunk_bytes=chunk_bytes,
                buffered_bytes=buffered_bytes,
            ),
        )
    )


async def _emit_mock(
    websocket: WebSocket,
    session: StreamSession,
    speaker_name: str,
    utterances: list[MockUtterance],
) -> None:
    """Send asr.partial/final and try to fan-out subtitle.update.

    Args:
        websocket: ASR client socket.
        session: Active stream (room_id, user_id, session_id).
        speaker_name: Label for the overlay (may be empty).
        utterances: Steps from MockEngine.
    """
    publisher = websocket.app.state.subtitle_publisher
    for utt in utterances:
        await websocket.send_json(
            _dump(to_asr_event(session.session_id, session.user_id, speaker_name, utt))
        )
        await publisher.publish(
            to_subtitle_event(session.room_id, session.user_id, speaker_name, utt)
        )


@ws_router.websocket("/v1/stream")
async def asr_stream(websocket: WebSocket, token: str = Query(...)) -> None:
    """Accept PCM, run the mock engine, emit transcripts (call stays up if publish fails).

    Query:
        token: Access token from signaling login (same SQLite `sessions` table).

    Client → server: `asr.start`, `asr.audio` (16 kHz mono pcm_s16le), `asr.stop`.
    Server → client: `asr.info`, `asr.partial`, `asr.final`, or `asr.error`.
    Signaling members also get `subtitle.update` via `SIGNALING_INTERNAL_URL`.

    Example:
        ws://127.0.0.1:8001/v1/stream?token=ACCESS_TOKEN
    """
    await websocket.accept()
    settings: Settings = websocket.app.state.settings
    user_id = user_id_for_token(settings.sqlite_path, token)
    if user_id is None:
        await websocket.send_json(_error("auth", ErrorCode.INVALID_TOKEN, "Access token is invalid or expired"))
        await websocket.close()
        return

    session: StreamSession | None = None
    engine: MockEngine | None = None
    speaker_name = display_name_for_user(settings.sqlite_path, user_id)
    try:
        while True:
            raw = await websocket.receive_json()
            if not isinstance(raw, dict):
                continue
            sid = str(raw.get("session_id") or "unknown")
            try:
                msg = parse_asr_message(raw)
            except ValidationError:
                await websocket.send_json(
                    _error(sid, ErrorCode.INTERNAL_ERROR, "Invalid ASR message")
                )
                continue
            if isinstance(msg, AsrStartEvent):
                session = StreamSession(session_id=msg.session_id, user_id=user_id)
                session.start(msg.payload)
                engine = MockEngine(
                    return_partial=msg.payload.return_partial,
                    return_final=msg.payload.return_final,
                )
                if msg.payload.speaker_labels:
                    speaker_name = display_name_for_user(settings.sqlite_path, user_id)
                else:
                    speaker_name = ""
                await websocket.send_json(
                    _info(
                        msg.session_id,
                        "session_started",
                        model_name="mock",
                        version="0.1",
                    )
                )
            elif isinstance(msg, AsrAudioEvent):
                if session is None or engine is None or session.session_id != msg.session_id:
                    await websocket.send_json(
                        _error(msg.session_id, ErrorCode.INTERNAL_ERROR, "Call asr.start first")
                    )
                    continue
                try:
                    added = session.append_audio(msg.payload)
                except AudioFormatError as exc:
                    await websocket.send_json(
                        _error(msg.session_id, ErrorCode.INVALID_AUDIO_FORMAT, str(exc))
                    )
                    continue
                await websocket.send_json(
                    _info(
                        msg.session_id,
                        "chunk_buffered",
                        chunk_bytes=added,
                        buffered_bytes=len(session.pcm),
                    )
                )
                await _emit_mock(websocket, session, speaker_name, engine.feed(added))
            elif isinstance(msg, AsrStopEvent):
                if session is None or engine is None:
                    await websocket.send_json(
                        _error(msg.session_id, ErrorCode.INTERNAL_ERROR, "No active session")
                    )
                    continue
                await _emit_mock(websocket, session, speaker_name, engine.flush())
                total = session.stop()
                await websocket.send_json(
                    _info(
                        msg.session_id,
                        "session_stopped",
                        buffered_bytes=total,
                        version="0.1",
                    )
                )
                session = None
                engine = None
            else:
                await websocket.send_json(
                    _error(msg.session_id, ErrorCode.INTERNAL_ERROR, "Unexpected ASR event from client")
                )
    except WebSocketDisconnect:
        return
