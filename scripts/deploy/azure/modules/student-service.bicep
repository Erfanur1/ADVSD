// Reusable module: one student's backend + frontend Container Apps,
// plus the Azure Files mount that backs their SQLite database.
// Called once per student from main.bicep.

param studentId string
param studentName string
param containerAppsEnvironmentId string
param containerAppsEnvironmentName string
param acrLoginServer string
param imageName string
param backendPort int
param frontendPort int
param storageAccountName string
param aiModeUrl string

@secure()
param storageAccountKey string

param fileShareName string
param acrUsername string

@secure()
param acrPassword string

// Mount this student's Azure Files share into the Container Apps environment
resource envStorage 'Microsoft.App/managedEnvironments/storages@2023-05-01' = {
  name: '${containerAppsEnvironmentName}/${fileShareName}'
  properties: {
    azureFile: {
      accountName: storageAccountName
      accountKey: storageAccountKey
      shareName: fileShareName
      accessMode: 'ReadWrite'
    }
  }
}

resource backend 'Microsoft.App/containerApps@2023-05-01' = {
  name: '${studentName}-backend'
  location: resourceGroup().location
  properties: {
    managedEnvironmentId: containerAppsEnvironmentId
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: false
        targetPort: backendPort
        transport: 'http'
      }
      registries: [
        {
          server: acrLoginServer
          username: acrUsername
          passwordSecretRef: 'acr-password' // pragma: allowlist secret
        }
      ]
      secrets: [
        {
          name: 'acr-password'
          value: acrPassword
        }
      ]
    }
    template: {
      containers: [
        {
          name: '${studentName}-backend'
          image: imageName
          command: [ 'sh', '-c' ]
          args: [ 'python backend/init_db.py && python backend/app.py' ]
          env: [
            {
              name: 'DB_PATH'
              value: '/data/student${studentId}.db'
            }
            {
              name: 'AI_MODE_URL'
              value: aiModeUrl
            }
          ]
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
          volumeMounts: [
            {
              volumeName: 'dbstorage'
              mountPath: '/data'
            }
          ]
        }
      ]
      volumes: [
        {
          name: 'dbstorage'
          storageType: 'AzureFile'
          storageName: fileShareName
        }
      ]
      scale: {
        minReplicas: 1
        maxReplicas: 1
      }
    }
  }
  dependsOn: [
    envStorage
  ]
}

resource frontend 'Microsoft.App/containerApps@2023-05-01' = {
  name: '${studentName}-frontend'
  location: resourceGroup().location
  properties: {
    managedEnvironmentId: containerAppsEnvironmentId
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: frontendPort
        transport: 'http'
      }
      registries: [
        {
          server: acrLoginServer
          username: acrUsername
          passwordSecretRef: 'acr-password' // pragma: allowlist secret
        }
      ]
      secrets: [
        {
          name: 'acr-password'
          value: acrPassword
        }
      ]
    }
    template: {
      containers: [
        {
          name: '${studentName}-frontend'
          image: imageName
          command: [ 'python', 'frontend/app.py' ]
          env: [
            {
              name: 'BACKEND_URL'
              value: 'https://${backend.properties.configuration.ingress.fqdn}'
            }
          ]
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

output frontendUrl string = 'https://${frontend.properties.configuration.ingress.fqdn}'
output backendInternalUrl string = 'https://${backend.properties.configuration.ingress.fqdn}'