# Copyright 2026 MIA contributors
# SPDX-License-Identifier: Apache-2.0
import numpy as np
import pytest
from sklearn.metrics import roc_auc_score

from backend.analytics.bootstrap import bootstrap_interval
from backend.analytics.comparison import compare_decisions
from backend.analytics.leakage import validate_grouped_splits
from backend.analytics.metrics import Observation, calibration, observed_values, score_binary


def test_hand_computed_binary_metrics_and_confusion():
    result = score_binary([0, 0, 1, 1], [.1, .7, .8, .9], threshold=.65)
    assert result["confusion_matrix"] == {"tn": 1, "fp": 1, "fn": 0, "tp": 2}
    assert result["accuracy"] == .75
    assert result["precision"] == pytest.approx(2 / 3, abs=1e-6)
    assert result["recall"] == 1
    assert result["specificity"] == .5
    assert result["f1"] == .8
    assert result["fpr"] == .5 and result["fnr"] == 0
    assert score_binary([0, 1], [.2, .8])["auroc"] == 1
    assert score_binary([0, 1], [.8, .2])["auroc"] == 0


def test_auroc_matches_sklearn_and_threshold_is_required():
    labels = np.array([0, 1, 0, 1, 1, 0])
    scores = np.array([.2, .4, .6, .9, .7, .1])
    assert score_binary(labels, scores)["auroc"] == roc_auc_score(labels, scores)
    assert "accuracy" not in score_binary(labels, scores)


def test_random_rankings_are_near_chance_and_ci_is_seeded():
    rng = np.random.default_rng(1984)
    labels = np.tile([0, 1], 500)
    scores = rng.random(len(labels))
    assert abs(score_binary(labels, scores)["auroc"] - .5) < .1
    shuffled = rng.permutation(labels)
    assert abs(score_binary(shuffled, scores)["auroc"] - .5) < .1
    first = bootstrap_interval(np.arange(30), np.mean, seed=4)
    assert first == bootstrap_interval(np.arange(30), np.mean, seed=4)
    assert first["replicates"] == 2000 and first["lower"] <= first["estimate"] <= first["upper"]
    with pytest.raises(ValueError):
        bootstrap_interval([1, 2], np.mean, seed=1, replicates=1999)


def test_bootstrap_mean_interval_narrows_with_more_observations():
    rng = np.random.default_rng(72)
    small = bootstrap_interval(rng.normal(size=40), np.mean, seed=22)
    large = bootstrap_interval(rng.normal(size=400), np.mean, seed=22)
    assert large["upper"] - large["lower"] < small["upper"] - small["lower"]


def test_censoring_and_missing_are_not_converted_to_zero():
    observations = [Observation("value", 2), Observation("censored", detail="<=1"), Observation("missing")]
    values, counts = observed_values(observations)
    assert values == [2.0]
    assert counts == {"value": 1, "censored": 1, "missing": 1}
    with pytest.raises(ValueError):
        Observation("censored", 0)


def test_probability_calibration_and_detector_comparison():
    assert calibration([.1, .9], [0, 1])["ece"] == pytest.approx(.1)
    with pytest.raises(ValueError):
        calibration([20, 90], [0, 1])
    compared = compare_decisions([0, 1, 1], [0, 1, 0])
    assert compared["n"] == 3 and compared["first_only_positive"] == 1


def test_grouped_splits_reject_shared_author_and_duplicate_groups():
    assert validate_grouped_splits({"train": [{"author_id": "a"}], "validation": [{"author_id": "b"}], "test": []})
    with pytest.raises(ValueError, match="leakage"):
        validate_grouped_splits({"train": [{"author_id": "a"}], "validation": [], "test": [{"author_id": "a"}]})
    with pytest.raises(ValueError, match="duplicate_group"):
        validate_grouped_splits({"train": [{"duplicate_group": "same"}], "validation": [{"duplicate_group": "same"}], "test": []})


def test_structured_rule_requires_valid_class_sets_and_direction():
    from backend.schemas.experiments import ExperimentCreate
    base = {"name": "x", "research_question": "RQ1", "hypothesis": "h", "document_ids": ["d"],
            "detector_keys": ["det"], "classification_rule": {"version": "m6.1", "positive_provenance": ["AI_GENERATED"],
            "negative_provenance": ["HUMAN"], "detectors": {"det": {"direction": "higher", "threshold": .5}}},
            "metrics": ["auroc"]}
    assert ExperimentCreate.model_validate(base).classification_rule["version"] == "m6.1"
    invalid = {**base, "classification_rule": {**base["classification_rule"], "negative_provenance": ["AI_GENERATED"]}}
    with pytest.raises(ValueError):
        ExperimentCreate.model_validate(invalid)


