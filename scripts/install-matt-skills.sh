#!/usr/bin/env bash
# Stage upstream skill documents on Linux MCP server/build host, not on clients.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REVISION="4ae2317ddb22b046e26455e4f9c9b3aaaf62212d"
DEST="${1:-$ROOT/vendor/mattpocock-skills}"
if [[ -e "$DEST" ]]; then
  if [[ -f "$DEST/.lkh-pinned-revision" ]] &&
     [[ "$(tr -d '\r\n' < "$DEST/.lkh-pinned-revision")" == "$REVISION" ]] &&
     [[ -f "$DEST/LICENSE" ]] && [[ -f "$DEST/.claude-plugin/plugin.json" ]]; then
    echo "Pinned server skills already installed: $REVISION"
    exit 0
  fi
  echo "Target exists but is not the pinned installation: $DEST" >&2
  exit 1
fi
command -v git >/dev/null || { echo "Git required on MCP server" >&2; exit 1; }
git clone --no-checkout --filter=blob:none https://github.com/mattpocock/skills.git "$DEST"
git -C "$DEST" checkout --detach "$REVISION"
test "$(git -C "$DEST" rev-parse HEAD)" = "$REVISION"
test -f "$DEST/LICENSE"
test -f "$DEST/.claude-plugin/plugin.json"
printf '%s\n' "$REVISION" > "$DEST/.lkh-pinned-revision"
echo "Server skill documents staged: $REVISION"
