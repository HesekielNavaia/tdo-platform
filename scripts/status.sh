#!/usr/bin/env bash
# TDO Platform — real-time status dashboard
# Usage: ./scripts/status.sh

set -uo pipefail
export PYTHONIOENCODING=utf-8
export PYTHONUTF8=1

# ── Colours ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'
YLW='\033[0;33m'
GRN='\033[0;32m'
CYN='\033[0;36m'
BLD='\033[1m'
RST='\033[0m'

ok()   { echo -e "  ${GRN}✅  $*${RST}"; }
warn() { echo -e "  ${YLW}⚠️   $*${RST}"; }
fail() { echo -e "  ${RED}❌  $*${RST}"; }
hdr()  { echo -e "\n${BLD}${CYN}## $*${RST}"; echo -e "${CYN}$(printf '─%.0s' {1..60})${RST}"; }

# ── Config ────────────────────────────────────────────────────────────────────
RG="tdo-platform-dev"
APP="tdo-app-api-dev"
BASE="https://tdo-app-api-dev.mangocliff-4ea581ad.northeurope.azurecontainerapps.io"
FRONTEND_APP="tdo-frontend-dev"
KEY="tdo-dev-key-63ac09ac2414579c6e5a22d08c86f963"
HARVEST_JOB="tdo-job-harvest-dev"
EMBED_JOB="tdo-job-embed-dev"
REPO="HesekielNavaia/tdo-platform"

# Temp files for JSON (avoids pipe + heredoc stdin conflict)
TMPDIR_TDO=$(mktemp -d)
trap 'rm -rf "$TMPDIR_TDO"' EXIT

pyq() {
  # pyq <json_file> <python_expression_on_d>
  # e.g. pyq /tmp/foo.json "d.get('key','?')"
  local f="$1"; local expr="$2"
  python3 - "$f" <<PYEOF 2>/dev/null
import sys, json
with open(sys.argv[1]) as fh:
    d = json.load(fh)
print($expr)
PYEOF
}

echo -e "\n${BLD}TDO Platform Status${RST}  —  $(date -u '+%Y-%m-%d %H:%M UTC')"

# ─────────────────────────────────────────────────────────────────────────────
hdr "DEPLOYED VERSIONS"
# ─────────────────────────────────────────────────────────────────────────────

HEALTH_FILE="$TMPDIR_TDO/health.json"
if curl -sf --max-time 10 "$BASE/v1/health" -H "X-API-Key: $KEY" -o "$HEALTH_FILE" 2>/dev/null; then
  GIT_SHA=$(pyq "$HEALTH_FILE"    "d.get('git_sha','?')")
  DEPLOY_T=$(pyq "$HEALTH_FILE"   "d.get('deploy_time','?')")
  EMBEDDER=$(pyq "$HEALTH_FILE"   "d.get('model_endpoints',{}).get('embedder','?')")
  HARMONISER=$(pyq "$HEALTH_FILE" "d.get('model_endpoints',{}).get('harmoniser','?')")

  ok "API git SHA   : ${BLD}$GIT_SHA${RST}  (deployed $DEPLOY_T)"

  if [[ "$EMBEDDER" == "connected" ]]; then
    ok  "Embedder      : connected (Cohere-embed-v3-multilingual)"
  else
    warn "Embedder      : $EMBEDDER  — semantic search disabled"
  fi

  if [[ "$HARMONISER" == "connected" ]]; then
    ok  "Harmoniser    : connected"
  else
    warn "Harmoniser    : $HARMONISER  — LLM harmonisation disabled"
  fi
else
  fail "API unreachable at $BASE"
fi

# Active revision
ACTIVE_REV=$(az containerapp revision list -n "$APP" -g "$RG" \
  --query "[?properties.trafficWeight==\`100\`].name | [0]" -o tsv 2>/dev/null || echo "?")
ok "Active revision: $ACTIVE_REV"

# Frontend
FRONTEND_URL=$(az staticwebapp show -n "$FRONTEND_APP" -g "$RG" \
  --query "properties.defaultHostname" -o tsv 2>/dev/null | tr -d '[:space:]' || true)
if [[ -z "$FRONTEND_URL" ]]; then
  warn "Frontend URL  : could not determine"
