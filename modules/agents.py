"""
modules/agents.py
-----------------
Manages the Agent system.

Each agent has its own folder under data/agents/<name>/
containing:
  config.json  — name, schedule, prompt template, enabled state
  memory.json  — list of past outputs the agent has generated

Commands:
  /create agent1             → creates a new agent
  /scheduleadv agent1 ...    → sets the agent's scheduled prompt
  /agents                    → lists all agents
  /agentmemory agent1        → shows agent's recent memory
  /agenttoggle agent1        → enable/disable agent
"""

import json
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

SGT = ZoneInfo("Asia/Singapore")


AGENTS_DIR = Path("data/agents")


def _agent_path(name: str) -> Path:
    return AGENTS_DIR / name.lower()


def _config_path(name: str) -> Path:
    return _agent_path(name) / "config.json"


def _memory_path(name: str) -> Path:
    return _agent_path(name) / "memory.json"


# ── Agent creation ────────────────────────────────────────

def create_agent(name: str) -> dict | None:
    """
    Create a new agent with empty config and memory.
    Returns None if agent already exists.
    """
    path = _agent_path(name)
    if path.exists():
        return None  # already exists

    path.mkdir(parents=True, exist_ok=True)

    config = {
        "name":      name.lower(),
        "created":   datetime.now(SGT).isoformat(timespec="seconds"),
        "enabled":   True,
        "schedule":  None,   # "08:00"
        "frequency": None,   # "daily" or "weekly:mon"
        "task_name": None,
        "prompt":    None,   # raw prompt with **TAG** markers
        "last_run":  None,
    }

    memory = {"entries": []}

    _config_path(name).write_text(json.dumps(config, indent=2))
    _memory_path(name).write_text(json.dumps(memory, indent=2))

    return config


def agent_exists(name: str) -> bool:
    return _agent_path(name).exists()


# ── Agent config ──────────────────────────────────────────

def get_agent(name: str) -> dict | None:
    path = _config_path(name)
    if not path.exists():
        return None
    return json.loads(path.read_text())


def set_agent_schedule(
    name: str,
    schedule: str,
    frequency: str,
    task_name: str,
    prompt: str,
) -> dict | None:
    """
    Set or update the scheduled prompt for an agent.
    Returns updated config or None if agent not found.
    """
    config = get_agent(name)
    if not config:
        return None

    config["schedule"]  = schedule
    config["frequency"] = frequency
    config["task_name"] = task_name
    config["prompt"]    = prompt
    config["last_run"]  = None

    _config_path(name).write_text(json.dumps(config, indent=2))
    return config


def toggle_agent(name: str) -> bool | None:
    """Flip enabled state. Returns new state or None if not found."""
    config = get_agent(name)
    if not config:
        return None
    config["enabled"] = not config["enabled"]
    _config_path(name).write_text(json.dumps(config, indent=2))
    return config["enabled"]


def delete_agent(name: str) -> bool:
    """Delete an agent and all its data. Returns True if deleted, False if not found."""
    import shutil
    path = _agent_path(name)
    if not path.exists():
        return False
    shutil.rmtree(path)
    return True


def mark_agent_run(name: str) -> None:
    config = get_agent(name)
    if config:
        config["last_run"] = datetime.now(SGT).isoformat(timespec="seconds")
        _config_path(name).write_text(json.dumps(config, indent=2))


def list_agents() -> list[dict]:
    """Return config of all existing agents."""
    if not AGENTS_DIR.exists():
        return []
    agents = []
    for folder in AGENTS_DIR.iterdir():
        if folder.is_dir():
            config_file = folder / "config.json"
            if config_file.exists():
                agents.append(json.loads(config_file.read_text()))
    return agents


# ── Agent memory ──────────────────────────────────────────

def save_to_memory(name: str, content: str) -> None:
    """
    Save a new entry to the agent's memory file.
    Keeps last 50 entries to avoid the file growing too large.
    """
    path = _memory_path(name)
    if not path.exists():
        memory = {"entries": []}
    else:
        try:
            memory = json.loads(path.read_text())
        except Exception:
            memory = {"entries": []}

    memory["entries"].append({
        "date":    datetime.now(SGT).strftime("%Y-%m-%d %H:%M"),
        "content": content,
    })

    # Keep only last 50 entries
    memory["entries"] = memory["entries"][-50:]
    path.write_text(json.dumps(memory, indent=2))


def get_memory(name: str, limit: int = 5) -> list:
    """Return the most recent memory entries for an agent."""
    path = _memory_path(name)
    if not path.exists():
        return []
    try:
        memory = json.loads(path.read_text())
        return memory.get("entries", [])[-limit:]
    except Exception:
        return []


# ── Scheduler check ───────────────────────────────────────

def get_due_agents() -> list[dict]:
    """
    Return all enabled agents whose scheduled time has arrived.
    Called every minute by the scheduler.
    """
    now         = datetime.now(SGT)
    now_time    = now.strftime("%H:%M")
    now_weekday = now.strftime("%a").lower()
    today_date  = now.strftime("%Y-%m-%d")

    due = []
    for agent in list_agents():
        if not agent.get("enabled"):
            continue
        if not agent.get("schedule") or not agent.get("prompt"):
            continue
        if agent["schedule"] != now_time:
            continue

        # Check already ran today
        last_run = agent.get("last_run") or ""
        if last_run.startswith(today_date):
            continue

        freq = agent.get("frequency", "daily")
        if freq == "daily":
            due.append(agent)
        elif freq.startswith("weekly:"):
            if now_weekday == freq.split(":")[1]:
                due.append(agent)

    return due