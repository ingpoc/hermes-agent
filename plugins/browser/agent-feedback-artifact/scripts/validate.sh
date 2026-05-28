#!/usr/bin/env bash
set -euo pipefail

skill_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

node --check "$skill_dir/scripts/add-agent-feedback.mjs"
node --check "$skill_dir/scripts/remove-agent-feedback.mjs"
node --check "$skill_dir/scripts/artifact-feedback-server.mjs"
node --check "$skill_dir/scripts/agent-feedback-preflight.mjs"
node --check "$skill_dir/scripts/agent-feedback-closeout.mjs"
node --check "$skill_dir/scripts/agent-feedback-next.mjs"
node --check "$skill_dir/scripts/agent-feedback-details.mjs"
node --check "$skill_dir/scripts/agent-feedback-mark.mjs"
node --check "$skill_dir/scripts/agent-feedback-routing.mjs"
node --check "$skill_dir/scripts/agent-feedback-dispatch.mjs"
node --check "$skill_dir/scripts/test-agent-feedback-webhook-receiver.mjs"
node --check "$skill_dir/scripts/test-agent-feedback-auto-runtime.mjs"

# Skill structure validation (skip Codex-specific audit if not available)
if [ -f "$HOME/.codex/skills/create-skill/scripts/audit.py" ]; then
  python3 "$HOME/.codex/skills/create-skill/scripts/audit.py" "$skill_dir" --strict
fi
