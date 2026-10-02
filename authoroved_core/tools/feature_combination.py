"""Совокупность признаков против лучшего одиночного: перекрёстная проверка по авторам.

Вопрос: различает ли авторов набор морфологических показателей лучше, чем самый
сильный из них по отдельности (AUC около 0,65 на текстах ~466 слов).

Чтобы не подогнать комбинацию под те же данные, на которых она оценивается,
авторы делятся на 5 групп. Отбор показателей, нормировка и веса считаются на
четырёх группах, оценка — на пятой, чьих текстов модель не видела; так по кругу,
и всё это повторяется с несколькими случайными разбиениями.

Расстояние между текстами для набора показателей — среднее модулей разностей
нормированных значений (z-оценок, нормировка по обучающим текстам); для одного
показателя это просто модуль разности. Взвешенный вариант — логистическая
регрессия по тем же модулям разностей, обученная отличать пары одного автора от пар
разных (классы уравновешены, L2-регуляризация).

Мера — AUC, как в проверке одиночных коэффициентов. Это проверка пригодности
признаков, а не точности установления автора программой; порогов и вывода о
тождестве отсюда не следует.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import random
from time import perf_counter

import numpy as np

from authoroved_core.tools.coefficient_validity import (
    SEED, auc_from_sorted, author_streams, fill_absent_shares, is_word, numeric_metrics,
    pair_index, window,
)
from authoroved_core.tools.corpus_tokens import DEFAULT_CORPUS, load_tokens, read_documents

FOLDS = 5
TOP_K = 10
CLASSIC_PREFIXES = ("Индекс ", "Коэффициент ")
METHODS = (
    ("single", "Лучший одиночный показатель (выбран на обучающих авторах)"),
    ("classic", "Классические коэффициенты, равные веса"),
    (f"top{TOP_K}", f"{TOP_K} лучших показателей (выбраны на обучающих авторах), равные веса"),
    ("all", "Все показатели, равные веса"),
    ("logistic", "Все показатели, веса по логистической регрессии"),
)


def build_matrix(per_doc: list[dict[str, float]], min_share: float = 0.8) -> tuple[np.ndarray, list[str]]:
    """Матрица «текст × показатель» (NaN — значение не определено)."""
    names = sorted({name for values in per_doc for name in values})
    keep = [name for name in names if sum(name in values for values in per_doc) >= min_share * len(per_doc)]
    matrix = np.array([[values.get(name, np.nan) for name in keep] for values in per_doc], dtype=float)
    return matrix, keep


def author_folds(authors: np.ndarray, folds: int, seed: int) -> list[np.ndarray]:
    unique = np.unique(authors)
    rng = np.random.default_rng(seed)
    rng.shuffle(unique)
    return [np.isin(authors, chunk) for chunk in np.array_split(unique, folds)]


def pair_features(z: np.ndarray, left: np.ndarray, right: np.ndarray) -> np.ndarray:
    return np.abs(z[left] - z[right])


def auc(scores: np.ndarray, same: np.ndarray) -> float | None:
    """AUC расстояния: у разных авторов оно должно быть больше. NaN не участвуют."""
    usable = ~np.isnan(scores)
    scores, same = scores[usable], same[usable]
    if not same.any() or same.all():
        return None
    return auc_from_sorted(np.sort(scores), scores[same])


def logistic_fit(features: np.ndarray, target: np.ndarray, l2: float = 0.01,
                 iterations: int = 25) -> np.ndarray:
    """Логистическая регрессия методом Ньютона; классы уравновешены весами.

    Потери усреднены по уравновешенным весам пар, поэтому сила регуляризации `l2`
    не зависит от числа пар и выбрана заранее (0,01), а не по проверочным авторам.
    Без регуляризации модель на обучающих авторах доходила до AUC 0,77, а на новых
    давала 0,64: веса подгонялись под конкретных людей.
    """
    x = np.hstack([features, np.ones((len(features), 1))])
    positive = target.mean()
    sample = np.where(target == 1, 0.5 / positive, 0.5 / (1 - positive)) / len(target)
    penalty = np.full(x.shape[1], l2)
    penalty[-1] = 0.0                                   # свободный член не штрафуется
    weights = np.zeros(x.shape[1])
    for _ in range(iterations):
        prediction = 1 / (1 + np.exp(-np.clip(x @ weights, -30, 30)))
        gradient = x.T @ (sample * (prediction - target)) + penalty * weights
        curvature = sample * prediction * (1 - prediction)
        hessian = (x * curvature[:, None]).T @ x + np.diag(penalty + 1e-9)
        step = np.linalg.solve(hessian, gradient)
        weights -= step
        if np.abs(step).max() < 1e-6:
            break
    return weights


def evaluate_split(matrix: np.ndarray, names: list[str], authors: np.ndarray, test: np.ndarray,
                   rng: np.random.Generator, max_train_pairs: int = 60000) -> dict[str, float | None]:
    train = ~test
    mean = np.nanmean(matrix[train], axis=0)
    scale = np.nanstd(matrix[train], axis=0)
    scale[scale == 0] = np.nan
    z = (matrix - mean) / scale
    classic = np.array([name.startswith(CLASSIC_PREFIXES) for name in names])

    train_idx, test_idx = np.flatnonzero(train), np.flatnonzero(test)
    tl, tr = pair_index(len(train_idx))
    tl, tr = train_idx[tl], train_idx[tr]
    el, er = pair_index(len(test_idx))
    el, er = test_idx[el], test_idx[er]
    train_same = authors[tl] == authors[tr]
    test_same = authors[el] == authors[er]
    train_diff = pair_features(z, tl, tr)
    test_diff = pair_features(z, el, er)

    single_auc = np.array([auc(train_diff[:, k], train_same) or 0.0 for k in range(len(names))])
    best = int(np.argmax(single_auc))
    top = np.argsort(-single_auc)[:TOP_K]

    def mean_distance(columns):
        with np.errstate(all="ignore"):
            return np.nanmean(test_diff[:, columns], axis=1)

    results = {
        "single": auc(test_diff[:, best], test_same),
        "single_name": names[best],
        "classic": auc(mean_distance(np.flatnonzero(classic)), test_same),
        f"top{TOP_K}": auc(mean_distance(top), test_same),
        "all": auc(mean_distance(np.arange(len(names))), test_same),
    }
    # Логистическая регрессия: обучающих пар десятки тысяч — берём все пары одного автора
    # и случайную часть пар разных, чтобы не гонять гигантскую матрицу.
    same_rows = np.flatnonzero(train_same)
    diff_rows = np.flatnonzero(~train_same)
    if len(diff_rows) > max_train_pairs:
        diff_rows = rng.choice(diff_rows, max_train_pairs, replace=False)
    rows = np.concatenate([same_rows, diff_rows])
    x_train = np.nan_to_num(train_diff[rows])
    y_train = (~train_same[rows]).astype(float)        # 1 — разные авторы
    weights = logistic_fit(x_train, y_train)
    x_test = np.hstack([np.nan_to_num(test_diff), np.ones((len(test_diff), 1))])
    results["logistic"] = auc(x_test @ weights, test_same)
    results["logistic_top"] = [names[k] for k in np.argsort(-weights[:-1])[:8]]
    return results


def cross_validate(matrix: np.ndarray, names: list[str], authors: np.ndarray,
                   repeats: int, seed: int) -> dict:
    rng = np.random.default_rng(seed)
    collected: dict[str, list[float]] = {key: [] for key, _ in METHODS}
    chosen, logistic_top = [], []
    for repeat in range(repeats):
        for test in author_folds(authors, FOLDS, seed + repeat):
            result = evaluate_split(matrix, names, authors, test, rng)
            for key, _ in METHODS:
                if result[key] is not None:
                    collected[key].append(result[key])
            chosen.append(result["single_name"])
            logistic_top.append(result["logistic_top"])
    summary = {}
    for key, title in METHODS:
        values = np.array(collected[key])
        if not len(values):
            summary[key] = {"title": title, "auc": None, "spread": None, "low": None, "high": None, "splits": 0}
            continue
        summary[key] = {
            "title": title, "auc": round(float(values.mean()), 4),
            "spread": round(float(values.std(ddof=1)), 4) if len(values) > 1 else None,
            "low": round(float(np.percentile(values, 2.5)), 4),
            "high": round(float(np.percentile(values, 97.5)), 4),
            "splits": int(len(values)),
        }
    singles = {name: chosen.count(name) for name in set(chosen)}
    weights = {}
    for top in logistic_top:
        for rank, name in enumerate(top):
            weights[name] = weights.get(name, 0) + (len(top) - rank)
    return {
        "methods": summary,
        "single_chosen": dict(sorted(singles.items(), key=lambda kv: -kv[1])),
        "logistic_leading": [name for name, _ in sorted(weights.items(), key=lambda kv: -kv[1])[:10]],
    }


def study_texts(corpus: Path, documents: list[dict], repeats: int) -> dict:
    main = [doc for doc in documents if not doc["reserve"]]
    per_doc, groups = [], {}
    for doc in main:
        values, metric_groups = numeric_metrics(load_tokens(corpus, doc))
        per_doc.append(values)
        groups.update(metric_groups)
    fill_absent_shares(per_doc, groups)
    matrix, names = build_matrix(per_doc)
    authors = np.array([doc["author"] for doc in main])
    result = cross_validate(matrix, names, authors, repeats, SEED)
    result.update({"texts": len(main), "authors": int(len(np.unique(authors))),
                   "features": len(names), "classic_features": sum(n.startswith(CLASSIC_PREFIXES) for n in names)})
    return result


def study_lengths(corpus: Path, documents: list[dict], lengths: tuple[int, ...],
                  fragments_per_author: int, repeats: int) -> dict:
    """Те же методы на фрагментах по N слов (по нескольку фрагментов на автора)."""
    streams = author_streams(corpus, documents)
    authors_all = sorted(streams)
    positions = {a: [i for i, t in enumerate(streams[a]) if is_word(t)] for a in authors_all}
    rng = random.Random(SEED)
    result = {}
    for length in lengths:
        eligible = [a for a in authors_all if len(positions[a]) >= fragments_per_author * length]
        per_fragment, labels, groups = [], [], {}
        for author in eligible:
            total = len(positions[author])
            # Непересекающиеся фрагменты: случайные начала в своих участках потока.
            block = total // fragments_per_author
            for part in range(fragments_per_author):
                start = part * block + rng.randrange(0, block - length + 1)
                values, fragment_groups = numeric_metrics(window(streams[author], positions[author], start, length))
                groups.update(fragment_groups)
                per_fragment.append(values)
                labels.append(author)
        fill_absent_shares(per_fragment, groups)
        matrix, names = build_matrix(per_fragment)
        cv = cross_validate(matrix, names, np.array(labels), repeats, SEED + length)
        result[str(length)] = {"authors": len(eligible), "features": len(names),
                               "methods": {key: value["auc"] for key, value in cv["methods"].items()},
                               "spread": {key: value["spread"] for key, value in cv["methods"].items()}}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--repeats", type=int, default=5, help="сколько раз повторить разбиение на 5 групп")
    parser.add_argument("--output", type=Path, default=Path("authoroved_core/artifacts/feature_combination.json"))
    args = parser.parse_args()
    started = perf_counter()
    documents = read_documents(args.corpus)
    print("Совокупность признаков на целых текстах…", flush=True)
    texts = study_texts(args.corpus, documents, args.repeats)
    for key, value in texts["methods"].items():
        print(f"  {value['auc']:.3f} ±{value['spread']:.3f}  {value['title']}", flush=True)
    print("Зависимость от объёма…", flush=True)
    lengths = study_lengths(args.corpus, documents, (200, 300, 500, 1000), fragments_per_author=2,
                            repeats=max(2, args.repeats // 2))
    report = {
        "kind": "Совокупность морфологических признаков; проверка пригодности, не оценка точности установления автора",
        "generated_at": datetime.now(timezone.utc).isoformat(), "corpus": str(args.corpus), "seed": SEED,
        "folds": FOLDS, "repeats": args.repeats, "seconds": round(perf_counter() - started, 1),
        "texts": texts, "lengths": lengths,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"отчёт: {args.output} · {report['seconds']} с")


if __name__ == "__main__":
    main()
