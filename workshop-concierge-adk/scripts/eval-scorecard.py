#!/usr/bin/env python3
"""G5 deterministic scorecard — query the DEPLOYED hosted agent with the golden
set and score exact track-match accuracy over the private endpoint.

This is the architecture-preserving, objective corroboration of the Foundry eval
(intent resolution). It proves the deployed agent routes every labeled query to
the correct workshop track. Requires: VPN connected, `az login`, wc-dev env.
"""
import json
import os
import re
import subprocess
import sys
import time
import urllib.request

ENDPOINT = (
    "https://aif-zliorc-pha-dev-ncus-001.services.ai.azure.com/api/projects/"
    "aifp-zliorc-pha-dev-ncus-001/agents/workshop-concierge/endpoint/protocols/"
    "openai/responses?api-version=v1"
)
GOLDEN = os.path.join(os.path.dirname(__file__), "..", "tests", "golden.jsonl")

# Map a ground-truth sentence to the canonical expected track id.
TRACKS = ("build", "integrate", "govern")


def expected_track(ground_truth: str) -> str:
    m = re.search(r"Recommend the (\w+) track", ground_truth)
    return m.group(1).lower() if m else ""


def observed_track(text: str) -> str:
    """Extract the single recommended track from the agent's prose deterministically.

    The agent says e.g. 'Best fit: Build Track' / 'The Govern track fits best' /
    'You should choose the Build track'. We take the first track keyword that
    appears in a recommending context, ignoring the 'alternative' offer sentence.
    """
    low = text.lower()
    # Cut off the optional 'single best alternative' offer so it can't shadow.
    for marker in ("single best alternative", "single a", "if you want", "if you'd like"):
        idx = low.find(marker)
        if idx != -1:
            low = low[:idx]
            break
    hits = [(low.find(t), t) for t in TRACKS if low.find(t) != -1]
    hits = [(i, t) for i, t in hits if i != -1]
    if not hits:
        return ""
    hits.sort()
    return hits[0][1]


def token() -> str:
    out = subprocess.run(
        ["az", "account", "get-access-token", "--resource", "https://ai.azure.com",
         "--query", "accessToken", "-o", "tsv"],
        capture_output=True, text=True, check=True,
    )
    return out.stdout.strip()


def call(query: str, tok: str) -> str:
    body = json.dumps({"model": "workshop-concierge", "input": query}).encode()
    last = None
    for attempt in range(4):  # bounded retries for transient platform 5xx
        try:
            req = urllib.request.Request(
                ENDPOINT, data=body,
                headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=90) as r:
                d = json.load(r)
            if d.get("status") == "completed":
                return d["output"][0]["content"][0]["text"]
            last = f"status={d.get('status')} err={d.get('error')}"
        except Exception as e:  # noqa: BLE001 - transient network/5xx
            last = str(e)
        time.sleep(3 * (attempt + 1))
    raise RuntimeError(last)


def run_once(rows, tok):
    correct = 0
    details = []
    for row in rows:
        exp = expected_track(row["ground_truth"])
        text = call(row["query"], tok)
        obs = observed_track(text)
        ok = obs == exp
        correct += ok
        details.append({"query": row["query"], "expected": exp, "observed": obs, "pass": ok})
    return correct, details


def main():
    rows = [json.loads(l) for l in open(GOLDEN) if l.strip()]
    passes = 0
    for run in range(1, 4):  # 3 consecutive runs
        tok = token()  # refresh per run to avoid mid-run expiry
        correct, details = run_once(rows, tok)
        acc = correct / len(rows)
        print(f"\n=== RUN {run}: {correct}/{len(rows)} correct ({acc:.0%}) ===")
        for d in details:
            flag = "PASS" if d["pass"] else "FAIL"
            print(f"  [{flag}] exp={d['expected']:9s} obs={d['observed']:9s} | {d['query'][:60]}")
        json.dump({"run": run, "correct": correct, "total": len(rows), "accuracy": acc,
                   "details": details},
                  open(os.path.join(os.path.dirname(__file__), "..", "evidence",
                                    f"g5-scorecard-run{run}.json"), "w"), indent=2)
        if correct == len(rows):
            passes += 1
    print(f"\nCONSECUTIVE 100% RUNS: {passes}/3")
    sys.exit(0 if passes == 3 else 1)


if __name__ == "__main__":
    main()
