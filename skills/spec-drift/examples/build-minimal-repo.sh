#!/usr/bin/env bash
# Build a throwaway repository for the spec-drift evals.
# Usage: build-minimal-repo.sh [--main-branch NAME] [--with-predict] TARGET_DIR
set -euo pipefail
MAIN=main; PREDICT=0; TARGET=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --main-branch) MAIN="$2"; shift 2;;
    --with-predict) PREDICT=1; shift;;
    *) TARGET="$1"; shift;;
  esac
done
[[ -n "$TARGET" ]] || { echo "usage: $0 [--main-branch NAME] [--with-predict] TARGET_DIR" >&2; exit 2; }
HERE="$(cd "$(dirname "$0")" && pwd)"
TOOL="$HERE/../tool"
mkdir -p "$TARGET"; TARGET="$(cd "$TARGET" && pwd)"
REPO="$TARGET/repo"; ORIGIN="$TARGET/origin.git"

mkdir -p "$REPO"
cp -R "$HERE/minimal-repo/." "$REPO/"
git init -q -b "$MAIN" "$REPO"
git -C "$REPO" config user.name "Eval"; git -C "$REPO" config user.email "eval@example.com"
git -C "$REPO" add -A && git -C "$REPO" commit -qm "initial code and ledger"

# sync every entry so the lock exists and check is clean
for id in $(grep -o '^### [A-Z][A-Z0-9-]*' "$REPO/ledger.md" | awk '{print $2}'); do
  (cd "$REPO" && python3 "$TOOL" sync "$id" --by Alice --note "initial sync" >/dev/null)
done
git -C "$REPO" add -A && git -C "$REPO" commit -qm "sync ledger lock"

git init -q --bare -b "$MAIN" "$ORIGIN"
git -C "$REPO" remote add origin "$ORIGIN"
git -C "$REPO" push -q origin "$MAIN"
git -C "$REPO" checkout -q -b feature/x

if [[ "$PREDICT" == 1 ]]; then
  mkdir -p "$REPO/docs/predictions"
  printf '# Prediction\n\nP1: src/order.py::is_refundable\n' > "$REPO/docs/predictions/prediction.md"
  git -C "$REPO" add docs && git -C "$REPO" commit -qm "prediction for this cycle"
fi
(cd "$REPO" && python3 "$TOOL" check >/dev/null) && echo "ready: $REPO (mainline $MAIN)"
