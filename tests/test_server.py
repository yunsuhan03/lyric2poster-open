import io

from fastapi.testclient import TestClient
from PIL import Image

from server.image_server import create_app


def fake(prompt, seed, w, h):
    out = io.BytesIO()
    Image.new("RGB", (w // 16, h // 16), (9, 9, 9)).save(out, format="PNG")
    return out.getvalue()


def client(token="tok", fn=fake):
    return TestClient(create_app(generate_fn=fn, token=token, model_id="test-model"))


def test_auth_and_success():
    c = client()
    body = {"prompt": "a harbor", "seed": 3}
    assert c.post("/generate", json=body).status_code == 401
    assert c.post("/generate", json=body, headers={"Authorization": "Bearer nope"}).status_code == 401
    r = c.post("/generate", json=body, headers={"Authorization": "Bearer tok"})
    assert r.status_code == 200 and r.content[:4] == b"\x89PNG" and r.headers["x-model"] == "test-model"


def test_no_token_configured_refuses():
    assert client(token="").post("/generate", json={"prompt": "x"}, headers={"Authorization": "Bearer "}).status_code == 503


def test_validation_and_failure_hidden():
    c = client()
    h = {"Authorization": "Bearer tok"}
    assert c.post("/generate", json={"prompt": "x", "width": 100}, headers=h).status_code == 422
    assert c.post("/generate", json={"prompt": "x", "width": 770}, headers=h).status_code == 422

    def boom(*a):
        raise RuntimeError("gpu secret")
    r = client(fn=boom).post("/generate", json={"prompt": "x"}, headers=h)
    assert r.status_code == 500 and "gpu secret" not in r.text
    assert c.get("/health").json()["ok"] is True
