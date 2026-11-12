#!/usr/bin/env bash
# Fails if the committed OpenAPI document or generated TypeScript client is stale (ADR-0004).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CLIENT="$ROOT/packages/api-client"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

(cd "$ROOT/backend" && uv run python -m scripts.export_openapi "$TMP/openapi.json")
(cd "$CLIENT" && npx --no openapi-typescript "$TMP/openapi.json" --output "$TMP/schema.d.ts" >/dev/null)

stale=0
diff -u "$CLIENT/openapi.json" "$TMP/openapi.json" || stale=1
diff -u "$CLIENT/src/schema.d.ts" "$TMP/schema.d.ts" || stale=1
if [[ "$stale" == "1" ]]; then
  echo "API contract is stale. Run 'make gen-client' and commit the result." >&2
  exit 1
fi
echo "API contract is up to date."
