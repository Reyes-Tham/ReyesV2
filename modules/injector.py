"""
modules/injector.py
-------------------
Handles the &&TAG&& injection system.
When a prompt contains &&TAGNAME&&, this module
replaces it with the actual data from that source.

Supported tags:
  &&STOCKWATCH&&  → live watchlist data with P&L
  &&TODOS&&       → current todo list
  &&agentX&&      → memory of a specific agent
"""

import re
from pathlib import Path


def resolve_tags(prompt: str) -> str:
    """
    Find all &&TAG&& patterns in a prompt and replace
    them with the actual data they reference.

    Args:
        prompt: The raw prompt string possibly containing &&TAG&& markers

    Returns:
        The prompt with all tags replaced with real data
    """
    # Find all &&TAG&& occurrences
    tags = re.findall(r"&&([A-Za-z0-9_]+)&&", prompt)

    for tag in tags:
        replacement = _resolve_single_tag(tag)
        prompt = prompt.replace(f"&&{tag}&&", replacement)

    return prompt


def _resolve_single_tag(tag: str) -> str:
    """
    Resolve one tag to its data string.
    Falls back to an empty string if data unavailable.
    """
    tag_upper = tag.upper()

    # ── STOCKWATCH → live portfolio data ──────────────────
    if tag_upper == "STOCKWATCH":
        try:
            from modules.watchlist import get_watchlist_text
            return get_watchlist_text()
        except Exception as e:
            return f"[STOCKWATCH data unavailable: {e}]"

    # ── TODOS → current todo list ──────────────────────────
    if tag_upper == "TODOS":
        try:
            from modules.reminders import list_todos
            todos = list_todos()
            if not todos:
                return "No pending todos."
            return "TODOS:\n" + "\n".join(f"- [{t['id']}] {t['task']}" for t in todos)
        except Exception as e:
            return f"[TODOS data unavailable: {e}]"

    # ── agent memory → reads another agent's memory file ──
    agent_memory_path = Path(f"data/agents/{tag.lower()}/memory.json")
    if agent_memory_path.exists():
        try:
            import json
            content = json.loads(agent_memory_path.read_text())
            entries = content.get("entries", [])
            if not entries:
                return f"[{tag} memory is empty]"
            # Return last 3 memory entries
            recent = entries[-3:]
            lines  = [f"MEMORY FROM {tag.upper()}:"]
            for e in recent:
                lines.append(f"[{e['date']}] {e['content']}")
            return "\n".join(lines)
        except Exception as e:
            return f"[{tag} memory unavailable: {e}]"

    return f"[Unknown tag: {tag}]"