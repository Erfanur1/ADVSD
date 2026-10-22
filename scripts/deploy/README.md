# Deployment scripts -- Release 2, Task 3

Deploys the Prediction Market Intelligence Hub to **Azure Container Apps**.

## What gets deployed (and what doesn't)

Deployed by default: the shared `home` landing page and all 4
students' backend + frontend containers (9 containers). Each
backend's SQLite database lives on the container's own **ephemeral**
local disk, not a persistent volume -- `init_db.py` already recreates
and reseeds it on every container start, so this costs nothing
functionally (CRUD against seeded mock data works fine while a
container is running), only a guarantee that nobody asked for (data
surviving a restart/redeploy).

**Why no Azure Files**: this subscription's Container Apps environment
is an "Express" environment (Azure's current default without VNet
integration), and Express environments categorically do not support
Storage-backed volumes -- confirmed directly, both via a fresh
reference environment created through `az containerapp env create
--enable-workload-profiles true` and via `az containerapp env storage
set` against the real environment, same
`ExpressEnvironmentResourceNotSupported` error either way, regardless
of the environment's declared `workloadProfiles` or an individual
Container App's `workloadProfileName`. Getting a Storage-capable
environment needs full VNet integration (a virtual network + subnet
wired into `vnetConfiguration`) -- a substantially bigger
infrastructure addition, out of scope here since persistence isn't
actually required by the brief.

**Disabled by default, per the Release 2 "Cloud Baseline" rule**:
`mcp-server`, `rag-server`, `multi-agent-server` -- never deployed at
all, full stop -- and **AI-Mode + Ollama**, which are deployed only
when explicitly opted into (see below). Backends already fall back
gracefully when `AI_MODE_URL` / `MCP_URL` / `RAG_URL` are unset or
unreachable, so the default run is fully spec-compliant.

### Opting in to Bonus B1 (Cloud AI-Mode)

Pass `enableCloudAi=true` to deploy the Ollama + AI-Mode Container
Apps and wire every backend's `AI_MODE_URL` to the real thing:

```
az deployment group create \
  --resource-group "$RESOURCE_GROUP" --name main \
  --template-file scripts/deploy/azure/main.bicep \
  --parameters namePrefix="$NAME_PREFIX" imageTag="$IMAGE_TAG" enableCloudAi=true
```

Do this as a deliberate, separate step when you're ready to record
the Bonus B1 evidence -- never as the default path, or it costs the
required Criterion 7 marks (AI-Mode must be disabled by default).
Ollama is the expensive part (2 vCPU / 4Gi always-on), so turn it back
off (redeploy with `enableCloudAi=false`, the default) once you've
captured the demo evidence. Note Ollama has no persistent model cache
(see the persistence note above) -- it re-pulls the model on every
cold start, a couple of minutes of startup time before AI-Mode is
actually reachable.

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
  --subject "repo:Erfanur1@169593210/ADVSD@1343409389:ref:refs/heads/main" \
  --audiences api://AzureADTokenExchange
```

**Note on the `--subject` format**: GitHub's OIDC tokens now include
immutable owner/repo IDs in the subject claim
(`repo:<owner>@<owner_id>/<repo>@<repo_id>:ref:<ref>`), not the plain
`repo:<owner>/<repo>:ref:<ref>` most docs/examples (including Azure's
own) still show. Using the plain form fails Azure-side with
`AADSTS700213: No matching federated identity record found`. If you
ever need the exact current value for this repo, trigger the workflow
once with a deliberately wrong `--subject` and read the real one back
out of the `azure/login` step's failure log (`subject claim - ...`), or
check Settings -> Actions -> General -> "Customize the JWT claims" for
this repo once GitHub's subject-claim customization UI is out of beta.

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