"""Latency harness for RemoteColabASREngine on mixed RU/TT phrases (step 4.3).

Default: in-process dummy worker (no GPU). Optional `--url` hits a live tunnel.

Example:
    cd project
    uv run python apps/colab_asr/benchmark.py
    uv run python apps/colab_asr/benchmark.py --url http://127.0.0.1:8090
"""

from __future__ import annotations

import argparse
import json
import math
import struct
import sys
import time
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "apps" / "colab_asr"))
sys.path.insert(0, str(ROOT / "services" / "asr_server" / "src"))

from phrases import DUMMY_TEXT, PHRASES  # noqa: E402


def pcm_s16le_tone(duration_ms: int, sample_rate: int = 16000) -> bytes:
    """Build mono s16le PCM (quiet 220 Hz tone) of a given duration.

    Args:
        duration_ms: Length in milliseconds (product chunks are 500–1000 ms).
        sample_rate: Samples per second (worker expects 16000).

    Returns:
        Little-endian int16 bytes.

    Example:
        len(pcm_s16le_tone(500)) == 16000
    """
    n = max(0, sample_rate * duration_ms // 1000)
    amp = 0.08
    freq = 220.0
    out = bytearray()
    for i in range(n):
        sample = amp * math.sin(2.0 * math.pi * freq * i / sample_rate)
        value = int(max(-1.0, min(1.0, sample)) * 32767)
        out += struct.pack("<h", value)
    return bytes(out)


def percentile_ms(values: list[float], p: float) -> float:
    """Nearest-rank percentile.

    Args:
        values: Milliseconds.
        p: 0–100.

    Returns:
        Percentile value; 0.0 if empty.

    Example:
        percentile_ms([10.0, 20.0, 30.0], 50) == 20.0
    """
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (p / 100.0) * (len(ordered) - 1)
    lo = int(math.floor(rank))
    hi = int(math.ceil(rank))
    if lo == hi:
        return ordered[lo]
    frac = rank - lo
    return ordered[lo] * (1.0 - frac) + ordered[hi] * frac


def dummy_http_client():
    """Starlette TestClient wrapped as httpx-like `.post` for the dummy worker.

    Returns:
        Object with `post(url, json=, headers=)`.
    """
    from fastapi.testclient import TestClient

    from worker import DummyRecognizer, create_app

    app = create_app(DummyRecognizer())
    inner = TestClient(app)

    class _Shim:
        def post(self, url: str, json=None, headers=None):
            path = "/" + url.split("://", 1)[-1].split("/", 1)[-1]
            if not path.startswith("/v1/"):
                path = "/v1/transcribe"
            return inner.post(path, json=json, headers=headers)

    return _Shim()


def make_engine(url: str = "", token: str = ""):
    """Build RemoteColabASREngine against dummy (empty url) or a live origin.

    Args:
        url: Colab/ngrok origin; empty uses in-process dummy.
        token: Optional X-Worker-Token.

    Returns:
        RemoteColabASREngine
    """
    from asr_server.engine import RemoteColabASREngine

    if url.strip():
        return RemoteColabASREngine(url.strip(), worker_token=token.strip())
    return RemoteColabASREngine("http://dummy.local", http_client=dummy_http_client())


def run_bench(
    *,
    url: str = "",
    token: str = "",
    duration_ms: int = 500,
    repeats: int = 1,
) -> dict[str, Any]:
    """Time `feed()` once per phrase (and optional repeats).

    Args:
        url: Live worker origin or empty for dummy.
        token: Optional worker token.
        duration_ms: Synthetic PCM length.
        repeats: Extra passes after the first (warmup is the first phrase).

    Returns:
        JSON-serializable report with per-phrase ms and p50/p95.

    Example:
        report = run_bench(duration_ms=500)
        report["p50_ms"] < 1000
    """
    engine = make_engine(url, token)
    pcm = pcm_s16le_tone(duration_ms)
    rows: list[dict[str, Any]] = []
    times: list[float] = []
    for phrase in PHRASES:
        for _ in range(max(1, repeats)):
            t0 = time.perf_counter()
            utts = engine.feed(pcm)
            ms = (time.perf_counter() - t0) * 1000.0
            times.append(ms)
            hyp = utts[0].text if utts else ""
            rows.append(
                {
                    "phrase_id": phrase.phrase_id,
                    "language": phrase.language,
                    "reference": phrase.text,
                    "hypothesis": hyp,
                    "latency_ms": round(ms, 2),
                    "ok": bool(hyp),
                }
            )
    return {
        "backend": "remote-url" if url.strip() else "dummy",
        "duration_ms": duration_ms,
        "pcm_bytes": len(pcm),
        "dummy_text": DUMMY_TEXT,
        "p50_ms": round(percentile_ms(times, 50), 2),
        "p95_ms": round(percentile_ms(times, 95), 2),
        "max_ms": round(max(times) if times else 0.0, 2),
        "rows": rows,
    }


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    """CLI flags.

    Args:
        argv: Optional argument list.

    Returns:
        Parsed namespace.
    """
    parser = argparse.ArgumentParser(description="ASR latency bench (mixed RU/TT phrases)")
    parser.add_argument("--url", default="", help="Live worker origin (empty = dummy)")
    parser.add_argument("--token", default="", help="X-Worker-Token")
    parser.add_argument("--duration-ms", type=int, default=500)
    parser.add_argument("--repeats", type=int, default=1)
    return parser.parse_args(argv)


def main() -> None:
    """Print a JSON latency report to stdout.

    Example:
        python apps/colab_asr/benchmark.py --duration-ms 500
    """
    args = parse_args()
    report = run_bench(
        url=args.url,
        token=args.token,
        duration_ms=args.duration_ms,
        repeats=args.repeats,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
