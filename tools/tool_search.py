"""Tool search — on-demand schema discovery for registered tools.

Deferred-loading contract
-------------------------
At startup, only ``ALWAYS_LOADED_TOOLS`` (defined in ``tools/registry.py``)
are injected into the API ``tools`` parameter.  All other registered tools
are *deferred* — they are known to the registry but their schemas are not
sent on every turn.  The startup banner prints ``+N deferred, use
tool_search to discover`` to show how many tools are held back.

To use a deferred tool:

1. **Discover** — call ``tool_search(query="<keyword>")`` to find tools by
   name or description.  An empty query lists every registered tool.

2. **Fetch schema** — call ``tool_search(query="__schema__:<tool_name>")``
   to get the full JSON schema for a specific tool before calling it.

This keeps cold-session context small (name + one-line desc only for deferred
tools) while making every registered tool accessible on demand.
"""

import json
import logging

logger = logging.getLogger(__name__)


def tool_search(query: str) -> str:
    """Discover registered tools matching a query, or fetch a specific schema.

    - Regular query: returns name + description for all tools containing the
      query in their name or description.
    - Empty query ``''``: returns all tool names + descriptions.
    - ``'__schema__:<name>'``: returns the full JSON schema for the named tool.
    """
    from tools.registry import registry

    query = (query or "").strip()

    # Full-schema fetch for a specific tool
    if query.startswith("__schema__:"):
        name = query[len("__schema__:"):]
        schema = registry.get_schema(name)
        if schema is None:
            return json.dumps({"error": f"Tool '{name}' not found in registry."})
        return json.dumps({"name": name, "schema": schema}, indent=2)

    # Discovery: return name + description for all matching tools
    q_lower = query.lower()
    matches = []
    for tool_name in registry.get_all_tool_names():
        schema = registry.get_schema(tool_name)
        if schema is None:
            continue
        desc = schema.get("description", "")
        if not q_lower or q_lower in tool_name.lower() or q_lower in desc.lower():
            matches.append({"name": tool_name, "description": desc})

    if not matches:
        return json.dumps({"results": [], "message": f"No tools found matching: {query!r}"})

    return json.dumps({"results": matches}, indent=2)


TOOL_SEARCH_SCHEMA = {
    "name": "tool_search",
    "description": (
        "Discover available tools by name or description. "
        "Pass an empty string to list all tools. "
        "Pass '__schema__:<tool_name>' to retrieve the full JSON schema for a specific tool. "
        "Use this when you need a tool that may not be in your default set."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": (
                    "Search query to filter tools by name/description, "
                    "empty string to list all, or '__schema__:<name>' for a full schema."
                ),
            }
        },
        "required": ["query"],
    },
}

from tools.registry import registry

registry.register(
    name="tool_search",
    toolset="docs",
    schema=TOOL_SEARCH_SCHEMA,
    handler=lambda args, **_kw: tool_search(args.get("query", "")),
    emoji="🔍",
)
