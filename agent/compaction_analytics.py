"""Compaction analytics — per-event logging to ~/.hermes/compaction.jsonl.

Each context-compression event appends one JSON record. The log lets operators
diagnose why a session lost coherence (e.g. frequent 413 errors, oversized
tool outputs causing repeated compaction) and tune HERMES_MAX_TOOL_OUTPUT_TOKENS
or compaction thresholds accordingly.

Usage::

    from agent.compaction_analytics import CompactionEvent, log_compaction
    log_compaction(CompactionEvent(
        trigger="413_error",
        strategy="summarize_middle",
        tokens_before=80000,
        tokens_after=40000,
        messages_before=120,
        messages_after=60,
    ))
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Literal

logger = logging.getLogger(__name__)

CompactionTrigger = Literal["413_error", "pre_turn", "manual", "context_limit"]
CompactionStrategy = Literal["summarize_middle", "drop_oldest", "summarize_all", "unknown"]


@dataclass
class CompactionEvent:
    trigger: CompactionTrigger
    strategy: CompactionStrategy
    tokens_before: int
    tokens_after: int
    messages_before: int
    messages_after: int
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    session_id: str = ""
    model: str = ""
    notes: str = ""

    @property
    def reduction_pct(self) -> float:
        if self.tokens_before == 0:
            return 0.0
        return round(100.0 * (1 - self.tokens_after / self.tokens_before), 1)


def log_compaction(event: CompactionEvent) -> None:
    """Append *event* as a JSONL record to ~/.hermes/compaction.jsonl."""
    try:
        from hermes_constants import get_compaction_log_path
        log_path = get_compaction_log_path()
        log_path.parent.mkdir(parents=True, exist_ok=True)
        record = asdict(event)
        record["reduction_pct"] = event.reduction_pct
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
    except Exception as exc:
        logger.debug("compaction log write failed (non-fatal): %s", exc)
