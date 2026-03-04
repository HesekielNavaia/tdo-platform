// keyvault.bicep - Key Vault with RBAC authorization

@description('Environment name')
param environment string

@description('Azure region')
param location string = 'northeurope'

@description('Resource name prefix')
param namePrefix string

@description('Tenant ID')
param tenantId string

@description('Object ID of the administrator who gets Key Vault Administrator role')
param administratorObjectId string

@description('Subnet ID for private endpoint')
param privateEndpointsSubnetId string

@description('Private DNS zone ID for Key Vault')
param dnsZoneKeyVaultId string

@description('Managed identity principal IDs that need Key Vault Secrets User role')
param secretsUserPrincipalIds array = []

// Role definition IDs
var kvAdministratorRoleId = '00482a5a-887f-4fb3-b363-3b7fe8e74483'
var kvSecretsUserRoleId = '4633458b-17de-408a-b874-0445c86b69e6'
var kvSecretsOfficerRoleId = 'b86a8fe4-44ce-4948-aee5-eccb2c155cd7'

// ── Key Vault ─────────────────────────────────────────────────────────────────

resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: '${namePrefix}-kv-${environment}'
  location: location
  properties: {
    tenantId: tenantId
    sku: {
      family: 'A'
      name: 'standard'
    }
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 90
    enablePurgeProtection: true
    publicNetworkAccess: 'Disabled'
    networkAcls: {
      bypass: 'AzureServices'
      defaultAction: 'Deny'
      virtualNetworkRules: []
      ipRules: []
    }
  }
}

// ── RBAC: Key Vault Administrator for human administrator ─────────────────────

resource kvAdminRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(keyVault.id, administratorObjectId, kvAdministratorRoleId)
  scope: keyVault
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', kvAdministratorRoleId)
    principalId: administratorObjectId
    principalType: 'User'
  }
}

// ── RBAC: Key Vault Secrets Officer for automation ────────────────────────────

resource kvSecretsOfficerRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(keyVault.id, administratorObjectId, kvSecretsOfficerRoleId)
  scope: keyVault
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', kvSecretsOfficerRoleId)
    principalId: administratorObjectId
    principalType: 'User'
  }
}

// ── RBAC: Key Vault Secrets User for managed identities ──────────────────────

resource kvSecretsUserRoleAssignments 'Microsoft.Authorization/roleAssignments@2022-04-01' = [
  for principalId in secretsUserPrincipalIds: {
    name: guid(keyVault.id, principalId, kvSecretsUserRoleId)
    scope: keyVault
    properties: {
      roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', kvSecretsUserRoleId)
      principalId: principalId
      principalType: 'ServicePrincipal'
    }
  }
]

// ── Private Endpoint ──────────────────────────────────────────────────────────

resource privateEndpointKv 'Microsoft.Network/privateEndpoints@2023-05-01' = {
  name: '${namePrefix}-pe-kv-${environment}'
  location: location
  properties: {
    subnet: {
      id: privateEndpointsSubnetId
    }
    privateLinkServiceConnections: [
      {
        name: '${namePrefix}-plsc-kv-${environment}'
        properties: {
          privateLinkServiceId: keyVault.id
          groupIds: ['vault']
        }
      }
    ]
  }
}

resource privateEndpointDnsGroup 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2023-05-01' = {
  name: 'kvDnsZoneGroup'
  parent: privateEndpointKv
  properties: {
    privateDnsZoneConfigs: [
      {
        name: 'keyvault'
        properties: {
          privateDnsZoneId: dnsZoneKeyVaultId
        }
      }
    ]
  }
}

// ── Outputs ───────────────────────────────────────────────────────────────────

output keyVaultId string = keyVault.id
output keyVaultName string = keyVault.name
output keyVaultUri string = keyVault.properties.vaultUri
