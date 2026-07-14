// app-gateway.bicep — Public ingress for the Foundry Hosted Agent's activity-protocol
// endpoint so Microsoft Teams / M365 Copilot Bot Channel Adapters can reach it while the
// Foundry project stays PNA-disabled (private endpoint only).
//
// SANCTIONED PUBLIC-INGRESS EXCEPTION — this template intentionally creates a public IP.
// It is deploy-gated (PUBLIC_INGRESS_ENABLED) and requires an MCAPS policy exception plus a
// TLS certificate. See architecture/decisions/ADR-001-teams-public-ingress.md.
//
// Path (corrected — no custom bot host):
//   Teams -> Bot Channel Adapter (public MS IPs, BF JWT)
//         -> Azure Bot Service (endpoint = AGW FQDN + activityProtocol path)
//         -> THIS App Gateway (public IP + TLS terminate + WAF)
//         -> Foundry agent PRIVATE endpoint (services.ai.azure.com -> 192.168.2.30)
//         -> Hosted Agent. Foundry does validate-jwt (issuer https://api.botframework.com)
//            and end-user RBAC itself.
//
// Reference: https://learn.microsoft.com/azure/foundry/agents/how-to/publish-copilot-virtual-network

targetScope = 'resourceGroup'

@description('Application Gateway name.')
param name string

@description('Region — must match the spoke (e.g. northcentralus).')
param location string

@description('Dedicated App Gateway subnet resourceId (v2 requires its own subnet, /26 or larger). Must be pre-created with the AGW NSG — see scripts/create-appgw-subnet.sh.')
param subnetResourceId string

@description('Foundry account FQDN the agent endpoint resolves to, e.g. aif-zliorc-pha-dev-ncus-001.services.ai.azure.com. This is the private-endpoint DNS name; the AGW subnet VNet must be linked to the privatelink.services.ai.azure.com zone so it resolves to the private IP.')
param foundryBackendFqdn string

@description('Public listener hostname (custom domain) presented to the Bot Channel Adapter, e.g. teams-bot.contoso.com. Leave empty to use the AGW public IP FQDN and a matching cert.')
param listenerHostName string = ''

@description('Key Vault secret resourceId (unversioned) of the TLS certificate (PFX) for the HTTPS listener. The AGW user-assigned identity needs Key Vault Secrets User on that vault.')
#disable-next-line secure-secrets-in-params // This is a Key Vault secret *reference URI*, not a secret value; AGW resolves it via its UAMI.
param sslCertKeyVaultSecretId string

@description('User-assigned managed identity resourceId AGW uses to read the TLS cert from Key Vault.')
param userAssignedIdentityId string

@description('Public IP name.')
param publicIpName string = '${name}-pip'

@description('Shared Log Analytics workspace resourceId for diagnostics.')
param logAnalyticsWorkspaceId string = ''

@description('Min/Max autoscale capacity (v2).')
param minCapacity int = 1
param maxCapacity int = 2

@description('Predefined SSL policy pinning a minimum TLS version. AppGwSslPolicy20220101 enforces TLS 1.2+ (MCAPS TLS-hardening control). Default listener TLS otherwise still permits TLS 1.0/1.1.')
param sslPolicyName string = 'AppGwSslPolicy20220101'

@description('DNS label for the AGW public IP (must be globally unique within the region).')
param publicIpDnsLabel string = toLower(name)

param tags object = {}

// activityProtocol path the Bot Channel Adapter posts to and that AGW proxies to Foundry.
@description('Agent activityProtocol path (no host), including api-version.')
param activityProtocolPath string

var appGwId = resourceId('Microsoft.Network/applicationGateways', name)
var frontendPortName = 'port443'
var feIpConfigName = 'appGwPublicFrontendIp'
var listenerName = 'https-listener'
var backendPoolName = 'foundry-private-pool'
var backendHttpSettingsName = 'foundry-https-settings'
var probeName = 'activityprotocol-probe'
var sslCertName = 'listener-cert'
var routingRuleName = 'teams-inbound-rule'
var wafPolicyName = '${name}-waf'

// WAF policy — OWASP 3.2 in Prevention mode.
resource wafPolicy 'Microsoft.Network/ApplicationGatewayWebApplicationFirewallPolicies@2023-11-01' = {
  name: wafPolicyName
  location: location
  tags: tags
  properties: {
    policySettings: {
      state: 'Enabled'
      mode: 'Prevention'
      requestBodyCheck: true
      maxRequestBodySizeInKb: 128
      fileUploadLimitInMb: 100
    }
    managedRules: {
      managedRuleSets: [
        {
          ruleSetType: 'OWASP'
          ruleSetVersion: '3.2'
          // Bot Framework activity requests are false-positives against two CRS rules, which
          // together push the anomaly score past the block threshold (949110). This gateway
          // ONLY fronts the Foundry activityProtocol endpoint (Bot Channel Adapter traffic),
          // so disabling exactly these two rules is safe and is the documented Bot Service +
          // WAF remediation. Everything else stays in Prevention.
          //   920300  Request Missing an Accept Header  — the adapter sends no Accept header.
          //   931130  RFI: Off-Domain Reference/Link    — activity JSON carries legit off-domain
          //           serviceUrl links (e.g. smba.trafficmanager.net).
          ruleGroupOverrides: [
            {
              ruleGroupName: 'REQUEST-920-PROTOCOL-ENFORCEMENT'
              rules: [
                {
                  ruleId: '920300'
                  state: 'Disabled'
                }
              ]
            }
            {
              ruleGroupName: 'REQUEST-931-APPLICATION-ATTACK-RFI'
              rules: [
                {
                  ruleId: '931130'
                  state: 'Disabled'
                }
              ]
            }
          ]
        }
      ]
    }
  }
}

