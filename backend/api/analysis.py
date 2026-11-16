"""Read-only evaluation of immutable experiment snapshots and persisted outputs."""
from collections import defaultdict

import numpy as np
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.analytics.bootstrap import bootstrap_interval
from backend.analytics.comparison import compare_decisions
from backend.analytics.metrics import calibration, score_binary
from backend.api.detectors import get_db
from backend.models import Experiment, Result

router = APIRouter(tags=["analysis"])
SUPPORTED = {"accuracy", "precision", "recall", "specificity", "f1", "fpr", "fnr", "auroc", "auprc",
             "cohen_kappa", "confusion_matrix", "calibration", "ece"}
PROVENANCE = {"HUMAN": 0, "AI_GENERATED": 1, "AI_ASSISTED": 2}


def _subgroups(rows, floor, requested, cfg, seed, replicates):
    keys = ("domain", "genre", "language", "author_language_background", "provenance", "length_bin")
    out = {}
    for key in keys:
        buckets = defaultdict(list)
        for row in rows:
            value = row["document"].get(key)
            if key == "length_bin":
                count = row["document"].get("word_count")
                value = "unknown" if count is None else ("<500" if count < 500 else "500-999" if count < 1000 else "1000+")
            buckets[str(value or "unknown")].append(row)
        cells = []
        for value, items in sorted(buckets.items()):
            labels = np.array([row["label"] for row in items], dtype=int)
            scores = np.array([row["score"] for row in items], dtype=float)
            metrics = score_binary(labels, scores, direction=cfg["direction"], threshold=cfg.get("threshold"))
            cell_metrics = {name: metrics.get(name) for name in requested if name in metrics}
            intervals = {}
            for name in requested:
                if name not in metrics or metrics[name] is None or not isinstance(metrics[name], (int, float)):
                    continue
                def stat(indices, metric=name):
                    try:
                        return score_binary(labels[indices], scores[indices], direction=cfg["direction"],
                                            threshold=cfg.get("threshold")).get(metric)
                    except ValueError:
                        return None
                intervals[name] = bootstrap_interval(np.arange(len(labels)),
                    lambda index, stat=stat: stat(np.asarray(index, dtype=int)), seed=seed,
                    replicates=replicates)
            cells.append({"value": value, "n": len(items), "unreliable": len(items) < floor,
                          "metrics": cell_metrics, "confidence_intervals": intervals})
        out[key] = cells
    return out


