#!/usr/bin/env python3
"""
reset_orrin.py — wipe Orrin's runtime state for a clean (newborn) run.

Usage:
    python3 reset_orrin.py            # clear runtime state, keep config/knowledge
    python3 reset_orrin.py --hard     # also clear bandit/decision learning + self-written code
    python3 reset_orrin.py --dry-run  # print what would be cleared, don't touch files
    python3 reset_orrin.py --no-snapshot   # skip the built-in brain/data/*.json archive
    python3 reset_orrin.py --verify   # assertions only: is the tree actually newborn-clean?

What this clears (so a fresh run starts as a true newborn):
    • brain/data/*.json runtime state (memory, goals, drives, traces, etc.)
    • brain/data/*.jsonl + *.txt runtime streams (trace, events, memory_graph,
      private_thoughts, activity_log, run_log, …) — truncated to empty
    • brain/data/*.corrupt*.json salvage artifacts — deleted
    • brain/data/rotated/ + sandbox_tmp/ — emptied
    • brain/data/language/felt_experience.txt + narration_pairs.jsonl + book_reads.json
      — the native-LM experiential corpus, thought→narration pairs, and reading
      history (kept native_lm.pt — the trained model)
    • concepts.json + attention_value_weights.json — these LOOK like config but are
      actually run-learned/contaminated, so they are wiped, not kept
    • identity_state.json — stripped back to its seed (directive/identity/values/traits/
      roles); learned fields (knowledge_domains, weaknesses, recent_focus,
      identity_story, latent vector, …) reset so no prior-run self-narrative carries over
    • brain/logs/*.txt, *.log, *.jsonl — emptied
    • outbox/notes.json — emptied
    • root data/ tree — goals/ (state.jsonl, wal.log, artifacts, snapshots,
      wal-rotated), memory/wal/, media/, and runtime_state.json (né alive_brain_state.json)

What this KEEPS regardless (config/knowledge + trained artifacts):
    knowledge_base.json, model_config.json, cognitive_functions.json,
    behavioral_functions_list.json, capability_descriptions.json, meta_rules.json,
    symbolic_rules.json, vocabulary.json, vocab_weights.json, emotion/affect_model.json,
    brain/data/language/native_lm.pt (trained from-scratch LM),
    brain/data/self_code/**/__init__.py (package scaffolding the loader needs)

UNRECOGNIZED-FILE GUARD:
    After clearing, the script scans the data trees for any file it does NOT have an
    explicit rule for and prints a warning. When new state files appear in the codebase,
    this flags them so a future maintainer can decide whether reset should handle them
    (instead of silently leaving stale state behind). Always shown; in --dry-run too.

NOTE: the built-in snapshot only archives brain/data/*.json. For a full backup (jsonl,
txt, root data/, the LM), take an external copy (e.g. a zip) before resetting.
"""

import argparse
import json
import shutil
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "brain" / "data"
LOGS_DIR = ROOT / "brain" / "logs"
ROOT_DATA_DIR = ROOT / "data"
OUTBOX_NOTES = ROOT / "outbox" / "notes.json"
ARCHIVE_DIR = DATA_DIR / "_archive"

# Always kept — config and knowledge that takes effort to rebuild (boot-critical).
ALWAYS_KEEP = {
    "life_lineage.json",   # L3 §3d: the previous life's QUESTION survives (never the ambition)
    "knowledge_base.json",
    "model_config.json",
    "emotion_model.json",      # may also be present as affect_model.json after rename
    "affect_model.json",
    "meta_rules.json",
    "symbolic_rules.json",
    "behavioral_functions_list.json",
    "cognitive_functions.json",
    "capability_descriptions.json",   # curated fn→goal match manifest
    "vocabulary.json",
    "vocab_weights.json",
}

