"""Node self-test for web_client PCM helpers (step 3.3)."""

import shutil
import subprocess

import pytest
from ru_tat_call_shared.config import PROJECT_ROOT


def test_pcm_js_syntax_and_downsample() -> None:
    """node --check on capture scripts; downsample 48 kHz → 16 kHz length."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    js_dir = PROJECT_ROOT / "web_client" / "js"
    for name in (
        "pcm.js",
        "asr.js",
        "pcm-capture.js",
        "pcm-worklet.js",
        "call.js",
        "app.js",
        "subtitles.js",
        "reconnect.js",
    ):
        subprocess.run([node, "--check", str(js_dir / name)], check=True)
    selftest = PROJECT_ROOT / "tests" / "js" / "pcm_selftest.js"
    result = subprocess.run(
        [node, str(selftest), str(js_dir / "pcm.js")],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    recon = subprocess.run(
        [
            node,
            str(PROJECT_ROOT / "tests" / "js" / "reconnect_selftest.js"),
            str(js_dir / "reconnect.js"),
        ],
        capture_output=True,
        text=True,
    )
    assert recon.returncode == 0, recon.stderr or recon.stdout
