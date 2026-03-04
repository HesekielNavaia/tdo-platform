// acr.bicep - Azure Container Registry with geo-replication

@description('Environment name')
param environment string

@description('Azure region (primary)')
param location string = 'northeurope'

@description('Resource name prefix')
param namePrefix string

@description('Subnet ID for private endpoint')
param privateEndpointsSubnetId string

@description('Private DNS zone ID for ACR')
param dnsZoneAcrId string

@description('Managed identity principal IDs that need ACR pull access')
param pullIdentityPrincipalIds array = []

@description('Managed identity principal IDs that need ACR push access')
param pushIdentityPrincipalIds array = []

// Role IDs
var acrPullRoleId = '7f951dda-4ed3-4680-a7ca-43fe172d538d'
var acrPushRoleId = '8311e382-0749-4cb8-b61a-304f252e45ec'

// ACR name must be globally unique, alphanumeric only, 5–50 chars
// Pad with 'cr' prefix to ensure minimum length is always met
var acrBaseName = '${replace(namePrefix, '-', '')}acr${environment}'
var acrName = length(acrBaseName) < 5 ? 'tdoacr${environment}' : acrBaseName

// ── Container Registry ────────────────────────────────────────────────────────

resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: length(acrBaseName) > 50 ? substring(acrBaseName, 0, 50) : acrName
  location: location
  sku: {
    name: 'Premium'
  }
  properties: {
    adminUserEnabled: false
    publicNetworkAccess: 'Disabled'
    zoneRedundancy: 'Disabled'
    networkRuleSet: {
      defaultAction: 'Deny'
    }
    policies: {
      quarantinePolicy: {
        status: 'disabled'
      }
      trustPolicy: {
        type: 'Notary'
        status: 'disabled'
      }
      retentionPolicy: {
        days: 30
        status: 'enabled'
      }
    }
    encryption: {
      status: 'disabled'
    }
  }
}

// ── Geo-replication to West Europe ────────────────────────────────────────────

resource acrReplication 'Microsoft.ContainerRegistry/registries/replications@2023-07-01' = {
  name: 'westeurope'
  parent: acr
  location: 'westeurope'
  properties: {
    zoneRedundancy: 'Disabled'
    regionEndpointEnabled: true
  }
}

// ── Private Endpoint ──────────────────────────────────────────────────────────

resource privateEndpointAcr 'Microsoft.Network/privateEndpoints@2023-05-01' = {
  name: '${namePrefix}-pe-acr-${environment}'
  location: location
  properties: {
    subnet: {
      id: privateEndpointsSubnetId
    }
    privateLinkServiceConnections: [
      {
        name: '${namePrefix}-plsc-acr-${environment}'
        properties: {
          privateLinkServiceId: acr.id
          groupIds: ['registry']
        }
      }
    ]
  }
}

resource privateEndpointDnsGroup 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2023-05-01' = {
  name: 'acrDnsZoneGroup'
  parent: privateEndpointAcr
  properties: {
    privateDnsZoneConfigs: [
      {
        name: 'acr'
        properties: {
          privateDnsZoneId: dnsZoneAcrId
        }
      }
    ]
  }
}

// ── RBAC: AcrPull for workload identities ─────────────────────────────────────

resource acrPullRoleAssignments 'Microsoft.Authorization/roleAssignments@2022-04-01' = [
  for principalId in pullIdentityPrincipalIds: {
    name: guid(acr.id, principalId, acrPullRoleId)
    scope: acr
    properties: {
      roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', acrPullRoleId)
      principalId: principalId
      principalType: 'ServicePrincipal'
    }
  }
]

// ── RBAC: AcrPush for CI/CD identities ───────────────────────────────────────

resource acrPushRoleAssignments 'Microsoft.Authorization/roleAssignments@2022-04-01' = [
  for principalId in pushIdentityPrincipalIds: {
    name: guid(acr.id, principalId, acrPushRoleId)
    scope: acr
    properties: {
      roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', acrPushRoleId)
      principalId: principalId
      principalType: 'ServicePrincipal'
    }
  }
]

// ── Outputs ───────────────────────────────────────────────────────────────────

output acrId string = acr.id
output acrName string = acr.name
output acrLoginServer string = acr.properties.loginServer
