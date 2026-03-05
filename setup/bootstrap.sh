#!/usr/bin/env bash
# setup/bootstrap.sh — TDO platform bootstrap
#
# Idempotent: safe to run multiple times. Existing resources are reused,
# Key Vault secrets are overwritten with current values.
#
# Prerequisites:
#   - az CLI logged in with an account that has Contributor + Key Vault
#     Secrets Officer on tdo-platform-dev resource group
#   - az ml extension installed: az extension add -n ml

set -euo pipefail

# ── Colours ───────────────────────────────────────────────────────────────────

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BOLD='\033[1m'
NC='\033[0m'

ok()   { echo -e "${GREEN}✓${NC} $*"; }
info() { echo -e "${YELLOW}→${NC} $*"; }
fail() { echo -e "${RED}✗ ERROR:${NC} $*" >&2; }
header() { echo -e "\n${BOLD}── $* ──────────────────────────────────────────${NC}"; }

# ── Config ────────────────────────────────────────────────────────────────────

RG="tdo-platform-dev"
OPENAI_ACCOUNT="tdo-openai-dev"
OPENAI_DEPLOYMENT="gpt-4o"
OPENAI_MODEL="gpt-4o"
OPENAI_MODEL_VERSION="2024-11-20"

KV="tdo-kv-dev"

AI_HUB="tdo-ai-hub-dev"
AI_PROJECT="tdo-ai-project-dev"
AI_LOCATION="swedencentral"
EMBEDDER_ENDPOINT="tdo-embedder-dev"
# Verify this model ID in the Azure AI catalog if the deployment fails:
EMBEDDER_MODEL_ID="azureml://registries/azureml/models/multilingual-e5-large/versions/1"

CONTAINER_APP="tdo-app-api-dev"
CONTAINER_APP_RG="$RG"
API_KEY="tdo-dev-key-63ac09ac2414579c6e5a22d08c86f963"
HEALTH_URL="https://tdo-app-api-dev.mangocliff-4ea581ad.northeurope.azurecontainerapps.io/v1/health"

# Track outcomes for the summary
declare -A STATUS

# ── Step 1: Deploy gpt-4o to Azure OpenAI ────────────────────────────────────

header "Step 1: Deploy gpt-4o model"

EXISTING_DEPLOYMENT=$(az cognitiveservices account deployment show \
  --name "$OPENAI_ACCOUNT" \
  --resource-group "$RG" \
  --deployment-name "$OPENAI_DEPLOYMENT" \
  --query name -o tsv 2>/dev/null || true)

if [[ -n "$EXISTING_DEPLOYMENT" ]]; then
  ok "Deployment '$OPENAI_DEPLOYMENT' already exists — skipping."
  STATUS[openai_deploy]="already existed"
else
  info "Creating deployment '$OPENAI_DEPLOYMENT' in '$OPENAI_ACCOUNT'..."
  az cognitiveservices account deployment create \
    --name "$OPENAI_ACCOUNT" \
    --resource-group "$RG" \
    --deployment-name "$OPENAI_DEPLOYMENT" \
    --model-name "$OPENAI_MODEL" \
    --model-version "$OPENAI_MODEL_VERSION" \
    --model-format OpenAI \
    --sku-name "Standard" \
    --sku-capacity 10
  ok "Deployment '$OPENAI_DEPLOYMENT' created."
  STATUS[openai_deploy]="created"
fi

# ── Step 2: Store OpenAI endpoint and key in Key Vault ───────────────────────

header "Step 2: Store OpenAI credentials in Key Vault"

info "Fetching OpenAI endpoint..."
OPENAI_ENDPOINT=$(az cognitiveservices account show \
  --name "$OPENAI_ACCOUNT" \
  --resource-group "$RG" \
  --query properties.endpoint -o tsv)

info "Fetching OpenAI key..."
OPENAI_KEY=$(az cognitiveservices account keys list \
  --name "$OPENAI_ACCOUNT" \
  --resource-group "$RG" \
  --query key1 -o tsv)

info "Storing 'openai-endpoint' in Key Vault '$KV'..."
az keyvault secret set \
  --vault-name "$KV" \
  --name "openai-endpoint" \
  --value "$OPENAI_ENDPOINT" \
  --output none
