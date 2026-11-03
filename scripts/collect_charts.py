"""Collect Last.fm charts into the repository (run by GitHub Actions, or by hand).

For each chart in L2P_CHARTS it writes
  data/charts/<chart_id>.json      the latest top list (what the app reads)
  data/charts/index.json           list of available charts
  data/history/<chart_id>.csv      one row per track per day (for the Big Data analysis)
A failed chart keeps its old file. Re-running on the same day replaces that day's rows.

Environment
  LASTFM_API_KEY   required (a GitHub Actions secret)
  L2P_CHARTS       semicolon list of country names, or "global": "global;South Korea;United States"
  L2P_CHART_LIMIT  tracks per chart (default 50)

The error messages never contain the request URL, because the URL holds the API key.
"""
from __future__ import annotations

import csv
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

LASTFM_URL = "https://ws.audioscrobbler.com/2.0/"
CSV_FIELDS = ["date", "rank", "title", "artist", "listeners"]


class LastfmError(RuntimeError):
    """Raised without the request URL."""


@dataclass(frozen=True)
class ChartSpec:
    chart_id: str
    label: str
    country: Optional[str]  # None = global chart

    @property
    def method(self) -> str:
        return "chart.gettoptracks" if self.country is None else "geo.gettoptracks"


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def parse_charts(spec: str) -> list[ChartSpec]:
    out = []
    for item in [s.strip() for s in spec.split(";") if s.strip()]:
        if item.lower() == "global":
            out.append(ChartSpec("global", "Global top tracks", None))
        else:
            out.append(ChartSpec(slug(item), f"Top tracks: {item}", item))
    return out


def fetch_chart(session: Any, api_key: str, chart: ChartSpec, limit: int) -> dict:
    params: dict[str, Any] = {"method": chart.method, "api_key": api_key, "format": "json", "limit": limit}
    if chart.country:
        params["country"] = chart.country
    try:
        response = session.get(LASTFM_URL, params=params, timeout=20)
        status = getattr(response, "status_code", 200)
        try:
            data = response.json()
        except ValueError:
            data = None
    except Exception as exc:  # noqa: BLE001 - the URL holds the key, so never include it
        raise LastfmError(f"request for chart '{chart.chart_id}' failed ({type(exc).__name__})") from None
    # Last.fm often answers HTTP 4xx with a JSON body {"error": <code>}; report that code.
    if isinstance(data, dict) and "error" in data:
        raise LastfmError(f"Last.fm refused chart '{chart.chart_id}' (error {data.get('error')}, HTTP {status})")
    if status >= 400 or not isinstance(data, dict):
        raise LastfmError(f"request for chart '{chart.chart_id}' failed (HTTP {status})")
    return data


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def normalize(data: dict) -> list[dict]:
    """chart.getTopTracks and geo.getTopTracks share this shape. Rank is the list order from 1."""
    tracks = (data.get("tracks") or {}).get("track") or []
    if isinstance(tracks, dict):
        tracks = [tracks]
    out = []
    for i, t in enumerate(tracks, start=1):
        artist = t.get("artist")
        artist = artist.get("name") if isinstance(artist, dict) else artist
        title = (t.get("name") or "").strip()
        if not title or not artist:
            continue
        out.append({"rank": i, "title": title, "artist": str(artist).strip(),
                    "listeners": _int(t.get("listeners")), "url": t.get("url", "")})
    return out


def _same_tracks(path: Path, tracks: list[dict]) -> bool:
    try:
        old = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return old.get("tracks") == tracks


def write_history(path: Path, day: str, tracks: list[dict]) -> None:
    """Idempotent: rows for `day` are replaced, other days are kept."""
    rows: list[dict] = []
    if path.exists():
        with path.open(newline="", encoding="utf-8") as fh:
            rows = [r for r in csv.DictReader(fh) if r.get("date") != day]
    rows += [{"date": day, "rank": t["rank"], "title": t["title"], "artist": t["artist"], "listeners": t["listeners"]} for t in tracks]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def run(session: Any, api_key: str, specs: list[ChartSpec], limit: int, root: Path, now: Optional[datetime] = None) -> list[str]:
    """Returns a list of problems (empty on success). Never raises for one bad chart."""
    now = now or datetime.now(timezone.utc)
    day = now.strftime("%Y-%m-%d")
    charts_dir, history_dir = root / "data" / "charts", root / "data" / "history"
    charts_dir.mkdir(parents=True, exist_ok=True)
    problems: list[str] = []
    for spec in specs:
        try:
            tracks = normalize(fetch_chart(session, api_key, spec, limit))
        except LastfmError as exc:
            problems.append(str(exc))
            continue
        if not tracks:
            problems.append(f"chart '{spec.chart_id}' came back empty; kept the old file")
            continue
        target = charts_dir / f"{spec.chart_id}.json"
        if not _same_tracks(target, tracks):  # no needless commits when nothing changed
            doc = {"chart_id": spec.chart_id, "label": spec.label, "source": "lastfm",
                   "fetched_at": now.isoformat(timespec="seconds"), "tracks": tracks}
            target.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        write_history(history_dir / f"{spec.chart_id}.csv", day, tracks)
    index = []
    for path in sorted(charts_dir.glob("*.json")):
        if path.name == "index.json":
            continue
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
            index.append({"chart_id": doc["chart_id"], "label": doc.get("label", doc["chart_id"]),
                          "fetched_at": doc.get("fetched_at", ""), "count": len(doc.get("tracks", []))})
        except (OSError, ValueError, KeyError):
            continue
    (charts_dir / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return problems


def main() -> int:
    api_key = os.environ.get("LASTFM_API_KEY", "")
    if not api_key:
        print("Set LASTFM_API_KEY (a free key from Last.fm).", file=sys.stderr)
        return 2
    import requests

    specs = parse_charts(os.environ.get("L2P_CHARTS", "global;South Korea;United States"))
    try:
        limit = max(1, min(200, int(os.environ.get("L2P_CHART_LIMIT", "50"))))
    except ValueError:
        limit = 50
    problems = run(requests.Session(), api_key, specs, limit, Path(__file__).resolve().parent.parent)
    for p in problems:
        print("problem:", p, file=sys.stderr)
    return 1 if problems and len(problems) == len(specs) else 0


if __name__ == "__main__":
    raise SystemExit(main())
