"""Step 3: prompt in, image bytes out. Three engines behind one interface.

demo      Pillow gradient blobs. Offline, free, always works.
hf_space  A public Hugging Face Space (FLUX.1-schnell by default) called with gradio_client.
remote    Your own FLUX server, for example the Colab notebook in notebooks/02_flux_image_server.ipynb.

Streamlit Community Cloud has no GPU, so the real image model always runs somewhere else.
"""
from __future__ import annotations

import io
import random
from dataclasses import dataclass
from typing import Any, Optional, Protocol

from PIL import Image, ImageDraw, ImageFilter

from .config import Settings

WIDTH, HEIGHT = 768, 1024  # 3:4, both multiples of 8


class EngineError(RuntimeError):
    """The engine failed. The message is safe to show to the user."""


@dataclass
class ImageRequest:
    prompt: str
    palette: list[str]
    seed: int
    width: int = WIDTH
    height: int = HEIGHT


@dataclass
class EngineResult:
    png: bytes
    engine: str
    model: str


class ImageEngine(Protocol):
    name: str
    model: str

    def generate(self, req: ImageRequest) -> EngineResult: ...


def to_png(data: bytes) -> bytes:
    image = Image.open(io.BytesIO(data))
    out = io.BytesIO()
    image.convert("RGB").save(out, format="PNG")
    return out.getvalue()


def _rgb(color: str) -> tuple[int, int, int]:
    c = color.lstrip("#")
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


class DemoEngine:
    name = "demo"
    model = "pillow-demo"

    def generate(self, req: ImageRequest) -> EngineResult:
        rng = random.Random(req.seed)
        w, h = req.width, req.height
        colors = [_rgb(c) for c in (req.palette or ["#16192E", "#E4572E", "#F2C14E"])]
        top, bottom = colors[0], colors[min(1, len(colors) - 1)]
        base = Image.new("RGB", (w, h))
        px = ImageDraw.Draw(base)
        for y in range(h):
            t = y / (h - 1)
            px.line([(0, y), (w, y)], fill=tuple(int(top[i] * (1 - t) + bottom[i] * t) for i in range(3)))
        layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(layer)
        for i in range(7):
            r = rng.randint(w // 6, w * 5 // 12)
            cx, cy = rng.randint(0, w), rng.randint(0, int(h * 0.75))
            draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(*colors[i % len(colors)], rng.randint(90, 170)))
        layer = layer.filter(ImageFilter.GaussianBlur(28))
        out = io.BytesIO()
        Image.alpha_composite(base.convert("RGBA"), layer).convert("RGB").save(out, format="PNG")
        return EngineResult(png=out.getvalue(), engine=self.name, model=self.model)


def _first_path(result: Any) -> Optional[str]:
    """gradio_client returns a path, a tuple like (path, seed), or a dict with a 'path' or 'value'."""
    if isinstance(result, str):
        return result
    if isinstance(result, dict):
        value = result.get("path") or result.get("value")
        return _first_path(value) if value is not None else None
    if isinstance(result, (list, tuple)):
        for item in result:
            found = _first_path(item)
            if found:
                return found
    return None


class HFSpaceEngine:
    """Calls a public Hugging Face Space through gradio_client.

    The default arguments match the FLUX.1-schnell Space as we remember its API (api_name "/infer").
    Spaces change. If your call fails, run  Client("<space>").view_api()  and adapt `_predict` below:
    that one function is the only place that knows the Space's argument names.
    ZeroGPU Spaces share a daily GPU quota per account, so pass an HF token for a bigger quota.
    """

    name = "hf_space"

    def __init__(self, space: str, api_name: str = "/infer", token: str = "", client: Any = None) -> None:
        self.model = space
        self._api_name = api_name
        self._token = token
        self._client = client  # created on first use, so a Space problem never breaks the whole app

    def _get_client(self) -> Any:
        if self._client is None:
            import inspect

            from gradio_client import Client

            # gradio_client 2.x renamed hf_token to token; support both.
            params = inspect.signature(Client.__init__).parameters
            kwargs = {}
            if self._token:
                kwargs["token" if "token" in params else "hf_token"] = self._token
            self._client = Client(self.model, **kwargs)
        return self._client

    def _predict(self, req: ImageRequest) -> Any:
        return self._get_client().predict(
            prompt=req.prompt,
            seed=req.seed,
            randomize_seed=False,
            width=req.width,
            height=req.height,
            num_inference_steps=4,
            api_name=self._api_name,
        )

    def generate(self, req: ImageRequest) -> EngineResult:
        try:
            result = self._predict(req)
            path = _first_path(result)
            if not path:
                raise EngineError("The Space returned no image.")
            with open(path, "rb") as fh:
                png = to_png(fh.read())
        except EngineError:
            raise
        except Exception as exc:  # noqa: BLE001
            detail = str(exc).replace(self._token, "***") if self._token else str(exc)
            detail = " ".join(detail.split())[:160]
            raise EngineError(f"The Hugging Face Space call failed ({type(exc).__name__}: {detail}).") from None
        return EngineResult(png=png, engine=self.name, model=self.model)


class RemoteEngine:
    """Calls your own image server (server/image_server.py) over HTTPS with a bearer token."""

    name = "remote"

    def __init__(self, url: str, token: str, session: Any = None, timeout: int = 240) -> None:
        self._url = url.rstrip("/")
        self._token = token
        self._timeout = timeout
        self.model = "remote-server"
        if session is None:
            import requests

            session = requests.Session()
        self._session = session

    def generate(self, req: ImageRequest) -> EngineResult:
        try:
            response = self._session.post(
                f"{self._url}/generate",
                json={"prompt": req.prompt, "seed": req.seed, "width": req.width, "height": req.height},
                headers={"Authorization": f"Bearer {self._token}"},
                timeout=self._timeout,
            )
            if response.status_code == 401:
                raise EngineError("The image server rejected the token.")
            response.raise_for_status()
            png = to_png(response.content)
            model = response.headers.get("X-Model", self.model)
        except EngineError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise EngineError(f"The image server call failed ({type(exc).__name__}). Is the Colab session still running?") from None
        return EngineResult(png=png, engine=self.name, model=model)


def build_engine(settings: Settings, hf_token: str = "") -> ImageEngine:
    """Build the primary engine. Missing settings fall back to the demo engine."""
    if settings.image_engine == "hf_space":
        return HFSpaceEngine(settings.hf_space, settings.hf_api_name, hf_token or settings.hf_token)
    if settings.image_engine == "remote" and settings.remote_url:
        return RemoteEngine(settings.remote_url, settings.remote_token)
    return DemoEngine()


def generate_with_fallback(primary: ImageEngine, req: ImageRequest) -> tuple[EngineResult, bool, str]:
    """Returns (result, fell_back, note). The demo engine is the last resort."""
    try:
        return primary.generate(req), False, ""
    except EngineError as exc:
        if primary.name == "demo":
            raise
        return DemoEngine().generate(req), True, str(exc)