ok "Stored openai-endpoint: $OPENAI_ENDPOINT"

info "Storing 'openai-key' in Key Vault '$KV'..."
az keyvault secret set \
  --vault-name "$KV" \
  --name "openai-key" \
  --value "$OPENAI_KEY" \
  --output none
ok "Stored openai-key: ${OPENAI_KEY:0:8}..."
STATUS[openai_secrets]="stored"

# ── Step 3: Create AI Foundry hub and project ─────────────────────────────────

header "Step 3: Create AI Foundry hub and project"

# Hub
EXISTING_HUB=$(az ml workspace show \
  --name "$AI_HUB" \
  --resource-group "$RG" \
  --query name -o tsv 2>/dev/null || true)

if [[ -n "$EXISTING_HUB" ]]; then
  ok "AI hub '$AI_HUB' already exists — reusing."
  STATUS[ai_hub]="already existed"
else
  info "Creating AI hub '$AI_HUB' in $AI_LOCATION..."
  az ml workspace create \
    --name "$AI_HUB" \
    --resource-group "$RG" \
    --location "$AI_LOCATION" \
    --kind hub
  ok "Created AI hub '$AI_HUB'."
  STATUS[ai_hub]="created"
fi

# Project
EXISTING_PROJECT=$(az ml workspace show \
  --name "$AI_PROJECT" \
  --resource-group "$RG" \
  --query name -o tsv 2>/dev/null || true)

if [[ -n "$EXISTING_PROJECT" ]]; then
  ok "AI project '$AI_PROJECT' already exists — reusing."
  STATUS[ai_project]="already existed"
else
  info "Creating AI project '$AI_PROJECT' under hub '$AI_HUB'..."
  az ml workspace create \
    --name "$AI_PROJECT" \
    --resource-group "$RG" \
    --location "$AI_LOCATION" \
    --kind project \
    --hub-id "$(az ml workspace show --name "$AI_HUB" --resource-group "$RG" --query id -o tsv)"
  ok "Created AI project '$AI_PROJECT'."
  STATUS[ai_project]="created"
fi

# ── Step 4: Deploy multilingual-e5-large serverless endpoint ──────────────────

header "Step 4: Deploy multilingual-e5-large serverless endpoint"

EXISTING_ENDPOINT=$(az ml serverless-endpoint show \
  --name "$EMBEDDER_ENDPOINT" \
  --workspace-name "$AI_PROJECT" \
  --resource-group "$RG" \
  --query name -o tsv 2>/dev/null || true)

if [[ -n "$EXISTING_ENDPOINT" ]]; then
  ok "Serverless endpoint '$EMBEDDER_ENDPOINT' already exists — skipping."
  STATUS[embedder_deploy]="already existed"
else
  info "Creating serverless endpoint '$EMBEDDER_ENDPOINT' (this may take several minutes)..."
  az ml serverless-endpoint create \
    --name "$EMBEDDER_ENDPOINT" \
    --model-id "$EMBEDDER_MODEL_ID" \
    --workspace-name "$AI_PROJECT" \
    --resource-group "$RG"
  ok "Serverless endpoint '$EMBEDDER_ENDPOINT' created."
  STATUS[embedder_deploy]="created"
fi

# Wait for endpoint to be ready
info "Waiting for endpoint to reach 'Online' state..."
for i in $(seq 1 20); do
  STATE=$(az ml serverless-endpoint show \
    --name "$EMBEDDER_ENDPOINT" \
    --workspace-name "$AI_PROJECT" \
    --resource-group "$RG" \
    --query provisioningState -o tsv 2>/dev/null || echo "Unknown")
  if [[ "$STATE" == "Succeeded" ]]; then
    ok "Endpoint is online."
    break
  fi
  echo "  State: $STATE (attempt $i/20, waiting 30s...)"
  sleep 30
done

# ── Step 5: Store embedding endpoint and key in Key Vault ─────────────────────

header "Step 5: Store embedding credentials in Key Vault"

info "Fetching embedder endpoint URL..."
EMBEDDER_URL=$(az ml serverless-endpoint show \
  --name "$EMBEDDER_ENDPOINT" \
  --workspace-name "$AI_PROJECT" \
  --resource-group "$RG" \
  --query inferenceEndpoint.uri -o tsv)

