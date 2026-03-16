// containerApps.bicep - Container Apps Environment, Jobs, and API App
// Managed identities are passed in from the identities module to avoid
// circular dependencies with keyvault and storage modules.

@description('Environment name')
param environment string

@description('Azure region')
param location string = 'northeurope'

@description('Resource name prefix')
param namePrefix string

@description('Subnet ID for Container Apps Environment')
param containerAppsSubnetId string

@description('Log Analytics workspace ID')
param logAnalyticsWorkspaceId string

@description('Log Analytics workspace customer ID')
param logAnalyticsCustomerId string

@description('App Insights connection string')
param appInsightsConnectionString string

@description('ACR login server')
param acrLoginServer string

@description('Key Vault URI')
param keyVaultUri string

@description('Storage account name')
param storageAccountName string

@description('Postgres FQDN')
param postgresFqdn string

@description('TDO database name')
param tdoDatabaseName string

// ── Identity parameters (from identities module) ──────────────────────────────

@description('Resource ID of the Harvest managed identity')
param identityHarvestId string

@description('Client ID of the Harvest managed identity')
param identityHarvestClientId string

@description('Resource ID of the Harmonise managed identity')
param identityHarmoniseId string

@description('Client ID of the Harmonise managed identity')
param identityHarmoniseClientId string

@description('Resource ID of the Embed managed identity')
param identityEmbedId string

@description('Client ID of the Embed managed identity')
param identityEmbedClientId string

@description('Resource ID of the API managed identity')
param identityApiId string

@description('Client ID of the API managed identity')
param identityApiClientId string

@description('Use placeholder image for initial deployment before ACR images are pushed. Set to false after deploy-app has pushed real images.')
param initialDeploy bool = false

// ── Variables ─────────────────────────────────────────────────────────────────

var placeholderImage = 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'

// ── Log Analytics workspace reference (for shared key) ────────────────────────

resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2022-10-01' existing = {
  name: last(split(logAnalyticsWorkspaceId, '/'))
}

// ── Container Apps Managed Environment ───────────────────────────────────────

resource containerAppsEnv 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: '${namePrefix}-cae-${environment}'
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalyticsCustomerId
        sharedKey: logAnalytics.listKeys().primarySharedKey
      }
    }
    vnetConfiguration: {
      infrastructureSubnetId: containerAppsSubnetId
      internal: false
    }
    workloadProfiles: [
      {
        name: 'Consumption'
        workloadProfileType: 'Consumption'
      }
    ]
  }
}

// ── Common environment variables ──────────────────────────────────────────────

var commonEnvVars = [
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
    name: 'POSTGRES_FQDN'
    value: postgresFqdn
  }
  {
    name: 'POSTGRES_DB'
    value: tdoDatabaseName
  }
]

// ── Container App Job: Harvest ────────────────────────────────────────────────

resource jobHarvest 'Microsoft.App/jobs@2024-03-01' = {
  name: '${namePrefix}-job-harvest-${environment}'
  location: location
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${identityHarvestId}': {}
    }
  }
  properties: {
    environmentId: containerAppsEnv.id
    workloadProfileName: 'Consumption'
    configuration: {
      triggerType: 'Manual'
      replicaTimeout: 7200
      replicaRetryLimit: 0
      manualTriggerConfig: {
        parallelism: 1
        replicaCompletionCount: 1
      }
      registries: initialDeploy ? [] : [
        {
          server: acrLoginServer
          identity: identityHarvestId
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'harvest'
          image: initialDeploy ? placeholderImage : '${acrLoginServer}/tdo-api:latest'
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
          env: concat(commonEnvVars, [
            {
              name: 'AZURE_CLIENT_ID'
              value: identityHarvestClientId
            }
            {
              name: 'JOB_NAME'
              value: 'harvest'
            }
            {
              name: 'PORTAL_ID'
              value: ''
            }
          ])
        }
      ]
    }
  }
}

// ── Container App Job: Harmonise ──────────────────────────────────────────────

