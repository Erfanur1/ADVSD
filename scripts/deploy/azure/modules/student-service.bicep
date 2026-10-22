// Reusable module: one student's backend + frontend Container Apps.
// Called once per student from main.bicep.
//
// No Azure Files / volume mount here -- see main.bicep's persistence note.
// Each backend's SQLite DB lives on the container's own ephemeral local
// disk; init_db.py recreates and reseeds it on every container start.

param studentId string
param studentName string
param containerAppsEnvironmentId string
param acrLoginServer string
param imageName string
param backendPort int
param frontendPort int
param aiModeUrl string
param acrUsername string

@secure()
param acrPassword string

resource backend 'Microsoft.App/containerApps@2026-07-01' = {
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
        }
      ]
      scale: {
        minReplicas: 1
        maxReplicas: 1
      }
    }
  }
}

resource frontend 'Microsoft.App/containerApps@2026-07-01' = {
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
