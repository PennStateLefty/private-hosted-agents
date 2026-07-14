#!/usr/bin/env bash
# Start the Microsoft 365 Agents Playground (formerly "Teams App Test Tool") and point
# it at the LOCAL bot host started by ./run-bot.sh. Opens a web chat UI in the browser;
# no M365 tenant, license, Azure Bot registration, or tunnel is required.
#
# The Playground uses built-in mock data by default (no config file needed). We pin the
# bot endpoint and channel via the documented, version-stable env vars so the run is
# unambiguous:
#   - BOT_ENDPOINT       -> where the Playground POSTs inbound Activities (our host).
#   - DEFAULT_CHANNEL_ID -> "msteams" so Teams-specific activities (membersAdded /
#                           conversationUpdate, which drive our proactive intake card)
#                           are available in the "Mock an Activity" menu.
#
# If you ever need to customize the mock Teams context (users, team, chats), create a
# ".m365agentsplayground.yml" here using the CURRENT schema documented at
# https://aka.ms/teams-app-test-tool-config-guide (root tenantId + bot + exactly five
# users). It is optional and intentionally omitted. NOTE: the old ".teamsapptesttool.yml"
# schema (version: v1.0 / config.botEndpoint) is rejected by the current CLI.
set -euo pipefail

TOOL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$TOOL_DIR"

export BOT_ENDPOINT="${BOT_ENDPOINT:-http://localhost:3978/api/messages}"
export DEFAULT_CHANNEL_ID="${DEFAULT_CHANNEL_ID:-msteams}"

echo "Agents Playground → bot endpoint ${BOT_ENDPOINT} (channel ${DEFAULT_CHANNEL_ID})"
echo "(LOCAL TEST ONLY — never deployed; see ./README.md and ../../KNOWN-ISSUES.md #1)"

# Downloaded from the npm registry on first run (not Azure). The teams-app-test-tool
# package now ships the Agents Playground engine; its CLI entrypoint is `teamsapptester
# start` (a.k.a. `agentsplayground start`).
exec npx --yes @microsoft/teams-app-test-tool@latest start
