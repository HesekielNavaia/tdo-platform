// database.bicep - PostgreSQL Flexible Server with pgvector extension

@description('Environment name')
param environment string

@description('Azure region')
param location string = 'northeurope'

@description('Resource name prefix')
param namePrefix string

@description('Subnet ID for PostgreSQL delegation')
param postgresSubnetId string

@description('Private DNS zone ID for PostgreSQL')
param dnsZonePostgresId string

@description('Private DNS zone name for PostgreSQL (reserved for future DNS record creation)')
#disable-next-line no-unused-params
param dnsZonePostgresName string

@description('Tenant ID for AAD admin')
param tenantId string

@description('Object ID of the administrator (AAD group or user)')
param administratorObjectId string

@description('Embedding dimension (used to set max vector dims)')
param embeddingDim int = 1024

@description('SKU name for PostgreSQL (dev: Standard_B1ms, prod: Standard_D4s_v3)')
param skuName string = 'Standard_B1ms'

@description('SKU tier')
@allowed(['Burstable', 'GeneralPurpose', 'MemoryOptimized'])
param skuTier string = 'Burstable'

@description('Storage size in GB')
param storageSizeGB int = 32

@description('PostgreSQL version')
param postgresVersion string = '16'

// ── PostgreSQL Flexible Server ────────────────────────────────────────────────

resource postgresServer 'Microsoft.DBforPostgreSQL/flexibleServers@2023-06-01-preview' = {
  name: '${namePrefix}-pg-${environment}'
  location: location
  sku: {
    name: skuName
    tier: skuTier
  }
  properties: {
    version: postgresVersion
    administratorLogin: null
    authConfig: {
      activeDirectoryAuth: 'Enabled'
      passwordAuth: 'Disabled'
      tenantId: tenantId
    }
    storage: {
      storageSizeGB: storageSizeGB
    }
    backup: {
      backupRetentionDays: 7
      geoRedundantBackup: environment == 'prod' ? 'Enabled' : 'Disabled'
    }
    highAvailability: {
      mode: environment == 'prod' ? 'ZoneRedundant' : 'Disabled'
    }
    network: {
      delegatedSubnetResourceId: postgresSubnetId
      privateDnsZoneArmResourceId: dnsZonePostgresId
    }
    maintenanceWindow: {
      customWindow: 'Enabled'
      dayOfWeek: 0
      startHour: 2
      startMinute: 0
    }
  }
}

// ── AAD Administrator ─────────────────────────────────────────────────────────

resource postgresAadAdmin 'Microsoft.DBforPostgreSQL/flexibleServers/administrators@2023-06-01-preview' = {
  name: administratorObjectId
  parent: postgresServer
  properties: {
    principalType: 'Group'
    principalName: 'tdo-pg-admins-${environment}'
    tenantId: tenantId
  }
}

// ── Server Configurations ─────────────────────────────────────────────────────
// Note: pgvector is enabled via CREATE EXTENSION vector; after deployment.
// Do NOT add 'vector' to shared_preload_libraries — it is not a preload library.

resource configMaxConnections 'Microsoft.DBforPostgreSQL/flexibleServers/configurations@2023-06-01-preview' = {
  name: 'max_connections'
  parent: postgresServer
  properties: {
    value: environment == 'prod' ? '200' : '50'
    source: 'user-override'
  }
}

resource configWorkMem 'Microsoft.DBforPostgreSQL/flexibleServers/configurations@2023-06-01-preview' = {
  name: 'work_mem'
  parent: postgresServer
  dependsOn: [configMaxConnections]
  properties: {
    value: '16384'
    source: 'user-override'
  }
}

// ── Database ──────────────────────────────────────────────────────────────────

resource tdoDatabase 'Microsoft.DBforPostgreSQL/flexibleServers/databases@2023-06-01-preview' = {
  name: 'tdo'
  parent: postgresServer
  properties: {
    charset: 'UTF8'
    collation: 'en_US.utf8'
  }
}

// ── Firewall: Allow Azure services (for initial setup only) ───────────────────

resource firewallAllowAzure 'Microsoft.DBforPostgreSQL/flexibleServers/firewallRules@2023-06-01-preview' = {
  name: 'AllowAllAzureServicesAndResourcesWithinAzureIps'
  parent: postgresServer
  properties: {
    startIpAddress: '0.0.0.0'
    endIpAddress: '0.0.0.0'
  }
}

// ── Outputs ───────────────────────────────────────────────────────────────────

output postgresServerId string = postgresServer.id
output postgresServerName string = postgresServer.name
output postgresFqdn string = postgresServer.properties.fullyQualifiedDomainName
output tdoDatabaseName string = tdoDatabase.name
output embeddingDim int = embeddingDim
