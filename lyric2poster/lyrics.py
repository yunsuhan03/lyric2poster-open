"""Optional: fetch lyrics for the chosen song so the visitor does not have to paste them.

Provider: LRCLIB, an open community lyrics database with a free HTTP API and no key
(https://lrclib.net). Not run against the live service when this sample was written, so the
response shape below is Unverified. If it fails the app simply asks the visitor to paste.

Rules this module keeps:
- no scraping of lyrics websites;
- nothing is cached or written anywhere: the text goes to the visitor's session and is erased
  after the art brief is made;
- every failure returns None, never an exception that could carry request details.

Copyright note: lyrics are protected works. Showing them to the public may need a licence.
This sample shows them only to the visitor who selected the song. Set L2P_LYRICS_PROVIDER=off
to turn the feature off, and check the provider's terms before a public launch.
"""
from __future__ import annotations

from typing import Any, Callable, Optional, Protocol

from .safety import clean_lyrics, InputError

MAX_CHARS = 8000


class LyricsProvider(Protocol):
    name: str

    def fetch(self, title: str, artist: str) -> Optional[str]: ...


class LrclibProvider:
    name = "lrclib"
    base = "https://lrclib.net/api"

    def __init__(self, get: Optional[Callable[..., Any]] = None, timeout: int = 8) -> None:
        if get is None:
            import requests

            get = requests.get
        self._get = get
        self._timeout = timeout

    def fetch(self, title: str, artist: str) -> Optional[str]:
        if not title or not artist:
            return None
        try:
            response = self._get(
                f"{self.base}/search",
                params={"track_name": title, "artist_name": artist},
                headers={"User-Agent": "lyric2poster-sample (classroom project)"},
                timeout=self._timeout,
            )
            if getattr(response, "status_code", 200) >= 400:
                return None
            items = response.json()
        except Exception:  # noqa: BLE001 - network, JSON, anything: just report "not found"
            return None
        if not isinstance(items, list):
            return None
        for item in items:
            if not isinstance(item, dict) or item.get("instrumental"):
                continue
            text = item.get("plainLyrics")
            if isinstance(text, str) and text.strip():
                try:
                    return clean_lyrics(text, min_chars=20, max_chars=10**6)[:MAX_CHARS]
                except InputError:
                    continue
        return None


def build_provider(name: str) -> Optional[LyricsProvider]:
    if name == "lrclib":
        return LrclibProvider()
    return None
