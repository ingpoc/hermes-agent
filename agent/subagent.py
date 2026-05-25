"""Typed subagent delegation — spawns isolated AIAgent instances for focused sub-tasks.

Four specializations are defined (explore / review / plan / execute).  Each has
a tightly-scoped system prompt and returns a compact summary as its sole output.
The main agent's conversation history receives only the summary — never the
subagent's full turn history — keeping the main context window near-constant
regardless of sub-task depth.

Inspired by the agentharness-audit P06 recommendation and Claude Code's
``Agent(subagent_type="Explore|Plan|code-reviewer")`` pattern.

Usage::

    from agent.subagent import spawn_subagent, spawn_subagents_parallel

    result = spawn_subagent("Map the auth module", agent_type="explore", parent_agent=agent)
    results = await spawn_subagents_parallel([
        {"task": "Explore auth/", "agent_type": "explore"},
        {"task": "Review token.py for XSS", "agent_type": "review"},
    ], parent_agent=agent)
"""

from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional
from uuid import uuid4

logger = logging.getLogger(__name__)

SubagentType = Literal["explore", "review", "plan", "execute"]

SUBAGENT_SYSTEM_PROMPTS: Dict[str, str] = {
    "explore": (
        "You are a read-only exploration agent. Your ONLY job is to map and describe "
        "the given codebase area or resource. You MUST NOT modify any files. "
        "Return a structured summary: key files, symbols, patterns, and architectural notes. "
        "One paragraph max per section. Return the summary only — no preamble."
    ),
    "review": (
        "You are a code-review agent. Review the provided code or output for correctness, "
        "security, and style issues. Return ONLY a findings list: each item must include "
        "issue description, severity (high/medium/low), file:line (if applicable), and "
        "suggested fix. No narrative. No praise. Findings only."
    ),
    "plan": (
        "You are a planning agent. Create an ordered implementation plan for the given task. "
        "Return numbered steps ONLY. Each step: action, file to modify, and acceptance criterion. "
        "No explanations. No conversational text. Steps only."
    ),
    "execute": (
        "You are an execution agent. Complete the given task using available tools. "
        "When done, return a structured result with exactly three sections: "
        "STATUS (done/blocked), FILES_CHANGED (list), SUMMARY (one paragraph). "
        "Do not include conversation history — result sections only."
    ),
}

_DEFAULT_MAX_TURNS = 20


def _create_worktree(cwd: Optional[str] = None) -> Optional[tuple]:
    """Create a temporary git worktree. Returns (path, branch) or None on failure."""
    try:
        work_dir = cwd or os.getcwd()
        probe = subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            cwd=work_dir,
            capture_output=True,
            timeout=10,
        )
        if probe.returncode != 0:
            logger.debug("worktree isolation skipped: not a git repo in %s", work_dir)
            return None

        branch = f"hermes-subagent-{uuid4().hex[:8]}"
        wt_path = Path(tempfile.mkdtemp(prefix="hermes-wt-"))
        subprocess.run(
            ["git", "worktree", "add", str(wt_path), "-b", branch],
            cwd=work_dir,
            check=True,
            capture_output=True,
            timeout=30,
        )
        logger.debug("worktree created: %s (branch %s)", wt_path, branch)
        return str(wt_path), branch
    except Exception as exc:
        logger.debug("worktree creation failed (running without isolation): %s", exc)
        return None


def _cleanup_worktree(wt_path: str, branch: str) -> None:
    """Remove a temporary git worktree and its branch."""
    try:
        subprocess.run(
            ["git", "worktree", "remove", "--force", wt_path],
            capture_output=True,
            timeout=30,
        )
    except Exception:
        pass
    try:
        subprocess.run(["git", "branch", "-D", branch], capture_output=True, timeout=10)
    except Exception:
        pass
    logger.debug("worktree cleaned up: %s", wt_path)


@dataclass
class SubagentResult:
    agent_type: SubagentType
    summary: str
    structured: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None

    @property
    def succeeded(self) -> bool:
        return self.error is None


