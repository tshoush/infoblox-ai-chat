#!/usr/bin/env bash
#
# Download the public Infoblox WAPI object reference (HTML) into rag_docs/wapidoc/.
# These per-object pages document every field (name, type, supports flags) and
# are excellent grounding for generating correct WAPI calls.
#
# Source: the public WAPI 2.13.7 doc mirror. Override with WAPIDOC_BASE.
# Re-runnable: existing non-empty files are skipped.
#
# Usage: bash scripts/fetch_wapidoc.sh
set -euo pipefail

BASE="${WAPIDOC_BASE:-https://ipam.illinois.edu/wapidoc}"
OUT="rag_docs/wapidoc"
mkdir -p "$OUT"

echo "Fetching object index from $BASE ..."
index="$(mktemp)"
curl -sS -L --max-time 30 "$BASE/index.html" -o "$index"

mapfile -t objs < <(grep -oE 'objects/[a-zA-Z0-9_.:-]+\.html' "$index" | sort -u)
echo "Found ${#objs[@]} object pages."

ok=0; fail=0
for obj in "${objs[@]}"; do
  name="${obj#objects/}"
  dest="$OUT/$name"
  if [ -s "$dest" ]; then ok=$((ok+1)); continue; fi
  code="$(curl -sS -L --max-time 25 -o "$dest" -w '%{http_code}' "$BASE/$obj" || echo 000)"
  if [ "$code" = "200" ] && [ -s "$dest" ]; then
    ok=$((ok+1))
  else
    fail=$((fail+1)); rm -f "$dest"; echo "  FAIL($code): $name"
  fi
  sleep 0.3   # be polite to the server
done

rm -f "$index"
echo "Done: $ok fetched, $fail failed. Now run: python scripts/build_rag_index.py"
