// monitoring.bicep - Log Analytics, App Insights, alert rules

@description('Environment name')
param environment string

@description('Azure region')
param location string = 'northeurope'

@description('Resource name prefix')
param namePrefix string

@description('Email address for alert notifications')
param alertEmailAddress string = 'ops@tdo-platform.example.com'

// ── Log Analytics Workspace ───────────────────────────────────────────────────

resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2022-10-01' = {
  name: '${namePrefix}-law-${environment}'
  location: location
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: environment == 'prod' ? 90 : 30
    features: {
      enableLogAccessUsingOnlyResourcePermissions: true
    }
    workspaceCapping: {
      dailyQuotaGb: environment == 'prod' ? 10 : 1
    }
  }
}

// ── Application Insights ──────────────────────────────────────────────────────

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: '${namePrefix}-ai-${environment}'
  location: location
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logAnalytics.id
    IngestionMode: 'LogAnalytics'
    RetentionInDays: environment == 'prod' ? 90 : 30
    publicNetworkAccessForIngestion: 'Enabled'
    publicNetworkAccessForQuery: 'Enabled'
  }
}

// ── Action Group ──────────────────────────────────────────────────────────────

resource actionGroup 'Microsoft.Insights/actionGroups@2023-01-01' = {
  name: '${namePrefix}-ag-ops-${environment}'
  location: 'global'
  properties: {
    groupShortName: 'TDOOps'
    enabled: true
    emailReceivers: [
      {
        name: 'OpsEmail'
        emailAddress: alertEmailAddress
        useCommonAlertSchema: true
      }
    ]
  }
}

// ── Alert rules removed ───────────────────────────────────────────────────────
// Alert rules that referenced ContainerAppConsoleLogs_CL, customEvents, and
// customMetrics have been removed. These tables require the Container Apps
// diagnostics settings and Application Insights custom telemetry to be
// configured first. Re-add alert rules once the pipeline is emitting logs.

// ── Outputs ───────────────────────────────────────────────────────────────────

output logAnalyticsId string = logAnalytics.id
output logAnalyticsName string = logAnalytics.name
output logAnalyticsWorkspaceId string = logAnalytics.properties.customerId
output appInsightsId string = appInsights.id
output appInsightsName string = appInsights.name
output appInsightsConnectionString string = appInsights.properties.ConnectionString
output appInsightsInstrumentationKey string = appInsights.properties.InstrumentationKey
