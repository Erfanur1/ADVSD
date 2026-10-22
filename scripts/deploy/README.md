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

### Running `deploy.sh` by hand (local terminal)

```
az login
az account set --subscription "<your subscription>"
```

### Running via `cloud-deployment.yml` (GitHub Actions)

Authenticates with **GitHub OIDC federation to a user-assigned managed
identity**, not a classic service-principal secret. This matters because
`az ad sp create-for-rbac` (the usual approach, and what the brief's
own example commands suggest) needs Entra ID "register applications"
permission -- **UTS's student Azure tenant blocks that for students**,
Azure-for-Students Owner-on-the-subscription or not. A managed identity
only needs ordinary subscription-level RBAC, which doesn't hit that
restriction.

One-time setup (done once against the target subscription/resource
group -- already done for `group29-r2-rg`, keeping this here so it's
reproducible if the group is ever recreated):

```bash
SUBSCRIPTION_ID="<subscription id>"
RESOURCE_GROUP="group29-r2-rg"

az group create --name "$RESOURCE_GROUP" --location australiaeast

az identity create --name group29-r2-github-identity --resource-group "$RESOURCE_GROUP"
# note the clientId + principalId from the output

az role assignment create \
  --assignee-object-id "<principalId from above>" \
  --assignee-principal-type ServicePrincipal \
  --role Contributor \
  --scope "/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP"

az identity federated-credential create \
  --name github-actions-main \
  --identity-name group29-r2-github-identity \
  --resource-group "$RESOURCE_GROUP" \
  --issuer https://token.actions.githubusercontent.com \
  --subject repo:Erfanur1/ADVSD:ref:refs/heads/main \
  --audiences api://AzureADTokenExchange
```

Then add three GitHub Actions secrets (Settings -> Secrets and
variables -> Actions): `AZURE_CLIENT_ID` (the identity's `clientId`),
`AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`. No secret value to rotate --
there's no long-lived credential, GitHub's OIDC token is exchanged for a
short-lived Azure one at run time.

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