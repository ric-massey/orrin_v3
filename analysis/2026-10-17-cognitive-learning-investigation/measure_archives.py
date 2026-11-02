"""Read-only archive measurements; standard library only, no Orrin imports.

Writes derived JSON only beside this script. Retained snapshots are explicitly
not interpreted as lifetime totals. Run from any directory with python3.
"""
from pathlib import Path
from collections import Counter
import gzip
import hashlib
import json
import re
import tarfile

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
RUNS = ROOT / "docs/Behavioral Evaluation & Runtime Diagnostics/demo_runs"
INPUTS = {}


def read(p):
    INPUTS[str(p.relative_to(ROOT))] = hashlib.sha256(p.read_bytes()).hexdigest()
    return gzip.open(p, "rt", errors="replace") if p.suffix == ".gz" else p.open(errors="replace")


def get(d, name, lines=False):
    p = d / name
    if not p.exists():
        p = d / (name + ".gz")
    if not p.exists():
        return None
    with read(p) as f:
        if not lines:
            return json.load(f)
        rows = []
        for n, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except ValueError:
                rows.append({"_parse_error_line": n})
        return rows


def counts(rows, field):
    return dict(Counter(str(r.get(field)) for r in rows if isinstance(r, dict)).most_common())


def flatten(rows):
    for r in rows:
        if isinstance(r, dict):
            yield r
            yield from flatten(r.get("subgoals") or [])


