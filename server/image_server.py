"""A tiny image server for Colab (or any GPU machine): POST /generate returns a PNG.

  MODEL_ID=black-forest-labs/FLUX.1-schnell SERVER_TOKEN=<secret> uvicorn server.image_server:app

The heavy imports (torch, diffusers) happen only when the first request needs the model,
so the file can be imported and tested without a GPU.
Not run on a real GPU when this sample was written. On a 16 GB T4 a 12B model needs CPU offload
and may be slow; fp16 on a T4 can produce black images, so bfloat16 is tried first.
"""
from __future__ import annotations

import hmac
import io
import os
from typing import Callable, Optional

from fastapi import FastAPI, Header, HTTPException, Response
from pydantic import BaseModel, Field

GenerateFn = Callable[[str, int, int, int], bytes]


class GenerateRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=2000)
    seed: int = Field(default=0, ge=0, le=2**31 - 1)
    width: int = Field(default=768, ge=256, le=1280, multiple_of=8)
    height: int = Field(default=1024, ge=256, le=1280, multiple_of=8)


def _flux_generate_fn(model_id: str) -> GenerateFn:  # pragma: no cover - needs a GPU
    state: dict = {}

    def generate(prompt: str, seed: int, width: int, height: int) -> bytes:
        if "pipe" not in state:
            import torch
            from diffusers import FluxPipeline

            pipe = FluxPipeline.from_pretrained(model_id, torch_dtype=torch.bfloat16)
            pipe.enable_model_cpu_offload()
            state["pipe"], state["torch"] = pipe, torch
        torch = state["torch"]
        image = state["pipe"](
            prompt=prompt, width=width, height=height, num_inference_steps=4, guidance_scale=0.0,
            max_sequence_length=256, generator=torch.Generator("cpu").manual_seed(seed),
        ).images[0]
        out = io.BytesIO()
        image.save(out, format="PNG")
        return out.getvalue()

    return generate


def create_app(generate_fn: Optional[GenerateFn] = None, token: Optional[str] = None, model_id: Optional[str] = None) -> FastAPI:
    token = token if token is not None else os.environ.get("SERVER_TOKEN", "")
    model_id = model_id or os.environ.get("MODEL_ID", "black-forest-labs/FLUX.1-schnell")
    fn = generate_fn
    app = FastAPI(title="lyric2poster image server")

    @app.get("/health")
    def health() -> dict:
        return {"ok": True, "model": model_id}

    @app.post("/generate")
    def generate(req: GenerateRequest, authorization: str = Header(default="")) -> Response:
        nonlocal fn
        if not token:
            raise HTTPException(503, "Server has no SERVER_TOKEN set.")
        given = authorization.removeprefix("Bearer ").strip()
        if not hmac.compare_digest(given.encode(), token.encode()):
            raise HTTPException(401, "Bad token.")
        if fn is None:
            fn = _flux_generate_fn(model_id)
        try:
            png = fn(req.prompt, req.seed, req.width, req.height)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(500, f"Generation failed ({type(exc).__name__}).") from None
        return Response(content=png, media_type="image/png", headers={"X-Model": model_id})

    return app


app = create_app()
