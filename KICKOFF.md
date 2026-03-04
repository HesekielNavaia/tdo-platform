# TDO Platform — Claude Code Kickoff Instructions

You are building the Trusted Data Observatory (TDO), a metadata discovery
platform that harvests official statistical datasets from 5 international
portals, harmonises the metadata using AI, indexes it for semantic search,
and exposes it via a REST API with a React frontend.

## Your working environment

- Mac with PowerShell terminal
- Azure subscription: Microsoft Azure Sponsorship (2984fe6f-916e-4ab1-ba5d-c34cdf8f9dd8)
- Azure resource group: tdo-platform-dev (North Europe)
- GitHub repo: HesekielNavaia/tdo-platform
- Azure tenant: e078eae9-f34e-495c-b095-7e1648269606
- Azure Client ID for GitHub Actions: 95e0befa-a09a-43ea-acc9-8294ea2bf104

## The full technical specification

Read `tdo_build_prompt_v2.md` in this folder. It contains the complete
architecture, data models, pipeline design, API spec, and infrastructure
requirements. Follow it precisely.

## Files already in this repo

- `tdo_build_prompt_v2.md` — full technical specification (read this first)
- `mapping_tables.py` — completed schema mapping tables, use as-is
- `tdo-demo.jsx` — completed frontend demo UI, use as-is
- `TASKS.md` — your task checklist, work through this in order

## How to work

1. Read `tdo_build_prompt_v2.md` fully before writing any code
2. Work through `TASKS.md` in order, top to bottom
3. After completing each task, mark it as done in TASKS.md: change `- [ ]` to `- [x]`
4. After each task, run the relevant test command listed in TASKS.md
5. If tests fail, fix the code and rerun — do not move to the next task until tests pass
6. After each completed task, commit to git:
   git add .
   git commit -m "Complete task: [task name]"
7. After every 5 tasks, push to GitHub:
   git push origin main

## PowerShell note

You are in a PowerShell terminal on Mac. Use semicolons instead of &&
to chain commands. Example:
   python -m pytest tests/unit; git add .
Never use backslash line continuation — put commands on one line.

## Azure note

All Azure resources go into:
- Resource group: tdo-platform-dev
- Location: northeurope

Use Azure AI Foundry serverless endpoints for:
- Phi-4 (harmonisation LLM)
- multilingual-e5-large (embeddings)

Use the already-provisioned Azure OpenAI as fallback only.

## Rules you must follow

1. Never store secrets in code or config files. Use Azure Key Vault references
   and Managed Identities throughout.
2. LLMs must never invent URLs, publisher names, licenses, or dates.
   If not in the raw payload, the field must be null.
3. Every pipeline stage must write its state to the pipeline_runs PostgreSQL
   table before proceeding — the pipeline must be resumable.
4. Embedding dimensions must be validated at runtime before any records
   are processed. Fail fast if mismatch.
5. Use 'simple' (not 'english') for PostgreSQL full-text search config.
6. Respect robots.txt. Use official APIs only for all 5 portals.
7. All HTTP calls must have exponential backoff (max 3 retries) and 30s timeout.

## If you get stuck

- On Azure deployment errors: run `az deployment group validate` before apply
- On Python errors: check Python version is 3.12+
- On PostgreSQL pgvector errors: confirm extension is enabled with
  `CREATE EXTENSION IF NOT EXISTS vector;`
- On embedding dimension errors: check the model endpoint response shape
  before assuming 1024 dims

## Definition of done

The build is complete when:
1. All tasks in TASKS.md are marked [x]
2. The integration test passes:
   python -m pytest tests/integration/test_full_pipeline.py -v
3. The API returns results for:
   curl http://localhost:8000/v1/datasets?q=unemployment+finland
4. The frontend loads at http://localhost:3000 and shows real data

## Start now

Read `tdo_build_prompt_v2.md`, then open `TASKS.md` and begin Task 1.
