import json
from types import SimpleNamespace

import pytest

from lyric2poster.art_director import (BriefError, ClaudeArtDirector, OpenAIArtDirector,
                                       build_art_director, DemoArtDirector)
from tests.conftest import LYRICS

GOOD = {"summary": "a night harbor that refuses to sleep", "mood": ["restless"], "themes": ["waiting"],
        "imagery": ["wet piers", "a single lamp"], "setting": "a harbor after midnight",
        "palette": ["#0E1022", "#E4572E", "#5CC4B8"], "composition": "lamp left, open sky right",
        "style_preset": "neon_noir", "language": "en", "flags": []}


class FakeClaude:
    """Mimics client.messages.create and records the keyword arguments."""

    def __init__(self, replies, stop_reason="end_turn"):
        self.replies, self.calls, self.stop_reason = list(replies), [], stop_reason
        self.messages = self

    def create(self, **kw):
        self.calls.append(kw)
        text = self.replies.pop(0)
        return SimpleNamespace(stop_reason=self.stop_reason, content=[SimpleNamespace(type="text", text=text)])


def test_claude_request_shape():
    fake = FakeClaude([json.dumps(GOOD)])
    brief = ClaudeArtDirector("k", "claude-sonnet-5-5", client=fake).brief("T", "A", LYRICS)
    kw = fake.calls[0]
    assert kw["model"] == "claude-sonnet-5-5"
    assert kw["output_config"]["format"]["type"] == "json_schema"
    assert kw["output_config"]["format"]["schema"]["additionalProperties"] is False
    assert not {"temperature", "top_p", "top_k"} & set(kw)
    assert "<lyrics>" in kw["messages"][0]["content"]
    assert "untrusted" in kw["system"]
    assert brief.style_preset == "neon_noir"


def test_retry_on_bad_json_then_success():
    fake = FakeClaude(["not json", json.dumps(GOOD)])
    ClaudeArtDirector("k", "m", client=fake).brief("T", "A", LYRICS)
    assert len(fake.calls) == 2 and "rejected" in fake.calls[1]["messages"][0]["content"]


def test_retry_when_brief_copies_lyrics_then_fail():
    copied = dict(GOOD, summary="we keep the last train waiting at the door")
    fake = FakeClaude([json.dumps(copied), json.dumps(copied)])
    with pytest.raises(BriefError):
        ClaudeArtDirector("k", "m", client=fake).brief("T", "A", LYRICS)
    assert len(fake.calls) == 2


def test_refusal_and_cutoff_are_clean_errors():
    with pytest.raises(BriefError, match="declined"):
        ClaudeArtDirector("k", "m", client=FakeClaude(["{}"], stop_reason="refusal")).brief("T", "A", LYRICS)
    with pytest.raises(BriefError, match="cut off"):
        ClaudeArtDirector("k", "m", client=FakeClaude(["{}"], stop_reason="max_tokens")).brief("T", "A", LYRICS)


def test_api_exception_never_leaks_lyrics():
    class Boom:
        messages = None

        def __init__(self):
            self.messages = self

        def create(self, **kw):
            raise RuntimeError("bad request containing " + kw["messages"][0]["content"])

    with pytest.raises(BriefError) as err:
        ClaudeArtDirector("k", "m", client=Boom()).brief("T", "A", LYRICS)
    assert "harbor" not in str(err.value) and "RuntimeError" in str(err.value)


def test_openai_adapter_with_fake_client():
    msg = SimpleNamespace(message=SimpleNamespace(content=json.dumps(GOOD)))
    calls = []
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(
        create=lambda **kw: (calls.append(kw), SimpleNamespace(choices=[msg]))[1])))
    brief = OpenAIArtDirector("k", "some-model", client=client).brief("T", "A", LYRICS)
    assert brief.mood == ["restless"] and calls[0]["response_format"] == {"type": "json_object"}
    with pytest.raises(BriefError):
        OpenAIArtDirector("k", "", client=client)


def test_build_art_director_falls_back_to_demo():
    assert isinstance(build_art_director("claude"), DemoArtDirector)
    assert isinstance(build_art_director("openai", openai_api_key="k"), DemoArtDirector)  # no model named
    assert build_art_director("claude", anthropic_api_key="k", claude_model="m").name == "claude"
