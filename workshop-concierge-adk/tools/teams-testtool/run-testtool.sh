#!/usr/bin/env bash
# Start the Microsoft 365 Agents Playground (Teams App Test Tool) and point it at the
# LOCAL bot host started by ./run-bot.sh. Opens a web chat UI in the browser; no M365
# tenant, license, Azure Bot registration, or tunnel is required.
#
# The Playground defaults its bot endpoint to http://localhost:3978/api/messages and
# we also pin it in ./.teamsapptesttool.yml, so no extra flags are needed.
set -euo pipefail

TOOL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$TOOL_DIR"

# Downloaded from the npm registry on first run (not Azure). Pinned to the CLI wrapper
# for the Agents Playground component.
exec npx --yes @microsoft/teams-app-test-tool@latest start
