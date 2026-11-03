"""Step 2: turn an ArtBrief into one image prompt. Pure text, easy to unit test."""
from __future__ import annotations

from .safety import needs_softening
from .schemas import ArtBrief

STYLE_TEXT = {
    "risograph": "risograph print, limited ink colors, visible grain, slight misregistration, flat shapes",
    "film_grain": "analog film photograph look, soft grain, natural light, shallow depth of field",
    "paper_cut": "layered paper-cut collage with soft shadows between the layers",
    "neon_noir": "neon noir, high contrast, glowing signs, deep shadows, wet reflections",
    "watercolor": "loose watercolor painting, soft bleeding edges, textured paper",
    "bauhaus": "Bauhaus-inspired geometric poster, bold simple shapes, strong grid",
}

NO_TEXT_RULE = (
    "Do not draw any text, letters, numbers, logos, signatures or watermarks anywhere in the image. "
    "Do not depict real people or celebrity likenesses; if figures appear, keep them faceless silhouettes."
)


def build_image_prompt(brief: ArtBrief, style_preset: str | None = None) -> str:
    style = STYLE_TEXT.get(style_preset or brief.style_preset, STYLE_TEXT[brief.style_preset])
    parts = [
        "A vertical 3:4 music cover poster illustration.",
        f"Style: {style}.",
        f"Scene: {brief.setting}.",
        f"Key imagery: {', '.join(brief.imagery)}.",
        f"Mood: {', '.join(brief.mood)}. Themes: {', '.join(brief.themes)}.",
        f"Dominant colors: {', '.join(brief.palette)}.",
        f"Composition: {brief.composition}. Keep calm, uncluttered space along the bottom edge.",
    ]
    if needs_softening(brief):
        parts.append("Treat difficult themes symbolically and abstractly. Show no gore, weapons or nudity.")
    parts.append(NO_TEXT_RULE)
    return " ".join(parts)
