"""Small, read-only research probes. No Orrin imports, processes, or network.

Compiles selected source function definitions with in-memory dependency stubs.
This verifies local semantics, not a live Orrin run or end-to-end performance.
Also streams archived ZIPs and independently recomputes telemetry statistics.
"""
import ast
import copy
import hashlib
import json
import statistics
import zipfile
from collections import Counter
from pathlib import Path

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
RUNS = ROOT / 'docs/Behavioral Evaluation & Runtime Diagnostics/demo_runs'
hashes = {}


def source_functions(relative, names, namespace):
    path = ROOT / relative
    raw = path.read_bytes()
    hashes[relative] = hashlib.sha256(raw).hexdigest()
    tree = ast.parse(raw)
    selected = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
    assert len(selected) == len(names)
    module = ast.Module(body=selected, type_ignores=[])
    exec(compile(module, str(path), 'exec'), namespace)
    return namespace


def signal_probe():
    state = {'drive': {'historically_good': .5, 'historically_bad': .5}}
    ns = {'SIGNAL_FUNCTION_MAP_FILE': 'stub', 'MAX_ASSOCIATIONS_PER_EMOTION': 5,
          'MIN_REINFORCEMENT_THRESHOLD': 2, 'DECAY_RATE': .05, '_COUPLING_CAP': .5,
          'load_json': lambda *a, **k: copy.deepcopy(state),
          'save_json': lambda p, d: (state.clear(), state.update(copy.deepcopy(d))),
          'record_failure': lambda *a: None}
    source_functions('brain/control_signals/signal_learning.py',
                     {'update_signal_function_map', '_bound_coupling_shares'}, ns)
    before = copy.deepcopy(state)
    negative = ns['update_signal_function_map']('drive', 'failed_action', -1)
    after = copy.deepcopy(state)
    zero = ns['update_signal_function_map']('drive', 'next_action', 0)
    return {'before': before, 'negative_reward_result': negative,
            'state_after_negative': after, 'next_zero_reward_result': zero}


def verifier_probe():
    from typing import Dict, Optional, List
    # The optional imported pattern-scorer call is intentionally blocked; only
    # outcome matching / confidence-update requests are under examination.
    def no_import(*args, **kwargs):
        raise ImportError('Orrin imports disabled for isolated research probe')
    builtins_dict = dict(vars(__import__('builtins')))
    builtins_dict['__import__'] = no_import
    updates = []
    entry = {'rule_id': 'old_rule', 'query_hash': 'old_query', 'outcome': None}
    ns = {'Dict': Dict, 'Optional': Optional, 'List': List, '__builtins__': builtins_dict,
          '_read_wal_recent': lambda: [copy.deepcopy(entry)], '_query_hash': lambda q: q,
          '_REWARD': .025, '_PENALTY': -.04,
          '_adjust_confidence': lambda *args: updates.append(args[:3]),
          'record_failure': lambda *args: None}
    source_functions('brain/symbolic/rule_verifier.py', {'apply_outcome'}, ns)
    first = ns['apply_outcome'](.8, query='unrelated_query')
    second = ns['apply_outcome'](.8, query='another_unrelated_query')
    return {'first': first, 'second': second, 'update_requests': updates,
            'note': 'Dependency-stubbed matching probe; source separately inspected for WAL consumption.'}


def goal_reward_probe():
    from typing import Dict, Any
    ns = {'Dict': Dict, 'Any': Any, 'bound_goal': lambda ctx: ctx.get('committed_goal'),
          '_W_ACTION_TAKEN': .4, '_W_PURSUIT_FN': .3, '_W_GOAL_IN_WM': .1,
          '_W_STALL_PENALTY': .2, '_STALL_THRESHOLD': 3, '_BASE_SCORE': .5}
    source_functions('brain/cognition/planning/goal_progress.py',
                     {'compute_goal_progress', 'goal_weighted_reward'}, ns)
    ctx = {'committed_goal': {'id': 'g', 'title': 'Solve unseen task'}, 'working_memory': [], 'action_debt': 0}
    return {'ordinary_nonfailure_no_evidence_gp': ns['compute_goal_progress'](ctx, True, 'unrelated_cognition'),
            'ordinary_nonfailure_base_032': ns['goal_weighted_reward'](.32, ctx, True, 'unrelated_cognition'),
            'failure_base_minus_01': ns['goal_weighted_reward'](-.1, ctx, False, 'failed_cognition'),
            'note': 'Goal-weighting stage only; final shaping and explicit-noop override may alter these numbers.'}


