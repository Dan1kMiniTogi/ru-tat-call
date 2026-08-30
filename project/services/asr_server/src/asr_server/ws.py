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

from asr_server.auth import user_id_for_token
from asr_server.buffer import AudioFormatError, StreamSession

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


@ws_router.websocket("/v1/stream")
async def asr_stream(websocket: WebSocket, token: str = Query(...)) -> None:
    """Accept asr.start / asr.audio / asr.stop and keep a PCM buffer (no mock STT yet).

    Query:
        token: Access token from signaling login (same SQLite `sessions` table).

    Client → server: `asr.start`, `asr.audio` (16 kHz mono pcm_s16le), `asr.stop`.
    Server → client: `asr.info` (`session_started`, `chunk_buffered`, `session_stopped`)
    or `asr.error` (`INVALID_TOKEN`, `INVALID_AUDIO_FORMAT`, …).

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
                await websocket.send_json(
                    _info(
                        msg.session_id,
                        "session_started",
                        model_name="buffer",
                        version="0.1",
                    )
                )
            elif isinstance(msg, AsrAudioEvent):
                if session is None or session.session_id != msg.session_id:
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
            elif isinstance(msg, AsrStopEvent):
                if session is None:
                    await websocket.send_json(
                        _error(msg.session_id, ErrorCode.INTERNAL_ERROR, "No active session")
                    )
                    continue
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
            else:
                await websocket.send_json(
                    _error(msg.session_id, ErrorCode.INTERNAL_ERROR, "Unexpected ASR event from client")
                )
    except WebSocketDisconnect:
        return
