"""Lyric2Poster (open-source edition): chart song -> lyrics -> art brief (Claude) -> poster.

Runs as one Streamlit script, so it deploys to Streamlit Community Cloud straight from GitHub.
Lyrics live only in this browser session: they are cleared right after the art brief is made,
and nothing in this file writes them to disk, a log or a database.
"""
from __future__ import annotations

import logging
import random

import streamlit as st

from lyric2poster.art_director import BriefError, build_art_director
from lyric2poster.charts import load_charts
from lyric2poster.config import load_settings
from lyric2poster.image_engines import EngineError, ImageRequest, build_engine, generate_with_fallback
from lyric2poster.lyrics import build_provider
from lyric2poster.limits import SessionLimiter, owner_key_allowed, passcode_ok
from lyric2poster.overlay import add_title_overlay
from lyric2poster.prompt_builder import build_image_prompt
from lyric2poster.safety import InputError, blocked_reason, clean_label, clean_lyrics, needs_softening
from lyric2poster.schemas import STYLE_PRESETS, ArtBrief

log = logging.getLogger("l2p.app")

st.set_page_config(page_title="Lyric2Poster", page_icon="🎨", layout="centered")


def _secrets():
    try:
        return st.secrets
    except Exception:  # noqa: BLE001 - no secrets file when running locally
        return None


settings = load_settings(secrets=_secrets())
limiter = SessionLimiter(st.session_state, settings.brief_limit, settings.poster_limit)


@st.cache_data(ttl=3600, show_spinner=False)
def _charts(directory: str, url: str) -> list[dict]:
    return load_charts(directory, url)


# ------------------------------------------------------------------ sidebar: keys and limits
with st.sidebar:
    st.header("Access")
    st.caption("Without a key the app runs in demo mode: canned art brief, Pillow-drawn poster.")
    if settings.app_passcode:
        code = st.text_input("Class passcode (to use the owner's key)", type="password", key="passcode_input")
        if code:
            st.session_state["unlocked"] = passcode_ok(code, settings.app_passcode)
            if not st.session_state["unlocked"]:
                st.error("Wrong passcode.")
    own_claude = st.text_input("Or paste your own Claude API key", type="password", key="byo_claude",
                               help="Used only for your requests in this session. Never stored.")
    st.caption(f"Briefs left: {limiter.remaining('briefs')}  |  Posters left: {limiter.remaining('posters')}")

unlocked = bool(st.session_state.get("unlocked"))
anthropic_key = own_claude.strip() or (settings.anthropic_api_key if owner_key_allowed(settings, unlocked) else "")
openai_key = settings.openai_api_key if owner_key_allowed(settings, unlocked) else ""
# A key pasted in the sidebar always means Claude, even when no owner key is configured.
llm = "claude" if own_claude.strip() else settings.llm
director = build_art_director(
    llm if (anthropic_key or openai_key) else "demo",
    anthropic_api_key=anthropic_key, openai_api_key=openai_key,
    claude_model=settings.claude_model, openai_model=settings.openai_model,
)
engine = build_engine(settings)

st.title("Lyric2Poster")
st.caption(f"Art director: **{director.name}**  |  Image engine: **{engine.name}**")


# ------------------------------------------------------------------ step 1: choose a song
charts = _charts(settings.charts_dir, settings.charts_url)
chart = st.selectbox("Chart", charts, format_func=lambda c: c.get("label", c["chart_id"]))
tracks = chart["tracks"]
labels = [f"{t['rank']}. {t['title']} - {t['artist']}" for t in tracks] + ["Type my own song"]
choice = st.selectbox("Song", labels)
if choice == "Type my own song":
    title = st.text_input("Title", max_chars=120)
    artist = st.text_input("Artist", max_chars=120)
else:
    picked = tracks[labels.index(choice)]
    title, artist = picked["title"], picked["artist"]
title, artist = clean_label(title), clean_label(artist)


