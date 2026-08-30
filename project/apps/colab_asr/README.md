# Colab / Kaggle ASR worker

HTTP-воркер для GPU (шаг 4.1). Ноутбук (`RemoteColabASREngine`, шаг 4.2) шлёт PCM на:

`POST /v1/transcribe` — PCM 16 kHz s16le (base64) → `{text, language, is_final}`.

После туннеля в `project/.env`:

```
ASR_ENGINE=remote
ASR_REMOTE_URL=https://ВАШ-ТУННЕЛЬ
```

Чекпоинты по умолчанию (список из `context/asr.md`): `anton-l/wav2vec2-large-xlsr-53-tatar`, `openai/whisper-small`.

## Colab

1. Открой [`colab_asr_worker.ipynb`](colab_asr_worker.ipynb) в Google Colab, runtime **GPU**.
2. Прогони ячейки. Публичный URL (ngrok или cloudflared) = `ASR_REMOTE_URL`.
3. Токен ngrok, если нужен, клади в Colab Secrets `NGROK_AUTHTOKEN` — в git и в чат не копируй.

Локальный smoke без GPU:

```bash
cd project/apps/colab_asr
python worker.py --backend dummy --port 8090
curl -s http://127.0.0.1:8090/health
```