resource jobHarmonise 'Microsoft.App/jobs@2024-03-01' = {
  name: '${namePrefix}-job-harmonise-${environment}'
  location: location
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${identityHarmoniseId}': {}
    }
  }
  properties: {
    environmentId: containerAppsEnv.id
    workloadProfileName: 'Consumption'
    configuration: {
      triggerType: 'Schedule'
      replicaTimeout: 3600
      replicaRetryLimit: 3
      scheduleTriggerConfig: {
        cronExpression: '0 4 * * *'
        parallelism: 1
        replicaCompletionCount: 1
      }
      registries: initialDeploy ? [] : [
        {
          server: acrLoginServer
          identity: identityHarmoniseId
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'harmonise'
          image: initialDeploy ? placeholderImage : '${acrLoginServer}/tdo-api:latest'
          resources: {
            cpu: json('1.0')
            memory: '2Gi'
          }
          env: concat(commonEnvVars, [
            {
              name: 'AZURE_CLIENT_ID'
              value: identityHarmoniseClientId
            }
            {
              name: 'JOB_NAME'
              value: 'harmonise'
            }
          ])
        }
      ]
    }
  }
}

// ── Container App Job: Embed ──────────────────────────────────────────────────

resource jobEmbed 'Microsoft.App/jobs@2024-03-01' = {
  name: '${namePrefix}-job-embed-${environment}'
  location: location
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${identityEmbedId}': {}
    }
  }
  properties: {
    environmentId: containerAppsEnv.id
    workloadProfileName: 'Consumption'
    configuration: {
      triggerType: 'Schedule'
      replicaTimeout: 7200
      replicaRetryLimit: 2
      scheduleTriggerConfig: {
        cronExpression: '0 6 * * *'
        parallelism: 1
        replicaCompletionCount: 1
      }
      registries: initialDeploy ? [] : [
        {
          server: acrLoginServer
          identity: identityEmbedId
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'embed'
          image: initialDeploy ? placeholderImage : '${acrLoginServer}/tdo-api:latest'
          resources: {
            cpu: json('2.0')
            memory: '4Gi'
          }
          env: concat(commonEnvVars, [
            {
              name: 'AZURE_CLIENT_ID'
              value: identityEmbedClientId
            }
            {
              name: 'JOB_NAME'
              value: 'embed'
            }
          ])
        }
      ]
    }
  }
}

// ── Container App: API ────────────────────────────────────────────────────────

resource appApi 'Microsoft.App/containerApps@2024-03-01' = {
  name: '${namePrefix}-app-api-${environment}'
  location: location
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${identityApiId}': {}
    }
  }
  properties: {
    environmentId: containerAppsEnv.id
    workloadProfileName: 'Consumption'
    configuration: {
      activeRevisionsMode: 'Single'
      secrets: [
        {
          name: 'ghcr-token'
          keyVaultUrl: '${keyVaultUri}secrets/ghcr-token'
          identity: identityApiId
        }
      ]
      ingress: {
        external: true
        targetPort: 8000
        transport: 'http'
        allowInsecure: false
        traffic: [
          {
            weight: 100
            latestRevision: true
          }
        ]
      }
      registries: [
        {
          server: 'ghcr.io'
          username: 'hesekielnavaia'
          passwordSecretRef: 'ghcr-token'
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'api'
          image: initialDeploy ? placeholderImage : 'ghcr.io/hesekielnavaia/tdo-api:latest'
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
          env: concat(commonEnvVars, [
            {
              name: 'AZURE_CLIENT_ID'
              value: identityApiClientId
            }
            {
              name: 'JOB_NAME'
              value: 'api'
            }
          ])
          probes: initialDeploy ? [] : [
            {
              type: 'Liveness'
              httpGet: {
                path: '/healthz'
                port: 8000
                scheme: 'HTTP'
              }
              initialDelaySeconds: 10
              periodSeconds: 30
            }
            {
              type: 'Readiness'
              httpGet: {
                path: '/ready'
                port: 8000
                scheme: 'HTTP'
              }
              initialDelaySeconds: 5
              periodSeconds: 10
            }
          ]
        }
      ]
      scale: {
        minReplicas: 1
        maxReplicas: environment == 'prod' ? 10 : 2
        rules: [
          {
            name: 'http-scaling'
            http: {
              metadata: {
                concurrentRequests: '20'
              }
            }
          }
        ]
      }
    }
  }
}

// ── Outputs ───────────────────────────────────────────────────────────────────

output containerAppsEnvId string = containerAppsEnv.id
output containerAppsEnvName string = containerAppsEnv.name
output apiAppFqdn string = appApi.properties.configuration.ingress.fqdn
