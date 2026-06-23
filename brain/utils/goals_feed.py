# utils/goals_feed.py
# Goals store/API wiring + JSON encoder/provider for the goals dashboard

from __future__ import annotations
from pathlib import Path
from typing import Tuple, List, Dict, Any

from goals.store import FileGoalsStore
from goals.api import GoalsAPI
# goal_to_jsonable lives on the model (canonical encoder), re-exported here so the
# dashboard's existing import path keeps working (structure audit §8).
from goals.model import goal_to_jsonable

def init_goals(data_dir: Path) -> Tuple[FileGoalsStore, GoalsAPI]:
    data_dir.mkdir(parents=True, exist_ok=True)
    store = FileGoalsStore(data_dir=data_dir)
    api = GoalsAPI(store=store)
    return store, api

def build_goals_provider(api: GoalsAPI):
    def provider() -> List[Dict[str, Any]]:
        goals = api.list_goals()
        return [goal_to_jsonable(g) for g in goals]
    return provider