else
  FE_STATUS=$(curl -sf --max-time 10 "https://$FRONTEND_URL" -o /dev/null -w "%{http_code}" 2>/dev/null || echo "000")
  FE_BODY=$(curl -sf --max-time 10 "https://$FRONTEND_URL" 2>/dev/null | head -c 500 || true)
  if [[ "$FE_STATUS" == "200" ]]; then
    if echo "$FE_BODY" | grep -qiE "vite|react|TDO|tdo-frontend" 2>/dev/null; then
      ok "Frontend      : https://$FRONTEND_URL  (HTTP $FE_STATUS, app loaded)"
    else
      warn "Frontend      : https://$FRONTEND_URL  (HTTP $FE_STATUS, may be placeholder)"
    fi
  else
    fail "Frontend      : https://$FRONTEND_URL  (HTTP $FE_STATUS)"
  fi
fi

# ─────────────────────────────────────────────────────────────────────────────
hdr "RECORD COUNTS"
# ─────────────────────────────────────────────────────────────────────────────

STATS_FILE="$TMPDIR_TDO/stats.json"
if curl -sf --max-time 10 "$BASE/v1/stats" -H "X-API-Key: $KEY" -o "$STATS_FILE" 2>/dev/null; then
  TOTAL=$(pyq "$STATS_FILE" "d.get('total_datasets',0)")
  echo -e "  Total records: ${BLD}$TOTAL${RST}"
  echo ""
  python3 - "$STATS_FILE" 2>/dev/null <<'PYEOF'
import sys, json
with open(sys.argv[1]) as fh:
    d = json.load(fh)
portals = d.get("by_portal", {})
GRN = '\033[0;32m'; YLW = '\033[0;33m'; RED = '\033[0;31m'; RST = '\033[0m'
for portal in ("statfin", "eurostat", "oecd", "worldbank", "undata"):
    n = portals.get(portal, 0)
    colour = GRN if n >= 200 else (YLW if n > 0 else RED)
    icon = u"\u2705" if n >= 200 else (u"\u26a0\ufe0f " if n > 0 else u"\u274c")
    print(u"  " + colour + icon + u"  " + portal.ljust(12) + u"  " + str(n).rjust(6) + u" records" + RST)
PYEOF
  true
else
  fail "Could not fetch /v1/stats"
fi

# Embedding coverage via backfill endpoint (dry-run with max_records=0)
echo ""
echo -e "  ${BLD}Embedding coverage:${RST}"
BF_FILE="$TMPDIR_TDO/backfill.json"
if curl -sf --max-time 20 -X POST "$BASE/v1/admin/backfill-embeddings" \
    -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
    -d '{"batch_size":1,"max_records":0}' -o "$BF_FILE" 2>/dev/null; then
  MISSING=$(pyq "$BF_FILE" "d.get('total_missing_before', d.get('missing_at_start', d.get('total_missing', '?')))")
  if [[ "$MISSING" == "0" ]]; then
    ok "embedding_vec : all records have embeddings"
  elif [[ "$MISSING" == "?" ]]; then
    warn "embedding_vec : count unknown"
  else
    warn "embedding_vec : $MISSING records missing  (run POST /v1/admin/backfill-embeddings to fix)"
  fi
else
  warn "Could not reach backfill endpoint"
fi

# ─────────────────────────────────────────────────────────────────────────────
hdr "SEARCH HEALTH"
# ─────────────────────────────────────────────────────────────────────────────

run_query() {
  local label="$1"
  local question="$2"
  local qfile="$TMPDIR_TDO/q_$(echo "$label" | tr ' ' '_').json"

  if ! curl -sf --max-time 20 -X POST "$BASE/v1/query" \
      -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
      -d "{\"question\":\"$question\",\"limit\":5}" \
      -o "$qfile" 2>/dev/null; then
    fail "\"$label\"  →  request failed"
    return
  fi

  COUNT=$(pyq "$qfile" "len(d.get('results',[]))")
  PORTALS=$(python3 - "$qfile" 2>/dev/null <<'PYEOF'
import sys, json
with open(sys.argv[1]) as fh:
    d = json.load(fh)
seen = dict.fromkeys(r["portal"] for r in d.get("results", []))
print(", ".join(seen.keys()))
PYEOF
  )

  if   [[ "$COUNT" -ge 3 ]]; then
    ok  "\"$label\"  →  $COUNT results  [$PORTALS]"
  elif [[ "$COUNT" -ge 1 ]]; then
    warn "\"$label\"  →  $COUNT results  [$PORTALS]  (expected ≥ 3)"
  else
    fail "\"$label\"  →  0 results"
  fi
}

run_query "GDP growth"                        "GDP growth"
run_query "population age structure Finland"  "population age structure Finland"
run_query "inflation eurozone monthly"        "inflation eurozone monthly"

# ─────────────────────────────────────────────────────────────────────────────
hdr "ONGOING JOBS"
# ─────────────────────────────────────────────────────────────────────────────

