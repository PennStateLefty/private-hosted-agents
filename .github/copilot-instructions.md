# .github/copilot-instructions.md — landing-zone context for demo repos
#
# This file orients any GitHub Copilot session (CLI, GitHub App, or VS Code)
# to the MCAPS "mcaps-foundation" landing zone. It is safe to share (no
# confidential content). The confidential MCAPS policy detail lives in the
# local `mcaps-compliance` Copilot Skill — invoke that, never paste catalogs here.

## What this repo is

A demo project that deploys into an existing **MCAPS-managed Azure landing zone**
(`mcaps-foundation`, a hub-and-spoke topology in a single MCAP-managed subscription).
Each demo lives in its own repo (stamped from `mcaps-demo-template`) with its own IaC,
but must fit the landing zone's topology and satisfy MCAPS compliance.

## Golden rules (do these every time)

1. **Compliance first — use the `mcaps-compliance` Skill.** Before authoring or
   deploying any Azure resource, consult the local **`mcaps-compliance`** Copilot Skill.
   It carries the authoritative MCAPS guardrails and compliant-by-default presets.
   Do NOT hardcode or paste MCAPS policy text into this repo.
2. **Discover live handles at runtime via the Azure MCP server — never hardcode.**
   The landing zone's resource IDs change per deployment. Query the **Azure MCP**
   server for current values (see "Discovering landing-zone handles" below).
3. **Build on Azure Verified Modules (AVM).** Reference `br/public:avm/res/...`,
   pin versions, and apply the compliant presets from the Skill (AVM defaults are
   NOT MCAPS-compliant — e.g. `publicNetworkAccess` defaults to `Enabled`).
4. **Private by default.** `publicNetworkAccess: 'Disabled'` + private endpoints into
   the hub's `privatelink.*` zones; managed-identity + Entra auth only (no keys/secrets);
   subnets set `defaultOutboundAccess: false`.
5. **Idempotent / redeployable.** MCAPS cost automation resizes/deallocates resources
   nightly — your deploy must re-run cleanly and re-assert desired state.
6. **Region:** default to an approved region (**Central US** for this landing zone).
   Never default to West Europe for non-prod.

## Landing-zone topology (stable facts)

- **Single MCAP-managed subscription**, single central **hub** VNet (`10.0.0.0/16`) +
  global-peered **spokes** (one per demo).
- **Connectivity:** reach private resources over the **Point-to-Site VPN** (Entra auth).
  DNS resolves via the hub's **DNS Private Resolver** (inbound endpoint pushed to VPN clients).
- **Shared services in the hub:** Key Vault, Azure Container Registry (Premium), a
  user-assigned managed identity — all private-endpoint + no-local-auth.
- **Private DNS zones** are global, hosted once in the hub, auto-linked to spokes.
- **Naming:** CAF abbreviations + an 8-char `take(uniqueString(...), 8)` suffix.

## Discovering landing-zone handles (via Azure MCP — do not hardcode)

Ask the Azure MCP server for the current values, locating them by these **stable**
identifiers (the landing zone's resource-group and naming conventions):

| Need | How to find it |
| --- | --- |
| Hub VNet + subnets | RG `rg-connectivity-hub`, VNet `vnet-*-hub-*`; PE subnet `snet-privateendpoints` |
| Private DNS zone IDs | RG `rg-dns`, zones `privatelink.*` (blob, vaultcore, azurecr.io, etc.) |
| DNS resolver inbound IP | RG `rg-dns` / hub — inbound endpoint static IP (pushed to VPN clients) |
| Shared ACR | RG `rg-connectivity-hub`, `cr*` (login server `cr*.azurecr.io`) |
| Shared Key Vault | RG `rg-connectivity-hub`, `kv-*` |
| Shared managed identity | RG `rg-connectivity-hub`, `id-*` (use its clientId for workload auth) |

If a spoke does not yet exist for this demo, create one (VNet + subnet with
`defaultOutboundAccess: false`, global peering to the hub with gateway transit, and
auto-link to the hub's private DNS zones), then deploy the workload into it.

## Where to build

- `infra/` — your Bicep (AVM-based, compliant presets). Start from the skeleton provided.
- Deploy with `az deployment sub create` (or `azd`), passing the region parameter.
- Run a compliance pass (invoke `mcaps-compliance`) on the what-if before deploying.

## Do NOT

- Do NOT copy `docs/research/` or any MCAPS catalog into this repo — confidential/local-only.
- Do NOT hardcode subscription IDs, resource IDs, or secrets.
- Do NOT enable public network access or key/local auth on PaaS resources.
