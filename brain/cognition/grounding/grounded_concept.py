"""A grounded concept — a PREDICTIVE SIGNATURE, not a string.

The direction doc's definition (Part D): "a concept is the learned bundle of what
percepts co-occur with it, what it lets him predict — the string is just a handle."
Here the narrowest honest instance: a concept that predicts whether a command will
SUCCEED (exit 0) from its STRUCTURAL features. The mapping feature→outcome is
LEARNED from real exit codes (never authored), so the concept is grounded; it is
inspectable as a signature (`signature()`), not a stored command string.

Learning rule (Phase 4A upgrade): online LOGISTIC REGRESSION — a learned weight per
feature plus a bias, updated by gradient on each real outcome. This replaces the
naive-Bayes log-odds sum, which weighted features *present* and could not EXPLAIN
AWAY a feature that merely co-occurs with a stronger one (e.g. `has_binop` appears in
both arithmetic successes and unbound-name failures; naive Bayes mis-blamed it,
costing transfer on noisy families). Logistic regression learns `has_binop ≈ 0` and
`references_unbound_name ≪ 0`, and correctly reads the ABSENCE of a failure signature
as success. Still grounded: every weight moves only toward what actually happened
(Rescorla-Wagner / delta rule).
"""
from __future__ import annotations

import math
from typing import Dict, Iterable, List


class GroundedConcept:
    def __init__(self, name: str = "command_succeeds", lr: float = 0.3,
                 l2: float = 1e-4) -> None:
        self.name = name
        self.lr = lr
        self.l2 = l2                      # mild decay so rare-feature weights stay honest
        self._w: Dict[str, float] = {}    # feature -> learned weight (the signature)
        self._bias = 0.0
        self._seen: Dict[str, int] = {}   # feature -> times observed (evidence)
        self.episodes = 0

    # ── prediction ───────────────────────────────────────────────────────────
    @staticmethod
    def _sigmoid(z: float) -> float:
        if z < -30:
            return 1e-13
        if z > 30:
            return 1.0
        return 1.0 / (1.0 + math.exp(-z))

    def _score(self, features: Iterable[str]) -> float:
        return self._bias + sum(self._w.get(f, 0.0) for f in set(features))

    def predict(self, features: Iterable[str]) -> float:
        """P(success) for a command with these structural features. A feature not
        present contributes nothing (absence is handled correctly); the bias carries
        the base rate."""
        return self._sigmoid(self._score(features))

    # ── learning (only from REAL outcomes) ─────────────────────────────────────
    def update(self, features: Iterable[str], success: bool) -> None:
        self.episodes += 1
        feats = set(features)
        target = 1.0 if success else 0.0
        err = target - self.predict(feats)          # delta rule
        self._bias += self.lr * err
        for f in feats:
            self._seen[f] = self._seen.get(f, 0) + 1
            w = self._w.get(f, 0.0)
            self._w[f] = w + self.lr * err - self.l2 * w
        # L2 only nudges weights of features actually present (cheap, keeps the map small).

    # ── introspection (the concept is a SIGNATURE, not a string) ──────────────
    def signature(self, min_evidence: int = 2) -> Dict[str, Dict[str, float]]:
        """The inspectable predictive signature: the learned weight per feature
        (negative ⇒ predicts failure, positive ⇒ predicts success) and how much
        grounded evidence backs it. This — not any stored command — IS the concept."""
        out: Dict[str, Dict[str, float]] = {}
        for f, w in self._w.items():
            ev = self._seen.get(f, 0)
            if ev >= min_evidence:
                # report P(success) when ONLY this feature is present, for readability
                out[f] = {
                    "weight": round(w, 3),
                    "p_success": round(self._sigmoid(self._bias + w), 3),
                    "evidence": ev,
                }
        return out

    def top_features(self, k: int = 5) -> List[str]:
        """The features carrying the most predictive weight (either direction)."""
        return [f for f, _ in sorted(self._w.items(),
                                     key=lambda kv: abs(kv[1]), reverse=True)[:k]]
