# utils/goals_feed.py
# Goals store/API wiring + JSON encoder/provider for the goals dashboard

from __future__ import annotations
from pathlib import Path
from dataclasses import asdict, is_dataclass
from typing import Tuple, List, Dict, Any

from goals.store import FileGoalsStore
from goals.api import GoalsAPI
from goals.model import Goal

def init_goals(data_dir: Path) -> Tuple[FileGoalsStore, GoalsAPI]:
    data_dir.mkdir(parents=True, exist_ok=True)
    store = FileGoalsStore(data_dir=data_dir)
    api = GoalsAPI(store=store)
    return store, api

def goal_to_jsonable(g: Goal) -> Dict[str, Any]:
    d = g.__dict__.copy()
    d["status"] = getattr(g.status, "name", str(g.status))
    d["priority"] = getattr(g.priority, "name", str(g.priority))
    if d.get("deadline"):    d["deadline"]    = g.deadline.isoformat()
    if d.get("created_at"):  d["created_at"]  = g.created_at.isoformat()
    if d.get("updated_at"):  d["updated_at"]  = g.updated_at.isoformat()
    pr = d.get("progress")
    if is_dataclass(pr):
        d["progress"] = asdict(pr)
    if d.get("acceptance") is not None:
        d["acceptance"] = dict(d["acceptance"])
    if d.get("spec") is not None:
        d["spec"] = dict(d["spec"])
    return d

def build_goals_provider(api: GoalsAPI):
    def provider() -> List[Dict[str, Any]]:
        goals = api.list_goals()
        return [goal_to_jsonable(g) for g in goals]
    return provider
