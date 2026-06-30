"""Grounding — the outward predict→act→observe→learn loop (Grounded Cognition
plan, Phase 3 / invariant #4).

This is the GO/NO-GO experiment, not a feature to ship. It re-points the existing
predictive machinery OUTWARD: instead of predicting his own internal signals and
grading against his own logs, Orrin predicts a concrete EXTERNAL observable of a
command (its exit code) BEFORE running it, runs it, and is corrected by the real
interpreter — an observable he did not author. A concept here is a learned
PREDICTIVE SIGNATURE over structural features, not an authored string; it is
grounded because every statistic in it is updated only from real execution
outcomes. The hypothesis is that such a concept TRANSFERS to unseen commands;
test_grounding_transfer.py is the falsifiable harness with a declared baseline and
kill criterion.
"""
