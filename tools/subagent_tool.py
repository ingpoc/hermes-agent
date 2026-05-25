"""Subagent delegation tool — spawn typed AIAgent sub-tasks from the main agent.

Exposes ``spawn_subagent`` as a callable tool so the LLM can delegate
focused work to isolated agents without bloating the main conversation.
The main context receives only the summary; the subagent's full turn
history is discarded after the run.
"""

import json
import logging

logger = logging.getLogger(__name__)

_AGENT_TYPES = ["explore", "review", "plan", "execute"]

SPAWN_SUBAGENT_SCHEMA = {
    "name": "spawn_subagent",
    "description": (
        "Delegate a focused sub-task to an isolated agent of the given type. "
        "The main context receives only the summary — the subagent's full conversation "
        "history is discarded, keeping your context window stable.\n\n"
        "Agent types:\n"
        "  explore  — read-only codebase/resource mapping (returns structured summary)\n"
        "  review   — code review for correctness/security (returns findings list)\n"
        "  plan     — ordered implementation plan (returns numbered steps)\n"
        "  execute  — runs the task with tools (returns STATUS/FILES_CHANGED/SUMMARY)\n\n"
        "Use explore before execute to avoid hallucinating file paths. "
        "Use review after execute to validate output quality.\n\n"
        "For parallel dispatch, pass a 'tasks' list instead of a single 'task'. "
        "All tasks in the list run concurrently and results are returned in order. "
        "For execute-type tasks that modify files, set worktree=true to run in an "
        "isolated git worktree (requires a git repo in the current directory)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "task": {
                "type": "string",
                "description": "Clear, self-contained task description for the subagent. "
                               "Omit when using 'tasks' for parallel dispatch.",
            },
            "agent_type": {
                "type": "string",
                "enum": _AGENT_TYPES,
                "description": "Specialization of the subagent to spawn. Used with single 'task'.",
            },
            "context": {
                "type": "string",
                "description": "Optional extra context to prepend to the task (file paths, background).",
            },
            "tasks": {
                "type": "array",
                "description": "Parallel batch: list of tasks to dispatch concurrently. "
                               "Each item must have 'task' and 'agent_type'; 'context' is optional. "
                               "Mutually exclusive with the top-level 'task' field.",
                "items": {
                    "type": "object",
                    "required": ["task", "agent_type"],
                    "properties": {
                        "task": {"type": "string"},
                        "agent_type": {"type": "string", "enum": _AGENT_TYPES},
                        "context": {"type": "string"},
                    },
                },
            },
            "worktree": {
                "type": "boolean",
                "description": "When true, execute-type subagents run in an isolated git worktree. "
                               "The worktree is created before the run and removed after. "
                               "Requires a git repository in the current directory. "
                               "Ignored for non-execute agent types.",
            },
        },
        "required": [],
    },
}


def _result_to_payload(result) -> dict:
    payload = {"agent_type": result.agent_type, "summary": result.summary}
    if result.error:
        payload["error"] = result.error
    if result.structured:
        payload["structured"] = result.structured
    return payload


def _handle_spawn_subagent(args: dict, **kwargs) -> str:
    parent_agent = kwargs.get("agent")
    worktree = bool(args.get("worktree", False))

    # ── Parallel batch path ──────────────────────────────────────────────────
    tasks_list = args.get("tasks")
    if tasks_list is not None:
        if not isinstance(tasks_list, list) or not tasks_list:
            return json.dumps({"error": "'tasks' must be a non-empty list"})
        for item in tasks_list:
            if not isinstance(item, dict) or not item.get("task") or not item.get("agent_type"):
                return json.dumps({"error": "each task must have 'task' and 'agent_type'"})
            if item["agent_type"] not in _AGENT_TYPES:
                return json.dumps({"error": f"unknown agent_type: {item['agent_type']!r}"})
        try:
            import asyncio
            from agent.subagent import spawn_subagents_parallel
            task_dicts = [
                {
                    "task": t["task"],
                    "agent_type": t.get("agent_type", "execute"),
                    "context": t.get("context", ""),
                    "worktree": worktree and t.get("agent_type") == "execute",
                }
                for t in tasks_list
            ]
            results = asyncio.run(spawn_subagents_parallel(task_dicts, parent_agent))
            return json.dumps([_result_to_payload(r) for r in results], ensure_ascii=False)
        except Exception as exc:
            logger.error("spawn_subagents_parallel failed: %s", exc)
            return json.dumps({"error": str(exc)})

    # ── Single task path ────────────────────────────────────────────────────
    task = (args.get("task") or "").strip()
    agent_type = args.get("agent_type", "execute")
    context = (args.get("context") or "").strip()

    if not task:
        return json.dumps({"error": "either 'task' or 'tasks' is required"})
    if agent_type not in _AGENT_TYPES:
        return json.dumps({"error": f"unknown agent_type: {agent_type!r}"})

    try:
        from agent.subagent import spawn_subagent
        result = spawn_subagent(
            task=task,
            agent_type=agent_type,
            context=context,
            parent_agent=parent_agent,
            worktree=worktree and agent_type == "execute",
        )
        return json.dumps(_result_to_payload(result), ensure_ascii=False)
    except Exception as exc:
        logger.error("spawn_subagent tool failed: %s", exc)
        return json.dumps({"error": str(exc)})


from tools.registry import registry

registry.register(
    name="spawn_subagent",
    toolset="subagent",
    schema=SPAWN_SUBAGENT_SCHEMA,
    handler=_handle_spawn_subagent,
    emoji="🤖",
)
