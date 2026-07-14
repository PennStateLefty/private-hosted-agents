"""Contract test for the Responses adapter.

Drives the real ResponsesAgentServerHost (Starlette ASGI) with Starlette's
TestClient, using a ConciergeRunner backed by the scripted FakeLlm — no network.
Proves: /readiness, a non-streaming /responses turn returns valid Responses
output, and an agent failure surfaces as a non-success error (not a 200 with a
success-shaped body).
"""
import pytest
from starlette.testclient import TestClient

from adapter.app import create_app
from adapter.adk_runner import ConciergeRunner
from fakes import FakeLlm


@pytest.fixture()
def client():
    runner = ConciergeRunner(model=FakeLlm(model="fake"))
    app = create_app(runner=runner)
    with TestClient(app) as c:
        yield c


def test_readiness(client):
    resp = client.get("/readiness")
    assert resp.status_code == 200


def test_non_streaming_responses_turn(client):
    resp = client.post(
        "/responses",
        json={
            "input": "I'm a Developer and I want to Build an agent",
            "stream": False,
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # Responses output shape: status completed + output_text somewhere.
    assert body.get("status") in ("completed", "complete"), body
    text = body.get("output_text") or _collect_output_text(body)
    assert "build" in text.lower(), body


def test_agent_failure_is_not_success_shaped():
    class BoomRunner(ConciergeRunner):
        async def run_turn(self, *a, **k):
            raise RuntimeError("boom: simulated agent failure")

    app = create_app(runner=BoomRunner(model=FakeLlm(model="fake")))
    with TestClient(app, raise_server_exceptions=False) as c:
        resp = c.post("/responses", json={"input": "hi", "stream": False})
    # Must NOT be a 200 completed success.
    if resp.status_code == 200:
        body = resp.json()
        assert body.get("status") not in ("completed", "complete"), body
        assert body.get("error") or body.get("status") == "failed", body
    else:
        assert resp.status_code >= 400


def _collect_output_text(body: dict) -> str:
    chunks = []
    for item in body.get("output", []) or []:
        for part in item.get("content", []) or []:
            if isinstance(part, dict) and part.get("text"):
                chunks.append(part["text"])
    return "".join(chunks)
