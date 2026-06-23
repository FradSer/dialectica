#!/usr/bin/env bash
# Scorer: blind A/B Workflow engine vs single call, prints ONE number (net workflow wins).
# Reads WEAK_MODEL/CLIPROXY env. Higher = better for the workflow engine.
set -e
cd "$(dirname "$0")/.."
export OPENAI_API_BASE="${OPENAI_API_BASE:-http://${CLIPROXYAPI_HOST}:8317/v1}"
export OPENAI_API_KEY="${OPENAI_API_KEY:-$CLIPROXYAPI_TOKEN}"
export DEFAULT_MODEL_CONFIG="${DEFAULT_MODEL_CONFIG:-openai:qwen3.6-flash}"
export DIALECTICA_WORKFLOW_CONCURRENCY="${DIALECTICA_WORKFLOW_CONCURRENCY:-4}"
# 3 problems keeps a round cheap (~3-5 min) so the loop can iterate.
uv run python -m evals.workflow_ablation --limit 3 --json evals/results/workflow_ablation.json 2>/dev/null | tail -1
