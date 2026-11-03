"""Settings from environment variables or Streamlit secrets (secrets win nothing: env first).

Nothing here logs or prints a key. API keys are excluded from repr().
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Mapping, Optional

DEFAULT_CLAUDE_MODEL = "claude-sonnet-5-5"  # check the current model list before your demo


def _bool(value: str, default: bool = False) -> bool:
    if value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    # LLM (art director). Claude is the course default.
    llm: str = "demo"  # claude | openai | demo
    claude_model: str = DEFAULT_CLAUDE_MODEL
    openai_model: str = ""
    anthropic_api_key: str = field(default="", repr=False)
    openai_api_key: str = field(default="", repr=False)
    # Image engine
    image_engine: str = "demo"  # demo | hf_space | remote
    hf_space: str = "black-forest-labs/FLUX.1-schnell"
    hf_api_name: str = "/infer"
    hf_token: str = field(default="", repr=False)
    remote_url: str = ""
    remote_token: str = field(default="", repr=False)
    # Public-app protection
    app_passcode: str = field(default="", repr=False)
    allow_public_owner_key: bool = False
    brief_limit: int = 10
    poster_limit: int = 6
    # Lyrics lookup: lrclib | off
    lyrics_provider: str = "lrclib"
    # Charts
    charts_dir: str = "data/charts"
    charts_url: str = ""  # e.g. https://raw.githubusercontent.com/<user>/<repo>/main/data/charts

    @property
    def llm_ready(self) -> bool:
        if self.llm == "claude":
            return bool(self.anthropic_api_key)
        if self.llm == "openai":
            return bool(self.openai_api_key and self.openai_model)
        return False


def load_settings(secrets: Optional[Mapping[str, object]] = None, env: Optional[Mapping[str, str]] = None) -> Settings:
    env = os.environ if env is None else env

    def get(name: str, default: str = "") -> str:
        if name in env and env[name] != "":
            return str(env[name])
        if secrets is not None:
            try:
                if name in secrets:
                    return str(secrets[name])
            except Exception:  # noqa: BLE001 - st.secrets raises if no secrets file exists
                pass
        return default

    anthropic_key = get("ANTHROPIC_API_KEY")
    llm = get("L2P_LLM", "claude" if anthropic_key else "demo").lower()
    if llm not in {"claude", "openai", "demo"}:
        llm = "demo"
    engine = get("L2P_IMAGE_ENGINE", "demo").lower()
    if engine not in {"demo", "hf_space", "remote"}:
        engine = "demo"

    def num(name: str, default: int) -> int:
        try:
            return max(0, int(get(name, str(default))))
        except ValueError:
            return default

    return Settings(
        llm=llm,
        claude_model=get("L2P_CLAUDE_MODEL", DEFAULT_CLAUDE_MODEL),
        openai_model=get("L2P_OPENAI_MODEL"),
        anthropic_api_key=anthropic_key,
        openai_api_key=get("OPENAI_API_KEY"),
        image_engine=engine,
        hf_space=get("L2P_HF_SPACE", "black-forest-labs/FLUX.1-schnell"),
        hf_api_name=get("L2P_HF_API_NAME", "/infer"),
        hf_token=get("HF_TOKEN"),
        remote_url=get("L2P_REMOTE_URL").rstrip("/"),
        remote_token=get("L2P_REMOTE_TOKEN"),
        app_passcode=get("APP_PASSCODE"),
        allow_public_owner_key=_bool(get("L2P_ALLOW_PUBLIC_OWNER_KEY"), False),
        brief_limit=num("L2P_BRIEF_LIMIT", 10),
        poster_limit=num("L2P_POSTER_LIMIT", 6),
        lyrics_provider=("off" if get("L2P_LYRICS_PROVIDER", "lrclib").lower() != "lrclib" else "lrclib"),
        charts_dir=get("L2P_CHARTS_DIR", "data/charts"),
        charts_url=get("L2P_CHARTS_URL").rstrip("/"),
    )
