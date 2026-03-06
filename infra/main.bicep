// main.bicep - TDO Platform infrastructure orchestration
// Deploys all modules for the TDO (Tender Data Observatory) platform.
//
// Deployment order (dependency graph):
//   1. monitoring   - Log Analytics + App Insights (no dependencies)
//   2. network      - VNet, subnets, NSGs, NAT GW, DNS zones (no dependencies)
//   3. identities   - All managed identities (no dependencies)
//   4. acr          - Container Registry + RBAC (needs network, identities)
//   5. storage      - Blob storage + RBAC      (needs network, identities)
//   6. database     - PostgreSQL + pgvector    (needs network)
//   7. keyVault     - Key Vault + RBAC         (needs network, identities)
//   8. containerApps- Jobs + API App           (needs monitoring, network,
//                                               identities, acr, storage,
//                                               database, keyVault)
//   9. functions    - Durable Functions        (needs monitoring, network,
//                                               identities, keyVault, storage)

targetScope = 'resourceGroup'

// ── Parameters ────────────────────────────────────────────────────────────────

@description('Environment name (dev, staging, prod)')
@allowed(['dev', 'staging', 'prod'])
param environment string

@description('Azure region for all resources')
param location string = 'northeurope'

@description('Azure AD tenant ID')
param tenantId string

@description('Object ID of the platform administrator (AAD user or group)')
param administratorObjectId string

@description('Dimension size of the embedding vectors (1024 for most models)')
param embeddingDim int = 1024

@description('Alert notification email address')
param alertEmailAddress string = 'ops@tdo-platform.example.com'

@description('PostgreSQL SKU name')
param postgresSkuName string = 'Standard_B1ms'

@description('PostgreSQL SKU tier')
@allowed(['Burstable', 'GeneralPurpose', 'MemoryOptimized'])
param postgresSkuTier string = 'Burstable'

@description('Use placeholder container image for initial deployment before ACR images are pushed. Set to false after deploy-app has run.')
param initialDeploy bool = true

@description('Apply PostgreSQL server parameter configurations. Set to false on re-deployments to avoid ServerIsBusy errors on an existing server.')
param postgresApplyServerConfig bool = true

@description('Deploy private endpoint for blob storage. Set to false on re-deployments to avoid CannotChangePrivateLinkConnectionOnPrivateEndpoint errors.')
param deployStoragePrivateEndpoint bool = true

// ── Name prefix ───────────────────────────────────────────────────────────────

var namePrefix = 'tdo'

// ── 1. Monitoring ─────────────────────────────────────────────────────────────

module monitoring 'modules/monitoring.bicep' = {
  name: 'monitoring'
  params: {
    environment: environment
    location: location
    namePrefix: namePrefix
    alertEmailAddress: alertEmailAddress
  }
}

// ── 2. Network ────────────────────────────────────────────────────────────────

module network 'modules/network.bicep' = {
  name: 'network'
  params: {
    environment: environment
    location: location
    namePrefix: namePrefix
  }
}

// ── 3. Managed Identities ─────────────────────────────────────────────────────

module identities 'modules/identities.bicep' = {
  name: 'identities'
  params: {
    environment: environment
    location: location
    namePrefix: namePrefix
  }
}

// ── 4. Container Registry ─────────────────────────────────────────────────────

module acr 'modules/acr.bicep' = {
  name: 'acr'
  params: {
    environment: environment
    location: location
    namePrefix: namePrefix
    privateEndpointsSubnetId: network.outputs.privateEndpointsSubnetId
    dnsZoneAcrId: network.outputs.dnsZoneAcrId
    pullIdentityPrincipalIds: identities.outputs.allWorkloadPrincipalIds
    pushIdentityPrincipalIds: []
  }
}

// ── 5. Storage ────────────────────────────────────────────────────────────────

module storage 'modules/storage.bicep' = {
  name: 'storage'
  params: {
    environment: environment
    location: location
    namePrefix: namePrefix
    privateEndpointsSubnetId: network.outputs.privateEndpointsSubnetId
    dnsZoneBlobId: network.outputs.dnsZoneBlobId
    dnsZoneBlobName: network.outputs.dnsZoneBlobName
    identityPrincipalIds: identities.outputs.allWorkloadPrincipalIds
    deployPrivateEndpoint: deployStoragePrivateEndpoint
  }
}

// ── 6. Database ───────────────────────────────────────────────────────────────

module database 'modules/database.bicep' = {
  name: 'database'
  params: {
    environment: environment
    location: location
    namePrefix: namePrefix
    postgresSubnetId: network.outputs.postgresSubnetId
    dnsZonePostgresId: network.outputs.dnsZonePostgresId
    dnsZonePostgresName: network.outputs.dnsZonePostgresName
    tenantId: tenantId
    embeddingDim: embeddingDim
    skuName: postgresSkuName
    skuTier: postgresSkuTier
    storageSizeGB: environment == 'prod' ? 128 : 32
    applyServerConfig: postgresApplyServerConfig
  }
}

