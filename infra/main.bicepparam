using './main.bicep'

// Phase 1 AI Gateway params. Populate the *ResourceId/endpoint values from the
// landing-zone azd outputs after `azd provision`:
//   cd landing-zone && azd env get-values
// Do NOT hardcode long-term — these are per-deployment handles.

param spokeResourceGroupName = '<landing-zone spoke RG, e.g. rg-pha-dev>'
param location = 'northcentralus'
param aiGatewayName = 'apim-pha-dev'

param userAssignedIdentityId = '<lz output: user-assigned MI resourceId>'
param foundryOpenAiEndpoint = '<lz output: https://<account>.openai.azure.com/>'
// Use the spoke-local Log Analytics workspace the landing zone creates in
// northcentralus — NOT the Central US hub LAW (avoids cross-region log egress).
param logAnalyticsWorkspaceId = '<lz output: spoke-local LAW resourceId (northcentralus)>'

// Optional: delegated APIM subnet for StandardV2 VNet integration (leave '' to skip).
param apimSubnetResourceId = ''

param tokensPerMinute = 20000

param tags = {
  workload: 'private-hosted-agents'
  environment: 'dev'
  // serviceTree: '<map to a valid Service Tree service — SFI-010>'
}