def telemetry_probe():
    from typing import Dict, List, Any, Tuple, Optional
    ns = {'Dict': Dict, 'List': List, 'Any': Any, 'Tuple': Tuple, 'Optional': Optional,
          'statistics': statistics, 'MAX_GAP_S': 120.0}
    source_functions('goals/handlers/characterize.py', {'driver_stats'}, ns)
    r = RUNS / '2026-10-06-run'
    p = r / 'data/resource_history.jsonl'
    hashes[str(p.relative_to(ROOT))] = hashlib.sha256(p.read_bytes()).hexdigest()
    rows = [json.loads(l) for l in p.read_text().splitlines() if l.strip()]
    out = []
    for p in sorted((r/'goals_daemon/goals/artifacts').glob('*/claims.json')):
        d = json.loads(p.read_text()); pred = d.get('prediction')
        if not pred:
            continue
        hashes[str(p.relative_to(ROOT))] = hashlib.sha256(p.read_bytes()).hexdigest()
        metric = pred['checkable_against'].split(':')[1]
        cutoff = pred['made_at_ts']; driver = pred['driver']
        train = [x for x in rows if x['ts'] <= cutoff]
        fresh = [x for x in rows if x['ts'] > cutoff]
        stats, base = ns['driver_stats'](train, metric, 30)
        record = {'id': p.parent.name, 'prediction': pred, 'train_rows_available': len(train),
                  'train_driver_recomputed': stats.get(driver), 'train_baseline_recomputed': base,
                  'fresh_rows_available': len(fresh)}
        # Locate a fresh prefix with exactly the archived test statistics. This
        # independently verifies existence of the disjoint sample, not its exact
        # wall-clock check instant (claims do not store that instant).
        target = pred.get('test')
        if target:
            matches = []
            for end in range(2, len(fresh)+1):
                if fresh[end-1].get('last_fn') == driver:
                    s, b = ns['driver_stats'](fresh[:end], metric, 10)
                    if driver in s and s[driver][0] > target['n']:
                        break
                # At most ~a few hundred rows for the two archived tests.
                s, b = ns['driver_stats'](fresh[:end], metric, 10)
                if driver in s and s[driver][0] == target['n'] and round(s[driver][1],4) == target['mean'] and round(b,4) == target['base']:
                    matches.append({'prefix_rows': end, 'last_ts': fresh[end-1]['ts']})
            record['matching_fresh_prefixes'] = matches
        out.append(record)
    return out


def early_archives():
    out = {}
    for p in sorted(RUNS.glob('*/*.zip')):
        hashes[str(p.relative_to(ROOT))] = hashlib.sha256(p.read_bytes()).hexdigest()
        counts = Counter(); boots = []; hashes_seen = set(); duplicate_files = []
        with zipfile.ZipFile(p) as z:
            names = z.namelist()
            for n in names:
                if 'activity_log' not in n or not n.endswith('.txt'):
                    continue
                data = z.read(n)
                h = hashlib.sha256(data).hexdigest()
                if h in hashes_seen:
                    duplicate_files.append(n); continue
                hashes_seen.add(h)
                for line in data.decode(errors='replace').splitlines():
                    if 'Run stamp' in line:
                        boots.append(line)
                    for marker in ['[consciousness] ignited:', 'avoidance breaker', '[meta_rut]', 'mode changed', 'Mode switched']:
                        if marker in line: counts[marker] += 1
            d = {'log_message_counts': dict(counts), 'boot_stamps': boots,
                 'duplicate_log_files_skipped': duplicate_files,
                 'unique_activity_files': len(hashes_seen)}
            for basename in ['decision_stats.json', 'production_loop.jsonl']:
                target = 'brain/data/'+basename
                if target not in names: continue
                raw = z.read(target)
                if basename.endswith('jsonl'):
                    lines = [json.loads(l) for l in raw.splitlines() if l.strip()]
                    cycles = [r.get('cycle') for r in lines]
                    d['production'] = {'rows':len(lines), 'first':cycles[:1], 'last':cycles[-1:],
                                       'committed_counts':dict(Counter(r.get('committed_goal_id') for r in lines))}
                else:
                    stats=json.loads(raw)
                    d['decision_stats']={'recorded_count':sum(v.get('count',0) for v in stats.values()),
                                         'top':sorted(stats.items(),key=lambda kv:kv[1].get('count',0),reverse=True)[:8]}
            out[p.parent.name] = d
    return out


if __name__ == '__main__':
    result = {'signal_association': signal_probe(), 'rule_verifier': verifier_probe(), 'goal_reward': goal_reward_probe(),
              'characterize_telemetry': telemetry_probe(), 'early_archives': early_archives()}
    (OUT/'probe_results.json').write_text(json.dumps(result,indent=2)+'\n')
    (OUT/'probe_input_hashes.json').write_text(json.dumps(hashes,indent=2)+'\n')
    print(json.dumps(result,indent=2))
