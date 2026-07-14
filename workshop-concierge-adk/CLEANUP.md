# Cleanup / Teardown

Order matters: remove dependent resources (private endpoints, DNS links, RBAC) before
their parents, and delete the hosted agent before the spoke networking. All commands are
idempotent. Substitute values from `golden-path-status.md` if the environment changes.

```
SUB=987a5b92-2573-4981-a76c-bbd7756592c8
RG=rg-pha-dev
VNET=vnet-zliorc-pha-dev-ncus-001
DNS_RG=rg-mcaps-dns-dev
FOUNDRY=aif-zliorc-pha-dev-ncus-001
```

## 1. Hosted agent (G2/G6)

```
# Remove the deployed Workshop Concierge agent versions via the isolated azd project.
cd workshop-concierge-adk
azd env select wc-dev
azd down --purge --force        # or delete the agent resource in the Foundry portal
```

> The agent's **instance** managed identity was granted `Cognitive Services OpenAI User`
> on the Foundry account. Remove that role assignment if the identity is torn down:
> `az role assignment delete --assignee <agent-instance-mi> --role "Cognitive Services OpenAI User" --scope <foundry-account-id>`

## 2. APIM AI gateway (G7)

```
# Inbound private endpoint + its DNS
az network private-endpoint delete -g $RG -n pe-apim-pha-dev
az network private-dns link vnet delete -g $DNS_RG -z privatelink.azure-api.net \
  -n link-$VNET -y          # only if this workload created it; leave the BYO zone intact
# APIM service (also drops the azure-openai API, chat-completions op, wc-test-sub, policy)
az apim delete -g $RG -n apim-pha-dev --no-wait -y
# APIM system-MI role grant on Foundry
az role assignment delete --assignee 38157d71-fe44-4139-a516-f5fc3069043d \
  --role "Cognitive Services OpenAI User" \
  --scope /subscriptions/$SUB/resourceGroups/$RG/providers/Microsoft.CognitiveServices/accounts/$FOUNDRY
```

## 3. Spoke networking added for APIM

Delete these **only after** APIM is fully gone (a lingering APIM/PE keeps the subnet in
use):

```
az network vnet subnet delete -g $RG --vnet-name $VNET -n apim-subnet
az network nsg delete -g $RG -n nsg-apim-pha-dev
```

> **Teardown caveat (from prior phases):** if a Container Apps managed environment ever
> binds `agent-subnet`, an orphaned `serviceAssociationLink` can make the spoke VNet
> undeletable (`InUseSubnetCannotBeDeleted`) and silently stall `azd down` /
> `az group delete`. If the backing managed env is in a Microsoft-managed subscription
> (RG like `hobov3_*`), only a support ticket can clear it. This capstone did **not**
> bind agent-subnet to a Container Apps env, so `apim-subnet` deletes cleanly once APIM
> and its PE are removed.

## 4. Bot / Teams (G3) — only if deployed

```
az deployment group create ... # was never deployed live (BLOCKED-EXTERNAL)
# If you deployed infra/bot/bot-service.bicep, delete the Azure Bot resource + channel
# and remove the app from the Teams admin center.
```

## 5. Local / scratch

```
rm -f /tmp/apim-key.txt /tmp/g7-policy.json /tmp/g8-policy.json /tmp/policy-body.json /tmp/*.json
# Do NOT commit infra/main.live.bicepparam (contains the subscription id) — delete or keep untracked.
```

## What is intentionally NOT torn down

- The **BYO** private DNS zones in `rg-mcaps-dns-dev` (`privatelink.azure-api.net`,
  `privatelink.openai.azure.com`, `privatelink.azurecr.io`, …) — landing-zone shared,
  hub-owned. Only remove spoke **links** this workload added.
- The shared Foundry account, ACR, Key Vault, VNet, and P2S VPN — landing-zone
  infrastructure managed by the `landing-zone/` azd project (`azure-ai-lz` / `pha-dev`),
  not this workload.
