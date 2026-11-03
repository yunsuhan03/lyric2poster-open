import csv
import json
from datetime import datetime, timezone
from types import SimpleNamespace

from lyric2poster.charts import FICTIONAL, load_charts
from scripts.collect_charts import (ChartSpec, LastfmError, normalize, parse_charts, run, write_history)

KEY = "SECRET-KEY-123"
SAMPLE = {"tracks": {"track": [
    {"name": "One", "artist": {"name": "A"}, "listeners": "10", "url": "u1"},
    {"name": "", "artist": {"name": "skip"}},
    {"name": "Two", "artist": "B", "listeners": "x"},
]}}


class FakeHTTP:
    def __init__(self, data=None, fail=False):
        self.data, self.fail, self.calls = data, fail, []

    def get(self, url, params=None, timeout=0):
        self.calls.append(params)
        if self.fail:
            raise RuntimeError(f"boom {url} {params}")  # a real error would carry the key
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: self.data)


NOW = datetime(2026, 11, 2, 19, 0, tzinfo=timezone.utc)


def test_parse_and_normalize():
    specs = parse_charts("global;South Korea")
    assert [s.method for s in specs] == ["chart.gettoptracks", "geo.gettoptracks"]
    assert specs[1].chart_id == "south-korea"
    tracks = normalize(SAMPLE)
    assert [t["rank"] for t in tracks] == [1, 3] and tracks[1]["listeners"] == 0


def test_run_writes_files_and_is_idempotent(tmp_path):
    http = FakeHTTP(SAMPLE)
    assert run(http, KEY, [ChartSpec("global", "Global", None)], 50, tmp_path, NOW) == []
    first = (tmp_path / "data/charts/global.json").read_text()
    assert run(http, KEY, [ChartSpec("global", "Global", None)], 50, tmp_path,
               datetime(2026, 11, 2, 22, 0, tzinfo=timezone.utc)) == []
    assert (tmp_path / "data/charts/global.json").read_text() == first  # unchanged tracks: no rewrite
    rows = list(csv.DictReader((tmp_path / "data/history/global.csv").open()))
    assert len(rows) == 2  # same day replaced, not duplicated
    index = json.loads((tmp_path / "data/charts/index.json").read_text())
    assert index[0]["chart_id"] == "global" and index[0]["count"] == 2


def test_history_keeps_other_days(tmp_path):
    p = tmp_path / "h.csv"
    write_history(p, "2026-11-01", [{"rank": 1, "title": "t", "artist": "a", "listeners": 1}])
    write_history(p, "2026-11-02", [{"rank": 1, "title": "t", "artist": "a", "listeners": 2}])
    assert [r["date"] for r in csv.DictReader(p.open())] == ["2026-11-01", "2026-11-02"]


def test_failure_keeps_old_file_and_hides_key(tmp_path):
    spec = ChartSpec("global", "Global", None)
    run(FakeHTTP(SAMPLE), KEY, [spec], 50, tmp_path, NOW)
    before = (tmp_path / "data/charts/global.json").read_text()
    problems = run(FakeHTTP(fail=True), KEY, [spec], 50, tmp_path, NOW)
    assert problems and KEY not in " ".join(problems) and "RuntimeError" in problems[0]
    assert (tmp_path / "data/charts/global.json").read_text() == before
    assert run(FakeHTTP({"error": 10}), KEY, [spec], 50, tmp_path, NOW)  # API error reported
    assert run(FakeHTTP({"tracks": {"track": []}}), KEY, [spec], 50, tmp_path, NOW)  # empty kept old


def test_load_charts_dir_url_and_fallback(tmp_path):
    assert load_charts(str(tmp_path / "none")) == [FICTIONAL]
    (tmp_path / "a.json").write_text(json.dumps({"chart_id": "a", "tracks": [{"title": "t", "artist": "x"}]}))
    (tmp_path / "bad.json").write_text("{not json")
    assert [c["chart_id"] for c in load_charts(str(tmp_path))] == ["a"]

    docs = {"https://h/index.json": [{"chart_id": "r"}, {"chart_id": "../evil"}],
            "https://h/r.json": {"chart_id": "r", "tracks": [{"title": "t", "artist": "x"}]}}
    asked = []

    def get(url, timeout=0):
        asked.append(url)
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: docs[url])

    assert [c["chart_id"] for c in load_charts(str(tmp_path), "https://h", get=get)] == ["r"]
    assert not any("evil" in u for u in asked)
