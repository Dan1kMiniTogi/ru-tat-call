# ASR: пайплайн, данные, модели

## Роль

Только **аудио → текст** в стриме. Не звонок, не аккаунты, не UI.

Схема: аудио → буфер → нормализация (16 kHz mono PCM) → VAD (желательно) → окна с overlap → streaming inference → постобработка (дубли, склейка, пунктуация без агрессивной «правки» татарского, длина строк) → partial/final.

Сейчас (шаг 4.2): `ASR_ENGINE=remote` + `ASR_REMOTE_URL` (туннель Colab) шлёт PCM на `POST /v1/transcribe`. Без URL остаётся mock. Воркер: `project/apps/colab_asr/`.

Постобработка **не** должна: автопереводить, насильно «очищать» язык, ломать mixed-фразы.

Приоритет качества: **понятность бытового mixed-диалога** важнее академического WER. Отдельно смотреть RU, TT и code-switch.

## Выбор модели (продуктовое решение)

Одна multilingual / mixed-capable модель проще, чем LID + две модели. API model-agnostic: клиент не меняется при смене чекпоинта.

Whisper — быстрый offline/batch baseline и translate, **плохой** кандидат на низкую задержку стрима без отдельной streaming-обвязки.

Для live: streaming ASR (NeMo streaming, Vosk/Kaldi, ONNX wav2vec и т.п.) + чанки порядка **500–1000 мс**. CTC + опционально KenLM — путь тонкой настройки; seq2seq удобнее для пунктуации, хуже для стрима.

Диаризация (pyannote) — **после** MVP, если потоки смешаются. Сейчас label = id потока.

Железо: слабый домашний хост ок для демо; семейный комфорт — средний сервер; GPU — качество и параллелизм. Fine-tune XLS-R 300M в заметках оценивался как 1–2×A100-класса; для infer — ONNX на более слабом GPU/CPU с худшим latency.

Логировать latency/ошибки/нагрузку, **не** сырое аудио и не полные разговоры по умолчанию.

## Датасеты (зафиксированные ссылки)

| Ресурс | Зачем | Ссылка |
| --- | --- | --- |
| **TatSC_ASR** (ISSAI) | Основной ASR-корпус, ~269 ч / ~272k utterances (краудсорс + аудиокниги) | https://huggingface.co/datasets/yasalma/TatSC_ASR |
| **Common Voice Tatar** | Разнообразие голосов, ~28 ч | https://mfa-models.readthedocs.io/en/latest/corpus/Tatar/Common%20Voice%20Tatar%20v7_0.html |
| **TatarTTS** | TTS / аугментация, не прямой ASR (~70 ч) | https://huggingface.co/datasets/issai/TatarTTS |
| **tatar-speech-commands** | Команды, вторично | https://huggingface.co/datasets/issai/tatar-speech-commands |

В GPT-заметках также: текстовые **Tatar News Corpus** и **ttWaC** для LM/пост-обработки; репозитории **TurkicASR** и **Söyle** как возможные примеры пайплайнов. Для звонков критичны **разговорные** данные (шум, короткие фразы, перекрытия, code-switch) — их в открытых корпусах мало, скорее всего понадобится свой сбор.

## Предобученные чекпоинты (список из Notion, не бенчмарк)

Проверены ли они на mixed RU/TT и на стриме — **неизвестно**. Пометки автора: «пока не понял», «нужно ещё поискать».

- https://huggingface.co/anton-l/wav2vec2-large-xlsr-53-tatar
- https://huggingface.co/emre/wav2vec2-large-xlsr-53-W2V2-TATAR-SMALL
- https://huggingface.co/crang/wav2vec2-large-xlsr-53-tatar
- https://huggingface.co/sammy786/wav2vec2-xlsr-tatar

Многие из них крутятся вокруг Common Voice Tatar (~в 10 раз меньше TatSC). Отсюда ранний план качества (декабрь 2025):

1. Поднять готовые модели.
2. Простой интерфейс: голос → субтитры, оценка на своих фразах.
3. Если хватает для быта — идти в продукт (звонок + стрим).
4. Если нет — fine-tune на TatSC (+ CV), снова оценка.

**Не** начинать с долгого дообучения до работающего стримингового пайплайна и звонка.

## Приёмка ML-слоя

Сервер принимает поток; отдаёт partial/final; latency приемлема; auto/mixed не требует UI-переключателя; ошибка ASR не рвёт звонок; модель сменная; крутится на доступном домашнем железе.
