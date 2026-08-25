#!/usr/bin/env bash
# MANIFEST
# sample_id: HARNESS-02
# vulns: []
#
# One-shot entry point for the MCP client harness: installs the client-side
# dependencies once, then runs client/runner.ts which spawns and exercises
# every server declared in the repository-root mcp.json.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TSX_CLI="$ROOT/client/node_modules/tsx/dist/cli.mjs"
TSX_BIN="$ROOT/client/node_modules/.bin/tsx"

if [ ! -f "$TSX_CLI" ]; then
  echo "[run_all] installing client dependencies..." >&2
  npm --prefix "$ROOT/client" install
fi

# Prefer the .bin shim when it exists; fall back to invoking the tsx CLI
# entry point directly (works on filesystems without symlink support).
if [ -x "$TSX_BIN" ]; then
  exec "$TSX_BIN" "$ROOT/client/runner.ts"
else
  exec node "$TSX_CLI" "$ROOT/client/runner.ts"
fi