def spawn_subagent(
    task: str,
    agent_type: SubagentType = "execute",
    context: str = "",
    model: Optional[str] = None,
    parent_agent: Any = None,
    max_turns: int = _DEFAULT_MAX_TURNS,
    worktree: bool = False,
) -> SubagentResult:
    """Spawn an isolated AIAgent for a focused sub-task.

    Returns a :class:`SubagentResult` containing only the summary — the
    subagent's full turn history is discarded after the run, keeping the
    main conversation window stable.

    Args:
        task: The task description for the subagent.
        agent_type: One of "explore", "review", "plan", "execute".
        context: Optional extra context prepended to the task prompt.
        model: Model override. Defaults to parent's model if parent_agent is provided.
        parent_agent: Optional parent AIAgent. Used to inherit provider/model/base_url.
        max_turns: Maximum iterations for the subagent (default 20).
        worktree: When True and agent_type is "execute", run in an isolated git
            worktree. The worktree is created before the run and removed after.
            Silently degrades to non-isolated if not in a git repo or git is absent.
    """
    try:
        from run_agent import AIAgent
    except ImportError as e:
        return SubagentResult(agent_type=agent_type, summary="", error=f"AIAgent import failed: {e}")

    system_prompt = SUBAGENT_SYSTEM_PROMPTS[agent_type]

    # Worktree isolation: only meaningful for execute-type tasks that modify files.
    wt_info = None
    if worktree and agent_type == "execute":
        wt_info = _create_worktree()

    wt_context = ""
    if wt_info:
        wt_path, _ = wt_info
        wt_context = f"You are running in an isolated git worktree at: {wt_path}\nOperate on files in that directory."

    full_context = "\n\n".join(filter(None, [context.strip(), wt_context]))
    prompt = f"{full_context}\n\nTask: {task}" if full_context else task

    # Inherit provider/model from parent when available
    _model = model
    _provider = None
    _base_url = None
    _api_key = None
    if parent_agent is not None:
        if _model is None:
            _model = getattr(parent_agent, "model", None)
        _provider = getattr(parent_agent, "provider", None)
        _base_url = getattr(parent_agent, "base_url", None)
        _api_key = getattr(parent_agent, "api_key", None)

    try:
        child = AIAgent(
            model=_model or "",
            provider=_provider,
            base_url=_base_url or "",
            api_key=_api_key or "",
            ephemeral_system_prompt=system_prompt,
            quiet_mode=True,
            max_iterations=max_turns,
            skip_memory=True,
            skip_context_files=True,
            load_soul_identity=False,
        )
        raw = child.chat(prompt)
        structured = _parse_structured_result(raw, agent_type)
        return SubagentResult(agent_type=agent_type, summary=raw, structured=structured)
    except Exception as exc:
        logger.error("spawn_subagent(%s) failed: %s", agent_type, exc)
        return SubagentResult(agent_type=agent_type, summary="", error=str(exc))
    finally:
        if wt_info:
            _cleanup_worktree(*wt_info)


async def spawn_subagents_parallel(
    tasks: List[Dict[str, Any]],
    parent_agent: Any = None,
) -> List[SubagentResult]:
    """Spawn multiple subagents concurrently and collect their results.

    Each dict in *tasks* is passed as keyword arguments to :func:`spawn_subagent`.
    Results are returned in the same order as the input list.

    Args:
        tasks: List of dicts with ``task`` (required) and optional
               ``agent_type``, ``context``, ``model``, ``max_turns``, ``worktree``.
        parent_agent: Optional parent AIAgent for credential/model inheritance.
    """
    async def _run(task_kwargs: Dict[str, Any]) -> SubagentResult:
        kw = dict(task_kwargs)
        kw.setdefault("parent_agent", parent_agent)
        return await asyncio.to_thread(spawn_subagent, **kw)

    return list(await asyncio.gather(*[_run(t) for t in tasks]))


def _parse_structured_result(raw: str, agent_type: SubagentType) -> Dict[str, Any]:
    """Extract structured fields from a subagent response where applicable."""
    if agent_type != "execute":
        return {}
    result: Dict[str, Any] = {}
    for key in ("STATUS", "FILES_CHANGED", "SUMMARY"):
        marker = f"{key}:"
        if marker in raw:
            start = raw.index(marker) + len(marker)
            next_markers = [f"{k}:" for k in ("STATUS", "FILES_CHANGED", "SUMMARY") if k != key and f"{k}:" in raw[start:]]
            if next_markers:
                end = raw.index(next_markers[0], start)
                result[key.lower()] = raw[start:end].strip()
            else:
                result[key.lower()] = raw[start:].strip()
    return result
