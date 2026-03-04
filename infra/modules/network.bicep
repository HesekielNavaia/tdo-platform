// network.bicep - VNet, subnets, NSGs, NAT gateway, private DNS zones

@description('Environment name (dev, staging, prod)')
param environment string

@description('Azure region')
param location string = 'northeurope'

@description('Resource name prefix')
param namePrefix string

// ── Address spaces ──────────────────────────────────────────────────────────
var vnetAddressPrefix = '10.0.0.0/16'

var subnets = {
  containerApps: {
    prefix: '10.0.0.0/23'
    delegation: 'Microsoft.App/environments'
  }
  postgres: {
    prefix: '10.0.2.0/24'
    delegation: 'Microsoft.DBforPostgreSQL/flexibleServers'
  }
  functions: {
    prefix: '10.0.3.0/24'
    delegation: 'Microsoft.Web/serverFarms'
  }
  privateEndpoints: {
    prefix: '10.0.4.0/24'
    delegation: ''
  }
}

// ── NSGs ─────────────────────────────────────────────────────────────────────

resource nsgContainerApps 'Microsoft.Network/networkSecurityGroups@2023-05-01' = {
  name: '${namePrefix}-nsg-containerapps-${environment}'
  location: location
  properties: {
    securityRules: [
      {
        name: 'AllowHttpsInbound'
        properties: {
          priority: 100
          direction: 'Inbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourceAddressPrefix: '*'
          sourcePortRange: '*'
          destinationAddressPrefix: '*'
          destinationPortRange: '443'
        }
      }
      {
        name: 'AllowHttpInbound'
        properties: {
          priority: 110
          direction: 'Inbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourceAddressPrefix: '*'
          sourcePortRange: '*'
          destinationAddressPrefix: '*'
          destinationPortRange: '80'
        }
      }
    ]
  }
}

resource nsgPostgres 'Microsoft.Network/networkSecurityGroups@2023-05-01' = {
  name: '${namePrefix}-nsg-postgres-${environment}'
  location: location
  properties: {
    securityRules: [
      {
        name: 'AllowPostgresFromVNet'
        properties: {
          priority: 100
          direction: 'Inbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourceAddressPrefix: vnetAddressPrefix
          sourcePortRange: '*'
          destinationAddressPrefix: '*'
          destinationPortRange: '5432'
        }
      }
      {
        name: 'DenyAllInbound'
        properties: {
          priority: 4096
          direction: 'Inbound'
          access: 'Deny'
          protocol: '*'
          sourceAddressPrefix: '*'
          sourcePortRange: '*'
          destinationAddressPrefix: '*'
          destinationPortRange: '*'
        }
      }
    ]
  }
}

resource nsgFunctions 'Microsoft.Network/networkSecurityGroups@2023-05-01' = {
  name: '${namePrefix}-nsg-functions-${environment}'
  location: location
  properties: {
    securityRules: [
      {
        name: 'AllowHttpsInbound'
        properties: {
          priority: 100
          direction: 'Inbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourceAddressPrefix: vnetAddressPrefix
          sourcePortRange: '*'
          destinationAddressPrefix: '*'
          destinationPortRange: '443'
        }
      }
    ]
  }
}

resource nsgPrivateEndpoints 'Microsoft.Network/networkSecurityGroups@2023-05-01' = {
  name: '${namePrefix}-nsg-pe-${environment}'
  location: location
  properties: {
    securityRules: []
  }
}

// ── Public IP for NAT Gateway ─────────────────────────────────────────────────

resource natPublicIp 'Microsoft.Network/publicIPAddresses@2023-05-01' = {
  name: '${namePrefix}-nat-pip-${environment}'
  location: location
  sku: {
    name: 'Standard'
  }
  properties: {
    publicIPAllocationMethod: 'Static'
  }
}

// ── NAT Gateway ───────────────────────────────────────────────────────────────

resource natGateway 'Microsoft.Network/natGateways@2023-05-01' = {
  name: '${namePrefix}-nat-${environment}'
  location: location
  sku: {
    name: 'Standard'
  }
  properties: {
    idleTimeoutInMinutes: 4
    publicIpAddresses: [
      {
        id: natPublicIp.id
      }
    ]
  }
}

// ── Virtual Network ───────────────────────────────────────────────────────────

