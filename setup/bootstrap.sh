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

ok()     { echo -e "${GREEN}✓${NC} $*"; }
info()   { echo -e "${YELLOW}→${NC} $*"; }
fail()   { echo -e "${RED}✗ ERROR:${NC} $*" >&2; }
header() { echo -e "\n${BOLD}── $* ──────────────────────────────────────────${NC}"; }

# ── Config ────────────────────────────────────────────────────────────────────

RG="tdo-platform-dev"
OPENAI_ACCOUNT="tdo-openai-dev"
OPENAI_DEPLOYMENT="gpt-4o"
OPENAI_MODEL="gpt-4o"
OPENAI_MODEL_VERSION="2024-11-20"

KV="tdo-kv-dev"

# northeurope hub/project (already exists, kept for other workloads)
AI_HUB="tdo-ai-hub-dev"
AI_PROJECT="tdo-ai-project-dev"

# swedencentral hub/project for serverless embedding models
# (Cohere/serverless catalog models are not available in northeurope)
AI_HUB_SC="tdo-ai-hub-sc-dev"
AI_PROJECT_SC="tdo-ai-project-sc-dev"
AI_LOCATION="swedencentral"
EMBEDDER_ENDPOINT="tdo-embedder-dev"
# Cohere multilingual embed v3 — available as serverless in swedencentral
EMBEDDER_MODEL_ID="azureml://registries/azureml-cohere/models/Cohere-embed-v3-multilingual"

CONTAINER_APP="tdo-app-api-dev"
CONTAINER_APP_RG="$RG"
API_KEY="tdo-dev-key-63ac09ac2414579c6e5a22d08c86f963"
HEALTH_URL="https://tdo-app-api-dev.mangocliff-4ea581ad.northeurope.azurecontainerapps.io/v1/health"

# Plain variables for summary (bash 3 compatible — no associative arrays)
# Ensure Key Vault public access and firewall rule are restored on exit
MY_IP=""
kv_restore_network() {
  echo ""
  info "Restoring Key Vault network access to private-only..."
  if [[ -n "$MY_IP" ]]; then
    az keyvault network-rule remove \
      --name "$KV" \
      --resource-group "$RG" \
      --ip-address "${MY_IP}/32" \
      --output none 2>/dev/null || true
  fi
  az keyvault update \
    --name "$KV" \
    --resource-group "$RG" \
    --public-network-access Disabled \
    --output none 2>/dev/null || true
  ok "Key Vault firewall rule removed and public network access disabled."
}

ST_OPENAI_DEPLOY="skipped"
ST_OPENAI_SECRETS="skipped"
ST_AI_HUB="skipped"
ST_AI_PROJECT="skipped"
ST_EMBEDDER_DEPLOY="skipped"
ST_EMBEDDER_SECRETS="skipped"
ST_API_KEY="skipped"
ST_RESTART="skipped"
ST_HEALTH="not run"
OPENAI_ENDPOINT=""
EMBEDDER_URL="n/a"

# ── Step 1: Deploy gpt-4o to Azure OpenAI ────────────────────────────────────

header "Step 1: Deploy gpt-4o model"

EXISTING_DEPLOYMENT=$(az cognitiveservices account deployment show \
  --name "$OPENAI_ACCOUNT" \
  --resource-group "$RG" \
  --deployment-name "$OPENAI_DEPLOYMENT" \
  --query name -o tsv 2>/dev/null || true)

if [[ -n "$EXISTING_DEPLOYMENT" ]]; then
  ok "Deployment '$OPENAI_DEPLOYMENT' already exists — skipping."
  ST_OPENAI_DEPLOY="already existed"
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
  ST_OPENAI_DEPLOY="created"
fi

# ── Enable Key Vault public access for secret writes ─────────────────────────

