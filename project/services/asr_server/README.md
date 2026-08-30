# asr_server

Потоковый ASR: VAD → `ASREngine` (`mock` / заглушки `remote` и `local`).

```bash
cd project
uv run uvicorn signaling_server.app:app --host 0.0.0.0 --port 8000
uv run uvicorn asr_server.app:app --host 0.0.0.0 --port 8001
```

`ASR_ENGINE=mock` по умолчанию. Живой Colab: `ASR_ENGINE=remote` и `ASR_REMOTE_URL` (URL из ноутбука `apps/colab_asr`). Опционально `ASR_REMOTE_TOKEN` = worker `--token`. Без URL — снова mock.
