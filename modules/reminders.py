import json
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

SGT = ZoneInfo("Asia/Singapore")

DATA_FILE = "data/bot_data.json"

def _load():
    path = Path(DATA_FILE)
    if not path.exists():
        return {"todos": [], "reminders": []}
    
    try:
        with open(path) as f:
            content = f.read().strip()
            if not content:  # file exists but is empty
                return {"todos": [], "reminders": []}
            return json.loads(content)
    except json.JSONDecodeError:
        return {"todos": [], "reminders": []}

def _save(data):
    path = Path(DATA_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

def _purge_and_renumber(data: dict) -> None:
    """Remove completed todos and reassign sequential IDs from 1."""
    active = [t for t in data["todos"] if not t["done"]]
    for i, t in enumerate(active, start=1):
        t["id"] = i
    data["todos"] = active

def add_todo(task: str) -> dict:
    data = _load()
    new_id = max((t["id"] for t in data["todos"]), default=0) + 1
    item = {"id": new_id, "task": task, "done": False}
    data["todos"].append(item)
    _save(data)
    return item

def list_todos() -> list:
    return [t for t in _load()["todos"] if not t["done"]]

def complete_todo(todo_id: int) -> bool:
    data = _load()
    for item in data["todos"]:
        if item["id"] == todo_id:
            item["done"] = True
            _purge_and_renumber(data)
            _save(data)
            return True
    return False

def complete_todos_bulk(ids: list[int]) -> tuple[list[int], list[int]]:
    """Mark multiple todos done in one save. Returns (completed, not_found)."""
    data = _load()
    id_set = set(ids)
    completed = []
    for item in data["todos"]:
        if item["id"] in id_set:
            item["done"] = True
            completed.append(item["id"])
    not_found = [i for i in ids if i not in completed]
    _purge_and_renumber(data)
    _save(data)
    return completed, not_found

#Scheduled Prompts

def add_scheduled_prompt(name: str, prompt: str, schedule: str, frequency: str) -> dict | None:
    try:
        datetime.strptime(schedule, "%H:%M")
    except ValueError:
        return None

    data = _load()

    # create the scheduled_prompts list if it doesn't exist yet
    if "scheduled_prompts" not in data:
        data["scheduled_prompts"] = []

    new_id = max((p["id"] for p in data["scheduled_prompts"]), default=0) + 1

    item = {
        "id":        new_id,
        "name":      name,
        "prompt":    prompt,
        "schedule":  schedule,  
        "frequency": frequency,  
        "enabled":   True,
        "last_run":  None,
        "created":   datetime.now(SGT).isoformat(timespec="seconds"),
    }

    data["scheduled_prompts"].append(item)
    _save(data)
    return item


def list_scheduled_prompts() -> list:
    """Return all scheduled prompts."""
    data = _load()
    return data.get("scheduled_prompts", [])


def toggle_scheduled_prompt(prompt_id: int) -> bool | None:
    """
    Enable or disable a scheduled prompt by ID.
    Returns the new enabled state, or None if not found.
    """
    data = _load()
    for p in data.get("scheduled_prompts", []):
        if p["id"] == prompt_id:
            p["enabled"] = not p["enabled"]
            _save(data)
            return p["enabled"]
    return None


def delete_scheduled_prompt(prompt_id: int) -> bool:
    """Delete a scheduled prompt by ID."""
    data = _load()
    before = len(data.get("scheduled_prompts", []))
    data["scheduled_prompts"] = [
        p for p in data.get("scheduled_prompts", [])
        if p["id"] != prompt_id
    ]
    if len(data["scheduled_prompts"]) < before:
        _save(data)
        return True
    return False


def mark_prompt_run(prompt_id: int) -> None:
    """Update the last_run timestamp after a prompt fires."""
    data = _load()
    for p in data.get("scheduled_prompts", []):
        if p["id"] == prompt_id:
            p["last_run"] = datetime.now(SGT).isoformat(timespec="seconds")
    _save(data)


def get_due_prompts() -> list:
    """
    Return all enabled scheduled prompts that are due to run right now.
    Checks time and frequency (daily vs specific weekday).
    """
    now         = datetime.now(SGT)
    now_time    = now.strftime("%H:%M")
    now_weekday = now.strftime("%a").lower()
    today_date  = now.strftime("%Y-%m-%d")

    due = []
    for p in list_scheduled_prompts():
        if not p["enabled"]:
            continue
        if p["schedule"] != now_time:
            continue

        # Check if already ran today
        if p["last_run"] and p["last_run"].startswith(today_date):
            continue

        freq = p["frequency"]

        if freq == "daily":
            due.append(p)
        elif freq.startswith("weekly:"):
            target_day = freq.split(":")[1] 
            if now_weekday == target_day:
                due.append(p)

    return due