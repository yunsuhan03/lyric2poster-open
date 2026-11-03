"""Drives the real Streamlit script with Streamlit's AppTest, in demo mode."""
import logging
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from tests.conftest import CANARY, LYRICS

APP = str(Path(__file__).resolve().parent.parent / "streamlit_app.py")


@pytest.fixture(autouse=True)
def demo_env(monkeypatch):
    monkeypatch.setenv("L2P_LYRICS_PROVIDER", "off")
    for k in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "L2P_LLM", "L2P_IMAGE_ENGINE", "APP_PASSCODE", "HF_TOKEN"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.chdir(Path(APP).parent)


def run_flow(at):
    at.run()
    assert not at.exception
    at.text_area(key="lyrics").set_value(LYRICS).run()
    at.button[0].click().run()
    return at


def test_full_flow_in_demo_mode_and_canary(caplog):
    caplog.set_level(logging.DEBUG)
    at = run_flow(AppTest.from_file(APP, default_timeout=60))
    assert not at.exception and not at.error
    assert "brief" in at.session_state
    # lyrics are cleared and never appear in state, logs, or any rendered text
    assert at.session_state["lyrics"] == ""
    blob = repr(dict(at.session_state)) + caplog.text + " ".join(str(m.value) for m in at.markdown)
    assert CANARY not in blob and "harbor lights" not in blob
    at.button[1].click().run()
    assert not at.exception
    assert at.session_state["poster"]["png"][:4] == b"\x89PNG"
    assert at.session_state["poster"]["engine"] == "demo"


def test_short_lyrics_show_error():
    at = AppTest.from_file(APP, default_timeout=60).run()
    at.text_area(key="lyrics").set_value("hi").run()
    at.button[0].click().run()
    assert at.error and "brief" not in at.session_state


def test_session_brief_limit(monkeypatch):
    monkeypatch.setenv("L2P_BRIEF_LIMIT", "1")
    at = run_flow(AppTest.from_file(APP, default_timeout=60))
    at.text_area(key="lyrics").set_value(LYRICS).run()
    at.button[0].click().run()
    assert at.error and "used all" in at.error[0].value


def test_owner_key_not_used_without_passcode(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-owner")
    at = AppTest.from_file(APP, default_timeout=60).run()
    assert "demo" in at.caption[0].value  # the owner's key stays unused for strangers


def test_pasted_key_switches_to_claude_even_without_owner_key():
    at = AppTest.from_file(APP, default_timeout=60).run()
    assert "demo" in at.caption[0].value
    at.text_input(key="byo_claude").set_value("sk-ant-test").run()
    assert not at.exception
    assert "claude" in at.caption[0].value


def test_owner_key_with_passcode_uses_claude(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-owner")
    monkeypatch.setenv("APP_PASSCODE", "letmein")
    at = AppTest.from_file(APP, default_timeout=60).run()
    assert "demo" in at.caption[0].value
    at.text_input(key="passcode_input").set_value("letmein").run()
    assert "claude" in at.caption[0].value


def test_lyrics_autofill_then_erased_after_brief(monkeypatch, caplog):
    import lyric2poster.lyrics as lyr

    class Fake:
        name = "fake"

        def fetch(self, title, artist):
            return LYRICS

    monkeypatch.setenv("L2P_LYRICS_PROVIDER", "lrclib")
    monkeypatch.setattr(lyr, "build_provider", lambda name: Fake())
    caplog.set_level(logging.DEBUG)
    at = AppTest.from_file(APP, default_timeout=60).run()
    assert not at.exception
    assert at.text_area(key="lyrics").value == LYRICS  # shown without pasting
    at.button[0].click().run()
    assert not at.exception and "brief" in at.session_state
    assert at.session_state["lyrics"] == ""
    assert CANARY not in repr(dict(at.session_state)) + caplog.text


def test_lyrics_not_found_shows_note(monkeypatch):
    import lyric2poster.lyrics as lyr

    class Nope:
        name = "fake"

        def fetch(self, title, artist):
            return None

    monkeypatch.setenv("L2P_LYRICS_PROVIDER", "lrclib")
    monkeypatch.setattr(lyr, "build_provider", lambda name: Nope())
    at = AppTest.from_file(APP, default_timeout=60).run()
    assert at.text_area(key="lyrics").value == ""
    assert any("No lyrics found" in c.value for c in at.caption)
