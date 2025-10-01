#!/usr/bin/env bash
set -euo pipefail

if ! command -v gh >/dev/null 2>&1; then
  echo "gh (GitHub CLI) is required. Install: https://cli.github.com/" >&2
  exit 1
fi
if ! command -v jq >/dev/null 2>&1; then
  echo "jq is required. Install: https://stedolan.github.io/jq/" >&2
  exit 1
fi

REPO=${GH_REPO:-}
if [[ -z "${REPO}" ]]; then
  # Try to infer from git remote origin
  if git remote get-url origin >/dev/null 2>&1; then
    url=$(git remote get-url origin)
    # Supports git@github.com:org/repo.git or https://github.com/org/repo.git
    if [[ "$url" =~ github.com[:/](.+)/(.+)\.git$ ]]; then
      REPO="${BASH_REMATCH[1]}/${BASH_REMATCH[2]}"
    fi
  fi
fi

if [[ -z "${REPO}" ]]; then
  echo "Set GH_REPO=org/repo or add a git remote origin." >&2
  exit 1
fi

echo "Seeding issues into ${REPO}…"

# Ensure labels exist
LABELS=("area:api" "feat" "area:harness" "area:frontend" "area:infra" "chore" "area:obs" "type:chore" "good-first-issue" "a11y" "type:bug")
for l in "${LABELS[@]}"; do
  gh label create "$l" --repo "$REPO" --force >/dev/null 2>&1 || true
done

jq -c '.[]' scripts/issues.json | while read -r item; do
  title=$(echo "$item" | jq -r .title)
  body=$(echo "$item" | jq -r .body)
  labels=$(echo "$item" | jq -r '.labels | join(",")')
  echo "Creating: $title"
  gh issue create --repo "$REPO" --title "$title" --body "$body" --label "$labels" || true
done

echo "Done."
