// storage.bicep - Blob storage with hot and cold tiers, lifecycle policies

@description('Environment name')
param environment string

@description('Azure region')
param location string = 'northeurope'

@description('Resource name prefix')
param namePrefix string

@description('Subnet ID for private endpoints')
param privateEndpointsSubnetId string

@description('Private DNS zone ID for blob storage')
param dnsZoneBlobId string

@description('Private DNS zone name for blob storage (reserved for future DNS record creation)')
#disable-next-line no-unused-params
param dnsZoneBlobName string

@description('Managed identity principal IDs that need storage access')
param identityPrincipalIds array = []

// Storage Blob Data Contributor role
var storageBlobDataContributorRoleId = 'ba92f5b4-2d11-453d-a403-e96b0029c9fe'

// ── Storage Account ───────────────────────────────────────────────────────────

// Unique suffix to avoid naming conflicts; storage names must be 3–24 alphanumeric chars
var storageBaseName = '${replace(namePrefix, '-', '')}sa${environment}'
// Ensure at least 3 characters by padding with a fixed prefix
var storageAccountNameFull = 'tdo${storageBaseName}'
var storageAccountName = length(storageAccountNameFull) > 24 ? substring(storageAccountNameFull, 0, 24) : storageAccountNameFull

resource storageAccount 'Microsoft.Storage/storageAccounts@2023-01-01' = {
  name: storageAccountName
  location: location
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    accessTier: 'Hot'
    allowBlobPublicAccess: false
    allowSharedKeyAccess: false
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
    networkAcls: {
      bypass: 'AzureServices'
      defaultAction: 'Deny'
      virtualNetworkRules: []
      ipRules: []
    }
    encryption: {
      services: {
        blob: {
          enabled: true
          keyType: 'Account'
        }
        file: {
          enabled: true
          keyType: 'Account'
        }
      }
      keySource: 'Microsoft.Storage'
    }
  }
}

// ── Blob Service ──────────────────────────────────────────────────────────────

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-01-01' = {
  name: 'default'
  parent: storageAccount
  properties: {
    deleteRetentionPolicy: {
      enabled: true
      days: 7
    }
    containerDeleteRetentionPolicy: {
      enabled: true
      days: 7
    }
  }
}

// ── Containers ────────────────────────────────────────────────────────────────

resource containerRaw 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-01-01' = {
  name: 'raw'
  parent: blobService
  properties: {
    publicAccess: 'None'
  }
}

resource containerHarmonised 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-01-01' = {
  name: 'harmonised'
  parent: blobService
  properties: {
    publicAccess: 'None'
  }
}

resource containerEmbeddings 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-01-01' = {
  name: 'embeddings'
  parent: blobService
  properties: {
    publicAccess: 'None'
  }
}

resource containerArchive 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-01-01' = {
  name: 'archive'
  parent: blobService
  properties: {
    publicAccess: 'None'
  }
}

// ── Lifecycle Management Policy ───────────────────────────────────────────────

resource lifecyclePolicy 'Microsoft.Storage/storageAccounts/managementPolicies@2023-01-01' = {
  name: 'default'
  parent: storageAccount
  properties: {
    policy: {
      rules: [
        {
          name: 'MoveRawToCool'
          enabled: true
          type: 'Lifecycle'
          definition: {
            filters: {
              blobTypes: ['blockBlob']
              prefixMatch: ['raw/']
            }
            actions: {
              baseBlob: {
                tierToCool: {
                  daysAfterModificationGreaterThan: 30
                }
                tierToArchive: {
                  daysAfterModificationGreaterThan: 90
                }
                delete: {
                  daysAfterModificationGreaterThan: 365
                }
              }
            }
          }
        }
        {
          name: 'MoveHarmonisedToCool'
          enabled: true
          type: 'Lifecycle'
          definition: {
            filters: {
              blobTypes: ['blockBlob']
              prefixMatch: ['harmonised/']
            }
            actions: {
              baseBlob: {
                tierToCool: {
                  daysAfterModificationGreaterThan: 60
                }
                tierToArchive: {
                  daysAfterModificationGreaterThan: 180
                }
              }
            }
          }
        }
        {
          name: 'ArchiveOldEmbeddings'
          enabled: true
          type: 'Lifecycle'
          definition: {
            filters: {
              blobTypes: ['blockBlob']
              prefixMatch: ['embeddings/']
            }
            actions: {
              baseBlob: {
                tierToCool: {
                  daysAfterModificationGreaterThan: 90
                }
              }
            }
          }
        }
      ]
    }
  }
}

// ── Private Endpoint ──────────────────────────────────────────────────────────

resource privateEndpointBlob 'Microsoft.Network/privateEndpoints@2023-05-01' = {
  name: '${namePrefix}-pe-blob-${environment}'
  location: location
  properties: {
    subnet: {
      id: privateEndpointsSubnetId
    }
    privateLinkServiceConnections: [
      {
        name: '${namePrefix}-plsc-blob-${environment}'
        properties: {
          privateLinkServiceId: storageAccount.id
          groupIds: ['blob']
        }
      }
    ]
  }
}

resource privateEndpointDnsGroup 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2023-05-01' = {
  name: 'blobDnsZoneGroup'
  parent: privateEndpointBlob
  properties: {
    privateDnsZoneConfigs: [
      {
        name: 'blob'
        properties: {
          privateDnsZoneId: dnsZoneBlobId
        }
      }
    ]
  }
}

// ── RBAC: Storage Blob Data Contributor for managed identities ────────────────

resource storageBlobRoleAssignments 'Microsoft.Authorization/roleAssignments@2022-04-01' = [
  for principalId in identityPrincipalIds: {
    name: guid(storageAccount.id, principalId, storageBlobDataContributorRoleId)
    scope: storageAccount
    properties: {
      roleDefinitionId: subscriptionResourceId(
        'Microsoft.Authorization/roleDefinitions',
        storageBlobDataContributorRoleId
      )
      principalId: principalId
      principalType: 'ServicePrincipal'
    }
  }
]

// ── Outputs ───────────────────────────────────────────────────────────────────

output storageAccountId string = storageAccount.id
output storageAccountName string = storageAccount.name
output blobEndpoint string = storageAccount.properties.primaryEndpoints.blob
