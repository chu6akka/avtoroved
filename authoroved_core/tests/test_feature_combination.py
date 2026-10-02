import numpy as np

from authoroved_core.tools.feature_combination import (
    author_folds, build_matrix, cross_validate, logistic_fit,
)


def synthetic(signal_features: int, noise_features: int, authors: int = 40, texts: int = 4, seed: int = 5):
    rng = np.random.default_rng(seed)
    labels = np.repeat(np.arange(authors), texts)
    centres = rng.normal(0, 1, (authors, signal_features))
    signal = centres[labels] + rng.normal(0, 1.0, (len(labels), signal_features))
    noise = rng.normal(0, 1, (len(labels), noise_features))
    names = [f"Индекс {i + 1:02d}. сигнал" for i in range(signal_features)] + \
            [f"Шум {i}" for i in range(noise_features)]
    return np.hstack([signal, noise]), names, labels.astype(str)


def test_folds_split_authors_without_overlap():
    labels = np.repeat(np.array([f"A{i}" for i in range(23)]), 4)
    folds = author_folds(labels, 5, seed=1)
    assert sum(fold.sum() for fold in folds) == len(labels)
    for fold in folds:
        assert not set(labels[fold]) & set(labels[~fold])   # автор целиком в одной группе


def test_logistic_regression_finds_the_informative_feature():
    rng = np.random.default_rng(0)
    x = rng.normal(0, 1, (2000, 3))
    y = (x[:, 0] + rng.normal(0, 0.5, 2000) > 0).astype(float)
    weights = logistic_fit(x, y)
    assert weights[0] > 5 * max(abs(weights[1]), abs(weights[2]))


def test_combining_several_weak_signals_beats_the_best_single_one():
    matrix, names, labels = synthetic(signal_features=8, noise_features=4)
    result = cross_validate(matrix, names, labels, repeats=1, seed=3)["methods"]
    assert result["classic"]["auc"] > result["single"]["auc"] + 0.05
    assert result["logistic"]["auc"] > result["single"]["auc"]


def test_pure_noise_stays_at_chance_out_of_sample():
    matrix, names, labels = synthetic(signal_features=0, noise_features=30)
    result = cross_validate(matrix, names, labels, repeats=1, seed=4)["methods"]
    for key in ("single", "all", "logistic", "top10"):
        assert 0.4 < result[key]["auc"] < 0.6, key   # отбор на обучении не даёт ложного выигрыша


def test_matrix_keeps_only_mostly_defined_metrics():
    matrix, names = build_matrix([{"a": 1.0, "b": 2.0}, {"a": 3.0}, {"a": 2.0}, {"a": 1.0, "b": 1.0}])
    assert names == ["a"]
    assert matrix.shape == (4, 1)