// ── 7. Key Vault ──────────────────────────────────────────────────────────────

module keyVault 'modules/keyvault.bicep' = {
  name: 'keyVault'
  params: {
    environment: environment
    location: location
    namePrefix: namePrefix
    tenantId: tenantId
    administratorObjectId: administratorObjectId
    privateEndpointsSubnetId: network.outputs.privateEndpointsSubnetId
    dnsZoneKeyVaultId: network.outputs.dnsZoneKeyVaultId
    // Grant Secrets User to all workload identities
    secretsUserPrincipalIds: identities.outputs.allWorkloadPrincipalIds
  }
}

// ── 8. Container Apps ─────────────────────────────────────────────────────────

module containerApps 'modules/containerApps.bicep' = {
  name: 'containerApps'
  params: {
    environment: environment
    location: location
    namePrefix: namePrefix
    containerAppsSubnetId: network.outputs.containerAppsSubnetId
    logAnalyticsWorkspaceId: monitoring.outputs.logAnalyticsId
    logAnalyticsCustomerId: monitoring.outputs.logAnalyticsWorkspaceId
    appInsightsConnectionString: monitoring.outputs.appInsightsConnectionString
    acrLoginServer: acr.outputs.acrLoginServer
    keyVaultUri: keyVault.outputs.keyVaultUri
    storageAccountName: storage.outputs.storageAccountName
    postgresFqdn: database.outputs.postgresFqdn
    tdoDatabaseName: database.outputs.tdoDatabaseName
    initialDeploy: initialDeploy
    // Identities
    identityHarvestId: identities.outputs.identityHarvestId
    identityHarvestClientId: identities.outputs.identityHarvestClientId
    identityHarmoniseId: identities.outputs.identityHarmoniseId
    identityHarmoniseClientId: identities.outputs.identityHarmoniseClientId
    identityEmbedId: identities.outputs.identityEmbedId
    identityEmbedClientId: identities.outputs.identityEmbedClientId
    identityApiId: identities.outputs.identityApiId
    identityApiClientId: identities.outputs.identityApiClientId
  }
}

// ── 9. Durable Functions ──────────────────────────────────────────────────────

module functions 'modules/functions.bicep' = {
  name: 'functions'
  params: {
    environment: environment
    location: location
    namePrefix: namePrefix
    functionsSubnetId: network.outputs.functionsSubnetId
    logAnalyticsWorkspaceId: monitoring.outputs.logAnalyticsId
    appInsightsConnectionString: monitoring.outputs.appInsightsConnectionString
    keyVaultUri: keyVault.outputs.keyVaultUri
    storageAccountName: storage.outputs.storageAccountName
    identityFunctionsId: identities.outputs.identityFunctionsId
    identityFunctionsClientId: identities.outputs.identityFunctionsClientId
  }
}

// ── Outputs ───────────────────────────────────────────────────────────────────

output resourceGroupName string = resourceGroup().name
output resourceGroupLocation string = resourceGroup().location

output vnetId string = network.outputs.vnetId
output vnetName string = network.outputs.vnetName

output acrLoginServer string = acr.outputs.acrLoginServer
output acrName string = acr.outputs.acrName

output storageAccountName string = storage.outputs.storageAccountName
output storageBlobEndpoint string = storage.outputs.blobEndpoint

output postgresServerName string = database.outputs.postgresServerName
output postgresFqdn string = database.outputs.postgresFqdn
output tdoDatabaseName string = database.outputs.tdoDatabaseName

output keyVaultName string = keyVault.outputs.keyVaultName
output keyVaultUri string = keyVault.outputs.keyVaultUri

output containerAppsEnvName string = containerApps.outputs.containerAppsEnvName
output apiAppFqdn string = containerApps.outputs.apiAppFqdn

output functionAppName string = functions.outputs.functionAppName
output functionAppHostname string = functions.outputs.functionAppHostname

output logAnalyticsName string = monitoring.outputs.logAnalyticsName
output appInsightsName string = monitoring.outputs.appInsightsName
output appInsightsConnectionString string = monitoring.outputs.appInsightsConnectionString

// Managed identity client IDs (useful for configuring apps post-deploy)
output harvestIdentityClientId string = identities.outputs.identityHarvestClientId
output harmoniseIdentityClientId string = identities.outputs.identityHarmoniseClientId
output embedIdentityClientId string = identities.outputs.identityEmbedClientId
output apiIdentityClientId string = identities.outputs.identityApiClientId
output functionsIdentityClientId string = identities.outputs.identityFunctionsClientId
