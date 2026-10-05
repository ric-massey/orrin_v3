"""Run 13 gate-passer 3: characterization goals answer a question about Orrin's own
behaviour with a prediction tested OUT OF SAMPLE on his telemetry. The prediction
must be able to fail — on the real Run 12 telemetry fixture both early hypotheses do."""
import gzip
import json
from pathlib import Path

from brain.cognition.epistemic_closeout import score_answer_structured
from goals.handlers import characterize as ch
from goals.model import Goal, Status

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "run12_resource_history_2600.jsonl.gz"


def _real_rows():
    with gzip.open(FIX, "rt", encoding="utf-8") as fh:
        return [json.loads(line) for line in fh]


def test_real_telemetry_hypotheses_fail_out_of_sample():
    rows = _real_rows()
    train, fresh = rows[:1300], rows[1300:]
    for metric in ("rss_mb", "cpu_util"):
        h = ch.hypothesize(train, metric)
        assert h is not None and h["n"] >= ch.MIN_TRAIN_OCC and h["mean"] > h["base"]
        result = ch.test_hypothesis(fresh, metric, h["driver"])
        assert result is not None and result["correct"] is False


def test_rare_driver_is_never_hypothesized():
    # A function seen 7 times with the biggest rise must not beat a frequent one.
    rows, ts, rss = [], 0.0, 100.0
    for i in range(400):
        fn = "rare_spike" if i % 60 == 0 else ("grow" if i % 2 else "idle")
        rss += 5.0 if fn == "rare_spike" else (1.0 if fn == "grow" else 0.0)
        ts += 3.5
        rows.append({"ts": ts, "rss_mb": rss, "last_fn": fn})
    assert ch.hypothesize(rows, "rss_mb")["driver"] == "grow"


def _series(n, start_ts, start_rss, grows):
    rows, ts, rss = [], start_ts, start_rss
    for i in range(n):
        fn = "grow" if i % 2 else "idle"
        rss += (1.0 if grows else -1.0) if fn == "grow" else 0.0
        ts += 3.5
        rows.append({"ts": ts, "rss_mb": rss, "cpu_util": 0.1, "last_fn": fn})
    return rows


def _run(handler, goal, step, ctx):
    out = handler.tick(goal, step, ctx)
    assert out is not None
    return out


def test_round_trip_hypothesize_defer_check_and_closeout(tmp_path, monkeypatch):
    tele = tmp_path / "resource_history.jsonl"
    train = _series(400, 0.0, 100.0, grows=True)
    tele.write_text("\n".join(json.dumps(r) for r in train), encoding="utf-8")
    ctx = {"artifacts_dir": str(tmp_path / "artifacts"), "resource_history_path": str(tele)}
    q = "What makes my memory use (RSS) climb?"
    goal = Goal(id="g_char", title="Characterize what makes my memory use (RSS) climb",
                kind="characterize", spec={"metric": "rss_mb", "question": q})
    h = ch.CharacterizeHandler()
    hyp, check = h.plan(goal, ctx)

    hyp = _run(h, goal, hyp, ctx)
    assert hyp.status == Status.DONE
    claims_path = tmp_path / "artifacts" / "g_char" / "claims.json"
    claims = json.loads(claims_path.read_text())
    assert claims["prediction"]["driver"] == "grow" and claims["prediction"]["resolved"] is False
    assert score_answer_structured(q, claims) == (False, "")   # pending → not answered

    # No fresh telemetry yet → the check defers instead of judging.
    check = _run(h, goal, check, ctx)
    assert check.status == Status.READY and "DEFERRED" in (check.last_error or "")

    # Fresh samples where the claim holds → resolved correct → answered.
    fresh = _series(200, train[-1]["ts"], train[-1]["rss_mb"], grows=True)
    with open(tele, "a", encoding="utf-8") as fh:
        fh.write("\n" + "\n".join(json.dumps(r) for r in fresh))
    monkeypatch.setattr(ch, "_last_check", {})
    check = _run(h, goal, check, ctx)
    assert check.status == Status.DONE
    claims = json.loads(claims_path.read_text())
    assert claims["prediction"]["resolved"] is True and claims["prediction"]["correct"] is True
    answered, excerpt = score_answer_structured(q, claims)
    assert answered is True and excerpt.startswith("prediction confirmed")


def test_falsified_prediction_is_not_an_answer(tmp_path, monkeypatch):
    tele = tmp_path / "resource_history.jsonl"
    train = _series(400, 0.0, 100.0, grows=True)
    fresh = _series(200, train[-1]["ts"], train[-1]["rss_mb"], grows=False)
    tele.write_text("\n".join(json.dumps(r) for r in train), encoding="utf-8")
    ctx = {"artifacts_dir": str(tmp_path / "artifacts"), "resource_history_path": str(tele)}
    goal = Goal(id="g_f", title="t", kind="characterize", spec={"metric": "rss_mb"})
    h = ch.CharacterizeHandler()
    hyp, check = h.plan(goal, ctx)
    _run(h, goal, hyp, ctx)
    with open(tele, "a", encoding="utf-8") as fh:
        fh.write("\n" + "\n".join(json.dumps(r) for r in fresh))
    monkeypatch.setattr(ch, "_last_check", {})
    check = _run(h, goal, check, ctx)
    claims = json.loads((tmp_path / "artifacts" / "g_f" / "claims.json").read_text())
    assert claims["prediction"]["correct"] is False
    assert "failed out of sample" in claims["prediction"]["outcome"]
    assert score_answer_structured("What makes my memory use (RSS) climb?", claims) == (False, "")
