import io
from types import SimpleNamespace

import pytest
from PIL import Image

from lyric2poster.image_engines import (DemoEngine, EngineError, HFSpaceEngine, ImageRequest, RemoteEngine,
                                        build_engine, generate_with_fallback)
from lyric2poster.config import load_settings


def png_bytes(size=(64, 80)):
    out = io.BytesIO()
    Image.new("RGB", size, (200, 30, 30)).save(out, format="PNG")
    return out.getvalue()


REQ = ImageRequest("a harbor", ["#112233", "#445566", "#778899"], 7)


def test_demo_engine_size_and_determinism():
    a, b = DemoEngine().generate(REQ), DemoEngine().generate(REQ)
    assert a.png == b.png and Image.open(io.BytesIO(a.png)).size == (768, 1024)


def test_hf_space_engine_handles_tuple_result(tmp_path):
    path = tmp_path / "out.webp"
    Image.new("RGB", (32, 32), (1, 2, 3)).save(path, format="WEBP")
    seen = {}
    client = SimpleNamespace(predict=lambda **kw: (seen.update(kw), (str(path), 7))[1])
    res = HFSpaceEngine("owner/space", client=client).generate(REQ)
    assert res.png[:4] == b"\x89PNG" and seen["api_name"] == "/infer" and seen["seed"] == 7


def test_hf_space_failure_is_clean():
    def boom(**kw):
        raise RuntimeError("secret detail: quota")
    with pytest.raises(EngineError) as err:
        HFSpaceEngine("o/s", token="hf_TOKEN123", client=SimpleNamespace(predict=boom)).generate(REQ)
    assert "RuntimeError" in str(err.value) and "hf_TOKEN123" not in str(err.value)


class FakeSession:
    def __init__(self, status=200, content=None):
        self.status, self.content, self.calls = status, content or png_bytes(), []

    def post(self, url, **kw):
        self.calls.append((url, kw))
        def raise_for_status():
            if self.status >= 400:
                raise RuntimeError("http")
        return SimpleNamespace(status_code=self.status, content=self.content, headers={"X-Model": "flux-x"},
                               raise_for_status=raise_for_status)


def test_remote_engine_sends_token_and_reads_model():
    s = FakeSession()
    res = RemoteEngine("https://x.example/", "tok", session=s).generate(REQ)
    url, kw = s.calls[0]
    assert url == "https://x.example/generate" and kw["headers"]["Authorization"] == "Bearer tok"
    assert kw["json"]["width"] == 768 and res.model == "flux-x"


def test_remote_engine_errors():
    with pytest.raises(EngineError, match="token"):
        RemoteEngine("https://x", "t", session=FakeSession(401)).generate(REQ)
    with pytest.raises(EngineError, match="Colab"):
        RemoteEngine("https://x", "t", session=FakeSession(500)).generate(REQ)


def test_fallback_to_demo_and_demo_failure_raises():
    bad = RemoteEngine("https://x", "t", session=FakeSession(500))
    res, fell_back, note = generate_with_fallback(bad, REQ)
    assert fell_back and res.engine == "demo" and note
    ok, fb, _ = generate_with_fallback(DemoEngine(), REQ)
    assert not fb


def test_build_engine_choices():
    assert build_engine(load_settings({}, {})).name == "demo"
    assert build_engine(load_settings({}, {"L2P_IMAGE_ENGINE": "remote"})).name == "demo"  # no URL
    e = build_engine(load_settings({}, {"L2P_IMAGE_ENGINE": "remote", "L2P_REMOTE_URL": "https://x", "L2P_REMOTE_TOKEN": "t"}))
    assert e.name == "remote"


def test_hf_client_is_lazy_and_uses_token_keyword(monkeypatch):
    import gradio_client

    seen = {}

    class FakeClient:
        def __init__(self, src, token=None, max_workers=1):
            seen.update(src=src, token=token)

    monkeypatch.setattr(gradio_client, "Client", FakeClient)
    engine = HFSpaceEngine("owner/space", token="hf_x")  # must not call Client yet
    assert seen == {}
    engine._get_client()
    assert seen == {"src": "owner/space", "token": "hf_x"}


def test_hf_client_old_keyword_name(monkeypatch):
    import gradio_client

    seen = {}

    class OldClient:
        def __init__(self, src, hf_token=None):
            seen.update(src=src, hf_token=hf_token)

    monkeypatch.setattr(gradio_client, "Client", OldClient)
    HFSpaceEngine("o/s", token="hf_y")._get_client()
    assert seen["hf_token"] == "hf_y"


def test_hf_construction_failure_falls_back_to_demo(monkeypatch):
    import gradio_client

    def broken(*a, **k):
        raise TypeError("no such argument")

    monkeypatch.setattr(gradio_client, "Client", broken)
    res, fell_back, note = generate_with_fallback(HFSpaceEngine("o/s", token="t"), REQ)
    assert fell_back and res.engine == "demo" and "TypeError" in note
