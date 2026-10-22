#!/usr/bin/env bash
set -euo pipefail

RESOURCE_GROUP="${RESOURCE_GROUP:-group29-r2-rg}"
LOCATION="${LOCATION:-australiaeast}"
NAME_PREFIX="${NAME_PREFIX:-group29r2}"
IMAGE_TAG="${IMAGE_TAG:-latest}"

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
  --parameters namePrefix="$NAME_PREFIX" imageTag="$IMAGE_TAG" \
  --output table || echo "(expected: first pass fails until images exist in ACR -- continuing)"

ACR_LOGIN_SERVER=$(az deployment group show --resource-group "$RESOURCE_GROUP" --name main --query "properties.outputs.acrLoginServer.value" -o tsv)
ACR_NAME="${ACR_LOGIN_SERVER%%.*}"

echo "== 3. Build and push images to ACR: $ACR_NAME =="
az acr build --registry "$ACR_NAME" --image "home:$IMAGE_TAG" ./shared
az acr build --registry "$ACR_NAME" --image "aimode:$IMAGE_TAG" ./ai-services/ai-mode
az acr build --registry "$ACR_NAME" --image "student1:$IMAGE_TAG" ./student-1
az acr build --registry "$ACR_NAME" --image "student2:$IMAGE_TAG" ./student-2
az acr build --registry "$ACR_NAME" --image "student3:$IMAGE_TAG" ./student-3
az acr build --registry "$ACR_NAME" --image "student4:$IMAGE_TAG" ./student-4

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
  --parameters namePrefix="$NAME_PREFIX" imageTag="$IMAGE_TAG" \
  --output table

echo "== Deployment complete. URLs: =="
az deployment group show --resource-group "$RESOURCE_GROUP" --name main --query "properties.outputs" -o json