def measure(run):
    d = run / "data"
    out = {}
    prod = get(d, "production_loop.jsonl", True)
    if prod:
        cycles = [r["cycle"] for r in prod if isinstance(r.get("cycle"), int)]
        seams = [{"row": i + 1, "previous": a, "next": b}
                 for i, (a, b) in enumerate(zip(cycles, cycles[1:]), 1) if b != a + 1]
        out["production"] = {"rows": len(prod), "first_cycle": cycles[0], "last_cycle": cycles[-1],
                             "seams": seams, "committed_counts": counts(prod, "committed_goal_id"),
                             "true_totals": {k: sum(r.get(k) is True for r in prod)
                                             for k in ["production_attempt", "production_success", "goal_model_hydrated", "goal_lens_active"]}}
    effects = get(d, "effect_ledger.jsonl", True)
    if effects:
        reuse = [r for r in effects if r.get("kind") == "reuse"]
        out["effects"] = {"rows": len(effects), "kinds": counts(effects, "kind"),
                          "reuse_rows": len(reuse),
                          "reuse_with_citer": sum(bool((r.get("metadata") or {}).get("citing_goal_id")) for r in reuse),
                          "dedupe_true": sum(r.get("dedupe") is True for r in effects),
                          "positive_significance": sum(float(r.get("significance") or 0) > 0 for r in effects),
                          "most_common_paths": dict(Counter((r.get("metadata") or {}).get("path") for r in effects if (r.get("metadata") or {}).get("path")).most_common(5))}
    stats = get(d, "decision_stats.json")
    if stats:
        out["decision_stats"] = {"total_recorded": sum(r.get("count", 0) for r in stats.values()),
                                 "top": sorted(({"fn": k, **v} for k,v in stats.items()),key=lambda r:r.get("count",0),reverse=True)[:12]}
    for n in ["action_reward_ema.json", "calibration_state.json", "avoidance_breaker.json", "runtime_lifetime.json"]:
        x = get(d, n)
        if x is not None:
            out[n] = x
    wal = get(d, "evaluator_wal.jsonl", True)
    if wal:
        out["retained_evaluator"] = {"rows": len(wal), "resolution_counts": counts(wal, "resolved_by"),
                                     "min_cycle": min(r.get("cycle", 0) for r in wal),
                                     "max_cycle": max(r.get("cycle", 0) for r in wal)}
    answers = get(d, "answered_questions.json")
    if answers:
        out["answers"] = {"rows": len(answers), "cited_rows": sum(bool(r.get("cited")) for r in answers),
                          "citation_total": sum(r.get("cited",0) for r in answers), "records": answers}
    ladder = get(d, "growth_ladder.json")
    if ladder:
        h = ladder.get("history", [])
        out["ladder"] = {"rung": ladder.get("rung"), "history_rows": len(h), "kinds": counts(h,"kind"),
                         "unique_kind_ref": len({(r.get("kind"),r.get("ref")) for r in h}),
                         "refs": dict(Counter(r.get("ref") for r in h).most_common())}
    ltm = get(d, "long_memory.json")
    if isinstance(ltm, list):
        out["ltm"] = {"rows": len(ltm), "event_types": counts(ltm,"event_type"),
                      "self_log_marker_rows": sum(any(m in str(r.get("content", "")) for m in ["🧠 Chose:", "[metacog/", "[chunk", "[compaction"]) for r in ltm if isinstance(r,dict))}
    graph = get(d, "causal_graph.json")
    if isinstance(graph,list):
        out["causal_graph"] = {"rows":len(graph), "domains":counts(graph,"domain"), "sources":counts(graph,"source"),
                               "counterfactual_positive":sum(r.get("counterfactual_count",0)>0 for r in graph)}
    rules = get(d,"symbolic_rules.json")
    if isinstance(rules,list):
        out["rules"] = {"rows":len(rules), "top_hits":sorted(rules,key=lambda r:r.get("hits",0),reverse=True)[:3]}
    goals = get(d,"comp_goals.json")
    if isinstance(goals,list):
        flat=list(flatten(goals)); stamped=[g for g in flat if "answered" in g]
        out["brain_goal_snapshot"]={"rows":len(flat), "statuses":counts(flat,"status"), "answer_stamps":len(stamped),
                                    "answered_true":sum(g.get("answered") is True for g in stamped),
                                    "unique_answered_questions":len({g.get("question") for g in stamped if g.get("answered") is True})}
    truth = get(d, "ground_truth.jsonl", True)
    if truth is not None:
        out["retained_ground_truth"] = {"rows": len(truth), "nonempty_rule_id": sum(bool(r.get("rule_id")) for r in truth),
                                         "action_types": counts(truth, "action_type")}
    for name in ["signal_function_map.json", "function_chains.json", "self_improvement_log.json", "identity_belief_revisions.json", "rule_grounding.json"]:
        value = get(d, name)
        if value is not None:
            out[name] = value
    if effects:
        out["effects"]["attributable_reuse_path_types"] = dict(Counter(
            Path((r.get("metadata") or {}).get("path", "")).name
            for r in effects if r.get("kind") == "reuse" and (r.get("metadata") or {}).get("citing_goal_id")))
    claim_paths = list((run / "goals_daemon/goals/artifacts").glob("*/claims.json"))
    if claim_paths:
        predictions = []
        for p in claim_paths:
            with read(p) as f:
                claim = json.load(f)
            if claim.get("prediction"):
                predictions.append({"goal_id": p.parent.name, "prediction": claim["prediction"]})
        out["daemon_claim_files"] = {"files": len(claim_paths), "predictions": predictions}
    # Each available activity file exactly once; compressed tar members streamed,
    # never extracted. These are log-message counts, not necessarily cycle counts.
    logpaths = [p for p in run.rglob('*') if p.is_file() and (p.name.startswith('activity_log') or p.name=='rotated_logs.tar.gz')]
    boots=[]; ign=Counter(); executed=Counter(); llm_block=0; ending=Counter(); logs=[]
    def scan(lines, label):
        nonlocal llm_block
        logs.append(label)
        for line in lines:
            if isinstance(line,bytes):line=line.decode(errors='replace')
            if 'Run stamp' in line: boots.append({"source":label,"text":line.strip()})
            if '[ask_llm] Blocked' in line:llm_block+=1
            if '[consciousness] ignited:' in line:ign[line.split('[consciousness] ignited:',1)[1].strip()]+=1
            m=re.search(r'Executed: ([A-Za-z_][A-Za-z_0-9]*)',line)
            if m:executed[m.group(1)]+=1
            for marker in ['Runtime lifetime elapsed','HARD:memory','clean exit','shutdown complete','lifespan already elapsed','avoidance breaker','[meta_rut]']:
                if marker in line:ending[marker]+=1
    for p in sorted(logpaths):
        if p.name=='rotated_logs.tar.gz':
            INPUTS[str(p.relative_to(ROOT))]=hashlib.sha256(p.read_bytes()).hexdigest()
            with tarfile.open(p,'r:gz') as tf:
                for m in tf:
                    if m.isfile() and 'activity_log' in m.name:
                        with tf.extractfile(m) as f:scan(f,str(p.relative_to(ROOT))+':'+m.name)
        else:
            with read(p) as f:scan(f,str(p.relative_to(ROOT)))
    boots.sort(key=lambda row: row["text"])
    out['activity_logs']={'files':logs,'boot_stamps':boots,'ignition_reasons':dict(ign.most_common()),
                          'ignition_lines':sum(ign.values()),'llm_block_lines':llm_block,
                          'executed':dict(executed.most_common()),'markers':dict(ending)}
    return out


if __name__=='__main__':
    results={r.name:measure(r) for r in sorted(RUNS.iterdir()) if r.is_dir()}
    (OUT/'archive_measurements.json').write_text(json.dumps(results,indent=2)+'\n')
    (OUT/'input_hashes.json').write_text(json.dumps(INPUTS,indent=2)+'\n')
    for name,r in results.items():
        p=r.get('production',{}); occ=p.get('committed_counts',{})
        top=next(iter(occ.items()),('',0)); n=p.get('rows',0)
        print(name,'rows',n,'seams',len(p.get('seams',[])),'top',top,'share',round(top[1]/n,4) if n else None,
              'ignition',r['activity_logs']['ignition_lines'],'boots',len(r['activity_logs']['boot_stamps']))
