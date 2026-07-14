# Final Report — Workshop Concierge Foundry Hosted Agent (Golden Path)

## Outcome

**8 of 9 gates PASS; 1 BLOCKED-EXTERNAL (with a corroborating proof).** Every gate that
could be closed with resources under this workload's control was proven **3 consecutive
times** with objective evidence. The one remaining live step (G3 Teams delivery) is
blocked by a landing-zone ingress toggle + Teams-admin publish, both outside this
workload; its full stack is built and offline-proven.

| Gate | Title | Status | Proof |
| ---- | ----- | ------ | ----- |
| G0 | Repository & environment baseline | **PASS** | env + PNA inventory, private DNS proven, 60 tests |
| G1 | Local Responses adapter | **PASS** | contract tests + linux/amd64 container + live ADK→Foundry model call |
| G2 | Foundry Hosted Agent deployment | **PASS** | `workshop-concierge` agent live; 3/3 completed turns over the private endpoint |
| G3 | Private-network Teams publishing | **BLOCKED-EXTERNAL** | bot adapter + Azure Bot bicep + Teams manifest + publish script, all offline-proven; blocked by `PUBLIC_INGRESS_ENABLED=false` + Teams admin |
| G4 | Adaptive Card + callback correlation | **PASS** | one correlation id threaded intake→recommend→alternative→accept; 3/3 suite |
| G5 | Foundry evaluation | **PASS** | deterministic scorecard 3/3 @ 100% (36/36) on the deployed agent; RAI-judge *run* BLOCKED-EXTERNAL (`raisvc`) |
| G6 | Agent guardrail | **PASS** | ADK before-model guardrail in image v2 → agent v6; 3/3 live blocks, valid flow intact |
| G7 | APIM AI Gateway | **PASS** | token-limit governance 3/3 (429↔200) over the **inbound-private** gateway, MI auth, no keys |
| G8 | Repeatable capstone | **PASS** | end-to-end (routing + guardrail + governance) 3/3 over the private path |

## Architecture (as built)

```
Teams (G3, ready) ──> Bot adapter ──> teams_dispatch (G4 card correlation)
                                           │
                                           ▼
                    Foundry Hosted Agent  "workshop-concierge"  (G2)
                    ADK agent, OpenAI Responses protocol (G1)
                    before_model guardrail (G6)   — Entra-only, private
                                           │  DefaultAzureCredential (MI)
                                           ▼
        APIM AI Gateway (G7)  ── system MI, token-limit + emit-metric ──►  Foundry model "chat"
        StandardV2, VNet-integrated, inbound PRIVATE ENDPOINT                (gpt-5.4-mini, private
        publicNetworkAccess=Disabled                                          endpoint 192.168.2.30)

  Evaluation (G5): golden set ──► deployed agent ──► deterministic scorecard (3× 100%)
```

Everything runs inside the MCAPS `mcaps-foundation` spoke (`vnet-zliorc-pha-dev-ncus-001`,
`192.168.0.0/21`) in `northcentralus`, reached from the workstation over the Azure P2S
VPN. All PaaS endpoints are private (Foundry, ACR, Key Vault, and now the APIM gateway);
auth is Entra / managed-identity only — no keys, connection strings, or SAS anywhere in
the request path.

## Compliance posture (MCAPS)

- **Private by default** — Foundry account, ACR, and the APIM gateway all have
  `publicNetworkAccess=Disabled` with private endpoints into the spoke; subnets set
  `defaultOutboundAccess=false`.
- **No local auth** — the hosted agent, the eval scorecard, and the gateway backend hop
  all authenticate with managed identity + Entra tokens. The only key in the system is
  the APIM **subscription key**, which authenticates the *caller to the gateway* and keys
  the per-tenant token counter; it is never used against a model backend.
- **Approved region** `northcentralus`; **idempotent** IaC (`az deployment sub create` /
  isolated `azd`), safe under the nightly cost-automation resize/deallocate.
- **azd isolation** — the agent has its own azd project (`workshop-concierge-adk/`,
  env `wc-dev`) fully separate from the infra project (`landing-zone/`, `azure-ai-lz` /
  `pha-dev`), per the user requirement (ADR-000).

## Live resources created by this workload

- Foundry Hosted Agent `workshop-concierge` (BYO image
  `crzliorcphadevncus001.azurecr.io/agents/workshop-concierge:v2`).
- APIM `apim-pha-dev` (StandardV2, VNet External) + API `azure-openai` + operation
  `chat-completions` + subscription `wc-test-sub` + token-limit policy; system MI granted
  `Cognitive Services OpenAI User` on the Foundry account.
- Spoke networking: subnet `apim-subnet` (192.168.4.0/27) + NSG `nsg-apim-pha-dev` +
  private endpoint `pe-apim-pha-dev` (via BYO `privatelink.azure-api.net`, hub+spoke
  linked → 192.168.2.26).
- RBAC: agent **instance** MI granted `Cognitive Services OpenAI User` on Foundry.

See `CLEANUP.md` for teardown, `KNOWN-ISSUES.md` for the two external blockers, and
`DEMO-SCRIPT.md` for the guided walkthrough.

## How it was proven (repeatable)

```
cd workshop-concierge-adk
python3 scripts/capstone-proof.py     # G8: routing + guardrail + governance, 3/3 end-to-end
python3 scripts/eval-scorecard.py     # G5: 3× 100% deterministic scorecard
python3 scripts/guardrail-proof.py    # G6: 3× adversarial blocked, valid routes
python3 scripts/gateway-proof.py      # G7: 3× enforce 429 / restore 200, private path
.venv/bin/python -m pytest            # 93 passed (offline suite)
```

Per-gate evidence lives under `evidence/G{0..8}-*.md` with raw `evidence/*-run*.json`
artifacts. `golden-path-status.md` is the durable source of truth for gate state.

## Residual / follow-up

1. **G3 live delivery** — needs a public/relayed HTTPS messaging ingress + Teams-admin
   publish (steps in `KNOWN-ISSUES.md`). Then run `scripts/publish-teams.sh`.
2. **G5 RAI judge** — needs a tenant grant to the RAI evaluation service; the
   deterministic scorecard corroborates intent resolution until then.
3. **Do not commit** `infra/main.live.bicepparam` (contains the subscription id) or
   `/tmp/apim-key.txt`.
