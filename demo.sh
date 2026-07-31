#!/usr/bin/env bash
#
# Adaptive CS Tutor — deterministic demo.
#
#   ./demo.sh              full run: tests, health, offline demo, live demo
#   ./demo.sh --offline    skip every model call (safe with the Wi-Fi off)
#   ./demo.sh --fast       skip the test suite
#   ./demo.sh --serve      finish by launching the web UI on :8123
#
# The scripted student is fixed (questions q2, q9, q18 answered wrong), so the
# diagnostic, the propagation and the learning path are identical on every run.
# Only the model's prose varies, and --offline removes even that.
set -euo pipefail

cd "$(dirname "$0")"

OFFLINE=0; FAST=0; SERVE=0
for arg in "$@"; do
  case "$arg" in
    --offline) OFFLINE=1 ;;
    --fast)    FAST=1 ;;
    --serve)   SERVE=1 ;;
    -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
    *) echo "unknown flag: $arg" >&2; exit 2 ;;
  esac
done

GOLD=$'\033[38;5;178m'; DIM=$'\033[2m'; RESET=$'\033[0m'
step() { printf '\n%s▸ %s%s\n' "$GOLD" "$1" "$RESET"; }

# Prefer uv, fall back to plain python3 — the runtime has zero dependencies.
if command -v uv >/dev/null 2>&1; then
  PY="uv run python"
  TEST="uv run --with pytest pytest"
else
  PY="python3"
  TEST="python3 -m pytest"
  printf '%suv not found — falling back to python3%s\n' "$DIM" "$RESET"
fi

if [ "$FAST" -eq 0 ]; then
  step "1/4  Test suite"
  $TEST
fi

step "2/4  Health check"
$PY cli.py health

if [ "$OFFLINE" -eq 1 ]; then
  step "3/4  Full walkthrough — OFFLINE (no model calls at all)"
  $PY cli.py demo --no-llm
  step "4/4  Done"
  printf '%sRan with zero network access and zero API cost.%s\n' "$DIM" "$RESET"
else
  step "3/4  Full walkthrough — OFFLINE fallback path"
  $PY cli.py demo --no-llm

  step "4/4  Full walkthrough — LIVE local model (qwen3-fast via Ollama HTTP)"
  printf '%sFirst generation loads the model and can take ~30s.%s\n' "$DIM" "$RESET"
  $PY cli.py demo --refresh
fi

if [ "$SERVE" -eq 1 ]; then
  step "Launching web UI"
  EXTRA=""
  [ "$OFFLINE" -eq 1 ] && EXTRA="--no-llm"
  $PY server.py --port 8123 $EXTRA
fi