header "Pre-step: Enable Key Vault public network access"
info "Detecting public IP..."
MY_IP=$(curl -sf https://api.ipify.org || curl -sf https://ifconfig.me)
ok "Public IP: $MY_IP"

info "Enabling public network access on '$KV' and adding firewall rule for $MY_IP..."
az keyvault update \
  --name "$KV" \
  --resource-group "$RG" \
  --public-network-access Enabled \
  --output none
az keyvault network-rule add \
  --name "$KV" \
  --resource-group "$RG" \
  --ip-address "${MY_IP}/32" \
  --output none
ok "Firewall rule added — waiting 15s for propagation..."
sleep 15
trap kv_restore_network EXIT

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
ST_OPENAI_SECRETS="stored"

# ── Step 3: Create AI Foundry hub and project in swedencentral ────────────────

header "Step 3: Create AI Foundry hub and project (swedencentral)"

# Hub in swedencentral
EXISTING_HUB_SC=$(az ml workspace show \
  --name "$AI_HUB_SC" \
  --resource-group "$RG" \
  --query name -o tsv 2>/dev/null || true)

if [[ -n "$EXISTING_HUB_SC" ]]; then
  ok "AI hub '$AI_HUB_SC' already exists — reusing."
  ST_AI_HUB="already existed"
else
  info "Creating AI hub '$AI_HUB_SC' in $AI_LOCATION..."
  az ml workspace create \
    --name "$AI_HUB_SC" \
    --resource-group "$RG" \
    --location "$AI_LOCATION" \
    --kind hub
  ok "Created AI hub '$AI_HUB_SC'."
  ST_AI_HUB="created"
fi

# Project in swedencentral
EXISTING_PROJECT_SC=$(az ml workspace show \
  --name "$AI_PROJECT_SC" \
  --resource-group "$RG" \
  --query name -o tsv 2>/dev/null || true)

if [[ -n "$EXISTING_PROJECT_SC" ]]; then
  ok "AI project '$AI_PROJECT_SC' already exists — reusing."
  ST_AI_PROJECT="already existed"
else
  info "Creating AI project '$AI_PROJECT_SC' under hub '$AI_HUB_SC'..."
  HUB_SC_ID=$(az ml workspace show \
    --name "$AI_HUB_SC" \
    --resource-group "$RG" \
    --query id -o tsv)
  az ml workspace create \
    --name "$AI_PROJECT_SC" \
    --resource-group "$RG" \
    --location "$AI_LOCATION" \
    --kind project \
    --hub-id "$HUB_SC_ID"
  ok "Created AI project '$AI_PROJECT_SC'."
  ST_AI_PROJECT="created"
fi

# ── Step 4: Deploy multilingual-e5-large serverless endpoint ──────────────────

header "Step 4: Deploy multilingual-e5-large serverless endpoint"

EXISTING_ENDPOINT=$(az ml serverless-endpoint show \
  --name "$EMBEDDER_ENDPOINT" \
  --workspace-name "$AI_PROJECT_SC" \
  --resource-group "$RG" \
  --query name -o tsv 2>/dev/null || true)

if [[ -n "$EXISTING_ENDPOINT" ]]; then
  ok "Serverless endpoint '$EMBEDDER_ENDPOINT' already exists — skipping."
  ST_EMBEDDER_DEPLOY="already existed"
else
  # Accept Cohere marketplace terms before creating the endpoint
  info "Accepting marketplace subscription for Cohere embed model..."
  EXISTING_MPSUB=$(az ml marketplace-subscription show \
    --name "$EMBEDDER_ENDPOINT" \
    --workspace-name "$AI_PROJECT_SC" \
    --resource-group "$RG" \
    --query name -o tsv 2>/dev/null || true)
  if [[ -z "$EXISTING_MPSUB" ]]; then
    cat > /tmp/marketplace_sub.yml << YAML
\$schema: https://azuremlschemas.azureedge.net/latest/marketplaceSubscription.schema.json
name: ${EMBEDDER_ENDPOINT}
model_id: ${EMBEDDER_MODEL_ID}
YAML
    az ml marketplace-subscription create \
      --file /tmp/marketplace_sub.yml \
      --workspace-name "$AI_PROJECT_SC" \
      --resource-group "$RG" \
      --output none
    ok "Marketplace subscription accepted."
  else
    ok "Marketplace subscription already exists — skipping."
  fi

  info "Creating serverless endpoint '$EMBEDDER_ENDPOINT' (this may take several minutes)..."
  cat > /tmp/embedder_endpoint.yml << YAML
\$schema: https://azuremlschemas.azureedge.net/latest/serverlessEndpoint.schema.json
name: ${EMBEDDER_ENDPOINT}
model_id: ${EMBEDDER_MODEL_ID}
YAML
  az ml serverless-endpoint create \
    --file /tmp/embedder_endpoint.yml \
    --workspace-name "$AI_PROJECT_SC" \
    --resource-group "$RG"
  ok "Serverless endpoint '$EMBEDDER_ENDPOINT' created."
  ST_EMBEDDER_DEPLOY="created"
fi

# Wait for endpoint to be ready
info "Waiting for endpoint to reach 'Succeeded' state..."
for i in $(seq 1 20); do
  STATE=$(az ml serverless-endpoint show \
    --name "$EMBEDDER_ENDPOINT" \
    --workspace-name "$AI_PROJECT_SC" \
    --resource-group "$RG" \
    --query provisioning_state -o tsv 2>/dev/null || echo "Unknown")
  if [[ "$(echo "$STATE" | tr '[:upper:]' '[:lower:]')" == "succeeded" ]]; then
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
  --workspace-name "$AI_PROJECT_SC" \
  --resource-group "$RG" \
  --query scoring_uri -o tsv)

