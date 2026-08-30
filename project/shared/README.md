# shared

Пакет `ru-tat-call-shared`: Pydantic-контракты REST, signaling, ASR и субтитров.

```python
from ru_tat_call_shared.contracts import LoginRequest, parse_signaling_message, parse_asr_message
from ru_tat_call_shared.config import get_settings
```

Настройки процесса: `get_settings()` читает `project/.env` (см. `project/.env.example`).
