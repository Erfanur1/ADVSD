#!/usr/bin/env bash
set -euo pipefail

RESOURCE_GROUP="${RESOURCE_GROUP:-group29-r2-rg}"
LOCATION="${LOCATION:-australiaeast}"
NAME_PREFIX="${NAME_PREFIX:-group29r2}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
# Off by default, per the Release 2 Cloud Baseline rule (see main.bicep's
# header comment and scripts/deploy/README.md) -- set to "true" only to
# deliberately claim Bonus B1.
ENABLE_CLOUD_AI="${ENABLE_CLOUD_AI:-false}"

echo "== 1. Resource group =="
az group create --name "$RESOURCE_GROUP" --location "$LOCATION" --output table

echo "== 2. Core infrastructure (ACR, storage, Container Apps environment, apps) =="
# This first pass is EXPECTED to report failure: the Container Apps it
# creates reference images that don't exist in ACR yet (chicken-and-egg --
# need the registry to build into, need the apps to reference an image
# once it exists), and Azure surfaces that as a deployment-level error
# (exit code 1), not just an unhealthy revision. Tolerate it here and let
# the second pass (after the real images are pushed) be the authoritative
# check -- a genuine infra problem (bad bicep, permissions, quota) fails
# there too, for real, uncaught.
az deployment group create \
  --resource-group "$RESOURCE_GROUP" \
  --name main \
  --template-file "$(dirname "$0")/main.bicep" \
  --parameters namePrefix="$NAME_PREFIX" imageTag="$IMAGE_TAG" enableCloudAi="$ENABLE_CLOUD_AI" \
  --output table || echo "(expected: first pass fails until images exist in ACR -- continuing)"

# Computed directly rather than read from the first pass's deployment
# outputs: a *Failed* deployment (expected here -- see above) doesn't
# populate `properties.outputs` via `az deployment group show`, so that
# query silently returns empty, which then fails ACR's own name
# validation ("Registry names may contain only alpha numeric characters
# and must be between 5 and 50 characters") -- reproduced live. This
# must exactly match main.bicep's `var acrName = '${namePrefix}acr'` and
# ACR's standard `<name>.azurecr.io` login server format.
ACR_NAME="${NAME_PREFIX}acr"
ACR_LOGIN_SERVER="${ACR_NAME}.azurecr.io"

echo "== 3. Build and push images to ACR: $ACR_NAME =="
# Plain 'docker build' + 'docker push' here, NOT 'az acr build': ACR
# Tasks (what 'az acr build' uses under the hood -- it uploads the
# context and builds remotely in Azure) are disabled on this
# Azure-for-Students subscription ("TasksOperationsNotAllowed" --
# reproduced live, same category of student/free-tier platform
# restriction as the blocked app-registration permission documented
# above). Building locally and pushing over the registry's normal
# Docker API doesn't need ACR Tasks at all, just registry auth.
az acr login --name "$ACR_NAME"
build_and_push() {
  local image="$1" context="$2"
  docker build -t "$ACR_LOGIN_SERVER/$image:$IMAGE_TAG" "$context"
  docker push "$ACR_LOGIN_SERVER/$image:$IMAGE_TAG"
}
build_and_push home ./shared
if [ "$ENABLE_CLOUD_AI" = "true" ]; then
  build_and_push aimode ./ai-services/ai-mode
fi
build_and_push student1 ./student-1
build_and_push student2 ./student-2
build_and_push student3 ./student-3
build_and_push student4 ./student-4

echo "== 4. Re-deploy so Container Apps pick up the freshly built images =="
# The first deploy above creates Container Apps pointing at images that
# don't exist in ACR yet (chicken-and-egg: need the environment to build
# into, need the apps to reference the image once it exists). This second
# pass makes the apps pull the real image and go healthy. This is expected
# -- not a bug -- the first pass's apps will briefly show a failed/pending
# revision until this step runs.
az deployment group create \
  --resource-group "$RESOURCE_GROUP" \
  --name main \
  --template-file "$(dirname "$0")/main.bicep" \
  --parameters namePrefix="$NAME_PREFIX" imageTag="$IMAGE_TAG" enableCloudAi="$ENABLE_CLOUD_AI" \
  --output table

echo "== Deployment complete. URLs: =="
az deployment group show --resource-group "$RESOURCE_GROUP" --name main --query "properties.outputs" -o json