resource publicIp 'Microsoft.Network/publicIPAddresses@2023-11-01' = {
  name: publicIpName
  location: location
  tags: tags
  sku: {
    name: 'Standard'
    tier: 'Regional'
  }
  properties: {
    publicIPAllocationMethod: 'Static'
    publicIPAddressVersion: 'IPv4'
    dnsSettings: {
      domainNameLabel: publicIpDnsLabel
    }
  }
}

resource appGw 'Microsoft.Network/applicationGateways@2023-11-01' = {
  name: name
  location: location
  tags: tags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${userAssignedIdentityId}': {}
    }
  }
  properties: {
    sku: {
      name: 'WAF_v2'
      tier: 'WAF_v2'
    }
    autoscaleConfiguration: {
      minCapacity: minCapacity
      maxCapacity: maxCapacity
    }
    firewallPolicy: {
      id: wafPolicy.id
    }
    // Pin minimum TLS 1.2 on the listener — the Azure default predefined policy still
    // permits TLS 1.0/1.1. (MCAPS TLS-hardening remediation.)
    sslPolicy: {
      policyType: 'Predefined'
      policyName: sslPolicyName
    }
    sslCertificates: [
      {
        name: sslCertName
        properties: {
          keyVaultSecretId: sslCertKeyVaultSecretId
        }
      }
    ]
    gatewayIPConfigurations: [
      {
        name: 'appGwIpConfig'
        properties: {
          subnet: {
            id: subnetResourceId
          }
        }
      }
    ]
    frontendIPConfigurations: [
      {
        name: feIpConfigName
        properties: {
          publicIPAddress: {
            id: publicIp.id
          }
        }
      }
    ]
    frontendPorts: [
      {
        name: frontendPortName
        properties: {
          port: 443
        }
      }
    ]
    // Backend = Foundry private endpoint FQDN. The AGW subnet VNet must be linked to the
    // privatelink.services.ai.azure.com zone so this resolves to the private IP (192.168.2.30).
    backendAddressPools: [
      {
        name: backendPoolName
        properties: {
          backendAddresses: [
            {
              fqdn: foundryBackendFqdn
            }
          ]
        }
      }
    ]
    // Health probe on the activityProtocol path. Unauthenticated probes are expected to be
    // rejected by Foundry's validate-jwt (401/403), so treat those as "backend reachable".
    probes: [
      {
        name: probeName
        properties: {
          protocol: 'Https'
          host: foundryBackendFqdn
          path: activityProtocolPath
          interval: 30
          timeout: 30
          unhealthyThreshold: 3
          pickHostNameFromBackendHttpSettings: false
          minServers: 0
          match: {
            statusCodes: [
              '200-499'
            ]
          }
        }
      }
    ]
    backendHttpSettingsCollection: [
      {
        name: backendHttpSettingsName
        properties: {
          protocol: 'Https'
          port: 443
          // Present the real Foundry hostname to the backend so its endpoint accepts the request.
          hostName: foundryBackendFqdn
          pickHostNameFromBackendAddress: false
          requestTimeout: 60
          probe: {
            id: '${appGwId}/probes/${probeName}'
          }
        }
      }
    ]
    httpListeners: [
      {
        name: listenerName
        properties: {
          frontendIPConfiguration: {
            id: '${appGwId}/frontendIPConfigurations/${feIpConfigName}'
          }
          frontendPort: {
            id: '${appGwId}/frontendPorts/${frontendPortName}'
          }
          protocol: 'Https'
          hostName: empty(listenerHostName) ? null : listenerHostName
          requireServerNameIndication: empty(listenerHostName) ? false : true
          sslCertificate: {
            id: '${appGwId}/sslCertificates/${sslCertName}'
          }
        }
      }
    ]
    requestRoutingRules: [
      {
        name: routingRuleName
        properties: {
          ruleType: 'Basic'
          priority: 100
          httpListener: {
            id: '${appGwId}/httpListeners/${listenerName}'
          }
          backendAddressPool: {
            id: '${appGwId}/backendAddressPools/${backendPoolName}'
          }
          backendHttpSettings: {
            id: '${appGwId}/backendHttpSettingsCollection/${backendHttpSettingsName}'
          }
        }
      }
    ]
  }
}

resource agwDiag 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = if (!empty(logAnalyticsWorkspaceId)) {
  name: 'agw-diag'
  scope: appGw
  properties: {
    workspaceId: logAnalyticsWorkspaceId
    logs: [
      {
        categoryGroup: 'allLogs'
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

@description('App Gateway resource id.')
output appGatewayId string = appGw.id

@description('Public IP address of the App Gateway.')
output publicIpAddress string = publicIp.properties.ipAddress

@description('Public FQDN of the App Gateway public IP (use for the bot messaging endpoint if no custom domain).')
output publicIpFqdn string = publicIp.properties.dnsSettings.fqdn

@description('The messaging endpoint to register on the Azure Bot resource = public host + activityProtocol path.')
output messagingEndpoint string = 'https://${empty(listenerHostName) ? publicIp.properties.dnsSettings.fqdn : listenerHostName}${activityProtocolPath}'
