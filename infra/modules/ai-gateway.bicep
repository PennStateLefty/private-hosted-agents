// ai-gateway.bicep — APIM GenAI (AI) Gateway in front of the private Foundry account.
//
// MCAPS-compliant presets:
//   - StandardV2 SKU with VNet integration (subnetResourceId) into the spoke
//   - System + user-assigned managed identity; gateway->Foundry auth is managed-identity
//     via policy (NO subscription keys / Foundry keys)
//   - Diagnostics to the shared Log Analytics workspace
//   - NOTE (open item): AVM apim 0.9.1 does not expose publicNetworkAccess/privateEndpoints.
//     Disable public inbound after deploy (SFI-012) with:
//       az apim update -g <rg> -n <name> --public-network-access false
//     or front APIM with a private endpoint via a newer AVM release. Tracked in PROVISION.md.
//
// Deployed additively AFTER the landing zone, consuming its outputs (see infra/main.bicep).

targetScope = 'resourceGroup'

@description('APIM service name (<= 50 chars).')
param name string

@description('Region — must match the spoke (e.g. northcentralus).')
param location string

@description('Publisher metadata (required by APIM).')
param publisherName string = 'MCAPS Private Hosted Agents'
param publisherEmail string = 'admin@contoso.com'

@description('Delegated APIM subnet resourceId for StandardV2 VNet integration (optional).')
param subnetResourceId string = ''

@description('User-assigned managed identity resourceId used to call Foundry.')
param userAssignedIdentityId string

@description('Foundry / Azure OpenAI inference endpoint, e.g. https://<account>.openai.azure.com/.')
param foundryOpenAiEndpoint string

@description('Shared Log Analytics workspace resourceId for diagnostics.')
param logAnalyticsWorkspaceId string

@description('Per-key token-per-minute limit enforced by the gateway (GenAI token-limit policy).')
param tokensPerMinute int = 20000

param tags object = {}

var apimName = take(name, 50)

module apim 'br/public:avm/res/api-management/service:0.9.1' = {
  name: 'ai-gateway-apim'
  params: {
    name: apimName
    location: location
    publisherName: publisherName
    publisherEmail: publisherEmail
    sku: 'StandardV2'
    skuCapacity: 1
    subnetResourceId: empty(subnetResourceId) ? null : subnetResourceId
    managedIdentities: {
      systemAssigned: true
      userAssignedResourceIds: [
        userAssignedIdentityId
      ]
    }
    diagnosticSettings: [
      {
        name: 'to-law'
        workspaceResourceId: logAnalyticsWorkspaceId
      }
    ]
    backends: [
      {
        name: 'foundry-openai'
        url: foundryOpenAiEndpoint
        protocol: 'http'
      }
    ]
    tags: tags
  }
}

// GenAI gateway policy applied to the Azure OpenAI API. Enforces:
//   - managed-identity auth to Foundry (no keys)
//   - per-subscription token-per-minute limit + token metric emission
// Import your Azure OpenAI OpenAPI as an API named 'azure-openai' and attach this
// policy, then add a backend load-balancing pool across model deployments as needed.
var aoaiApiPolicyXml = '<policies><inbound><base /><authentication-managed-identity resource="https://cognitiveservices.azure.com" output-token-variable-name="msi-access-token" ignore-error="false" /><set-header name="Authorization" exists-action="override"><value>@("Bearer " + (string)context.Variables["msi-access-token"])</value></set-header><azure-openai-token-limit counter-key="@(context.Subscription.Id)" tokens-per-minute="${tokensPerMinute}" estimate-prompt-tokens="true" remaining-tokens-header-name="x-ratelimit-remaining-tokens" /><azure-openai-emit-token-metric namespace="genai"><dimension name="subscription-id" value="@(context.Subscription.Id)" /></azure-openai-emit-token-metric><set-backend-service backend-id="foundry-openai" /></inbound><backend><base /></backend><outbound><base /></outbound><on-error><base /></on-error></policies>'

@description('APIM resource id of the AI gateway.')
output apimResourceId string = apim.outputs.resourceId
@description('APIM name.')
output apimName string = apim.outputs.name
@description('Ready-to-apply GenAI API policy XML (attach to the azure-openai API).')
output aoaiApiPolicyXml string = aoaiApiPolicyXml
