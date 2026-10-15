// Core Azure infrastructure for Release 2 cloud deployment.
// Deploys: Container Registry, Log Analytics, Container Apps Environment,
// the shared "home" landing page, and (via the student-service module)
// each student's backend + frontend containers.
//
// AI-Mode / MCP / RAG / Multi-Agent Server are deliberately NOT deployed
// here -- they stay local/non-containerised per the Release 2 spec. Each
// backend already falls back gracefully when those URLs are unreachable
// (same behaviour already verified in CI -- see .github/workflows/*.yml).

param location string = resourceGroup().location
param namePrefix string = 'group29r2'
param imageTag string = 'latest'
param llmModel string = 'llama3.2:3b'

var acrName = '${namePrefix}acr'
var logAnalyticsName = '${namePrefix}-logs'
var envName = '${namePrefix}-env'
var storageAccountName = toLower('${namePrefix}st${uniqueString(resourceGroup().id)}')

resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2022-10-01' = {
  name: logAnalyticsName
  location: location
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: 30
  }
}

resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: acrName
  location: location
  sku: { name: 'Basic' }
  properties: {
    adminUserEnabled: true
  }
}

resource storageAccount 'Microsoft.Storage/storageAccounts@2023-01-01' = {
  name: storageAccountName
  location: location
  sku: { name: 'Standard_LRS' }
  kind: 'StorageV2'
  properties: {
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
  }
}

resource fileServices 'Microsoft.Storage/storageAccounts/fileServices@2023-01-01' = {
  parent: storageAccount
  name: 'default'
}

resource s1Share 'Microsoft.Storage/storageAccounts/fileServices/shares@2023-01-01' = {
  parent: fileServices
  name: 's1data'
}
resource s2Share 'Microsoft.Storage/storageAccounts/fileServices/shares@2023-01-01' = {
  parent: fileServices
  name: 's2data'
}
resource s3Share 'Microsoft.Storage/storageAccounts/fileServices/shares@2023-01-01' = {
  parent: fileServices
  name: 's3data'
}
resource s4Share 'Microsoft.Storage/storageAccounts/fileServices/shares@2023-01-01' = {
  parent: fileServices
  name: 's4data'
}

resource containerAppsEnv 'Microsoft.App/managedEnvironments@2023-05-01' = {
  name: envName
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalytics.properties.customerId
        sharedKey: logAnalytics.listKeys().primarySharedKey
      }
    }
  }
}

resource home 'Microsoft.App/containerApps@2023-05-01' = {
  name: '${namePrefix}-home'
  location: location
  properties: {
    managedEnvironmentId: containerAppsEnv.id
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: 8080
        transport: 'http'
      }
      registries: [
        {
          server: acr.properties.loginServer
          username: acr.listCredentials().username
          passwordSecretRef: 'acr-password' // pragma: allowlist secret
        }
      ]
      secrets: [
        {
          name: 'acr-password'
          value: acr.listCredentials().passwords[0].value
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'home'
          image: '${acr.properties.loginServer}/home:${imageTag}'
          resources: {
            cpu: json('0.25')
            memory: '0.5Gi'
          }
        }
      ]
      scale: {
        minReplicas: 1
        maxReplicas: 1
      }
    }
  }
}

// Mount the Ollama model cache share into the environment
resource ollamaStorage 'Microsoft.App/managedEnvironments/storages@2023-05-01' = {
  parent: containerAppsEnv
  name: 'ollamadata'
  properties: {
    azureFile: {
      accountName: storageAccount.name
      accountKey: storageAccount.listKeys().keys[0].value
      shareName: 'ollamadata'
      accessMode: 'ReadWrite'
    }
  }
  dependsOn: [
    ollamaShare
  ]
}

// Ollama runtime: internal only. Pulls the approved LLM on startup and
// caches it on the Azure Files share so restarts do not re-download it.
resource ollama 'Microsoft.App/containerApps@2023-05-01' = {
  name: '${namePrefix}-ollama'
  location: location
  properties: {
    managedEnvironmentId: containerAppsEnv.id
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: false
        targetPort: 11434
        transport: 'http'
      }
    }
    template: {
      containers: [
        {
          name: 'ollama'
          image: 'docker.io/ollama/ollama:latest'
          command: [ 'sh', '-c' ]
          args: [ 'ollama serve & sleep 5 && ollama pull ${llmModel} && wait' ]
          resources: {
            cpu: json('2')
            memory: '4Gi'
          }
          volumeMounts: [
            {
              volumeName: 'ollamamodels'
              mountPath: '/root/.ollama'
            }
          ]
        }
      ]
      volumes: [
        {
          name: 'ollamamodels'
          storageType: 'AzureFile'
          storageName: 'ollamadata'
        }
      ]
      scale: {
        minReplicas: 1
        maxReplicas: 1
      }
    }
  }
  dependsOn: [
    ollamaStorage
  ]
}

