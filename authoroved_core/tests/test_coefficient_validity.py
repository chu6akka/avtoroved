import numpy as np

from authoroved_core.core.models import Span, Token
from authoroved_core.tools.coefficient_validity import (
    auc_from_sorted, benjamini_hochberg, discrimination, fragment_auc, icc1, metric_number,
    minimum_length, pair_index, same_pairs, window,
)


def brute_auc(same, different):
    wins = sum(1.0 if d > s else 0.5 if d == s else 0.0 for d in different for s in same)
    return wins / (len(same) * len(different))


def test_fast_auc_equals_brute_force_with_ties():
    rng = np.random.default_rng(1)
    same = rng.integers(0, 6, 40).astype(float)
    different = rng.integers(0, 9, 150).astype(float)
    fast = auc_from_sorted(np.sort(np.concatenate([same, different])), same)
    assert abs(fast - brute_auc(same, different)) < 1e-12


def test_permutation_test_detects_author_signal_and_not_noise():
    rng = np.random.default_rng(2)
    authors = np.repeat(np.arange(30), 4)
    signal = authors * 1.0 + rng.normal(0, 0.3, len(authors))  # значение задаёт автор
    noise = rng.normal(0, 1, len(authors))                     # автор ни при чём
    left, right = pair_index(len(authors))
    observed = same_pairs(authors, left, right)
    labels, permuted = authors.copy(), []
    for _ in range(199):
        rng.shuffle(labels)
        permuted.append(same_pairs(labels, left, right))
    everything = np.ones(len(left), dtype=bool)
    strong = discrimination(np.abs(signal[left] - signal[right]), everything, observed, permuted)
    weak = discrimination(np.abs(noise[left] - noise[right]), everything, observed, permuted)
    assert strong["auc"] > 0.95 and strong["p"] <= 0.01
    assert 0.4 < weak["auc"] < 0.6 and weak["p"] > 0.05
    assert strong["same_pairs"] == 30 * 6


def test_missing_values_are_left_out_of_pairs():
    values = np.array([1.0, 1.1, np.nan, 5.0, 5.2, 9.0])
    authors = np.array([0, 0, 0, 1, 1, 2])
    left, right = pair_index(len(values))
    stats = discrimination(np.abs(values[left] - values[right]), np.ones(len(left), dtype=bool),
                           same_pairs(authors, left, right), [])
    assert stats["same_pairs"] == 2      # (0,1) и (3,4); пары с NaN не считаются
    assert stats["different_pairs"] == 8


def test_icc_is_high_when_authors_differ_and_near_zero_otherwise():
    rng = np.random.default_rng(3)
    authors = np.repeat(np.arange(20), 4)
    assert icc1(authors * 2.0 + rng.normal(0, 0.2, 80), authors) > 0.9
    assert abs(icc1(rng.normal(0, 1, 80), authors)) < 0.25


def test_benjamini_hochberg_matches_hand_calculation():
    q = benjamini_hochberg({"a": 0.01, "b": 0.02, "c": 0.03, "d": 0.5})
    assert q == {"a": 0.04, "b": 0.04, "c": 0.04, "d": 0.5}


def test_metric_values_are_parsed_as_shares_and_ratios():
    assert metric_number("12 · 4,5 %") == 0.045
    assert metric_number("0,123 (12 / 98)") == 0.123
    assert metric_number("Нет данных: знаменатель равен нулю (числитель 3)") is None
    assert metric_number("Не рассчитывается автоматически") is None


def test_minimum_length_requires_stability_from_that_point_on():
    by_length = {"100": {"deviation": 0.4}, "200": {"deviation": 0.15},
                 "300": {"deviation": 0.25}, "500": {"deviation": 0.12}, "750": {"deviation": 0.08}}
    assert minimum_length(by_length, 0.20) == 500   # на 200 укладывается, но на 300 снова нет
    assert minimum_length(by_length, 0.10) == 750
    assert minimum_length({"100": {"deviation": 0.5}}, 0.2) is None


def test_window_takes_exact_number_of_words_with_inner_punctuation():
    words = ["Он", ",", "пришёл", "домой", ".", "Спал"]
    tokens = [Token(w, w, "PUNCT" if w in ",." else "NOUN", {}, "", 0, 0, i, Span(0, 1))
              for i, w in enumerate(words)]
    positions = [i for i, t in enumerate(tokens) if t.pos != "PUNCT"]
    assert [t.text for t in window(tokens, positions, 0, 3)] == ["Он", ",", "пришёл", "домой"]
    assert fragment_auc(np.array([1.0, 1.1, 5.0, 5.1]), np.array([0, 0, 1, 1])) == 1.0


def test_absent_shares_become_zero_only_where_they_are_defined():
    from authoroved_core.tools.coefficient_validity import fill_absent_shares
    groups = {
        "Деепричастия": "Морфология: части речи",
        "Существительные · падеж: звательная форма": "Категории: Существительные",
        "Существительные · падеж: именительный": "Категории: Существительные",
        "Причастия · залог: страдательный": "Категории: Причастия",
        "Индекс 13. Деепричастия / объём текста": "Морфологические индексы идиостиля",
    }
    values = [{"Существительные · падеж: именительный": 0.4}]
    fill_absent_shares(values, groups)
    assert values[0]["Деепричастия"] == 0.0                                   # нет — значит 0
    assert values[0]["Существительные · падеж: звательная форма"] == 0.0       # падеж у сущ. есть
    assert "Причастия · залог: страдательный" not in values[0]                 # причастий нет вовсе
    assert "Индекс 13. Деепричастия / объём текста" not in values[0]           # отношение не трогаем
