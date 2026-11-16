# Copyright 2026 MIA contributors
# SPDX-License-Identifier: Apache-2.0
"""Deterministic percentile bootstrap intervals, optionally clustered by source."""
import numpy as np


def bootstrap_interval(values, statistic, *, seed: int, replicates: int = 2000, clusters=None, confidence: float = .95):
    if replicates < 2000:
        raise ValueError("at least 2000 bootstrap replicates are required")
    values = np.asarray(values)
    if not len(values):
        return {"n": 0, "replicates": replicates, "estimate": None, "lower": None, "upper": None}
    rng = np.random.default_rng(seed)
    if clusters is None:
        groups = [np.array([i]) for i in range(len(values))]
    else:
        clusters = np.asarray(clusters)
        if len(clusters) != len(values):
            raise ValueError("cluster IDs must match values")
        groups = [np.flatnonzero(clusters == key) for key in np.unique(clusters)]
    samples = []
    for _ in range(replicates):
        chosen = rng.integers(0, len(groups), size=len(groups))
        idx = np.concatenate([groups[i] for i in chosen])
        estimate = statistic(values[idx])
        try:
            estimate = float(estimate)
        except (TypeError, ValueError):
            continue
        if np.isfinite(estimate):
            samples.append(estimate)
    alpha = (1 - confidence) / 2
    lo, hi = np.quantile(samples, [alpha, 1 - alpha]) if samples else (np.nan, np.nan)
    estimate = float(statistic(values))
    return {"n": len(values), "cluster_n": len(groups), "replicates": replicates,
            "estimate": estimate, "lower": float(lo), "upper": float(hi)}
