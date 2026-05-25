# Agent control plane operating model

This document captures a safe, repeatable operating model for Hermes self-improvement work and local agent-control-plane changes.

## Scope

Use this model for changes that affect local agent orchestration, workflow retrieval, quality gates, skills, evals, or Hermes runtime behavior.

## Repository safety rule

- Do not develop directly inside a user's active working copy.
- Work from a dedicated clone under the Hermes workspace.
- Make changes on a named branch.
- Push the branch to the user's fork or staging remote.
- Let the user decide when to replace, pull, or merge the active working copy.

For Gurusharan's Hermes fork, the safe development clone is:

```text
/Users/gurusharan/Documents/Hermes-Agent-Workspace/repos/hermes-agent-ingpoc
```

## Branch workflow

1. Fetch the fork's main branch.
2. Create a focused branch from the fork main branch.
3. Keep each branch limited to one improvement theme.
4. Run the smallest relevant checks before committing.
5. Commit only reviewed, intentional diffs.
6. Push to the fork; do not open upstream PRs unless explicitly requested.

## Non-invasive first layer

Before runtime changes, add or maintain infrastructure that improves confidence:

- Documentation of the operating model and safety boundaries.
- Local self-audit checks that can run without credentials or network access.
- Quality-gate scripts that fail on unsafe assumptions and report actionable findings.
- Evaluation scaffolding for agent behavior, tool use, and workflow retrieval.

## Local self-audit checklist

A control-plane branch should answer these before runtime code changes:

- What user-facing behavior changes?
- What workspace or profile can be affected?
- Are credentials or secrets touched? If yes, are they stored in Keychain or a secret manager rather than plaintext?
- Can the change run offline for basic validation?
- Is there a small verification command for the touched surface?
- Does the diff avoid broad rewrites when a targeted change would work?
- Does the change preserve the user's active working copy until they explicitly update it?

## Agent behavior invariants

Agents working on this repo should preserve these invariants:

- Inspect before claiming code, files, commands, or APIs exist.
- Prefer actual checks over plans-only responses when tools can safely verify.
- Keep persistent memories compact and durable; do not store transient task progress.
- Do not save secrets in repository files.
- Do not use upstream-facing actions such as opening PRs or publishing releases without explicit user direction.

## Future eval targets

Useful evals for this control plane include:

- Workspace-isolation eval: agent refuses to edit the user's active working copy when a safe clone exists.
- Tool-discipline eval: agent uses tools immediately after saying it will inspect, test, or modify something.
- Ingestion eval: agent converts external docs into deduplicated, source-attributed workflow knowledge rather than dumping pages verbatim.
- Quality-gate eval: branch changes include a minimal check for the touched behavior.
