using './main.bicep'

// Fill these from the landing zone. Discover the resource IDs at deploy time via the
// Azure MCP server (rg-connectivity-hub / rg-dns) — do NOT hardcode them long-term.

param demoName = 'sample'
param location = 'centralus'

// e.g. the hub's snet-privateendpoints subnet resourceId
param privateEndpointSubnetId = '<discover: hub snet-privateendpoints resourceId>'

// e.g. { blob: '<id>', vaultcore: '<id>', azurecr: '<id>' } from rg-dns privatelink.* zones
param privateDnsZoneIds = {}

param tags = {
  workload: 'demo-sample'
  environment: 'dev'
  // serviceTree: '<map to a valid Service Tree service — SFI-010>'
}
