# infra/

Your demo's Bicep. Subscription-scoped (`targetScope = 'subscription'`), built on
**Azure Verified Modules** with **MCAPS-compliant presets**.

## Deploy

```bash
# discover live landing-zone handles first (via Azure MCP), fill main.bicepparam, then:
az deployment sub create \
  --location centralus \
  --template-file infra/main.bicep \
  --parameters infra/main.bicepparam
```

Before deploying, run a compliance pass: `az deployment sub what-if ...` and use the
`compliance-check` agent (or the `mcaps-compliance` Skill checklist).

See [`../.github/copilot-instructions.md`](../.github/copilot-instructions.md) for the
golden rules and how to discover landing-zone handles.
