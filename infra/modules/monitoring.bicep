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

// ── Alert: Crawl Failure (harvest job fails 3+ times) ────────────────────────

resource alertCrawlFailure 'Microsoft.Insights/scheduledQueryRules@2023-03-15-preview' = {
  name: '${namePrefix}-alert-crawl-failure-${environment}'
  location: location
  properties: {
    displayName: 'TDO - Crawl Failure (3+ harvest failures)'
    description: 'Triggers when the portal harvest job fails 3 or more times within a 1-hour window'
    severity: 1
    enabled: true
    evaluationFrequency: 'PT15M'
    windowSize: 'PT1H'
    scopes: [logAnalytics.id]
    criteria: {
      allOf: [
        {
          query: '''
ContainerAppConsoleLogs_CL
| where ContainerName_s has "harvest"
| where Log_s has_any ("FAILED", "ERROR", "Exception")
| summarize FailureCount = count() by bin(TimeGenerated, 1h)
| where FailureCount >= 3
'''
          timeAggregation: 'Count'
          operator: 'GreaterThanOrEqual'
          threshold: 1
          failingPeriods: {
            numberOfEvaluationPeriods: 1
            minFailingPeriodsToAlert: 1
          }
        }
      ]
    }
    actions: {
      actionGroups: [actionGroup.id]
    }
  }
}

// ── Alert: Low Confidence (>20% records below 0.6) ───────────────────────────

resource alertLowConfidence 'Microsoft.Insights/scheduledQueryRules@2023-03-15-preview' = {
  name: '${namePrefix}-alert-low-confidence-${environment}'
  location: location
  properties: {
    displayName: 'TDO - Low Confidence Score (>20% records < 0.6)'
    description: 'Triggers when more than 20% of processed records have a confidence score below 0.6'
    severity: 2
    enabled: true
    evaluationFrequency: 'PT30M'
    windowSize: 'PT1H'
    scopes: [logAnalytics.id]
    criteria: {
      allOf: [
        {
          query: '''
customEvents
| where name == "RecordConfidenceScore"
| extend confidence = toreal(customDimensions["score"])
| summarize
    Total = count(),
    LowConfidence = countif(confidence < 0.6)
| extend LowConfidencePct = todouble(LowConfidence) / todouble(Total) * 100
| where LowConfidencePct > 20
'''
          timeAggregation: 'Count'
          operator: 'GreaterThanOrEqual'
          threshold: 1
          failingPeriods: {
            numberOfEvaluationPeriods: 1
            minFailingPeriodsToAlert: 1
          }
        }
      ]
    }
    actions: {
      actionGroups: [actionGroup.id]
    }
  }
}

// ── Alert: Pipeline Stall ─────────────────────────────────────────────────────

resource alertPipelineStall 'Microsoft.Insights/scheduledQueryRules@2023-03-15-preview' = {
  name: '${namePrefix}-alert-pipeline-stall-${environment}'
  location: location
  properties: {
    displayName: 'TDO - Pipeline Stall (no activity for 2h)'
    description: 'Triggers when no pipeline job activity is detected for more than 2 hours during business hours'
    severity: 2
    enabled: true
    evaluationFrequency: 'PT30M'
    windowSize: 'PT2H'
    scopes: [logAnalytics.id]
    criteria: {
      allOf: [
        {
          query: '''
ContainerAppConsoleLogs_CL
| where ContainerName_s has_any ("harvest", "harmonise", "embed")
| where Log_s has "Processing"
| summarize ActivityCount = count() by bin(TimeGenerated, 2h)
| where ActivityCount == 0
'''
          timeAggregation: 'Count'
          operator: 'GreaterThanOrEqual'
          threshold: 1
          failingPeriods: {
            numberOfEvaluationPeriods: 1
            minFailingPeriodsToAlert: 1
          }
        }
      ]
    }
    actions: {
      actionGroups: [actionGroup.id]
    }
  }
}

// ── Alert: Model Endpoint Unhealthy ──────────────────────────────────────────

resource alertModelEndpointUnhealthy 'Microsoft.Insights/scheduledQueryRules@2023-03-15-preview' = {
  name: '${namePrefix}-alert-model-endpoint-${environment}'
  location: location
  properties: {
    displayName: 'TDO - Model Endpoint Unhealthy'
    description: 'Triggers when the embedding model endpoint returns errors or is unreachable'
    severity: 1
    enabled: true
    evaluationFrequency: 'PT5M'
    windowSize: 'PT15M'
    scopes: [logAnalytics.id]
    criteria: {
      allOf: [
        {
          query: '''
customEvents
| where name == "EmbeddingModelCall"
| extend statusCode = toint(customDimensions["statusCode"])
| where statusCode >= 500 or isnull(statusCode)
| summarize ErrorCount = count() by bin(TimeGenerated, 5m)
| where ErrorCount >= 3
'''
          timeAggregation: 'Count'
          operator: 'GreaterThanOrEqual'
          threshold: 1
          failingPeriods: {
            numberOfEvaluationPeriods: 1
            minFailingPeriodsToAlert: 1
          }
        }
      ]
    }
    actions: {
      actionGroups: [actionGroup.id]
    }
  }
}

