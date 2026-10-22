// Core Azure infrastructure for Release 2 cloud deployment.
// Deploys: Container Registry, Log Analytics, Container Apps Environment,
// the shared "home" landing page, and (via the student-service module)
// each student's backend + frontend containers.
//
// MCP / RAG / Multi-Agent Server are never deployed here -- they stay
// local/non-containerised per the Release 2 spec, full stop.
//
// AI-Mode + Ollama are DISABLED BY DEFAULT (enableCloudAi = false), per the
// Release 2 "Cloud Baseline" rule: AI-Mode must be disabled by default in
// the required cloud deployment. Each backend already falls back
// gracefully when AI_MODE_URL is unset/unreachable (same behaviour already
// verified in CI -- see .github/workflows/*.yml). Set enableCloudAi=true
// (az deployment group create ... --parameters enableCloudAi=true) only to
// deliberately claim Bonus B1 (Cloud AI-Mode) -- never as the default path.
//
// NOTE on persistence: there is deliberately no Azure Files / persistent
// volume anywhere in this template. This subscription's Container Apps
// environment is an "Express" environment (the current Azure default
// without VNet integration), and Express environments categorically do not
// support Storage-backed volumes -- confirmed directly against this
// subscription, both via a plain `az containerapp env create
// --enable-workload-profiles true` reference environment and via
// `az containerapp env storage set` against this exact environment, same
// ExpressEnvironmentResourceNotSupported error either way. Getting a
// Storage-capable environment requires full VNet integration (a
// virtual network + subnet wired into the environment's vnetConfiguration),
// a substantially bigger infra addition. Since all data in this project is
// seeded mock data and the brief only requires operational CRUD (not
// persistence across restarts), each backend's SQLite DB simply lives on
// the container's own ephemeral local disk -- init_db.py already
// recreates and reseeds it on every container start, so this costs
// nothing functionally, only survives-a-restart guarantees nobody asked
// for in the cloud deployment.

param location string = resourceGroup().location
param namePrefix string = 'group29r2'
param imageTag string = 'latest'
param llmModel string = 'llama3.2:3b'
param enableCloudAi bool = false

var acrName = '${namePrefix}acr'
var logAnalyticsName = '${namePrefix}-logs'
var envName = '${namePrefix}-env'

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

resource containerAppsEnv 'Microsoft.App/managedEnvironments@2026-07-01' = {
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

resource home 'Microsoft.App/containerApps@2026-07-01' = {
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

// Ollama runtime: internal only. Deployed only when enableCloudAi=true (see
// header comment). Re-pulls the LLM on every cold start (no persistent
// model cache -- see the persistence note above), which costs a couple of
// minutes of startup time but nothing else.
resource ollama 'Microsoft.App/containerApps@2026-07-01' = if (enableCloudAi) {
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
        }
      ]
      scale: {
        minReplicas: 1
        maxReplicas: 1
      }
    }
  }
}

// AI-Mode: internal only, talks to Ollama. Deployed only when
// enableCloudAi=true (see header comment).
resource aiMode 'Microsoft.App/containerApps@2026-07-01' = if (enableCloudAi) {
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
              value: 'https://${ollama.?properties.?configuration.?ingress.?fqdn}'
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

// Empty string when disabled (the default) -- each backend's own fallback
// logic treats a missing/unreachable AI_MODE_URL as "AI-Mode off" already.
var aiModeUrl = enableCloudAi ? 'https://${aiMode.?properties.?configuration.?ingress.?fqdn}' : ''

module student1 'modules/student-service.bicep' = {
  name: 'student1Deploy'
  params: {
    studentId: '1'
    studentName: 'student-1'
    containerAppsEnvironmentId: containerAppsEnv.id
    acrLoginServer: acr.properties.loginServer
    imageName: '${acr.properties.loginServer}/student1:${imageTag}'
    backendPort: 5001
    frontendPort: 5101
    aiModeUrl: aiModeUrl
    acrUsername: acr.listCredentials().username
    acrPassword: acr.listCredentials().passwords[0].value
  }
}

module student2 'modules/student-service.bicep' = {
  name: 'student2Deploy'
  params: {
    studentId: '2'
    studentName: 'student-2'
    containerAppsEnvironmentId: containerAppsEnv.id
    acrLoginServer: acr.properties.loginServer
    imageName: '${acr.properties.loginServer}/student2:${imageTag}'
    backendPort: 5002
    frontendPort: 5102
    aiModeUrl: aiModeUrl
    acrUsername: acr.listCredentials().username
    acrPassword: acr.listCredentials().passwords[0].value
  }
}

module student3 'modules/student-service.bicep' = {
  name: 'student3Deploy'
  params: {
    studentId: '3'
    studentName: 'student-3'
    containerAppsEnvironmentId: containerAppsEnv.id
    acrLoginServer: acr.properties.loginServer
    imageName: '${acr.properties.loginServer}/student3:${imageTag}'
    backendPort: 5003
    frontendPort: 5103
    aiModeUrl: aiModeUrl
    acrUsername: acr.listCredentials().username
    acrPassword: acr.listCredentials().passwords[0].value
  }
}

module student4 'modules/student-service.bicep' = {
  name: 'student4Deploy'
  params: {
    studentId: '4'
    studentName: 'student-4'
    containerAppsEnvironmentId: containerAppsEnv.id
    acrLoginServer: acr.properties.loginServer
    imageName: '${acr.properties.loginServer}/student4:${imageTag}'
    backendPort: 5004
    frontendPort: 5104
    aiModeUrl: aiModeUrl
    acrUsername: acr.listCredentials().username
    acrPassword: acr.listCredentials().passwords[0].value
  }
}

output acrLoginServer string = acr.properties.loginServer
output homeUrl string = 'https://${home.properties.configuration.ingress.fqdn}'
output student1Url string = student1.outputs.frontendUrl
output student2Url string = student2.outputs.frontendUrl
output student3Url string = student3.outputs.frontendUrl
output student4Url string = student4.outputs.frontendUrl
