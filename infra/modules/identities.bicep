// identities.bicep - User-Assigned Managed Identities for all workloads
// Separated from containerApps.bicep so that other modules (Key Vault, Storage,
// ACR) can reference principal IDs without creating circular dependencies.

@description('Environment name')
param environment string

@description('Azure region')
param location string = 'northeurope'

@description('Resource name prefix')
param namePrefix string

// ── User-Assigned Managed Identities ─────────────────────────────────────────

resource identityHarvest 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: '${namePrefix}-id-harvest-${environment}'
  location: location
}

resource identityHarmonise 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: '${namePrefix}-id-harmonise-${environment}'
  location: location
}

resource identityEmbed 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: '${namePrefix}-id-embed-${environment}'
  location: location
}

resource identityApi 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: '${namePrefix}-id-api-${environment}'
  location: location
}

resource identityFunctions 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: '${namePrefix}-id-functions-${environment}'
  location: location
}

// ── Outputs ───────────────────────────────────────────────────────────────────

output identityHarvestId string = identityHarvest.id
output identityHarvestPrincipalId string = identityHarvest.properties.principalId
output identityHarvestClientId string = identityHarvest.properties.clientId

output identityHarmoniseId string = identityHarmonise.id
output identityHarmonisePrincipalId string = identityHarmonise.properties.principalId
output identityHarmoniseClientId string = identityHarmonise.properties.clientId

output identityEmbedId string = identityEmbed.id
output identityEmbedPrincipalId string = identityEmbed.properties.principalId
output identityEmbedClientId string = identityEmbed.properties.clientId

output identityApiId string = identityApi.id
output identityApiPrincipalId string = identityApi.properties.principalId
output identityApiClientId string = identityApi.properties.clientId

output identityFunctionsId string = identityFunctions.id
output identityFunctionsPrincipalId string = identityFunctions.properties.principalId
output identityFunctionsClientId string = identityFunctions.properties.clientId

output allWorkloadPrincipalIds array = [
  identityHarvest.properties.principalId
  identityHarmonise.properties.principalId
  identityEmbed.properties.principalId
  identityApi.properties.principalId
  identityFunctions.properties.principalId
]

output allWorkloadIdentityIds array = [
  identityHarvest.id
  identityHarmonise.id
  identityEmbed.id
  identityApi.id
  identityFunctions.id
]