// AI-Mode: internal only, talks to Ollama
resource aiMode 'Microsoft.App/containerApps@2023-05-01' = {
  name: '${namePrefix}-ai-mode'
  location: location
  properties: {
    managedEnvironmentId: containerAppsEnv.id
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: false
        targetPort: 8000
        transport: 'http'
      }
      registries: [
        {
          server: acr.properties.loginServer
          username: acr.listCredentials().username
          passwordSecretRef: 'acr-password' // pragma: allowlist secret
        }
      ]
      secrets: [
        {
          name: 'acr-password'
          value: acr.listCredentials().passwords[0].value
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'ai-mode'
          image: '${acr.properties.loginServer}/aimode:${imageTag}'
          env: [
            {
              name: 'OLLAMA_HOST'
              value: 'https://${ollama.properties.configuration.ingress.fqdn}'
            }
            {
              name: 'LLM_MODEL'
              value: llmModel
            }
          ]
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
        }
      ]
      scale: {
        minReplicas: 1
        maxReplicas: 1
      }
    }
  }
}

module student1 'modules/student-service.bicep' = {
  name: 'student1Deploy'
  params: {
    studentId: '1'
    studentName: 'student-1'
    containerAppsEnvironmentId: containerAppsEnv.id
    containerAppsEnvironmentName: containerAppsEnv.name
    acrLoginServer: acr.properties.loginServer
    imageName: '${acr.properties.loginServer}/student1:${imageTag}'
    backendPort: 5001
    frontendPort: 5101
    storageAccountName: storageAccount.name
    storageAccountKey: storageAccount.listKeys().keys[0].value
    fileShareName: 's1data'
    aiModeUrl: 'https://${aiMode.properties.configuration.ingress.fqdn}'
    acrUsername: acr.listCredentials().username
    acrPassword: acr.listCredentials().passwords[0].value
  }
  dependsOn: [
    s1Share
  ]
}

module student2 'modules/student-service.bicep' = {
  name: 'student2Deploy'
  params: {
    studentId: '2'
    studentName: 'student-2'
    containerAppsEnvironmentId: containerAppsEnv.id
    containerAppsEnvironmentName: containerAppsEnv.name
    acrLoginServer: acr.properties.loginServer
    imageName: '${acr.properties.loginServer}/student2:${imageTag}'
    backendPort: 5002
    frontendPort: 5102
    storageAccountName: storageAccount.name
    storageAccountKey: storageAccount.listKeys().keys[0].value
    fileShareName: 's2data'
    aiModeUrl: 'https://${aiMode.properties.configuration.ingress.fqdn}'
    acrUsername: acr.listCredentials().username
    acrPassword: acr.listCredentials().passwords[0].value
  }
  dependsOn: [
    s2Share
  ]
}

module student3 'modules/student-service.bicep' = {
  name: 'student3Deploy'
  params: {
    studentId: '3'
    studentName: 'student-3'
    containerAppsEnvironmentId: containerAppsEnv.id
    containerAppsEnvironmentName: containerAppsEnv.name
    acrLoginServer: acr.properties.loginServer
    imageName: '${acr.properties.loginServer}/student3:${imageTag}'
    backendPort: 5003
    frontendPort: 5103
    storageAccountName: storageAccount.name
    storageAccountKey: storageAccount.listKeys().keys[0].value
    fileShareName: 's3data'
    aiModeUrl: 'https://${aiMode.properties.configuration.ingress.fqdn}'
    acrUsername: acr.listCredentials().username
    acrPassword: acr.listCredentials().passwords[0].value
  }
  dependsOn: [
    s3Share
  ]
}

module student4 'modules/student-service.bicep' = {
  name: 'student4Deploy'
  params: {
    studentId: '4'
    studentName: 'student-4'
    containerAppsEnvironmentId: containerAppsEnv.id
    containerAppsEnvironmentName: containerAppsEnv.name
    acrLoginServer: acr.properties.loginServer
    imageName: '${acr.properties.loginServer}/student4:${imageTag}'
    backendPort: 5004
    frontendPort: 5104
    storageAccountName: storageAccount.name
    storageAccountKey: storageAccount.listKeys().keys[0].value
    fileShareName: 's4data'
    aiModeUrl: 'https://${aiMode.properties.configuration.ingress.fqdn}'
    acrUsername: acr.listCredentials().username
    acrPassword: acr.listCredentials().passwords[0].value
  }
  dependsOn: [
    s4Share
  ]
}

output acrLoginServer string = acr.properties.loginServer
output homeUrl string = 'https://${home.properties.configuration.ingress.fqdn}'
output student1Url string = student1.outputs.frontendUrl
output student2Url string = student2.outputs.frontendUrl
output student3Url string = student3.outputs.frontendUrl
output student4Url string = student4.outputs.frontendUrl