# Kept by default, cleared with --hard (learned bandit/decision state).
# habituation.json is NOT kept (Run-5 meter bug, RUN6_FIX_PLAN §4): 91 % of it
# survived the "clean" reset before Run 5, so exploration suppression carried a
# prior life into a newborn run — it's per-life satiety state, not learning.
SOFT_KEEP = {
    "bandit_state.json",
    "decision_stats.json",
    "depth_stats.json",
    "emotion_function_map.json",
    "intuition_patterns.json",
    "reward_trace.json",
    "reflection_stats.json",
}

# Trained/binary artifacts and package scaffolding: preserved as-is, never flagged.
# native_lm.pt = trained model; tokenizer.json = its paired vocab (wiping one without
# the other would mismatch), so both are kept together.
KEEP_ARTIFACT_NAMES = {"native_lm.pt", "tokenizer.json"}

# self_model.json gets a structured strip rather than a blanket wipe:
# keep the seed identity, reset everything the run accumulated.
SELF_MODEL_KEEP_FIELDS = ("core_directive", "identity", "core_values", "traits", "known_roles")
SELF_MODEL_RESET_FIELDS = {
    "recent_focus": [],
    "knowledge_domains": {},
    "weaknesses": [],
    "recent_changes": [],
    "symbolic_confidence": 0.5,
    "imaginative_threads": [],
    "latent_identity_vector": [],
    "identity_story": "",
}

# Files with specific default structures (everything else gets [] or {} by peeking).
DEFAULTS: dict = {
    "cycle_count.json":     {"count": 0},
    "world_model.json":     {"entities": {}, "relations": [], "facts": [], "events": [], "concepts": [], "forces": []},
    "world_model_stats.json": {},
    "health_state.json":    {"status": "nominal", "cycle": 0},
    "energy_mode.json":     {"mode": "normal", "level": 1.0},
    "mode.json":            {"current": "default"},
    "temporal_state.json":  {},
    "emotion_state.json":   {},
    "cognition_state.json": {},
    "context.json":         {},
    "last_active.json":     {},
    "lifespan.json":        {},
    "speaker_state.json":   {},
    "body_sense.json":      {},
    "bandit_state.json":    {},
    "decision_stats.json":  {},
    "depth_stats.json":     {},
    "emotion_function_map.json": {},
    "reflection_stats.json": {},
    # Previously "kept" but actually run-learned/contaminated — now always wiped:
    "concepts.json":              [],   # was a seed lexicon; fills with stuckness tokens
    "attention_value_weights.json": {}, # learned salience per source
    # List-typed state files. These MUST reset to [] regardless of the shape currently
    # on disk — a prior corruption to a dict is exactly what tripped the boot
    # "should be list, got dict" schema errors (run audit #4/#5). Peeking at the first
    # byte would faithfully re-emit the bad dict shape, so they are pinned here.
    "long_memory.json":     [],
    "working_memory.json":  [],
    "reflection_log.json":  [],
    "chat_log.json":        [],
}

# brain/data/language: native_lm.pt + tokenizer.json are kept (trained model + vocab);
# the rest is run-accumulated corpus/state and gets cleared.
LANGUAGE_EMPTY_FILE = {"felt_experience.txt", "replay_corpus.txt",
                       "narration_pairs.jsonl"}  # truncate to ""
LANGUAGE_DEFAULTS = {"book_reads.json": {}}      # reading history -> {}
LANGUAGE_CLEAR_DIRS = ("library",)               # downloaded reading material (recreated on demand)


def _write_json(path: Path, value, dry: bool) -> None:
    if dry:
        return
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(value, fh)


def _empty_file(path: Path, dry: bool) -> None:
    if dry:
        return
    path.write_text("", encoding="utf-8")


def _delete(path: Path, dry: bool) -> None:
    if dry:
        return
    try:
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
    except FileNotFoundError:
        pass


def _detect_default(path: Path):
    """Return the right empty value for a file by peeking at its current type."""
    if path.name in DEFAULTS:
        return DEFAULTS[path.name]
    try:
        with open(path, encoding="utf-8") as f:
            first = f.read(1).strip()
        return [] if first == "[" else {}
    except Exception:
        return {}


