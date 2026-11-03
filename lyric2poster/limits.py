"""Protecting the owner's API key on a public Streamlit app.

These are speed bumps, not a security system:
- the passcode keeps strangers off the owner's key;
- per-session counters stop one tab from looping;
- a visitor can paste their own key instead (bring your own key), which costs the owner nothing.
A determined visitor can open a new session, so also set a monthly spend limit in the Anthropic Console.
"""
from __future__ import annotations

import hmac
from typing import MutableMapping

from .config import Settings


def passcode_ok(given: str, expected: str) -> bool:
    if not expected:
        return False
    return hmac.compare_digest(given.encode(), expected.encode())


def owner_key_allowed(settings: Settings, unlocked: bool) -> bool:
    """May this visitor spend the owner's key?"""
    if unlocked:
        return True
    return settings.allow_public_owner_key and not settings.app_passcode


class SessionLimiter:
    """Counts uses in a dict (st.session_state in the app, a plain dict in tests)."""

    def __init__(self, store: MutableMapping, brief_limit: int, poster_limit: int) -> None:
        self._store = store
        self._limits = {"briefs": brief_limit, "posters": poster_limit}

    def used(self, kind: str) -> int:
        return int(self._store.get(f"_used_{kind}", 0))

    def remaining(self, kind: str) -> int:
        return max(0, self._limits[kind] - self.used(kind))

    def take(self, kind: str) -> bool:
        if self.remaining(kind) <= 0:
            return False
        self._store[f"_used_{kind}"] = self.used(kind) + 1
        return True
