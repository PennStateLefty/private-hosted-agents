using './main.bicep'

// Live landing-zone handles discovered at deploy time (cd landing-zone && azd env get-values
// + az cognitiveservices account show). Do NOT commit long-term values — regenerate per env.

param spokeResourceGroupName = 'rg-pha-dev'
param location = 'northcentralus'
param aiGatewayName = 'apim-pha-dev'

// USE_UAI=false in this landing zone → system-assigned identity only (empty UAMI).
param userAssignedIdentityId = ''
param foundryOpenAiEndpoint = 'https://aif-zliorc-pha-dev-ncus-001.openai.azure.com/'
// Spoke-local Log Analytics (northcentralus) — avoids cross-region log egress.
param logAnalyticsWorkspaceId = '/subscriptions/987a5b92-2573-4981-a76c-bbd7756592c8/resourceGroups/rg-pha-dev/providers/Microsoft.OperationalInsights/workspaces/log-zliorc-pha-dev-ncus-001'

// APIM StandardV2 outbound VNet integration into the dedicated spoke subnet so the
// gateway reaches the private Foundry endpoint (openai privatelink zone is spoke-linked).
param apimSubnetResourceId = '/subscriptions/987a5b92-2573-4981-a76c-bbd7756592c8/resourceGroups/rg-pha-dev/providers/Microsoft.Network/virtualNetworks/vnet-zliorc-pha-dev-ncus-001/subnets/apim-subnet'

param tokensPerMinute = 20000

param tags = {
  workload: 'private-hosted-agents'
  environment: 'dev'
}