info "Fetching embedder key..."
EMBEDDER_KEY=$(az ml serverless-endpoint get-keys \
  --name "$EMBEDDER_ENDPOINT" \
  --workspace-name "$AI_PROJECT" \
  --resource-group "$RG" \
  --query primaryKey -o tsv)

info "Storing 'embedder-endpoint' in Key Vault '$KV'..."
az keyvault secret set \
  --vault-name "$KV" \
  --name "embedder-endpoint" \
  --value "$EMBEDDER_URL" \
  --output none
ok "Stored embedder-endpoint: $EMBEDDER_URL"

info "Storing 'embedder-key' in Key Vault '$KV'..."
az keyvault secret set \
  --vault-name "$KV" \
  --name "embedder-key" \
  --value "$EMBEDDER_KEY" \
  --output none
ok "Stored embedder-key: ${EMBEDDER_KEY:0:8}..."
STATUS[embedder_secrets]="stored"

# ── Step 6: Store API key in Key Vault ───────────────────────────────────────

header "Step 6: Store API key in Key Vault"

info "Storing 'api-key' in Key Vault '$KV'..."
az keyvault secret set \
  --vault-name "$KV" \
  --name "api-key" \
  --value "$API_KEY" \
  --output none
ok "Stored api-key."
STATUS[api_key]="stored"

# ── Step 7: Restart container app ────────────────────────────────────────────

header "Step 7: Restart container app"

info "Restarting '$CONTAINER_APP' to pick up new Key Vault secrets..."
# Trigger a new revision by updating an innocuous annotation
az containerapp update \
  --name "$CONTAINER_APP" \
  --resource-group "$CONTAINER_APP_RG" \
  --revision-suffix "bootstrap-$(date +%s)" \
  --output none
ok "Container app restarted (new revision created)."
STATUS[restart]="done"

# ── Step 8: Health check ──────────────────────────────────────────────────────

header "Step 8: Health check"

info "Waiting 30 seconds for the new revision to start..."
sleep 30

info "Checking $HEALTH_URL ..."
HTTP_CODE=$(curl -s -o /tmp/health_response.json -w "%{http_code}" "$HEALTH_URL" || echo "000")
HEALTH_BODY=$(cat /tmp/health_response.json 2>/dev/null || echo "")

if [[ "$HTTP_CODE" == "200" ]]; then
  ok "Health check passed (HTTP $HTTP_CODE)."
  ok "Response: $HEALTH_BODY"
  STATUS[health]="ok (HTTP 200)"
else
  fail "Health check returned HTTP $HTTP_CODE"
  echo "Response: $HEALTH_BODY"
  STATUS[health]="FAILED (HTTP $HTTP_CODE)"
fi

# ── Step 9: Summary ───────────────────────────────────────────────────────────

header "Summary"

echo ""
printf "  %-25s %s\n" "OpenAI deployment:"    "${STATUS[openai_deploy]:-skipped}"
printf "  %-25s %s\n" "OpenAI secrets:"       "${STATUS[openai_secrets]:-skipped}"
printf "  %-25s %s\n" "AI hub:"               "${STATUS[ai_hub]:-skipped}"
printf "  %-25s %s\n" "AI project:"           "${STATUS[ai_project]:-skipped}"
printf "  %-25s %s\n" "Embedder deployment:"  "${STATUS[embedder_deploy]:-skipped}"
printf "  %-25s %s\n" "Embedder secrets:"     "${STATUS[embedder_secrets]:-skipped}"
printf "  %-25s %s\n" "API key:"              "${STATUS[api_key]:-skipped}"
printf "  %-25s %s\n" "Container app:"        "${STATUS[restart]:-skipped}"
printf "  %-25s %s\n" "Health check:"         "${STATUS[health]:-not run}"
echo ""
printf "  %-25s %s\n" "OpenAI endpoint:"  "$OPENAI_ENDPOINT"
printf "  %-25s %s\n" "Embedder endpoint:" "${EMBEDDER_URL:-n/a}"
printf "  %-25s %s\n" "API health URL:"   "$HEALTH_URL"
echo ""
