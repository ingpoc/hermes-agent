"""Docs search tool — full-text search over ~/.hermes/docs/ and ~/.hermes/skills/.

Allows the agent to locate relevant procedures, skill descriptions, and workflow
documentation without loading the entire docs directory into context upfront.
Follows the deferred-loading pattern from the agentharness-audit P02 recommendation.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List

from hermes_constants import get_hermes_home

logger = logging.getLogger(__name__)

_MAX_RESULTS = 5
_EXCERPT_CHARS = 300


def _get_excerpt(path: Path, query: str, *, chars: int = _EXCERPT_CHARS) -> str:
    """Return a short excerpt from *path* around the first match for *query*."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    lower = text.lower()
    idx = lower.find(query.lower())
    if idx == -1:
        return text[:chars]
    start = max(0, idx - 80)
    end = min(len(text), idx + chars - 80)
    snippet = text[start:end]
    if start > 0:
        snippet = "…" + snippet
    if end < len(text):
        snippet = snippet + "…"
    return snippet


def docs_search(query: str) -> str:
    """Search ~/.hermes/docs/ and ~/.hermes/skills/ for relevant procedures.

    Returns up to 5 results with file path and excerpt.
    """
    if not query or not query.strip():
        return json.dumps({"error": "query cannot be empty"})

    query = query.strip()
    hermes_home = get_hermes_home()
    search_dirs = [
        hermes_home / "docs",
        hermes_home / "skills",
    ]

    results: List[Dict[str, Any]] = []

    for search_dir in search_dirs:
        if not search_dir.exists():
            continue
        try:
            for md_path in sorted(search_dir.rglob("*.md")):
                if len(results) >= _MAX_RESULTS:
                    break
                try:
                    text = md_path.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                if query.lower() not in text.lower():
                    continue
                # Count occurrences as a relevance proxy
                count = text.lower().count(query.lower())
                results.append(
                    {
                        "path": str(md_path),
                        "hits": count,
                        "excerpt": _get_excerpt(md_path, query),
                    }
                )
        except (OSError, PermissionError) as e:
            logger.debug("docs_search scan error in %s: %s", search_dir, e)
        if len(results) >= _MAX_RESULTS:
            break

    if not results:
        return json.dumps({"results": [], "message": f"No docs found matching: {query!r}"})

    # Sort by hit count descending so most relevant results appear first
    results.sort(key=lambda r: r["hits"], reverse=True)
    return json.dumps({"results": results[:_MAX_RESULTS]}, indent=2)


DOCS_SEARCH_SCHEMA = {
    "name": "docs_search",
    "description": (
        "Search ~/.hermes/docs/ and ~/.hermes/skills/ for relevant procedures, "
        "skill descriptions, and workflow documentation. Use this before answering "
        "questions about how to perform tasks documented in your skill hub."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query — keywords or a short phrase to match against docs.",
            }
        },
        "required": ["query"],
    },
}

from tools.registry import registry

registry.register(
    name="docs_search",
    toolset="docs",
    schema=DOCS_SEARCH_SCHEMA,
    handler=lambda args, **kw: docs_search(args.get("query", "")),
    emoji="📖",
)
