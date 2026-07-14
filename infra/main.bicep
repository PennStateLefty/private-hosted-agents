// main.bicep — Phase 1 additive AI Gateway for the private hosted-agents spoke.
//
// The landing zone (landing-zone/, troyhite/bicep-ptn-aiml-landing-zone in
// ailz-integrated mode) provisions the private Foundry account, project, Agent
// Service, spoke VNet + private-endpoint subnet, and DNS. This template adds an
// APIM GenAI gateway in FRONT of that Foundry account, consuming the LZ outputs.
//
// Deploy AFTER `azd provision` of the landing zone:
//   az deployment sub create -l northcentralus -f infra/main.bicep -p infra/main.bicepparam
//
// Golden rules (see .github/copilot-instructions.md): AVM modules pinned; PNA Disabled +
// private endpoints; managed-identity auth only; approved region; idempotent.

targetScope = 'subscription'

@description('Spoke resource group created by the landing zone (BYO — must already exist).')
param spokeResourceGroupName string

@description('Region — must match the spoke (e.g. northcentralus).')
param location string = 'northcentralus'

@description('APIM AI gateway name.')
param aiGatewayName string

@description('Optional user-assigned managed identity resourceId used to call Foundry (landing-zone output). Empty = system-assigned only (this LZ sets USE_UAI=false).')
param userAssignedIdentityId string = ''

@description('Foundry / Azure OpenAI inference endpoint (landing-zone output).')
param foundryOpenAiEndpoint string

@description('Shared Log Analytics workspace resourceId for diagnostics.')
param logAnalyticsWorkspaceId string

@description('Delegated APIM subnet resourceId for StandardV2 VNet integration (optional).')
param apimSubnetResourceId string = ''

@description('Per-key token-per-minute limit at the gateway.')
param tokensPerMinute int = 20000

param tags object = {}

resource spokeRg 'Microsoft.Resources/resourceGroups@2024-03-01' existing = {
  name: spokeResourceGroupName
}

module aiGateway 'modules/ai-gateway.bicep' = {
  scope: spokeRg
  name: 'ai-gateway'
  params: {
    name: aiGatewayName
    location: location
    userAssignedIdentityId: userAssignedIdentityId
    foundryOpenAiEndpoint: foundryOpenAiEndpoint
    logAnalyticsWorkspaceId: logAnalyticsWorkspaceId
    subnetResourceId: apimSubnetResourceId
    tokensPerMinute: tokensPerMinute
    tags: tags
  }
}

output aiGatewayResourceId string = aiGateway.outputs.apimResourceId
output aiGatewayName string = aiGateway.outputs.apimName