@router.get("/analysis/experiments/{experiment_id}")
def analyze_experiment(experiment_id: str, min_subgroup_n: int = 30, bootstrap_replicates: int = 2000,
                       db: Session = Depends(get_db)):
    experiment = db.get(Experiment, experiment_id)
    if experiment is None:
        raise HTTPException(404, "Experiment not found")
    if experiment.status not in {"COMPLETED", "PARTIALLY_COMPLETED"}:
        raise HTTPException(409, "Only completed experiments can be analyzed")
    protocol = experiment.protocol or {}
    rule = protocol.get("classification_rule")
    if not isinstance(rule, dict) or rule.get("version") != "m6.1":
        raise HTTPException(422, "Statistics require a structured m6.1 classification rule")
    metrics = protocol.get("metrics") or []
    if not metrics or set(metrics) - SUPPORTED:
        raise HTTPException(422, {"message": "Select supported metrics in the frozen protocol", "unsupported": sorted(set(metrics) - SUPPORTED)})
    if min_subgroup_n < 1 or bootstrap_replicates < 2000:
        raise HTTPException(422, "min_subgroup_n must be positive and bootstrap_replicates at least 2000")
    positive, negative = set(rule["positive_provenance"]), set(rule["negative_provenance"])
    detector_rules = rule["detectors"]
    binary_metrics = SUPPORTED - {"auroc", "auprc", "calibration", "ece"}
    if set(metrics) & binary_metrics and any(d.get("threshold") is None for d in detector_rules.values()):
        raise HTTPException(422, "Binary metrics require a predeclared threshold for every detector")
    snapshot = {d["id"]: d for d in protocol.get("document_snapshot", [])}
    results = db.scalars(select(Result).where(Result.experiment_id == experiment_id)).all()
    grouped = defaultdict(list)
    for row in results:
        output = row.output or {}
        doc = snapshot.get(row.document_id)
        if doc is None:
            continue
        provenance = doc.get("provenance")
        if provenance in positive:
            label = 1
        elif provenance in negative:
            label = 0
        else:
            continue
        grouped[row.detector_version_id].append({"document": doc, "label": label,
            "score": output.get("score") if not output.get("error") else None,
            "state": "missing" if output.get("error") or output.get("score") is None else output.get("score_state", "value"),
            "semantics": output.get("score_semantics", "unknown")})
    detector_index = {d["version_id"]: d for d in protocol.get("detector_snapshot", [])}
    semantics_by_key = {d.get("key"): d.get("score_semantics") for d in protocol.get("detector_snapshot", [])}
    for key, cfg in detector_rules.items():
        semantics = semantics_by_key.get(key)
        threshold = cfg.get("threshold")
        if semantics == "probability" and threshold is not None and not 0 <= threshold <= 1:
            raise HTTPException(422, f"Probability threshold for {key} must be between 0 and 1")
        if semantics == "percentage" and threshold is not None and not 0 <= threshold <= 100:
            raise HTTPException(422, f"Percentage threshold for {key} must be between 0 and 100")
    summary, predictions = [], {}
    seed = int(rule.get("seed", protocol.get("seed", 0)))
    for version_id, rows in grouped.items():
        descriptor = detector_index.get(version_id, {})
        key = descriptor.get("key", version_id or "unknown")
        cfg = detector_rules.get(key)
        if cfg is None:
            continue
        valid = [r for r in rows if r["state"] == "value" and isinstance(r["score"], (int, float))]
        excluded = {state: sum(r["state"] == state for r in rows) for state in ("censored", "missing")}
        if not valid:
            summary.append({"detector": key, "n": 0, "excluded": excluded, "metrics": {},
                            "reason": "No observed numeric scores"})
            continue
        y = np.array([r["label"] for r in valid], dtype=int)
        scores = np.array([r["score"] for r in valid], dtype=float)
        try:
            computed = score_binary(y, scores, direction=cfg["direction"], threshold=cfg.get("threshold"))
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        calculated = {k: v for k, v in computed.items() if k in metrics}
        # Document bootstrap keeps each observed score paired with its frozen label.
        cis = {}
        for metric in (set(metrics) & {"accuracy", "precision", "recall", "specificity", "f1", "fpr", "fnr", "auroc", "auprc", "cohen_kappa"}):
            if metric not in computed or computed[metric] is None:
                continue
            def stat(indices, metric=metric):
                sample_y, sample_s = y[indices], scores[indices]
                try:
                    return score_binary(sample_y, sample_s, direction=cfg["direction"], threshold=cfg.get("threshold")).get(metric, np.nan)
                except ValueError:
                    return np.nan
            # resample pairs by passing index positions as bootstrap observations
            clusters = [r["document"].get("source_group") or r["document"]["id"] for r in valid]
            use_clusters = clusters if len(set(clusters)) < len(valid) else None
            ci = bootstrap_interval(np.arange(len(y)), lambda idx: stat(np.asarray(idx, dtype=int)),
                                    seed=seed, replicates=bootstrap_replicates, clusters=use_clusters)
            cis[metric] = ci
        if set(metrics) & {"calibration", "ece"}:
            if any(r["semantics"] != "probability" for r in valid):
                raise HTTPException(422, f"Calibration/ECE requires probability semantics; {key} is not a probability detector")
            cal = calibration(scores, y)
            if "ece" in metrics:
                calculated["ece"] = cal["ece"]
                def ece_stat(indices):
                    return calibration(scores[np.asarray(indices, dtype=int)], y[np.asarray(indices, dtype=int)])["ece"]
                cluster_ids = [r["document"].get("source_group") or r["document"]["id"] for r in valid]
                use_clusters = cluster_ids if len(set(cluster_ids)) < len(valid) else None
                cis["ece"] = bootstrap_interval(np.arange(len(y)), ece_stat, seed=seed,
                    replicates=bootstrap_replicates, clusters=use_clusters)
            if "calibration" in metrics:
                calculated["calibration"] = cal["bins"]
        predictions[key] = {r["document"]["id"]: (r["label"], r["score"], cfg) for r in valid}
        summary.append({"detector": key, "n": len(valid), "positive_n": int(y.sum()),
                        "negative_n": int(len(y)-y.sum()), "excluded": excluded,
                        "metrics": calculated, "confidence_intervals": cis,
                        "subgroups": _subgroups(valid, min_subgroup_n, metrics, cfg, seed, bootstrap_replicates),
                        "insufficient_classes": len(np.unique(y)) < 2})
    comparisons = []
    detector_keys = list(predictions)
    for i, first in enumerate(detector_keys):
        for second in detector_keys[i + 1:]:
            common = sorted(set(predictions[first]) & set(predictions[second]))
            if not common:
                continue
            y = np.array([predictions[first][doc][0] for doc in common], dtype=int)
            left_cfg, right_cfg = predictions[first][common[0]][2], predictions[second][common[0]][2]
            left = np.array([predictions[first][doc][1] for doc in common], dtype=float)
            right = np.array([predictions[second][doc][1] for doc in common], dtype=float)
            left_decision = (left >= left_cfg["threshold"] if left_cfg["direction"] == "higher" else left <= left_cfg["threshold"]).astype(int)
            right_decision = (right >= right_cfg["threshold"] if right_cfg["direction"] == "higher" else right <= right_cfg["threshold"]).astype(int)
            entry = {"first": first, "second": second, **compare_decisions(left_decision, right_decision)}
            if len(np.unique(y)) == 2:
                def auc_difference(indices):
                    ids = np.asarray(indices, dtype=int)
                    sample_y = y[ids]
                    if len(np.unique(sample_y)) < 2:
                        return float("nan")
                    return float(score_binary(sample_y, left[ids], direction=left_cfg["direction"])["auroc"] -
                                 score_binary(sample_y, right[ids], direction=right_cfg["direction"])["auroc"])
                entry["auroc_difference_first_minus_second"] = float(auc_difference(np.arange(len(y))))
                cluster_ids = [snapshot[doc].get("source_group") or doc for doc in common]
                use_clusters = cluster_ids if len(set(cluster_ids)) < len(common) else None
                entry["auroc_difference_ci"] = bootstrap_interval(np.arange(len(y)), auc_difference,
                    seed=seed, replicates=bootstrap_replicates, clusters=use_clusters)
            else:
                entry["auroc_difference_first_minus_second"] = None
                entry["auroc_difference_reason"] = "Both classes are required"
            comparisons.append(entry)
    return {"experiment_id": experiment.id, "protocol_version": protocol.get("protocol_version"),
            "classification_rule": rule, "metrics_requested": metrics, "bootstrap_replicates": bootstrap_replicates,
            "subgroup_floor": min_subgroup_n, "detectors": summary, "comparisons": comparisons,
            "note": "Censored and missing outputs are excluded and counted separately; estimates use observed numeric values only."}