// ── Alert: Review Queue Backlog (>500 items) ──────────────────────────────────

resource alertReviewQueueBacklog 'Microsoft.Insights/scheduledQueryRules@2023-03-15-preview' = {
  name: '${namePrefix}-alert-review-queue-${environment}'
  location: location
  properties: {
    displayName: 'TDO - Review Queue Backlog (>500 items)'
    description: 'Triggers when the manual review queue exceeds 500 pending items'
    severity: 3
    enabled: true
    evaluationFrequency: 'PT1H'
    windowSize: 'PT1H'
    scopes: [logAnalytics.id]
    criteria: {
      allOf: [
        {
          query: '''
customMetrics
| where name == "ReviewQueueDepth"
| summarize QueueDepth = max(value) by bin(TimeGenerated, 1h)
| where QueueDepth > 500
'''
          timeAggregation: 'Count'
          operator: 'GreaterThanOrEqual'
          threshold: 1
          failingPeriods: {
            numberOfEvaluationPeriods: 1
            minFailingPeriodsToAlert: 1
          }
        }
      ]
    }
    actions: {
      actionGroups: [actionGroup.id]
    }
  }
}

// ── Alert: Link Health Degradation ───────────────────────────────────────────

resource alertLinkHealthDegradation 'Microsoft.Insights/scheduledQueryRules@2023-03-15-preview' = {
  name: '${namePrefix}-alert-link-health-${environment}'
  location: location
  properties: {
    displayName: 'TDO - Link Health Degradation (>30% broken links)'
    description: 'Triggers when more than 30% of crawled links are broken or unreachable'
    severity: 2
    enabled: true
    evaluationFrequency: 'PT1H'
    windowSize: 'PT4H'
    scopes: [logAnalytics.id]
    criteria: {
      allOf: [
        {
          query: '''
customEvents
| where name == "LinkCheck"
| extend isHealthy = tobool(customDimensions["healthy"])
| summarize
    Total = count(),
    Broken = countif(not(isHealthy))
| extend BrokenPct = todouble(Broken) / todouble(Total) * 100
| where BrokenPct > 30
'''
          timeAggregation: 'Count'
          operator: 'GreaterThanOrEqual'
          threshold: 1
          failingPeriods: {
            numberOfEvaluationPeriods: 1
            minFailingPeriodsToAlert: 1
          }
        }
      ]
    }
    actions: {
      actionGroups: [actionGroup.id]
    }
  }
}

// ── Alert: Embedding Dimension Mismatch ──────────────────────────────────────

resource alertEmbeddingDimMismatch 'Microsoft.Insights/scheduledQueryRules@2023-03-15-preview' = {
  name: '${namePrefix}-alert-embed-dim-${environment}'
  location: location
  properties: {
    displayName: 'TDO - Embedding Dimension Mismatch'
    description: 'Triggers when produced embeddings have an unexpected dimension size'
    severity: 1
    enabled: true
    evaluationFrequency: 'PT15M'
    windowSize: 'PT15M'
    scopes: [logAnalytics.id]
    criteria: {
      allOf: [
        {
          query: '''
customEvents
| where name == "EmbeddingProduced"
| extend dim = toint(customDimensions["dimension"])
| extend expectedDim = toint(customDimensions["expectedDimension"])
| where dim != expectedDim
| summarize MismatchCount = count() by bin(TimeGenerated, 15m)
| where MismatchCount >= 1
'''
          timeAggregation: 'Count'
          operator: 'GreaterThanOrEqual'
          threshold: 1
          failingPeriods: {
            numberOfEvaluationPeriods: 1
            minFailingPeriodsToAlert: 1
          }
        }
      ]
    }
    actions: {
      actionGroups: [actionGroup.id]
    }
  }
}

// ── Outputs ───────────────────────────────────────────────────────────────────

output logAnalyticsId string = logAnalytics.id
output logAnalyticsName string = logAnalytics.name
output logAnalyticsWorkspaceId string = logAnalytics.properties.customerId
output appInsightsId string = appInsights.id
output appInsightsName string = appInsights.name
output appInsightsConnectionString string = appInsights.properties.ConnectionString
output appInsightsInstrumentationKey string = appInsights.properties.InstrumentationKey
