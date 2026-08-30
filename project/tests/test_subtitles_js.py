"""Node self-test for live subtitle store (step 3.4)."""

import shutil
import subprocess

import pytest
from ru_tat_call_shared.config import PROJECT_ROOT


def test_subtitles_js_store() -> None:
    """node --check plus in-place partial / frozen final / max rows."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    path = PROJECT_ROOT / "web_client" / "js" / "subtitles.js"
    subprocess.run([node, "--check", str(path)], check=True)
    selftest = PROJECT_ROOT / "tests" / "js" / "subtitles_selftest.js"
    result = subprocess.run(
        [node, str(selftest), str(path)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr or result.stdout
