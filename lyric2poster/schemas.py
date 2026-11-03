"""Request, response and art-brief models.

ArtBrief is the contract between the LLM "art director" and the rest of the code.
It never contains lyric text: it describes mood and imagery in new words.
"""
from __future__ import annotations

import re
from typing import Any, Literal, get_args

from pydantic import BaseModel, Field, field_validator

StylePreset = Literal["risograph", "film_grain", "paper_cut", "neon_noir", "watercolor", "bauhaus"]
Flag = Literal[
    "explicit_language", "violence", "self_harm", "sexual_content", "hate", "real_person_reference"
]
STYLE_PRESETS: tuple[str, ...] = get_args(StylePreset)

_URL = re.compile(r"https?://|www\.", re.I)
_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
_SPACE = re.compile(r"\s+")


def _tidy(text: str, limit: int) -> str:
    text = _SPACE.sub(" ", str(text)).strip()
    if _URL.search(text):
        raise ValueError("links are not allowed")
    if len(text) > limit:
        raise ValueError(f"text is longer than {limit} characters")
    return text


class ArtBrief(BaseModel):
    summary: str = Field(description="One sentence in your own words about what the song feels like. Never quote the lyrics.")
    mood: list[str] = Field(min_length=1, max_length=4, description="1 to 4 mood words.")
    themes: list[str] = Field(min_length=1, max_length=4, description="1 to 4 themes in new words.")
    imagery: list[str] = Field(min_length=2, max_length=5, description="2 to 5 concrete visual elements: objects, places, light. No text.")
    setting: str = Field(description="One short sentence describing the place and time of day.")
    palette: list[str] = Field(min_length=3, max_length=5, description="3 to 5 hex colors such as #1A2B3C.")
    composition: str = Field(description="One short sentence about where the main subject sits and where there is empty space.")
    style_preset: StylePreset = Field(description="The best matching visual style.")
    language: str = Field(default="und", description="ISO 639-1 code of the lyrics, or und.")
    flags: list[Flag] = Field(default_factory=list, description="Sensitive themes that apply; empty if none.")

    @field_validator("summary")
    @classmethod
    def _summary(cls, v: str) -> str:
        return _tidy(v, 240)

    @field_validator("setting")
    @classmethod
    def _setting(cls, v: str) -> str:
        return _tidy(v, 160)

    @field_validator("composition")
    @classmethod
    def _composition(cls, v: str) -> str:
        return _tidy(v, 200)

    @field_validator("mood", "themes", "imagery")
    @classmethod
    def _items(cls, v: list[str]) -> list[str]:
        return [_tidy(x, 60) for x in v]

    @field_validator("palette")
    @classmethod
    def _palette(cls, v: list[str]) -> list[str]:
        out = []
        for color in v:
            color = str(color).strip()
            if not _HEX.match(color):
                raise ValueError("palette colors must look like #1A2B3C")
            out.append(color.upper())
        return out

    @field_validator("language")
    @classmethod
    def _language(cls, v: str) -> str:
        v = (v or "und").strip().lower()
        return v if re.fullmatch(r"[a-z]{2,3}(-[a-z0-9]{2,8})?", v) else "und"

    def prose(self) -> str:
        """All free-text fields joined, used for the copy check and the image prompt."""
        return " ".join(
            [self.summary, *self.mood, *self.themes, *self.imagery, self.setting, self.composition]
        )


_SCHEMA_KEYS = {"type", "properties", "required", "items", "enum", "description"}


def _strip(node: Any) -> Any:
    """Keep only the JSON-schema keywords Claude's structured outputs accept.

    The API rejects maxItems and minItems above 1, so the counts live in the field descriptions
    and are enforced locally by pydantic (see ArtBrief).
    """
    if isinstance(node, dict):
        out: dict[str, Any] = {}
        for key, value in node.items():
            if key == "properties":
                out[key] = {name: _strip(sub) for name, sub in value.items()}
            elif key == "minItems":
                if value in (0, 1):
                    out[key] = value
            elif key in _SCHEMA_KEYS:
                out[key] = _strip(value)
        if out.get("type") == "object" and "properties" in out:
            out["required"] = list(out["properties"])  # every field required
            out["additionalProperties"] = False
        return out
    if isinstance(node, list):
        return [_strip(x) for x in node]
    return node


def llm_schema() -> dict[str, Any]:
    """A plain JSON schema for the model. Strict checks happen locally with pydantic."""
    return _strip(ArtBrief.model_json_schema())
