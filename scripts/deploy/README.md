# Deployment scripts -- Release 2, Task 3

Deploys the Prediction Market Intelligence Hub to **Azure Container Apps**.

## What gets deployed (and what doesn't)

Deployed: the shared `home` landing page, all 4 students' backend +
frontend containers, **AI-Mode**, and the **Ollama runtime with the
approved LLM** (11 containers total). Each backend's SQLite database
is persisted via an Azure Files share, and Ollama's downloaded model
is cached on its own share.

NOT deployed (disabled in the cloud, per the Release 2 spec):
`mcp-server`, `rag-server` and `multi-agent-server`. Backends already
fall back gracefully when those URLs are unreachable, so leaving
`MCP_URL` / `RAG_URL` unset keeps them disabled.

## One-time setup

```
az login
az account set --subscription "<your subscription>"
```

## Deploy

From the repo root:

```
chmod +x scripts/deploy/azure/deploy.sh
./scripts/deploy/azure/deploy.sh
```

Optional overrides (env vars): `RESOURCE_GROUP`, `LOCATION`,
`NAME_PREFIX`, `IMAGE_TAG`. Defaults are `group29-r2-rg`,
`australiaeast`, `group29r2`, `latest`.

The script runs in two passes: the first creates the Azure
infrastructure (ACR, storage, Container Apps environment, apps), the
second re-deploys after the images are actually built and pushed, so
the apps pick them up. Seeing a failed/pending revision after the
first pass is expected, not a bug.

## Redeploy after a code change

```
IMAGE_TAG=latest ./scripts/deploy/azure/deploy.sh
```

(or bump `IMAGE_TAG` to a new value to force a fresh revision)

## Tear down

```
chmod +x scripts/deploy/azure/teardown.sh
./scripts/deploy/azure/teardown.sh
```

Deletes the entire resource group. Requires typing the resource
group name to confirm.

## Known limitations (documented, not fixed -- out of scope for Task 3)

- ACR admin credentials are used directly as a Container Apps secret
  for simplicity. A production setup would use a managed identity +
  `AcrPull` role instead of admin credentials.
- No custom domain / TLS certificate configured; apps use the default
  `*.azurecontainerapps.io` HTTPS endpoint, which is sufficient for
  this assessment.