check_job() {
  local job_name="$1"
  local jfile="$TMPDIR_TDO/job_${job_name}.json"

  az containerapp job execution list -n "$job_name" -g "$RG" \
    --query "[?properties.status=='Running'].{name:name,started:properties.startTime}" \
    -o json > "$jfile" 2>/dev/null || echo "[]" > "$jfile"

  COUNT=$(pyq "$jfile" "len(d) if isinstance(d, list) else 0")
  if [[ "$COUNT" -gt 0 ]]; then
    warn "$job_name  →  $COUNT execution(s) RUNNING"
    python3 - "$jfile" 2>/dev/null <<'PYEOF'
import sys, json
with open(sys.argv[1]) as fh:
    execs = json.load(fh)
for e in execs:
    print("      " + e.get("name","?") + "  started " + e.get("started","?"))
PYEOF
  else
    local lastfile="$TMPDIR_TDO/job_last_${job_name}.json"
    az containerapp job execution list -n "$job_name" -g "$RG" \
      --query "[0].{status:properties.status,started:properties.startTime}" \
      -o json > "$lastfile" 2>/dev/null || echo "{}" > "$lastfile"
    LAST_STATUS=$(pyq "$lastfile" "d.get('status','?')")
    LAST_TIME=$(pyq "$lastfile"   "d.get('started','?')")
    if [[ "$LAST_STATUS" == "Succeeded" ]]; then
      ok  "$job_name  →  idle  (last: $LAST_STATUS  $LAST_TIME)"
    elif [[ "$LAST_STATUS" == "?" ]] || [[ "$LAST_STATUS" == "None" ]]; then
      warn "$job_name  →  no executions on record"
    else
      warn "$job_name  →  idle  (last: $LAST_STATUS  $LAST_TIME)"
    fi
  fi
}

check_job "$HARVEST_JOB"
check_job "$EMBED_JOB"

# ─────────────────────────────────────────────────────────────────────────────
hdr "GITHUB CI/CD STATUS"
# ─────────────────────────────────────────────────────────────────────────────

show_workflow_runs() {
  local workflow="$1"
  local wfile="$TMPDIR_TDO/wf_$(echo "$workflow" | tr '.' '_').json"
  echo -e "  ${BLD}$workflow${RST}"
  gh run list --repo "$REPO" --limit 3 \
    --workflow "$workflow" \
    --json displayTitle,status,conclusion,createdAt \
    > "$wfile" 2>/dev/null || echo "[]" > "$wfile"

  python3 - "$wfile" 2>/dev/null <<'PYEOF'
import sys, json
with open(sys.argv[1]) as fh:
    runs = json.load(fh)
if not runs:
    print("    (no runs found or gh not authenticated)")
    sys.exit(0)
GRN='\033[0;32m'; YLW='\033[0;33m'; RED='\033[0;31m'; RST='\033[0m'
for r in runs:
    status     = r.get("status", "?")
    conclusion = r.get("conclusion") or ""
    title      = r.get("displayTitle", "?")[:55]
    created    = r.get("createdAt", "?")[:16].replace("T", " ")
    if status == "completed" and conclusion == "success":
        icon = GRN + u"\u2705" + RST
    elif status == "in_progress":
        icon = YLW + u"\u23f3" + RST
    elif conclusion in ("failure", "cancelled"):
        icon = RED + u"\u274c" + RST
    else:
        icon = YLW + u"\u26a0\ufe0f" + RST
    row = u"    " + icon + u"  " + created + u"  " + (status + "/" + conclusion).ljust(22) + u"  " + title
    print(row)
PYEOF
  echo ""
}

show_workflow_runs "deploy-app.yml"
show_workflow_runs "deploy-infra.yml"

# ─────────────────────────────────────────────────────────────────────────────
hdr "KNOWN OPEN ISSUES"
# ─────────────────────────────────────────────────────────────────────────────

warn "tdo-job-embed-dev + tdo-job-harmonise-dev use placeholder helloworld image (not wired)"
warn "GitHub env 'dev' secrets (TDO_API_KEYS, EMBEDDER_ENDPOINT, EMBEDDER_KEY) must exist for CI/CD secret-restore step"
warn "Harmoniser not_configured in prod — records indexed with rule-based mapping only"
warn "PostgreSQL + Key Vault on private endpoints — no direct local access"

echo ""
echo -e "${BLD}Done.${RST}  API: ${CYN}$BASE${RST}  Key: ${CYN}$KEY${RST}"
echo ""
