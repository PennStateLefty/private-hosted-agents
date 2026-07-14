// bot-service.bicep — Azure Bot registration + Microsoft Teams channel that fronts
// the Foundry Hosted Agent's NATIVE activity-protocol endpoint (no custom bot host).
//
// Corrected architecture (see architecture/decisions/ADR-001-teams-public-ingress.md
// and https://learn.microsoft.com/azure/foundry/agents/how-to/publish-copilot-virtual-network):
//   - The Foundry agent endpoint speaks the Bot Framework `activity` protocol directly:
//       https://<res>.services.ai.azure.com/api/projects/<proj>/agents/<agent>/endpoint/protocols/activityProtocol
//     Foundry performs the validate-jwt (issuer https://api.botframework.com) and the
//     end-user RBAC itself. There is NO translator web app — `src/bot/messaging.py` is
//     an offline artifact, not part of this delivery path.
//   - The Azure Bot resource only proxies the channel<->agent. `msaAppId` is the agent's
//     instance_identity.principal_id (SingleTenant, no secret — SFI-005), and the bot is
//     created with publicNetworkAccess Disabled per the Foundry private-network guide.
//   - `messagingEndpoint` is the PUBLIC entry point (App Gateway FQDN) + the activityProtocol
//     path; App Gateway TLS-terminates and reverse-proxies to the agent's PRIVATE endpoint
//     (host-override to services.ai.azure.com). See infra/bot/app-gateway.bicep.
//   - Public ingress is a sanctioned exception (PUBLIC_INGRESS_ENABLED); this template stays
//     deploy-gated until that exception + a TLS cert are in place — see evidence/G3-teams-publish.md.
//   - Bot Service is a global resource; `location` is 'global'.

targetScope = 'resourceGroup'

@description('Azure Bot resource name.')
param botName string

@description('Messaging endpoint the Bot Channel Adapter calls: the App Gateway public FQDN carrying the agent activityProtocol path, e.g. https://<agw-fqdn>/api/projects/<proj>/agents/<agent>/endpoint/protocols/activityProtocol?api-version=2025-05-15-preview. App Gateway reverse-proxies this to the agent private endpoint.')
param messagingEndpoint string

@description('Bot msaAppId. For the Foundry-native path this is the agent instance_identity.principal_id (SingleTenant). For a UAMI bot it is the UAMI clientId.')
param msaAppId string

@description('msaApp type. Foundry-native Teams publish uses SingleTenant (agent principal).')
@allowed([ 'UserAssignedMSI', 'SingleTenant', 'MultiTenant' ])
param msaAppType string = 'SingleTenant'

@description('Tenant id (required for SingleTenant / UserAssignedMSI).')
param msaAppTenantId string = tenant().tenantId

@description('UAMI resourceId backing the bot (required only when msaAppType=UserAssignedMSI).')
param msaAppMSIResourceId string = ''

@description('Bot Service SKU. The Foundry guide uses F0; S1 gives higher throughput.')
@allowed([ 'F0', 'S1' ])
param botServiceSku string = 'S1'

@description('Log Analytics workspace resourceId for bot diagnostics.')
param logAnalyticsWorkspaceId string = ''

param tags object = {}

resource bot 'Microsoft.BotService/botServices@2022-09-15' = {
  name: botName
  location: 'global'
  tags: tags
  sku: {
    name: botServiceSku
  }
  kind: 'azurebot'
  properties: {
    displayName: botName
    endpoint: messagingEndpoint
    msaAppId: msaAppId
    msaAppType: msaAppType
    msaAppTenantId: msaAppTenantId
    msaAppMSIResourceId: empty(msaAppMSIResourceId) ? null : msaAppMSIResourceId
    isCmekEnabled: false
    // Private-network posture: the Bot resource itself is created with public network
    // access disabled per the Foundry private-network publish guide. Inbound reaches the
    // agent only through the App Gateway -> private-endpoint path.
    publicNetworkAccess: 'Disabled'
  }
}

resource teamsChannel 'Microsoft.BotService/botServices/channels@2022-09-15' = {
  parent: bot
  name: 'MsTeamsChannel'
  location: 'global'
  properties: {
    channelName: 'MsTeamsChannel'
    properties: {
      isEnabled: true
      acceptedTerms: true
    }
  }
}

resource botDiag 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = if (!empty(logAnalyticsWorkspaceId)) {
  name: 'bot-diag'
  scope: bot
  properties: {
    workspaceId: logAnalyticsWorkspaceId
    logs: [
      {
        category: 'BotRequest'
        enabled: true
      }
    ]
    metrics: [
      {
        category: 'AllMetrics'
        enabled: true
      }
    ]
  }
}

@description('Bot resource id.')
output botResourceId string = bot.id
@description('Bot name (== Teams app bot id reference).')
output botName string = bot.name
