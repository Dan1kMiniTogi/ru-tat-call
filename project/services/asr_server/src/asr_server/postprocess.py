"""Light transcript cleanup: glue, de-stutter, light punctuation. No translation.

Must not latinize Tatar, rewrite mixed phrases, or auto-translate.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Optional

from asr_server.engine import TranscriptUtterance

MAX_CHARS = 320
_END_PUNCT = frozenset(".?!…;:")


def collapse_ws(text: str) -> str:
    """Squeeze whitespace; keep letters and punctuation as-is.

    Args:
        text: Raw recognizer string.

    Returns:
        Stripped text with single spaces.

    Example:
        collapse_ws("  Әни,   сегодня  ") == "Әни, сегодня"
    """
    return " ".join(text.split())


def collapse_repeated_words(text: str) -> str:
    """Drop consecutive identical tokens (stutter). Does not merge distinct words.

    Args:
        text: Already whitespace-normalized.

    Returns:
        Text without immediate token repeats.

    Example:
        collapse_repeated_words("килдем килдем мама") == "килдем мама"
    """
    words = text.split(" ")
    out: list[str] = []
    for word in words:
        if not word:
            continue
        if out and out[-1] == word:
            continue
        out.append(word)
    return " ".join(out)


def stitch(prev: str, nxt: str) -> str:
    """Join a growing hypothesis: prefix grow, overlap glue, never shrink.

    Args:
        prev: Previous text for the same subtitle_id.
        nxt: New hypothesis.

    Returns:
        Combined string.

    Example:
        stitch("Әни,", "Әни, сегодня") == "Әни, сегодня"
        stitch("сегодня я", "я дома") == "сегодня я дома"
    """
    if not prev:
        return nxt
    if not nxt:
        return prev
    if nxt.startswith(prev):
        return nxt
    if prev.startswith(nxt):
        return prev
    max_ov = min(len(prev), len(nxt))
    for k in range(max_ov, 0, -1):
        if prev[-k:] == nxt[:k]:
            return prev + nxt[k:]
    return collapse_ws(prev + " " + nxt)


def ensure_final_punct(text: str) -> str:
    """Add a period on finals that end with a letter. Do not touch existing punct.

    Args:
        text: Hypothesis.

    Returns:
        Text, possibly with a trailing `.`

    Example:
        ensure_final_punct("Кичә килдем") == "Кичә килдем."
        ensure_final_punct("Әни,") == "Әни,"
    """
    if not text:
        return text
    last = text[-1]
    if last in _END_PUNCT or last in ",)]":
        return text
    if last.isalnum():
        return text + "."
    return text


def clip_length(text: str, limit: int = MAX_CHARS) -> str:
    """Keep the tail if the line is too long (latest speech).

    Args:
        text: Hypothesis.
        limit: Max characters.

    Returns:
        Possibly prefixed with `…`.
    """
    if len(text) <= limit:
        return text
    return "…" + text[-(limit - 1) :]


def polish(text: str, *, is_final: bool) -> str:
    """Run the conservative pipeline on one string.

    Args:
        text: Raw engine text.
        is_final: Whether this step is a frozen final.

    Returns:
        Cleaned text (may be empty).
    """
    out = collapse_repeated_words(collapse_ws(text))
    if is_final:
        out = ensure_final_punct(out)
    return clip_length(out)


class TranscriptSmoother:
    """Stateful filter for one ASR session (same subtitle_id grows in place).

    Example:
        s = TranscriptSmoother()
        a = s.apply(utt_partial)
        b = s.apply(utt_dup)  # None if identical
    """

    def __init__(self) -> None:
        self._last_id = ""
        self._last_text = ""
        self._last_status = ""

    def apply(self, utt: TranscriptUtterance) -> Optional[TranscriptUtterance]:
        """Clean one utterance. Returns None to drop a duplicate emit.

        Args:
            utt: Engine output.

        Returns:
            Copy with polished text, or None.
        """
        raw = collapse_repeated_words(collapse_ws(utt.text))
        if utt.subtitle_id == self._last_id:
            raw = collapse_ws(stitch(self._last_text, raw))
        if utt.status == "final":
            raw = ensure_final_punct(raw)
        raw = clip_length(raw)
        if not raw:
            return None
        if raw == self._last_text and utt.status == self._last_status:
            return None
        self._last_id = utt.subtitle_id
        self._last_text = raw
        self._last_status = utt.status
        return replace(utt, text=raw)
