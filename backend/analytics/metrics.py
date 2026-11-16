"""Small, explicit metric helpers for labeled detector evaluations."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
from scipy.stats import binomtest
from sklearn.metrics import (accuracy_score, average_precision_score, cohen_kappa_score,
                             confusion_matrix, f1_score, precision_score, recall_score,
                             roc_auc_score)


@dataclass(frozen=True)
class Observation:
    state: Literal["value", "censored", "missing"]
    value: float | None = None
    detail: str | None = None

    def __post_init__(self):
        if self.state == "value" and self.value is None:
            raise ValueError("value observations require a numeric value")
        if self.state != "value" and self.value is not None:
            raise ValueError("censored and missing observations cannot carry numeric values")


def score_binary(labels, scores, *, direction: Literal["higher", "lower"] = "higher", threshold: float | None = None):
    """Compute ranking metrics and, only with a declared threshold, binary metrics."""
    y = np.asarray(labels, dtype=int)
    s = np.asarray(scores, dtype=float)
    if y.ndim != 1 or s.ndim != 1 or len(y) != len(s) or not len(y):
        raise ValueError("labels and scores must be non-empty, equally sized one-dimensional arrays")
    if not set(np.unique(y)).issubset({0, 1}):
        raise ValueError("labels must be binary 0/1")
    if not np.isfinite(s).all():
        raise ValueError("scores must be finite")
    oriented = s if direction == "higher" else -s
    result = {"n": len(y), "positive_n": int(y.sum()), "negative_n": int(len(y) - y.sum()),
              "auroc": None, "auprc": None, "auroc_reason": None, "auprc_reason": None,
              "classification_rule_required": threshold is None}
    if len(np.unique(y)) == 2:
        result["auroc"] = float(roc_auc_score(y, oriented))
        result["auprc"] = float(average_precision_score(y, oriented))
    else:
        reason = "AUROC and AUPRC require both positive and negative examples"
        result["auroc_reason"] = reason
        result["auprc_reason"] = reason
    if threshold is not None:
        pred = (s >= threshold if direction == "higher" else s <= threshold).astype(int)
        tn, fp, fn, tp = confusion_matrix(y, pred, labels=[0, 1]).ravel()
        result.update({"accuracy": float(accuracy_score(y, pred)),
                       "precision": float(precision_score(y, pred, zero_division=0)),
                       "recall": float(recall_score(y, pred, zero_division=0)),
                       "specificity": float(tn / (tn + fp)) if tn + fp else None,
                       "f1": float(f1_score(y, pred, zero_division=0)),
                       "fpr": float(fp / (fp + tn)) if fp + tn else None,
                       "fnr": float(fn / (fn + tp)) if fn + tp else None,
                       "cohen_kappa": float(cohen_kappa_score(y, pred)) if len(np.unique(y)) > 1 else None,
                       "confusion_matrix": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)}})
    return result


def calibration(scores, labels, *, bins: int = 10):
    """Calibration is only defined for probability semantics."""
    p = np.asarray(scores, dtype=float)
    y = np.asarray(labels, dtype=int)
    if not len(p) or len(p) != len(y) or not np.isfinite(p).all() or np.any((p < 0) | (p > 1)):
        raise ValueError("calibration requires equally sized finite probabilities in [0, 1]")
    edges = np.linspace(0, 1, bins + 1)
    rows, ece = [], 0.0
    for i in range(bins):
        mask = (p >= edges[i]) & ((p <= edges[i + 1]) if i == bins - 1 else (p < edges[i + 1]))
        n = int(mask.sum())
        if n:
            confidence, observed = float(p[mask].mean()), float(y[mask].mean())
            interval = binomtest(int(y[mask].sum()), n).proportion_ci(confidence_level=.95, method="wilson")
            ece += n / len(p) * abs(confidence - observed)
            rows.append({"lower": float(edges[i]), "upper": float(edges[i + 1]), "n": n,
                         "mean_probability": confidence, "positive_rate": observed,
                         "positive_rate_ci": {"lower": float(interval.low), "upper": float(interval.high)}})
    return {"n": len(p), "ece": float(ece), "bins": rows}


def observed_values(observations: list[Observation]) -> tuple[list[float], dict[str, int]]:
    counts = {state: sum(o.state == state for o in observations) for state in ("value", "censored", "missing")}
    return [float(o.value) for o in observations if o.state == "value"], counts
