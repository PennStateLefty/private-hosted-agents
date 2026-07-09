// main.bicep — demo workload skeleton for the MCAPS mcaps-foundation landing zone.
//
// This is an intentionally thin starting point. Fill it in with the help of the
// `scaffold-demo` agent + the `mcaps-compliance` Skill, discovering live landing-zone
// handles (hub VNet, PE subnet, private DNS zone IDs) via the Azure MCP server.
//
// Golden rules (see .github/copilot-instructions.md):
//   - AVM modules (br/public:avm/res/...), pinned + Renovate-managed
//   - publicNetworkAccess 'Disabled' + private endpoints into the hub privatelink.* zones
//   - Entra / managed-identity auth only (no keys/secrets)
//   - subnets defaultOutboundAccess:false; idempotent; approved region (default Central US)

targetScope = 'subscription'

@description('Demo name — used to derive resource names and the spoke RG.')
param demoName string

@description('Deployment region. Approved regions only; never West Europe for non-prod.')
param location string = 'centralus'

@description('Resource IDs discovered from the landing zone at deploy time (do NOT hardcode).')
param privateEndpointSubnetId string
param privateDnsZoneIds object = {}

@description('Common tags (map workload identity to Service Tree per SFI-010).')
param tags object = {}

var namePrefix = 'demo-${demoName}'

resource rg 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: 'rg-${namePrefix}'
  location: location
  tags: tags
}

// ── TODO: add your workload here ─────────────────────────────────────────────
// Example (uncomment + pin a version, then apply compliant presets from the Skill):
//
// module storage 'br/public:avm/res/storage/storage-account:<ver>' = {
//   scope: rg
//   name: 'storage'
//   params: {
//     name: replace('st${namePrefix}', '-', '')
//     allowSharedKeyAccess: false
//     allowBlobPublicAccess: false
//     publicNetworkAccess: 'Disabled'
//     privateEndpoints: [ { subnetResourceId: privateEndpointSubnetId, privateDnsZoneResourceIds: [ privateDnsZoneIds.blob ] } ]
//     tags: tags
//   }
// }
// ─────────────────────────────────────────────────────────────────────────────

output resourceGroupName string = rg.name
