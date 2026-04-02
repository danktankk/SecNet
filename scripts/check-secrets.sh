#!/usr/bin/env bash
# Secret scanner — run before any git push.
# Exits 1 if anything suspicious is found.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FAIL=0

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Files/dirs to skip entirely
SKIP_DIRS="node_modules|__pycache__|dist|\.git"
SKIP_FILES="\.env$|check-secrets\.py|check-secrets\.sh"

# File extensions to scan
SCAN_PATTERN="\.(py|js|jsx|ts|tsx|yml|yaml|json|sh|md|txt|cfg|ini|toml)$|Dockerfile"

# ── Collect files to scan ────────────────────────────────────────────────────
mapfile -t FILES < <(
  find "$ROOT" -type f \
    | grep -vE "($SKIP_DIRS)/" \
    | grep -vE "/($SKIP_FILES)" \
    | grep -E "$SCAN_PATTERN"
)

echo ""
echo "Scanning ${#FILES[@]} files in $ROOT..."
echo ""

check() {
  local label="$1"
  local pattern="$2"
  local results

  results=$(grep -rnE "$pattern" "${FILES[@]}" 2>/dev/null \
    | grep -vE "^[^:]+:#" \
    | grep -vE "\.env\.example:" \
    | grep -vE "check-secrets\.(sh|py):" \
    || true)

  if [[ -n "$results" ]]; then
    echo -e "${RED}❌  [$label]${NC}"
    echo "$results" | head -10 | sed 's/^/    /'
    echo ""
    FAIL=1
  fi
}

# ── Checks ───────────────────────────────────────────────────────────────────

check "CrowdSec API key" \
  "7CuGrT5J"

check "OpenAI API key" \
  "sk-proj-"

check "Proxmox token UUID fragments" \
  "7eea4c1d|ee584044|9129e0e0"

check "UniFi password fragment" \
  "CCccCC"

check "Hardcoded internal IP as string literal" \
  "['\"]https?://192\.168\."

check "Inline credential assignment (generic)" \
  "(api[_-]?key|secret|password|token)\s*=\s*['\"][A-Za-z0-9+/=!@#\$%^&*]{12,}['\"]"

check "Hardcoded gate code in source" \
  "security_gate_code\s*[:=]\s*['\"]?[0-9]{4,}"

# ── .gitignore must exist and include .env ───────────────────────────────────
if [[ ! -f "$ROOT/.gitignore" ]]; then
  echo -e "${RED}❌  [Missing .gitignore]${NC}"
  echo "    .gitignore does not exist at project root"
  echo ""
  FAIL=1
elif ! grep -q "^\.env$" "$ROOT/.gitignore"; then
  echo -e "${RED}❌  [.env not in .gitignore]${NC}"
  echo "    .gitignore exists but does not explicitly ignore .env"
  echo ""
  FAIL=1
fi

# ── .env must NOT be tracked by git ─────────────────────────────────────────
if git -C "$ROOT" rev-parse --git-dir &>/dev/null; then
  if git -C "$ROOT" ls-files --error-unmatch "$ROOT/.env" &>/dev/null 2>&1; then
    echo -e "${RED}❌  [.env is tracked by git]${NC}"
    echo "    Run: git -C $ROOT rm --cached .env"
    echo ""
    FAIL=1
  fi
  # Check git history for known secrets
  echo -e "${YELLOW}Checking git history for leaked secrets...${NC}"
  HISTORY_HITS=$(git -C "$ROOT" log --all -p 2>/dev/null \
    | grep -E "7CuGrT5J|sk-proj-|7eea4c1d|ee584044|9129e0e0|CCccCC" \
    | head -5 || true)
  if [[ -n "$HISTORY_HITS" ]]; then
    echo -e "${RED}❌  [Secrets found in git history]${NC}"
    echo "$HISTORY_HITS" | sed 's/^/    /'
    echo ""
    echo "    You must rewrite history: git filter-repo or BFG Repo Cleaner"
    echo ""
    FAIL=1
  fi
fi

# ── Result ───────────────────────────────────────────────────────────────────
if [[ $FAIL -eq 1 ]]; then
  echo -e "${RED}Secret scan FAILED. Fix all issues before pushing to GitHub.${NC}"
  echo ""
  exit 1
else
  echo -e "${GREEN}✅  Secret scan passed — nothing sensitive found.${NC}"
  echo ""
  exit 0
fi
