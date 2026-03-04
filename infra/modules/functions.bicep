// functions.bicep - Durable Functions for orchestration
// Managed identity is passed in from the identities module to avoid
// circular dependencies with keyvault and storage modules.

@description('Environment name')
param environment string

@description('Azure region')
param location string = 'northeurope'

@description('Resource name prefix')
param namePrefix string

@description('Subnet ID for Functions VNet integration')
param functionsSubnetId string

@description('Log Analytics workspace ID')
param logAnalyticsWorkspaceId string

@description('App Insights connection string')
param appInsightsConnectionString string

@description('Key Vault URI')
param keyVaultUri string

@description('Storage account name used for task payloads')
param storageAccountName string

@description('Resource ID of the Functions managed identity')
param identityFunctionsId string

@description('Client ID of the Functions managed identity')
param identityFunctionsClientId string

// Role IDs
var storageQueueDataContributorRoleId = '974c5e8b-45b9-4653-ba55-5f855dd0fb88'
var storageTableDataContributorRoleId = '0a9a7e1f-b9d0-4cc4-a60d-0319b160aaa3'

// ── App Service Plan (Elastic Premium for Durable Functions) ──────────────────

resource appServicePlan 'Microsoft.Web/serverfarms@2023-01-01' = {
  name: '${namePrefix}-asp-functions-${environment}'
  location: location
  sku: {
    name: environment == 'prod' ? 'EP2' : 'EP1'
    tier: 'ElasticPremium'
  }
  kind: 'elastic'
  properties: {
    maximumElasticWorkerCount: environment == 'prod' ? 20 : 5
    reserved: false
  }
}

// ── Functions Storage Account (separate from main storage; shared key required) ─

var funcStorageBaseName = '${replace(namePrefix, '-', '')}fnc${environment}'
var funcStorageName = length(funcStorageBaseName) > 24 ? substring(funcStorageBaseName, 0, 24) : funcStorageBaseName

resource functionsStorage 'Microsoft.Storage/storageAccounts@2023-01-01' = {
  name: funcStorageName
  location: location
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    allowBlobPublicAccess: false
    allowSharedKeyAccess: true // Required for Durable Functions task hub runtime
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
  }
}

// ── Function App (Durable Functions) ─────────────────────────────────────────

resource functionApp 'Microsoft.Web/sites@2023-01-01' = {
  name: '${namePrefix}-func-${environment}'
  location: location
  kind: 'functionapp'
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${identityFunctionsId}': {}
    }
  }
  properties: {
    serverFarmId: appServicePlan.id
    virtualNetworkSubnetId: functionsSubnetId
    httpsOnly: true
    siteConfig: {
      netFrameworkVersion: 'v8.0'
      use32BitWorkerProcess: false
      vnetRouteAllEnabled: true
      functionsRuntimeScaleMonitoringEnabled: true
      appSettings: [
        {
          name: 'AzureWebJobsStorage'
          value: 'DefaultEndpointsProtocol=https;AccountName=${functionsStorage.name};AccountKey=${functionsStorage.listKeys().keys[0].value};EndpointSuffix=${az.environment().suffixes.storage}'
        }
        {
          name: 'WEBSITE_CONTENTAZUREFILECONNECTIONSTRING'
          value: 'DefaultEndpointsProtocol=https;AccountName=${functionsStorage.name};AccountKey=${functionsStorage.listKeys().keys[0].value};EndpointSuffix=${az.environment().suffixes.storage}'
        }
        {
          name: 'WEBSITE_CONTENTSHARE'
          value: '${namePrefix}-func-${environment}'
        }
        {
          name: 'FUNCTIONS_EXTENSION_VERSION'
          value: '~4'
        }
        {
          name: 'FUNCTIONS_WORKER_RUNTIME'
          value: 'dotnet-isolated'
        }
        {
          name: 'APPLICATIONINSIGHTS_CONNECTION_STRING'
          value: appInsightsConnectionString
        }
        {
          name: 'KEYVAULT_URI'
          value: keyVaultUri
        }
        {
          name: 'STORAGE_ACCOUNT_NAME'
          value: storageAccountName
        }
        {
          name: 'AZURE_CLIENT_ID'
          value: identityFunctionsClientId
        }
        {
          name: 'DurableTask__HubName'
          value: 'TDOTaskHub${environment}'
        }
        {
          name: 'WEBSITE_RUN_FROM_PACKAGE'
          value: '1'
        }
      ]
      cors: {
        allowedOrigins: ['https://portal.azure.com']
      }
    }
  }
}

// ── Diagnostic Settings ───────────────────────────────────────────────────────

resource funcDiagnostics 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'diag-functions'
  scope: functionApp
  properties: {
    workspaceId: logAnalyticsWorkspaceId
    logs: [
      {
        category: 'FunctionAppLogs'
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

// ── RBAC: Queue + Table access for Durable Functions task hub ─────────────────
// Uses identityFunctionsId (deploy-time known) in guid() to satisfy BCP120.

resource storageQueueRoleFunc 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(functionsStorage.id, identityFunctionsId, storageQueueDataContributorRoleId)
  scope: functionsStorage
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      storageQueueDataContributorRoleId
    )
    principalId: reference(identityFunctionsId, '2023-01-31').principalId
    principalType: 'ServicePrincipal'
  }
}

resource storageTableRoleFunc 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(functionsStorage.id, identityFunctionsId, storageTableDataContributorRoleId)
  scope: functionsStorage
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      storageTableDataContributorRoleId
    )
    principalId: reference(identityFunctionsId, '2023-01-31').principalId
    principalType: 'ServicePrincipal'
  }
}

// ── Outputs ───────────────────────────────────────────────────────────────────

output functionAppId string = functionApp.id
output functionAppName string = functionApp.name
output functionAppHostname string = functionApp.properties.defaultHostName
