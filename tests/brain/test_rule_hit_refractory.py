# R10-10: a rule's `hits` is its evidence count. apply() fires on every match,
# but the working-memory churn re-matched one rule ~6x/cycle (66,087 hits at conf
# 0.98 on no new evidence). One reinforcement per rule per cycle restores
# "hits == evidence".

import brain.symbolic.rule_engine as re_mod
from brain.paths import CYCLE_COUNT_FILE
from brain.utils.json_utils import save_json


def _set_cycle(n: int) -> None:
    save_json(CYCLE_COUNT_FILE, {"count": n})


def test_repeat_apply_within_a_cycle_banks_one_hit():
    re_mod._last_hit_cycle.clear()
    _set_cycle(42)
    rule = {"id": "r_test", "conclusion": "avoid the goal", "hits": 0}
    for _ in range(6):
        assert re_mod.apply(rule, log=False) == "avoid the goal"
    assert rule["hits"] == 1, "six matches in one cycle = one reinforcement"


def test_next_cycle_banks_a_new_hit():
    re_mod._last_hit_cycle.clear()
    rule = {"id": "r_test2", "conclusion": "c", "hits": 0}
    _set_cycle(1)
    re_mod.apply(rule, log=False)
    re_mod.apply(rule, log=False)
    _set_cycle(2)
    re_mod.apply(rule, log=False)
    assert rule["hits"] == 2, "one hit per distinct cycle"


def test_unknown_cycle_disables_refractory():
    re_mod._last_hit_cycle.clear()
    _set_cycle(0)   # no live loop → count == 0
    rule = {"id": "r_test3", "conclusion": "c", "hits": 0}
    re_mod.apply(rule, log=False)
    re_mod.apply(rule, log=False)
    assert rule["hits"] == 2, "with no cycle clock, counting still works"