resource vnet 'Microsoft.Network/virtualNetworks@2023-05-01' = {
  name: '${namePrefix}-vnet-${environment}'
  location: location
  properties: {
    addressSpace: {
      addressPrefixes: [
        vnetAddressPrefix
      ]
    }
    subnets: [
      {
        name: 'containerApps'
        properties: {
          addressPrefix: subnets.containerApps.prefix
          networkSecurityGroup: {
            id: nsgContainerApps.id
          }
          natGateway: {
            id: natGateway.id
          }
          delegations: [
            {
              name: 'containerAppsDelegation'
              properties: {
                serviceName: subnets.containerApps.delegation
              }
            }
          ]
        }
      }
      {
        name: 'postgres'
        properties: {
          addressPrefix: subnets.postgres.prefix
          networkSecurityGroup: {
            id: nsgPostgres.id
          }
          delegations: [
            {
              name: 'postgresDelegation'
              properties: {
                serviceName: subnets.postgres.delegation
              }
            }
          ]
        }
      }
      {
        name: 'functions'
        properties: {
          addressPrefix: subnets.functions.prefix
          networkSecurityGroup: {
            id: nsgFunctions.id
          }
          delegations: [
            {
              name: 'functionsDelegation'
              properties: {
                serviceName: subnets.functions.delegation
              }
            }
          ]
          natGateway: {
            id: natGateway.id
          }
        }
      }
      {
        name: 'privateEndpoints'
        properties: {
          addressPrefix: subnets.privateEndpoints.prefix
          networkSecurityGroup: {
            id: nsgPrivateEndpoints.id
          }
          privateEndpointNetworkPolicies: 'Disabled'
        }
      }
    ]
  }
}

// ── Private DNS Zones ─────────────────────────────────────────────────────────

resource dnsZoneBlob 'Microsoft.Network/privateDnsZones@2020-06-01' = {
  name: 'privatelink.blob.${az.environment().suffixes.storage}'
  location: 'global'
}

resource dnsZonePostgres 'Microsoft.Network/privateDnsZones@2020-06-01' = {
  name: 'privatelink.postgres.database.azure.com'
  location: 'global'
}

resource dnsZoneKeyVault 'Microsoft.Network/privateDnsZones@2020-06-01' = {
  name: 'privatelink.vaultcore.azure.net'
  location: 'global'
}

resource dnsZoneAcr 'Microsoft.Network/privateDnsZones@2020-06-01' = {
  name: 'privatelink.azurecr.io'
  location: 'global'
}

// ── DNS Zone VNet Links ───────────────────────────────────────────────────────

resource dnsLinkBlob 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2020-06-01' = {
  name: 'blob-link'
  parent: dnsZoneBlob
  location: 'global'
  properties: {
    virtualNetwork: {
      id: vnet.id
    }
    registrationEnabled: false
  }
}

resource dnsLinkPostgres 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2020-06-01' = {
  name: 'postgres-link'
  parent: dnsZonePostgres
  location: 'global'
  properties: {
    virtualNetwork: {
      id: vnet.id
    }
    registrationEnabled: false
  }
}

resource dnsLinkKeyVault 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2020-06-01' = {
  name: 'keyvault-link'
  parent: dnsZoneKeyVault
  location: 'global'
  properties: {
    virtualNetwork: {
      id: vnet.id
    }
    registrationEnabled: false
  }
}

resource dnsLinkAcr 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2020-06-01' = {
  name: 'acr-link'
  parent: dnsZoneAcr
  location: 'global'
  properties: {
    virtualNetwork: {
      id: vnet.id
    }
    registrationEnabled: false
  }
}

// ── Outputs ───────────────────────────────────────────────────────────────────

output vnetId string = vnet.id
output vnetName string = vnet.name
output containerAppsSubnetId string = vnet.properties.subnets[0].id
output postgresSubnetId string = vnet.properties.subnets[1].id
output functionsSubnetId string = vnet.properties.subnets[2].id
output privateEndpointsSubnetId string = vnet.properties.subnets[3].id
output dnsZoneBlobId string = dnsZoneBlob.id
output dnsZonePostgresId string = dnsZonePostgres.id
output dnsZoneKeyVaultId string = dnsZoneKeyVault.id
output dnsZoneAcrId string = dnsZoneAcr.id
output dnsZoneBlobName string = dnsZoneBlob.name
output dnsZonePostgresName string = dnsZonePostgres.name
output dnsZoneKeyVaultName string = dnsZoneKeyVault.name
output dnsZoneAcrName string = dnsZoneAcr.name
