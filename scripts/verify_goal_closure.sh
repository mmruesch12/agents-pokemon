#!/usr/bin/env bash
# Mechanical gate for goal closure: clean tree, tests, launches, evidence logs.
set -euo pipefail

SCRATCH="${SCRATCH:-/tmp/grok-goal-d33b25713fff/implementer}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

mkdir -p "$SCRATCH"
rm -f "$SCRATCH"/*.log

echo "== initial git status =="
git status --porcelain | tee "$SCRATCH/initial_status.log"

echo "== git status (must be clean) =="
git status --porcelain | tee "$SCRATCH/final_status.log"
if [ -s "$SCRATCH/final_status.log" ]; then
  echo "FAIL: working tree not clean (see $SCRATCH/final_status.log)" >&2
  exit 1
fi
echo "(clean working tree)" >>"$SCRATCH/final_status.log"
git status -sb >>"$SCRATCH/final_status.log"

echo "== stray scaffold check =="
if [ -d langsmith-app ]; then
  if git check-ignore -q langsmith-app/ 2>/dev/null; then
    echo "WARN: langsmith-app/ exists locally but is gitignored (remove locally)" | tee "$SCRATCH/stray_scaffold.log"
    echo "FAIL: remove local langsmith-app/ scaffold before closure" >&2
    exit 1
  else
    echo "FAIL: langsmith-app/ exists and is not gitignored" >&2
    exit 1
  fi
else
  echo "OK: no langsmith-app/ directory" | tee "$SCRATCH/stray_scaffold.log"
fi

echo "== pytest x2 =="
uv run pytest tests/ -q --tb=line 2>&1 | tee "$SCRATCH/pytest_pass_1.log"
COUNT1=$(grep -oE '[0-9]+ passed' "$SCRATCH/pytest_pass_1.log" | tail -1 | grep -oE '^[0-9]+')
uv run pytest tests/ -q --tb=line 2>&1 | tee "$SCRATCH/pytest_pass_2.log"
COUNT2=$(grep -oE '[0-9]+ passed' "$SCRATCH/pytest_pass_2.log" | tail -1 | grep -oE '^[0-9]+')
if [ "$COUNT1" != "$COUNT2" ]; then
  echo "FAIL: pytest counts differ ($COUNT1 vs $COUNT2)" >&2
  exit 1
fi

echo "== verify_setup =="
uv run python -m src.run.verify_setup 2>&1 | tee "$SCRATCH/verify_setup.log"

echo "== cli launch x2 (no implicit resume) =="
TID="closure-smoke-$$"
uv run python -m src.run.cli --steps 8 --thread-id "$TID" 2>&1 | tee "$SCRATCH/cli_launch.log"
uv run python -m src.run.cli --steps 8 --thread-id "${TID}-b" 2>&1 | tee "$SCRATCH/cli_launch_2.log"

for f in "$SCRATCH/cli_launch.log" "$SCRATCH/cli_launch_2.log"; do
  if ! grep -q "Cold boot detected" "$f"; then
    echo "FAIL: missing 'Cold boot detected' in $f" >&2
    exit 1
  fi
  if grep -q "Resumed from checkpoint thread_id=default" "$f"; then
    echo "FAIL: implicit resume leak in $f" >&2
    exit 1
  fi
done

echo "== ruff =="
uv run ruff check src tests 2>&1 | tee "$SCRATCH/ruff.log"

echo "== staged secret scan =="
if git diff --cached --stat | grep -q .; then
  git diff --cached | head -200 | tee "$SCRATCH/staged_scan.log"
else
  echo "(no staged changes — working tree clean)" | tee "$SCRATCH/staged_scan.log"
fi
if git diff --cached | grep -qiE 'xai-|sk-|lsv2_pt_|gho_|Bearer '; then
  echo "FAIL: possible secrets in staged diff" >&2
  exit 1
fi

echo "== recent commit secret scan =="
git log -7 -p --no-color 2>&1 | head -500 | tee "$SCRATCH/recent_commit_scan.log"
if git log -7 -p --no-color | grep -qiE 'xai-|sk-|lsv2_pt_|gho_|Bearer '; then
  echo "FAIL: possible secrets in recent commits" >&2
  exit 1
fi

git log -5 --oneline | tee "$SCRATCH/commits.log"
echo "OK: goal closure checks passed ($(date -u +%Y-%m-%dT%H:%M:%SZ))" | tee "$SCRATCH/closure_ok.log"