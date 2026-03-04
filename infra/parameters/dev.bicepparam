// dev.bicepparam - Development environment parameters for TDO Platform
// Usage: az deployment group create \
//   --resource-group tdo-platform-dev \
//   --template-file ../main.bicep \
//   --parameters dev.bicepparam

using '../main.bicep'

// ── Required parameters ───────────────────────────────────────────────────────

param environment = 'dev'

param location = 'northeurope'

// Replace with your Azure AD tenant ID
// az account show --query tenantId -o tsv
param tenantId = 'YOUR_TENANT_ID'

// Replace with the object ID of the administrator user or group
// az ad user show --id you@example.com --query id -o tsv
param administratorObjectId = 'YOUR_ADMIN_OBJECT_ID'

// ── Optional overrides ────────────────────────────────────────────────────────

param embeddingDim = 1024

param alertEmailAddress = 'ops@tdo-platform.example.com'

// Dev uses the burstable B1ms tier (default for non-prod)
param postgresSkuName = 'Standard_B1ms'

param postgresSkuTier = 'Burstable'