info "Fetching embedder key..."
EMBEDDER_KEY=$(az ml serverless-endpoint get-credentials \
  --name "$EMBEDDER_ENDPOINT" \
  --workspace-name "$AI_PROJECT_SC" \
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
ST_EMBEDDER_SECRETS="stored"

# ── Step 6: Store API key in Key Vault ───────────────────────────────────────

header "Step 6: Store API key in Key Vault"

info "Storing 'api-key' in Key Vault '$KV'..."
az keyvault secret set \
  --vault-name "$KV" \
  --name "api-key" \
  --value "$API_KEY" \
  --output none
ok "Stored api-key."
ST_API_KEY="stored"

# All Key Vault writes done — restore private-only access now
trap - EXIT
kv_restore_network

# ── Step 7: Restart container app ────────────────────────────────────────────

header "Step 7: Restart container app"

info "Restarting '$CONTAINER_APP' to pick up new Key Vault secrets..."
az containerapp update \
  --name "$CONTAINER_APP" \
  --resource-group "$CONTAINER_APP_RG" \
  --revision-suffix "bootstrap-$(date +%s)" \
  --output none
ok "Container app restarted (new revision created)."
ST_RESTART="done"

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
  ST_HEALTH="ok (HTTP 200)"
else
  fail "Health check returned HTTP $HTTP_CODE"
  echo "Response: $HEALTH_BODY"
  ST_HEALTH="FAILED (HTTP $HTTP_CODE)"
fi

# ── Step 9: Summary ───────────────────────────────────────────────────────────

header "Summary"

echo ""
printf "  %-25s %s\n" "OpenAI deployment:"   "$ST_OPENAI_DEPLOY"
printf "  %-25s %s\n" "OpenAI secrets:"      "$ST_OPENAI_SECRETS"
printf "  %-25s %s\n" "AI hub:"              "$ST_AI_HUB"
printf "  %-25s %s\n" "AI project:"          "$ST_AI_PROJECT"
printf "  %-25s %s\n" "Embedder deployment:" "$ST_EMBEDDER_DEPLOY"
printf "  %-25s %s\n" "Embedder secrets:"    "$ST_EMBEDDER_SECRETS"
printf "  %-25s %s\n" "API key:"             "$ST_API_KEY"
printf "  %-25s %s\n" "Container app:"       "$ST_RESTART"
printf "  %-25s %s\n" "Health check:"        "$ST_HEALTH"
echo ""
printf "  %-25s %s\n" "OpenAI endpoint:"     "$OPENAI_ENDPOINT"
printf "  %-25s %s\n" "Embedder endpoint:"   "$EMBEDDER_URL"
printf "  %-25s %s\n" "API health URL:"      "$HEALTH_URL"
echo ""
