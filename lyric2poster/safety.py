"""Input cleaning and safety rules.

Nothing in this file logs or returns lyric text.
"""
from __future__ import annotations

import re
import unicodedata

from .schemas import ArtBrief

BLOCKING_FLAGS = {"self_harm", "sexual_content", "hate"}
SOFTENING_FLAGS = {"violence", "explicit_language", "real_person_reference"}

_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_WORD = re.compile(r"\w+", re.UNICODE)


class InputError(ValueError):
    """The user's input cannot be used. The message never contains the input itself."""


def clean_lyrics(raw: str, min_chars: int, max_chars: int) -> str:
    text = unicodedata.normalize("NFC", raw)
    text = _CONTROL.sub("", text).replace("\r\n", "\n").replace("\r", "\n")
    # The prompt wraps lyrics in a tag; remove any attempt to close or reopen it.
    text = re.sub(r"</?\s*lyrics\s*>", "", text, flags=re.I).strip()
    if len(text) < min_chars:
        raise InputError(f"Please paste at least {min_chars} characters of lyrics.")
    if len(text) > max_chars:
        raise InputError(f"Please paste at most {max_chars} characters of lyrics.")
    return text


def clean_label(text: str, limit: int = 120) -> str:
    text = unicodedata.normalize("NFC", _CONTROL.sub("", text))
    return re.sub(r"\s+", " ", text).strip()[:limit]


def blocked_reason(brief: ArtBrief) -> str | None:
    hit = sorted(BLOCKING_FLAGS.intersection(brief.flags))
    if hit:
        return "This song's themes are outside what this demo will illustrate."
    return None


def needs_softening(brief: ArtBrief) -> bool:
    return bool(SOFTENING_FLAGS.intersection(brief.flags))


def _words(text: str) -> list[str]:
    return [w.lower() for w in _WORD.findall(unicodedata.normalize("NFKC", text))]


def has_copied_run(brief: ArtBrief, lyrics: str, words: int = 5, chars: int = 16) -> bool:
    """True if the brief repeats a run of the lyrics.

    Two checks: any run of `words` consecutive words, and any run of `chars` consecutive
    letters after spaces are removed (this catches languages written without spaces).
    """
    brief_text = brief.prose()
    lw, bw = _words(lyrics), _words(brief_text)
    if len(lw) >= words and len(bw) >= words:
        lyric_runs = {tuple(lw[i : i + words]) for i in range(len(lw) - words + 1)}
        for i in range(len(bw) - words + 1):
            if tuple(bw[i : i + words]) in lyric_runs:
                return True
    lc, bc = "".join(lw), "".join(bw)
    if len(lc) >= chars and len(bc) >= chars:
        shingles = {lc[i : i + chars] for i in range(len(lc) - chars + 1)}
        for i in range(len(bc) - chars + 1):
            if bc[i : i + chars] in shingles:
                return True
    return False
