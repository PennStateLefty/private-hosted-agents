# G0 — Environment & Network Baseline

_Captured: 2026-07-10. Autonomous golden-path run._

## Toolchain (host)

| Tool | Version | Source |
| ---- | ------- | ------ |
| Python (workload) | 3.13 | venv `.venv`, container `python:3.13-slim` |
| azd | 1.27.0 | `azd version` |
| az CLI | 2.88.0 | `az version` |
| docker | 29.6.1 | `docker version` |
| gh | 2.96.0 | `gh --version` |

## Workload dependency pins (compliant, sanitized)

| Package | Version |
| ------- | ------- |
| google-adk | 2.4.0 |
| litellm | 1.91.1 |
| azure-ai-agentserver-responses | 1.0.0b8 |
| azure-ai-agentserver-core | 2.0.0b7 |
| azure-ai-projects | 2.3.0 |
| opentelemetry-api | 1.42.1 (pinned; see note) |

**otel pin note:** google-adk 2.4.0 caps `opentelemetry-api<=1.42.1` while
`azure-monitor-opentelemetry-exporter` (transitive) requests `~=1.43.0`. This is
unsatisfiable via a strict resolver. The workload ships a **complete freeze**
(`requirements.lock.txt`) installed with `pip install --no-deps`, pinning
`opentelemetry-api==1.42.1`. Runtime imports verified in both the local venv and
the linux/amd64 container.

## Private-network / compliance state (live, `az`)

Foundry account `aif-zliorc-pha-dev-ncus-001` (RG `rg-pha-dev`):

```
publicNetworkAccess = Disabled     # private-endpoint only (MCAPS POLICY)
disableLocalAuth    = true         # Entra-only, no keys (SFI)
```

### Private DNS resolution (P2S VPN active)

```
$ nslookup aif-zliorc-pha-dev-ncus-001.services.ai.azure.com
Name:    aif-zliorc-pha-dev-ncus-001.privatelink.services.ai.azure.com
Address: 192.168.2.31        # PRIVATE endpoint (not public TM)
```

TCP 443 reachable on all three account FQDNs (`services.ai`, `openai`,
`cognitiveservices`) — `nc -z` succeeded for each.

> Earlier in the run the same host resolved to a **public** address
> (`20.125.164.145`, APIM traffic manager) and TLS was blackholed — the known
> GSA Private Access blocker on the managed Mac. Once GSA Private Access was
> disabled and the Azure P2S VPN connected, the private endpoint resolved and
> the live calls below succeeded. This is the documented unblock path.

## Determinism baseline (offline)

`python -m pytest` (host venv and container `test` stage): **60 passed**.
Covers: recommendation rules (all role×goal), session transitions, bounded
single-alternative loop, input normalization/aliases, invalid-input handling,
ADK tool path with a scripted fake model, and the Responses adapter contract.