# ------------------------------------------------------------------ step 2: lyrics -> brief
def make_brief() -> None:
    st.session_state["error"] = ""
    raw = st.session_state.get("lyrics", "")
    try:
        lyrics = clean_lyrics(raw, min_chars=20, max_chars=8000)
    except InputError as exc:
        st.session_state["error"] = str(exc)
        return
    if not title or not artist:
        st.session_state["error"] = "Please give a title and an artist."
        return
    if not limiter.take("briefs"):
        st.session_state["error"] = "You have used all your briefs for this session."
        return
    try:
        brief = director.brief(title, artist, lyrics)
    except BriefError as exc:
        st.session_state["error"] = str(exc)
        return
    finally:
        st.session_state["lyrics"] = ""  # lyrics are never kept after this point
    st.session_state["brief"] = brief.model_dump()
    st.session_state.pop("poster", None)


def load_lyrics() -> None:
    """Fill the lyrics box for the chosen song. Runs again only when the song changes."""
    provider = build_provider(settings.lyrics_provider)
    st.session_state["_lyrics_for"] = (title, artist)
    st.session_state["lyrics_note"] = ""
    if provider is None or not title or not artist:
        return
    found = provider.fetch(title, artist)
    if found:
        st.session_state["lyrics"] = found
        st.session_state["lyrics_note"] = f"Lyrics loaded from {provider.name}. You can edit them. They are erased after the brief."
    else:
        st.session_state["lyrics_note"] = "No lyrics found for this song. Please paste your own text."


if st.session_state.get("_lyrics_for") != (title, artist):
    load_lyrics()

st.text_area("Lyrics (used once, never saved)", key="lyrics", height=200, max_chars=8000)
if st.session_state.get("lyrics_note"):
    st.caption(st.session_state["lyrics_note"])
st.button("1. Write the art brief", on_click=make_brief, type="primary")
if settings.lyrics_provider != "off":
    st.button("Load lyrics again", on_click=load_lyrics)
if st.session_state.get("error"):
    st.error(st.session_state["error"])

# ------------------------------------------------------------------ step 3: review and generate
if "brief" in st.session_state:
    brief = ArtBrief.model_validate(st.session_state["brief"])
    reason = blocked_reason(brief)
    st.subheader("Art brief")
    st.write(brief.summary)
    st.caption(f"Mood: {', '.join(brief.mood)}  |  Imagery: {', '.join(brief.imagery)}")
    st.write("Palette: " + ", ".join(f"`{c}`" for c in brief.palette))
    if reason:
        st.warning(reason)
    else:
        if needs_softening(brief):
            st.info("This song touches sensitive themes, so the poster will treat them abstractly.")
        style = st.selectbox("Style", STYLE_PRESETS, index=STYLE_PRESETS.index(brief.style_preset))

        def make_poster() -> None:
            if not limiter.take("posters"):
                st.session_state["error"] = "You have used all your posters for this session."
                return
            req = ImageRequest(prompt=build_image_prompt(brief, style), palette=brief.palette,
                               seed=random.randint(0, 2**31 - 1))
            try:
                result, fell_back, note = generate_with_fallback(engine, req)
            except EngineError as exc:
                st.session_state["error"] = str(exc)
                return
            st.session_state["poster"] = {
                "png": add_title_overlay(result.png, title, artist),
                "engine": result.engine, "model": result.model, "fell_back": fell_back, "note": note,
            }

        st.button("2. Make the poster", on_click=make_poster)

if "poster" in st.session_state:
    poster = st.session_state["poster"]
    if poster["fell_back"]:
        st.warning(f"The image engine failed, so this is the offline demo poster. ({poster['note']})")
    st.image(poster["png"], caption=f"{poster['engine']} / {poster['model']}")
    st.download_button("Download PNG", poster["png"], file_name="poster.png", mime="image/png")
    st.caption("AI-generated image. Title and artist were added as text afterwards.")
