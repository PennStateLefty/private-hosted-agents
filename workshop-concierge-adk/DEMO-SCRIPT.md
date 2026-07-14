# Workshop Concierge — Demo Script

A ~10-minute guided walkthrough of the private-network Foundry Hosted Agent golden
path. Every step runs a real command against live Azure resources. Read
`FINAL-REPORT.md` first for the architecture; this script is the live demo.

## Prerequisites (once)

- **Azure P2S VPN connected** and **GSA Private Access disabled** on the workstation
  (keeps Internet Access + M365). This is what makes the private endpoints resolve —
  `nslookup aif-zliorc-pha-dev-ncus-001.openai.azure.com` must return `192.168.2.30`,
  not a public IP.
- `az login` as `jgutherie@microsoft.com` (subscription `ME-MngEnvMCAP438243-jgutherie-1`).
- APIM subscription key present at `/tmp/apim-key.txt` (regenerate with
  `az apim subscription show -g rg-pha-dev --service-name apim-pha-dev --sid wc-test-sub
  --query primaryKey -o tsv` — the `/listSecrets` variant).
- Python venv: `cd workshop-concierge-adk && python -m venv .venv &&
  .venv/bin/pip install -e .[dev]` (already provisioned in this workspace).

## 0. One-shot end-to-end proof (the money shot)

```
cd workshop-concierge-adk
python3 scripts/capstone-proof.py
```

Expect **3/3 consecutive PASS** — each run routes a real intake on the deployed agent,
blocks an injection attempt, and drives the APIM gateway 429→200 over the private path.

## 1. Deployed hosted agent routes correctly (G2/G4)

```
python3 scripts/eval-scorecard.py       # 3x 100% (12/12) exact track match
```

Talks to the **deployed** agent's private Responses endpoint
(`…/agents/workshop-concierge/endpoint/protocols/openai/responses`). Shows the ADK
agent (running as a Foundry Hosted Agent, Entra-only) routing every labelled query to
build / integrate / govern.

## 2. Guardrail blocks adversarial input (G6)

```
python3 scripts/guardrail-proof.py      # 3x: 4 injections blocked, valid input still routes
```

Same deployed agent; the ADK `before_model_callback` short-circuits injection /
exfiltration / off-scope inputs with a fixed refusal before any model call.

## 3. APIM AI gateway governs model traffic (G7)

```
python3 scripts/gateway-proof.py        # 3x: enforce tpm=100 -> 429, restore tpm=20000 -> 200
```

The gateway sits in front of the private Foundry account, authenticates to the backend
with its **system managed identity** (no keys), and enforces a token-per-minute budget.
Inbound is private (`publicNetworkAccess=Disabled`); the harness pins the APIM private
endpoint IP `192.168.2.26`. A public call returns `403 … use the Private Endpoint`.

Show the public-vs-private contrast live:

```
KEY=$(cat /tmp/apim-key.txt)
# public hostname resolution -> 403 (PNA disabled)
curl -s -o /dev/null -w "public: %{http_code}\n" -H "Ocp-Apim-Subscription-Key: $KEY" \
  -H "Content-Type: application/json" -X POST \
  "https://apim-pha-dev.azure-api.net/openai/deployments/chat/chat/completions?api-version=2025-01-01-preview" \
  -d '{"messages":[{"role":"user","content":"ping"}],"max_completion_tokens":8}'
# pinned to the private endpoint -> 200
curl -s -o /dev/null -w "private: %{http_code}\n" --resolve apim-pha-dev.azure-api.net:443:192.168.2.26 \
  -H "Ocp-Apim-Subscription-Key: $KEY" -H "Content-Type: application/json" -X POST \
  "https://apim-pha-dev.azure-api.net/openai/deployments/chat/chat/completions?api-version=2025-01-01-preview" \
  -d '{"messages":[{"role":"user","content":"ping"}],"max_completion_tokens":8}'
```

## 4. Adaptive Card correlation contract (G4, offline)

```
.venv/bin/python -m pytest tests/test_teams_dispatch.py -q
```

Threads one correlation id across intake → recommend → alternative → accept, enforcing
bounded single-alternative and no-external-commitment across the callback boundary.

## 5. Evaluation scorecard artifacts (G5)

`evidence/g5-scorecard-run{1,2,3}.json` (3× 100%). The Foundry RAI-judge *run* is
BLOCKED-EXTERNAL (tenant `raisvc` restriction) — see `KNOWN-ISSUES.md`.

## 6. Teams delivery stack (G3, ready but BLOCKED-EXTERNAL)

Code, bicep, manifest, and publish script are all built and offline-proven; live
delivery is blocked by `PUBLIC_INGRESS_ENABLED=false` + Teams-admin publish. Walk the
audience through `evidence/G3-teams-publish.md` and `scripts/publish-teams.sh`.

## Wrap-up

Point at `golden-path-status.md` (gate table: 8/9 PASS, G3 BLOCKED-EXTERNAL with exact
unblock steps) and `FINAL-REPORT.md`.
