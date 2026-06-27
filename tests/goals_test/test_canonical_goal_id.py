# Regression test for the canonical-ID contract (coherent goal self-history).
#
# Before this fix a single goal fragmented into THREE ids: the committed_goal /
# effect-ledger key ("intrinsic-<ts>"), the v2 record's freshly-minted id (the
# discarded create_goal return), and the v1 tree node's id. Completion/failure
# events could then only TITLE-match the cognitive goal, so a goal that failed
# re-committed as a look-alike and Orrin could not maintain a coherent history of
# his own goals across the v1/v2 layers.
#
# The contract: one id is minted at commit, stamped onto the source proposal
# immediately, ADOPTED by v2 (idempotently), and carried onto the v1 tree node.

from typing import Any, Dict, List

from goals.api import GoalsAPI


class _DictStore:
    """Minimal duck-typed store (upsert/get/iter) for GoalsAPI."""
    def __init__(self) -> None:
        self._g: Dict[str, Any] = {}

    def upsert_goal(self, goal: Any) -> None:
        self._g[goal.id] = goal

    def get_goal(self, gid: str) -> Any:
        return self._g.get(gid)

    def iter_goals(self):
        return list(self._g.values())


def _api() -> GoalsAPI:
    # plan_on_create=False: no daemon, no side effects on create.
    return GoalsAPI(_DictStore(), plan_on_create=False)


# ── create_goal: adopt the caller id, idempotently ──────────────────────────────

def test_create_goal_adopts_caller_id():
    api = _api()
    g = api.create_goal(title="Understand emergence", kind="generic", id="intrinsic-123")
    assert g.id == "intrinsic-123", "v2 must adopt the cognitive layer's id, not mint its own"


def test_create_goal_mints_when_no_id():
    api = _api()
    g = api.create_goal(title="Untitled", kind="generic")
    assert g.id and g.id != "", "absent caller id → v2 mints a single id"


def test_create_goal_id_adoption_is_idempotent():
    """Re-syncing the same proposal returns the live goal, not a reset duplicate."""
    api = _api()
    first = api.create_goal(title="Understand emergence", kind="generic", id="intrinsic-123")
    # Mutate status so we can prove the second call did NOT clobber it back to NEW.
    api.update_goal(first.id, status=first.status)
    second = api.create_goal(title="Understand emergence (re-proposed)", kind="generic",
                             id="intrinsic-123")
    assert second.id == first.id
    assert second is not None
    # Exactly one record exists under that id.
    assert sum(1 for x in api.list_goals(limit=50) if x.id == "intrinsic-123") == 1


# ── _build_committed_goal: stamp the source proposal in place ───────────────────

def test_committed_goal_stamps_source_proposal():
    from brain.cognition.intrinsic_goals import _build_committed_goal
    proposal: Dict[str, Any] = {"title": "Understand emergence", "driven_by": "will"}
    cg = _build_committed_goal(proposal, "intrinsic-xyz")
    # The committed goal and the SOURCE proposal now share one id.
    assert cg["id"] == "intrinsic-xyz"
    assert proposal["id"] == "intrinsic-xyz", "source proposal must be stamped in place"


def test_committed_goal_reuses_existing_proposal_id():
    from brain.cognition.intrinsic_goals import _build_committed_goal
    proposal = {"title": "X", "id": "already-here"}
    cg = _build_committed_goal(proposal, "intrinsic-new")
    assert cg["id"] == "already-here", "a re-commit must not fork a new id"
    assert proposal["id"] == "already-here"


# ── End-to-end: committed-goal id == synced v2 id (no fragmentation) ────────────

class _FakeGoal:
    def __init__(self, gid: str, title: str) -> None:
        self.id, self.title = gid, title


class _FakeApi:
    """Captures create_goal so we can assert the id that v2 receives."""
    def __init__(self) -> None:
        self.created: List[Dict[str, Any]] = []
        self._by_title: Dict[str, str] = {}

    def list_goals(self, limit: int = 500):
        return [_FakeGoal(gid, t) for t, gid in self._by_title.items()]

    def create_goal(self, *, title, kind, spec=None, priority="NORMAL", tags=None, id=None):
        gid = id or "g_minted"
        self.created.append({"title": title, "id": gid})
        self._by_title[title] = gid
        return _FakeGoal(gid, title)


def test_sync_passes_committed_id_to_v2():
    """A committed proposal syncs to v2 under ITS id — the single thread holds."""
    import brain.goal_io as goal_io
    api = _FakeApi()
    # Proposal as it exists post-commit: source node already stamped with canonical id.
    proposal = {"title": "Write a synthesis", "kind": "generic",
                "id": "intrinsic-2026", "milestones": [{"name": "draft"}]}
    ctx = {"proposed_goals": [proposal]}
    goal_io.sync_proposed_goals(api, ctx)
    assert api.created and api.created[0]["id"] == "intrinsic-2026", \
        "v2 must adopt the committed goal's id, not mint a rival"
    assert proposal["id"] == "intrinsic-2026"


def test_sync_stamps_id_when_proposal_uncommitted():
    """A never-committed proposal (no id) gets v2's minted id written back onto it."""
    import brain.goal_io as goal_io
    api = _FakeApi()
    proposal = {"title": "Research X", "kind": "generic", "milestones": [{"name": "m"}]}
    ctx = {"proposed_goals": [proposal]}
    goal_io.sync_proposed_goals(api, ctx)
    assert proposal.get("id") == "g_minted", "minted v2 id must be stamped back onto source"


def test_sync_dedup_adopts_existing_v2_id():
    """A proposal whose title already lives in v2 adopts that goal's id (no fork)."""
    import brain.goal_io as goal_io
    api = _FakeApi()
    api._by_title["Research X"] = "g_existing"
    proposal = {"title": "Research X", "kind": "generic", "milestones": [{"name": "m"}]}
    ctx = {"proposed_goals": [proposal]}
    goal_io.sync_proposed_goals(api, ctx)
    assert proposal.get("id") == "g_existing"
    assert not api.created, "must not create a duplicate v2 record"
