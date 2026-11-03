"""Read the chart files that scripts/collect_charts.py wrote into data/charts/.

Two sources, same format:
- the folder next to the app (what Streamlit Cloud checked out from GitHub), or
- a base URL such as https://raw.githubusercontent.com/<user>/<repo>/main/data/charts, which stays
  fresh between app restarts.
If neither works the app falls back to a tiny fictional chart so it never opens empty.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Optional

FICTIONAL = {
    "chart_id": "demo",
    "label": "Demo chart (fictional songs)",
    "source": "demo",
    "fetched_at": "",
    "tracks": [
        {"rank": 1, "title": "Paper Lanterns", "artist": "Example Band", "listeners": 0, "url": ""},
        {"rank": 2, "title": "Midnight Tunnel", "artist": "Sample Artist", "listeners": 0, "url": ""},
        {"rank": 3, "title": "Long Summer", "artist": "Placeholder Duo", "listeners": 0, "url": ""},
    ],
}


def _valid(doc: Any) -> bool:
    return (
        isinstance(doc, dict)
        and isinstance(doc.get("chart_id"), str)
        and isinstance(doc.get("tracks"), list)
        and all(isinstance(t, dict) and t.get("title") and t.get("artist") for t in doc["tracks"])
    )


def _from_dir(directory: str) -> list[dict]:
    out = []
    for path in sorted(Path(directory).glob("*.json")):
        if path.name == "index.json":
            continue
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if _valid(doc):
            out.append(doc)
    return out


def _from_url(base: str, get: Callable[..., Any]) -> list[dict]:
    try:
        index = get(f"{base}/index.json", timeout=15)
        index.raise_for_status()
        ids = [item["chart_id"] for item in index.json()]
    except Exception:  # noqa: BLE001
        return []
    out = []
    for chart_id in ids:
        if not isinstance(chart_id, str) or not chart_id.replace("-", "").isalnum():
            continue
        try:
            resp = get(f"{base}/{chart_id}.json", timeout=15)
            resp.raise_for_status()
            doc = resp.json()
        except Exception:  # noqa: BLE001
            continue
        if _valid(doc):
            out.append(doc)
    return out


def load_charts(charts_dir: str, charts_url: str = "", get: Optional[Callable[..., Any]] = None) -> list[dict]:
    charts: list[dict] = []
    if charts_url:
        if get is None:
            import requests

            get = requests.get
        charts = _from_url(charts_url, get)
    if not charts:
        charts = _from_dir(charts_dir)
    return charts or [FICTIONAL]
