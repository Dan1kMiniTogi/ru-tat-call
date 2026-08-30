"""Mixed-phrase latency harness (step 4.3). Dummy worker only in CI."""

import json
import os
import subprocess
import sys

import pytest
from ru_tat_call_shared.config import PROJECT_ROOT

sys.path.insert(0, str(PROJECT_ROOT / "apps" / "colab_asr"))

from benchmark import pcm_s16le_tone, percentile_ms, run_bench  # noqa: E402
from phrases import PHRASES  # noqa: E402


def test_phrase_set_covers_ru_tt_mixed() -> None:
    langs = {p.language for p in PHRASES}
    assert langs == {"ru", "tt", "mixed"}
    assert any("Әни" in p.text and "сегодня" in p.text for p in PHRASES)


def test_pcm_500ms_is_16k_s16le() -> None:
    pcm = pcm_s16le_tone(500)
    assert len(pcm) == 16000
    assert len(pcm) % 2 == 0


def test_dummy_latency_p95_under_one_second() -> None:
    """In-process dummy must stay well under a live GPU budget; no invented Colab numbers."""
    report = run_bench(duration_ms=500, repeats=1)
    assert report["backend"] == "dummy"
    assert report["p50_ms"] < 1000
    assert report["p95_ms"] < 1000
    assert all(row["ok"] for row in report["rows"])
    mixed = next(r for r in report["rows"] if r["phrase_id"] == "mixed_home")
    assert "Әни" in mixed["hypothesis"]


def test_percentile_helper() -> None:
    assert percentile_ms([10.0, 20.0, 30.0], 50) == 20.0
    assert percentile_ms([], 50) == 0.0


def test_cli_dummy_json() -> None:
    script = PROJECT_ROOT / "apps" / "colab_asr" / "benchmark.py"
    result = subprocess.run(
        [sys.executable, str(script), "--duration-ms", "500"],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        check=True,
    )
    body = json.loads(result.stdout)
    assert body["backend"] == "dummy"
    assert len(body["rows"]) == len(PHRASES)


@pytest.mark.skipif(not os.environ.get("ASR_REMOTE_URL"), reason="no live ASR_REMOTE_URL")
def test_live_remote_optional() -> None:
    """Only runs when the operator sets ASR_REMOTE_URL; does not assert WER."""
    url = os.environ["ASR_REMOTE_URL"]
    token = os.environ.get("ASR_REMOTE_TOKEN", "")
    report = run_bench(url=url, token=token, duration_ms=500, repeats=1)
    assert report["backend"] == "remote-url"
    assert report["rows"]
