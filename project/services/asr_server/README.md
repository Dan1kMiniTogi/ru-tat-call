# asr_server

Потоковый ASR: VAD → `ASREngine` (`mock` / заглушки `remote` и `local`).

```bash
cd project
uv run uvicorn signaling_server.app:app --host 0.0.0.0 --port 8000
uv run uvicorn asr_server.app:app --host 0.0.0.0 --port 8001
```

`ASR_ENGINE=mock` (по умолчанию). `remote` нужен `ASR_REMOTE_URL`, `local` — `ASR_ONNX_PATH`; иначе снова mock. Инференс Colab/ONNX — фаза 4.
