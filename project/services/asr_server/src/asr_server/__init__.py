"""Streaming ASR server: PCM buffer over WebSocket (mock STT in step 2.2).

Run from `project/`:

    uv run uvicorn asr_server.app:app --host 0.0.0.0 --port 8001

Auth uses the same SQLite `sessions` table as signaling (`SQLITE_PATH`).
"""

__version__ = "0.1.0"