def _reset_self_model(path: Path, dry: bool) -> None:
    """Strip self_model.json to its seed identity; reset run-accumulated fields."""
    try:
        sm = json.load(open(path, encoding="utf-8")) if path.exists() else {}
    except Exception:
        sm = {}
    seed = {k: sm[k] for k in SELF_MODEL_KEEP_FIELDS if k in sm}
    seed.update(SELF_MODEL_RESET_FIELDS)
    if not dry:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(seed, fh, indent=2)


def snapshot(label: str = "") -> Path:
    """Archive current brain/data/*.json to a timestamped folder (json only)."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    name = f"snapshot_{ts}" + (f"_{label}" if label else "")
    dest = ARCHIVE_DIR / name
    dest.mkdir(parents=True, exist_ok=True)
    count = 0
    for f in DATA_DIR.glob("*.json"):
        shutil.copy2(f, dest / f.name)
        count += 1
    print(f"  Snapshot: {dest} ({count} json files)")
    print("  (built-in snapshot covers brain/data/*.json only — take an external"
          " full backup for jsonl/txt/root data/ + the LM)")
    return dest


def reset(hard: bool = False, dry_run: bool = False) -> list:
    keep = ALWAYS_KEEP | (set() if hard else SOFT_KEEP)
    tag = "DRY RUN — would clear" if dry_run else "Clearing"

    # ── 1. brain/data/*.json runtime state ───────────────────────────────────
    json_to_clear = [f for f in sorted(DATA_DIR.glob("*.json")) if f.name not in keep]
    print(f"\n[1] {tag} {len(json_to_clear)} brain/data/*.json files...")
    for f in json_to_clear:
        if f.name in ("identity_state.json", "self_model.json"):
            # AR9/O2: the model file was renamed self_model.json → identity_state.json
            # (paths.SELF_MODEL_FILE); the old name is matched too so a stale tree
            # still gets the structured strip instead of a blanket wipe.
            _reset_self_model(f, dry_run)
        elif f.name.endswith(".corrupt.json") or ".corrupt." in f.name:
            _delete(f, dry_run)          # salvage artifacts: delete outright
        else:
            _write_json(f, _detect_default(f), dry_run)

    # ── 2. brain/data non-json runtime streams ───────────────────────────────
    streams = sorted(DATA_DIR.glob("*.jsonl")) + sorted(DATA_DIR.glob("*.txt"))
    print(f"[2] {tag} {len(streams)} brain/data/*.jsonl + *.txt streams (emptied)...")
    for f in streams:
        _empty_file(f, dry_run)

    # ── 3. transient dirs: rotated/, sandbox_tmp/, effect_artifacts/, tracked_work/ ──
    # effect_artifacts/ (AR9/O2): captured artifact TEXT keyed by content hash —
    # run-produced state; leaving it made a "clean instance" carry prior-run work.
    # tracked_work/ holds compose_section manuscripts — prior-run output, same rule.
    for sub in ("rotated", "sandbox_tmp", "effect_artifacts", "tracked_work"):
        d = DATA_DIR / sub
        if d.exists():
            n = sum(1 for _ in d.glob("*"))
            print(f"[3] {tag} {n} files in brain/data/{sub}/")
            for p in d.glob("*"):
                _delete(p, dry_run)

    # ── 4. brain/data/language: keep native_lm.pt, clear corpus + reads ───────
    lang = DATA_DIR / "language"
    if lang.exists():
        print(f"[4] {tag} language run state (keep native_lm.pt)...")
        for name in LANGUAGE_EMPTY_FILE:
            p = lang / name
            if p.exists():
                _empty_file(p, dry_run)
        for name, default in LANGUAGE_DEFAULTS.items():
            p = lang / name
            if p.exists():
                _write_json(p, default, dry_run)
        for sub in LANGUAGE_CLEAR_DIRS:
            d = lang / sub
            if d.exists():
                files = [p for p in d.rglob("*") if p.is_file()]
                print(f"    {tag} {len(files)} files in language/{sub}/")
                for p in files:
                    _delete(p, dry_run)

    # ── 5. self-written code (only with --hard); always keep __init__.py ──────
    self_code = DATA_DIR / "self_code"
    if self_code.exists():
        written = [p for p in self_code.rglob("*.py") if p.name != "__init__.py"]
        if hard:
            print(f"[5] {tag} {len(written)} self-written modules in self_code/ (--hard)...")
            for p in written:
                _delete(p, dry_run)
        elif written:
            print(f"[5] keeping {len(written)} self_code/ modules (use --hard to clear)")

    # ── 6. brain/logs ────────────────────────────────────────────────────────
    if LOGS_DIR.exists():
        logs = (sorted(LOGS_DIR.glob("*.txt")) + sorted(LOGS_DIR.glob("*.log"))
                + sorted(LOGS_DIR.glob("*.jsonl")))
        print(f"[6] {tag} {len(logs)} brain/logs files (emptied)...")
        for f in logs:
            _empty_file(f, dry_run)

    # ── 7. outbox notes ──────────────────────────────────────────────────────
    if OUTBOX_NOTES.exists():
        print(f"[7] {tag} outbox/notes.json")
        _write_json(OUTBOX_NOTES, [], dry_run)

    # ── 8. root data/ tree: goals, memory, media + alive_brain_state ─────────
    print(f"[8] {tag} root data/ tree (goals, memory, media)...")
    for sub in ("goals", "memory", "media"):
        base = ROOT_DATA_DIR / sub
        if not base.exists():
            continue
        for p in base.rglob("*"):
            if not p.is_file():
                continue
            # Truncate the live WAL/stream files at a store root; delete archives/gz/snapshots.
            if p.parent == base and p.suffix in (".jsonl", ".log", ".wal"):
                _empty_file(p, dry_run)
            else:
                _delete(p, dry_run)
    # Prune now-empty subdirectories bottom-up: leftover per-goal dirs under
    # goals/artifacts/ made "artifact exists on disk" checks hit stale prior-life
    # paths (Run 9 capture: 68 of 73 dirs were empty leftovers).
    for sub in ("goals", "memory", "media"):
        base = ROOT_DATA_DIR / sub
        if not base.exists():
            continue
        pruned = 0
        # Deepest-first so a parent emptied by its child's removal is caught in
        # the same pass; emptiness is checked at removal time, not collection time.
        for d in sorted(base.rglob("*"), key=lambda p: len(p.parts), reverse=True):
            if d.is_dir() and not any(d.iterdir()):
                pruned += 1
                if not dry_run:
                    d.rmdir()
        if pruned:
            print(f"    {tag} {pruned} empty leftover dir(s) under data/{sub}/")
    # runtime_state.json is the post-rename name of alive_brain_state.json
    # (brain/data_schema.py); match both so a stale tree still gets cleared.
    for state_name in ("alive_brain_state.json", "runtime_state.json"):
        alive = ROOT_DATA_DIR / state_name
        if alive.exists():
            _write_json(alive, {"last": {}, "created_once": []}, dry_run)

    print(f"\nKept {len(keep & {f.name for f in DATA_DIR.glob('*.json')})} "
          f"config/knowledge json files + native_lm.pt + self_code scaffolding.")

    # ── 9. unrecognized-file guard ───────────────────────────────────────────
    check_extra_files(hard)

    # ── 10. post-reset assertions — "clean" is checked, not remembered ────────
    failures: list = []
    if not dry_run:
        failures = verify_reset(hard=hard)
        if not failures:
            print("\nOrrin is reset and ready for a clean run.\n")
    return failures


def _is_recognized(path: Path, hard: bool) -> bool:
    """True if reset has an explicit rule for this file (cleared, kept, or deleted)."""
    name = path.name
    parts = path.parts

    if name.endswith(".lock"):
        return True                       # transient locks: ignored on purpose
    if "_archive" in parts:
        return True                       # our own snapshots
    if name in KEEP_ARTIFACT_NAMES:
        return True                       # native_lm.pt etc.
    if name == "__init__.py" and "self_code" in parts:
        return True                       # package scaffolding (kept)

    # brain/data top-level: every .json/.jsonl/.txt is handled
    if path.parent == DATA_DIR and path.suffix in (".json", ".jsonl", ".txt"):
        return True
    if path.parent in (DATA_DIR / "rotated", DATA_DIR / "sandbox_tmp"):
        return True
    if path.parent == DATA_DIR / "language" and (
        name in LANGUAGE_EMPTY_FILE or name in LANGUAGE_DEFAULTS
    ):
        return True
    if any(path.parent == DATA_DIR / "language" / sub for sub in LANGUAGE_CLEAR_DIRS):
        return True
    if "self_code" in parts and path.suffix == ".py":
        return True                       # cleared under --hard, kept otherwise

    # brain/logs
    if path.parent == LOGS_DIR and path.suffix in (".txt", ".log", ".jsonl"):
        return True

    # root data/ tree
    if path.parent == ROOT_DATA_DIR and name in ("alive_brain_state.json",
                                                  "runtime_state.json"):
        return True
    try:
        rel = path.relative_to(ROOT_DATA_DIR).parts
        if rel and rel[0] in ("goals", "memory", "media"):
            return True
    except ValueError:
        pass

    return False


def check_extra_files(hard: bool = False) -> list:
    """Scan the data trees and warn about any file reset has no explicit rule for.

    This is the future-proofing guard: when new state files are introduced, they
    surface here so a maintainer can decide whether reset should clear them.
    """
    unknown: list = []
    for base in (DATA_DIR, LOGS_DIR, ROOT_DATA_DIR):
        if not base.exists():
            continue
        for p in base.rglob("*"):
            if p.is_file() and not _is_recognized(p, hard):
                unknown.append(p)

    if unknown:
        print(f"\n⚠  {len(unknown)} UNRECOGNIZED file(s) — preserved, but reset has no "
              f"rule for them. Review whether they hold state that should be cleared:")
        for p in sorted(unknown):
            try:
                rel = p.relative_to(ROOT)
            except ValueError:
                rel = p
            print(f"     ? {rel}")
        print("   (add a rule in reset_orrin.py if any of these are runtime state.)")
    else:
        print("\n✓  No unrecognized files — every file in the data trees has a reset rule.")
    return unknown


def verify_reset(hard: bool = False) -> list:
    """Assert the tree is actually newborn-clean. Returns a list of failure strings.

    Every check here exists because a "clean" reset once wasn't: habituation
    survived into Run 5, the committed control_signals_model.json seed was
    emptied before Run 8, and 68 stale artifact dirs sat under data/goals/
    through Run 9. Run standalone with `python3 reset_orrin.py --verify`
    before trusting any staging launch.
    """
    failures: list = []

    def _fail(msg: str) -> None:
        failures.append(msg)

    # 1. Committed seeds must match git HEAD — reset must never leave a tracked
    #    seed file emptied/modified (the control_signals_model.json gotcha,
    #    caught generically for every current and future committed seed).
    import subprocess
    try:
        out = subprocess.run(
            ["git", "-C", str(ROOT), "status", "--porcelain", "--", "brain/data", "data"],
            capture_output=True, text=True, timeout=30,
        ).stdout
        dirty_seeds = [l for l in out.splitlines() if l and not l.startswith("??")]
        for l in dirty_seeds:
            _fail(f"committed seed modified by reset: {l.strip()} (restore from git)")
    except Exception as e:
        print(f"    (git seed check skipped: {e})")

    # 2. Per-life counters and satiety state at zero.
    for name, want in (("cycle_count.json", {"count": 0}), ("habituation.json", None)):
        p = DATA_DIR / name
        if p.exists():
            try:
                got = json.loads(p.read_text() or "null")
            except Exception:
                _fail(f"{name}: unreadable json")
                continue
            if want is not None and got != want:
                _fail(f"{name}: expected {want}, got {got!r}")
            if want is None and got not in ({}, [], None):
                _fail(f"{name}: not empty ({str(got)[:60]}…)")

    # 3. Every runtime stream truncated (reset step 2 empties all of these).
    for p in sorted(DATA_DIR.glob("*.jsonl")) + sorted(DATA_DIR.glob("*.txt")):
        if p.stat().st_size > 0:
            _fail(f"stream not empty: brain/data/{p.name} ({p.stat().st_size} bytes)")

    # 4. Life-state stores the verdicts read must be empty containers.
    life_state = ["outcome_metrics.json", "commitment_signals.json", "comp_goals.json",
                  "goals_mem.json", "production_funnel.json", "aspiration_scoreboard.json",
                  "action_reward_ema.json"]
    for name in life_state:
        p = DATA_DIR / name
        if not p.exists():
            continue
        try:
            got = json.loads(p.read_text() or "null")
        except Exception:
            _fail(f"{name}: unreadable json")
            continue
        if isinstance(got, (list, dict)) and len(got) > 0:
            # a dict of empty containers (e.g. {"goals": {}}) still counts as clean
            if not (isinstance(got, dict) and all(v in ({}, [], 0, None) for v in got.values())):
                _fail(f"{name}: not empty ({str(got)[:60]}…)")

    # 5. Transient dirs empty; no corruption salvage left behind.
    for sub in ("rotated", "sandbox_tmp", "effect_artifacts", "tracked_work"):
        d = DATA_DIR / sub
        if d.exists():
            leftover = [p.name for p in d.glob("*")]
            if leftover:
                _fail(f"brain/data/{sub}/ not empty: {len(leftover)} file(s)")
    for p in DATA_DIR.glob("*.corrupt*"):
        _fail(f"corruption artifact survived: brain/data/{p.name}")

    # 6. Daemon trees newborn: no WAL history, no artifact leftovers (files OR
    #    empty per-goal dirs — stale dirs fake "artifact exists on disk").
    goals = ROOT_DATA_DIR / "goals"
    if goals.exists():
        for name in ("state.jsonl", "wal.log"):
            p = goals / name
            if p.exists() and p.stat().st_size > 0:
                _fail(f"data/goals/{name} not empty")
        for sub in ("artifacts", "snapshots", "wal-rotated"):
            d = goals / sub
            if d.exists():
                entries = list(d.iterdir())
                if entries:
                    _fail(f"data/goals/{sub}/ has {len(entries)} leftover entr(ies)")
    mem_wal = ROOT_DATA_DIR / "memory" / "wal"
    if mem_wal.exists():
        for p in mem_wal.glob("*"):
            if p.is_file() and p.stat().st_size > 0:
                _fail(f"data/memory/wal/{p.name} not empty")

    # 7. A live instance lock means something is still running against this tree.
    if (DATA_DIR / ".orrin.instance.lock").exists():
        print("    ⚠ .orrin.instance.lock present — make sure no Orrin is running.")

    if failures:
        print(f"\n✗ RESET VERIFICATION FAILED — {len(failures)} problem(s):")
        for f in failures:
            print(f"    ✗ {f}")
        print("  Do NOT launch a staging life on this tree.")
    else:
        print("\n✓ Reset verified — tree is newborn-clean.")
    return failures


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Reset Orrin's runtime state.")
    parser.add_argument("--hard", action="store_true",
                        help="Also clear learned bandit/decision state + self-written code")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be cleared without doing it")
    parser.add_argument("--no-snapshot", action="store_true",
                        help="Skip the built-in brain/data/*.json archive before clearing")
    parser.add_argument("--verify", action="store_true",
                        help="Only run the post-reset assertions on the current tree (no clearing)")
    args = parser.parse_args()

    if args.verify:
        print("=== Orrin Reset — verify only ===")
        raise SystemExit(2 if verify_reset(hard=args.hard) else 0)

    print("=== Orrin Reset ===")

    if not args.dry_run and not args.no_snapshot:
        print("\nSnapshotting current brain/data/*.json first...")
        snapshot("pre_reset")

    _failures = reset(hard=args.hard, dry_run=args.dry_run)
    if _failures:
        raise SystemExit(2)
