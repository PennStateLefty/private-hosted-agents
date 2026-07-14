#!/usr/bin/env python
"""Live smoke: run the REAL Workshop Concierge ADK agent against the Foundry
model over the private network. Proves D1 (ADK -> Foundry model) and G1's live
criterion. Requires P2S VPN + `az login`.

Usage: FOUNDRY_PROJECT_ENDPOINT=... python scripts/smoke-live.py
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

os.environ.setdefault("OTEL_SDK_DISABLED", "true")
os.environ.setdefault(
    "FOUNDRY_PROJECT_ENDPOINT",
    "https://aif-zliorc-pha-dev-ncus-001.services.ai.azure.com/api/projects/aifp-zliorc-pha-dev-ncus-001",
)
os.environ.setdefault("MODEL_DEPLOYMENT_NAME", "chat")


async def main() -> int:
    from adapter.adk_runner import ConciergeRunner
    from workshop_concierge.agent import build_foundry_model

    model = build_foundry_model()
    runner = ConciergeRunner(model=model)
    conv = "smoke-live-1"

    print(">> turn 1: intake")
    r1 = await runner.run_turn(
        conv, "Hi! I'm a Developer and my goal is to Build an agent.",
        correlation_id="smoke-corr-1",
    )
    print("agent:", r1)

    session = await runner.session_service.get_session(
        app_name=runner.app_name, user_id=runner.user_id, session_id=conv
    )
    rec = session.state.get("recommendation")
    print("tool recommendation track_id:", rec.get("track_id") if rec else None)
    print("correlation_id in state:", session.state.get("correlation_id"))

    print(">> turn 2: alternative (continuity)")
    r2 = await runner.run_turn(conv, "Show me the alternative track.")
    print("agent:", r2)

    ok = bool(rec and rec.get("track_id") == "build")
    print("\nRESULT:", "PASS" if ok else "CHECK", "- tool selected track:",
          rec.get("track_id") if rec else None)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
