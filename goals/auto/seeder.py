# goals/auto/seeder.py
from datetime import datetime, timezone
from goals.model import Goal, Status, Priority

def seed_autogoals(store, ctx):
    UTC = timezone.utc
    now = datetime.now(UTC)

    # Example triggers (stub these to your data):
    interesting = ctx.get("memory").top_curiosities(limit=3) if ctx.get("memory") else []
    recent_failures = [g for g in store.list_goals(limit=50) if g.status == Status.FAILED]

    # 1) exploration_drive → research goal
    for item in interesting:
        title = f"Explore: {item.title}"
        if not store.find_goal_by_title_recent(title, days=2):
            g = Goal(
                id=f"g_auto_{now.strftime('%H%M%S')}_{item.id[:4]}",
                title=title,
                kind="research",
                spec={"topic": item.title, "why": item.reason, "tasks": ["literature_scan","design_small_experiment"]},
                status=Status.NEW,
                priority=Priority.NORMAL,
                created_by="orrin:auto",
            )
            store.upsert_goal(g)

    # 2) Failure → improvement goal
    if recent_failures:
        title = "Stability: investigate recent failures"
        if not store.find_goal_by_title_recent(title, days=1):
            g = Goal(
                id=f"g_auto_stability_{now.strftime('%H%M%S')}",
                title=title,
                kind="improvement",
                spec={"window": "24h", "tasks": ["aggregate_failures","rank_root_causes","propose_fixes"]},
                status=Status.NEW,
                priority=Priority.HIGH,
                created_by="orrin:auto",
            )
            store.upsert_goal(g)
