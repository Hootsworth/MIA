"""Paired detector comparison helpers."""
import numpy as np
from scipy.stats import binomtest, spearmanr
from sklearn.metrics import cohen_kappa_score


def compare_decisions(first, second):
    a, b = np.asarray(first, dtype=int), np.asarray(second, dtype=int)
    if a.shape != b.shape or not len(a):
        raise ValueError("decision arrays must have equal non-zero length")
    only_a = int(((a == 1) & (b == 0)).sum())
    only_b = int(((a == 0) & (b == 1)).sum())
    p = float(binomtest(min(only_a, only_b), only_a + only_b, .5).pvalue) if only_a + only_b else 1.0
    kappa, rho = float(cohen_kappa_score(a, b)), float(spearmanr(a, b).statistic)
    return {"n": len(a), "agreement_kappa": kappa if np.isfinite(kappa) else None,
            "spearman": rho if np.isfinite(rho) else None, "mcnemar_p_exact": p,
            "first_only_positive": only_a, "second_only_positive": only_b}
