"""Какие морфологические коэффициенты различают авторов и с какого объёма текста.

Две проверки на корпусе Pilot 02c (120 авторов, у каждого 4 основных и 2 резервных
текста Pikabu, ~466 слов). Это проверка ПРИГОДНОСТИ ПРИЗНАКОВ, а не точности
установления автора программой: корпус для такого заявления не предназначен
(см. README корпуса), порогов и вывода о тождестве отсюда не следует.

1. Различительная сила (основные тексты, 480 шт.). Для каждого показателя:
   - AUC — вероятность того, что у двух текстов РАЗНЫХ авторов значения
     расходятся сильнее, чем у двух текстов ОДНОГО автора (0,5 — признак ничего не
     говорит об авторе, 1,0 — разделяет полностью);
   - p — перестановочный тест: метки авторов случайно переставляются между текстами
     (по 4 на автора), и считается, как часто случайная разметка даёт AUC не хуже
     наблюдаемого. Пары текстов зависимы (один текст входит во многие пары), поэтому
     обычные формулы для AUC здесь завысили бы значимость, а перестановка — нет;
   - q — поправка Бенджамини–Хохберга на число проверяемых показателей;
   - ICC — доля разброса значений, объясняемая автором (внутриклассовая корреляция);
   - AUC без общих тем — та же мера только на парах текстов, у которых нет ни одной
     общей метки Pikabu: так снимается подозрение, что показатель различает темы.

2. Объём текста. Тексты автора (все 6) соединяются (~2800 слов); из них случайно
   берутся два непересекающихся фрагмента по N слов. Для каждого N и показателя:
   - AUC фрагментов (как в п. 1, но на фрагментах длины N);
   - отклонение — медиана относительной разницы между значением на фрагменте и на
     всём материале автора. Минимальный объём — наименьшее N, начиная с которого
     отклонение не больше 20 % (и 10 %).
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
import random
import re
from time import perf_counter

import numpy as np

from authoroved_core.core.models import Token
from authoroved_core.metrics.morphology import (
    GROUP_BIGRAMS, GROUP_PARTS, GROUP_PRONOUNS, category_scope, morphology_metrics,
)
from authoroved_core.tools.corpus_tokens import DEFAULT_CORPUS, load_tokens, read_documents

LENGTHS = (100, 200, 300, 500, 750, 1000, 1300)
SEED = 20261002
_NUMBER = re.compile(r"-?\d+(?:,\d+)?")


def metric_number(value: str) -> float | None:
    """Число из строкового значения показателя: доля (0..1) или отношение."""
    if not value or value.startswith(("Нет данных", "Не рассчитывается")):
        return None
    if "%" in value:
        match = re.search(r"(-?\d+(?:,\d+)?) %", value)
        return float(match.group(1).replace(",", ".")) / 100 if match else None
    match = _NUMBER.match(value)
    return float(match.group().replace(",", ".")) if match else None


def is_word(token: Token) -> bool:
    return token.pos not in {"PUNCT", "SYM"} and any(char.isalpha() for char in token.text)


def sentence_metrics(tokens: list[Token]) -> dict[str, float]:
    lengths = defaultdict(int)
    for token in tokens:
        if is_word(token):
            lengths[token.sentence] += 1
    values = [value for value in lengths.values() if value]
    if not values:
        return {}
    return {
        "Средняя длина предложения (слов)": sum(values) / len(values),
        "Доля предложений до 5 слов": sum(v <= 5 for v in values) / len(values),
        "Доля предложений от 20 слов": sum(v >= 20 for v in values) / len(values),
    }


def metric_group(metric) -> str:
    scope = category_scope(metric.group)
    return f"Категории: {scope}" if scope else metric.group


def numeric_metrics(tokens: list[Token]) -> tuple[dict[str, float], dict[str, str]]:
    """Все числовые показатели морфологии и длины предложений для набора токенов.

    Сочетания частей речи не берутся: программа выводит только 20 самых частых в
    данном тексте, и отсутствие сочетания не означает нулевую долю.
    """
    values, groups = {}, {}
    for metric in morphology_metrics(tokens):
        if metric.group == GROUP_BIGRAMS:
            continue
        number = metric_number(metric.value)
        if number is not None:
            values[metric.name] = number
            groups[metric.name] = metric_group(metric)
    for name, number in sentence_metrics(tokens).items():
        values[name] = number
        groups[name] = "Предложения"
    return values, groups


ZERO_WHEN_ABSENT = {GROUP_PARTS, GROUP_PRONOUNS}


def fill_absent_shares(per_doc: list[dict[str, float]], groups: dict[str, str]) -> None:
    """Достраивает нулевые доли, которые программа не выводит, потому что их нет.

    Части речи и разряды местоимений: нет в тексте — доля 0. Значение категории
    («Существительные · падеж: звательная форма»): 0, если сама категория у этой части
    речи в тексте есть (выведено хоть одно её значение); иначе доля не определена.
    """
    names = set(groups)
    for values in per_doc:
        present_prefixes = {name.rsplit(":", 1)[0] for name in values
                            if groups.get(name, "").startswith("Категории:")}
        for name in names - values.keys():
            group = groups[name]
            if group in ZERO_WHEN_ABSENT:
                values[name] = 0.0
            elif group.startswith("Категории:") and name.rsplit(":", 1)[0] in present_prefixes:
                values[name] = 0.0


# ── статистика ───────────────────────────────────────────────────────────────

def auc_from_sorted(all_sorted: np.ndarray, same: np.ndarray) -> float | None:
    """AUC «разные авторы расходятся сильнее одного» по расстояниям.

    all_sorted — отсортированные расстояния ВСЕХ пар, same — расстояния пар одного
    автора (они входят в all). Разные = все минус свои; вклад «свои против своих»
    ровно |S|²/2 по симметрии, поэтому его можно вычесть без перебора.
    """
    n_all, n_same = len(all_sorted), len(same)
    n_different = n_all - n_same
    if not n_same or not n_different:
        return None
    greater = n_all - np.searchsorted(all_sorted, same, side="right")
    equal = np.searchsorted(all_sorted, same, side="right") - np.searchsorted(all_sorted, same, side="left")
    wins = float(greater.sum() + 0.5 * equal.sum()) - n_same * n_same / 2
    return wins / (n_same * n_different)


def pair_index(count: int) -> tuple[np.ndarray, np.ndarray]:
    left, right = np.triu_indices(count, k=1)
    return left, right


def icc1(values: np.ndarray, labels: np.ndarray) -> float | None:
    """ICC(1): доля дисперсии, объясняемая автором (однофакторный дисперсионный анализ)."""
    groups = [values[labels == label] for label in np.unique(labels)]
    groups = [group for group in groups if len(group) >= 1]
    total = len(values)
    a = len(groups)
    if a < 2 or total <= a:
        return None
    grand = values.mean()
    ss_between = sum(len(g) * (g.mean() - grand) ** 2 for g in groups)
    ss_within = sum(((g - g.mean()) ** 2).sum() for g in groups)
    ms_between = ss_between / (a - 1)
    ms_within = ss_within / (total - a)
    n0 = (total - sum(len(g) ** 2 for g in groups) / total) / (a - 1)
    denominator = ms_between + (n0 - 1) * ms_within
    return float((ms_between - ms_within) / denominator) if denominator > 0 else None


def benjamini_hochberg(p_values: dict[str, float]) -> dict[str, float]:
    items = sorted(p_values.items(), key=lambda item: item[1])
    total = len(items)
    q, running = {}, 1.0
    for rank in range(total, 0, -1):
        name, p = items[rank - 1]
        running = min(running, p * total / rank)
        q[name] = running
    return q


def same_pairs(labels: np.ndarray, left: np.ndarray, right: np.ndarray) -> np.ndarray:
    """Номера пар (в общем списке пар) из текстов с одинаковой меткой автора."""
    return np.flatnonzero(labels[left] == labels[right])


def discrimination(distances: np.ndarray, keep: np.ndarray, observed_same: np.ndarray,
                   permuted_same: list[np.ndarray]) -> dict:
    """AUC и перестановочный p для одного показателя.

    distances — расстояния всех пар (NaN, если у текста нет значения), keep — какие
    пары участвуют (например, без общих тем), observed_same — пары одного автора,
    permuted_same — те же пары при случайных перестановках меток (общие для всех
    показателей, чтобы не пересчитывать их заново).
    """
    usable = keep & ~np.isnan(distances)
    all_sorted = np.sort(distances[usable])

    def auc_for(indices):
        selected = indices[usable[indices]]
        return auc_from_sorted(all_sorted, distances[selected]), len(selected)

    observed, same_count = auc_for(observed_same)
    if observed is None:
        return {"auc": None, "p": None, "same_pairs": same_count,
                "different_pairs": int(usable.sum()) - same_count}
    exceed = sum(1 for indices in permuted_same
                 if (value := auc_for(indices)[0]) is not None and value >= observed)
    p = (exceed + 1) / (len(permuted_same) + 1) if permuted_same else None
    return {"auc": round(observed, 4), "p": p, "same_pairs": same_count,
            "different_pairs": int(usable.sum()) - same_count}


def fragment_auc(values: np.ndarray, labels: np.ndarray) -> float | None:
    left, right = pair_index(len(values))
    distances = np.abs(values[left] - values[right])
    return auc_from_sorted(np.sort(distances), distances[labels[left] == labels[right]])


# ── проверка 1 ────────────────────────────────────────────────────────────────

def study_discrimination(corpus: Path, documents: list[dict], permutations: int) -> dict:
    main = [doc for doc in documents if not doc["reserve"]]
    per_doc, groups = [], {}
    for doc in main:
        values, metric_groups = numeric_metrics(load_tokens(corpus, doc))
        per_doc.append(values)
        groups.update(metric_groups)
    fill_absent_shares(per_doc, groups)
    authors = np.array([doc["author"] for doc in main])
    tags = [doc["tags"] for doc in main]
    left, right = pair_index(len(main))
    everything = np.ones(len(left), dtype=bool)
    disjoint_all = np.array([not (tags[i] & tags[j]) and bool(tags[i]) and bool(tags[j])
                             for i, j in zip(left, right)])
    rng = np.random.default_rng(SEED)
    observed_same = same_pairs(authors, left, right)
    permuted_same = []
    labels = authors.copy()
    for _ in range(permutations):
        rng.shuffle(labels)
        permuted_same.append(same_pairs(labels, left, right))
    results = {}
    names = sorted({name for values in per_doc for name in values})
    for name in names:
        present = np.array([name in values for values in per_doc])
        # Показатель, который у большинства текстов не определён, не сравниваем.
        if present.sum() < 0.8 * len(main):
            continue
        values = np.array([values.get(name, np.nan) for values in per_doc], dtype=float)
        observed = values[present]
        if np.allclose(observed, observed[0]):
            continue
        distances = np.abs(values[left] - values[right])
        full = discrimination(distances, everything, observed_same, permuted_same)
        neutral = discrimination(distances, disjoint_all, observed_same, permuted_same)
        idx = np.flatnonzero(present)
        values, labels = observed, authors[idx]
        results[name] = {
            "group": groups.get(name, ""), "texts": int(len(idx)),
            "auc": full["auc"], "p": full["p"],
            "same_pairs": full["same_pairs"], "different_pairs": full["different_pairs"],
            "icc": None if (value := icc1(values, labels)) is None else round(value, 4),
            "auc_topic_neutral": neutral["auc"], "p_topic_neutral": neutral["p"],
            "same_pairs_topic_neutral": neutral["same_pairs"],
            "different_pairs_topic_neutral": neutral["different_pairs"],
            "median": round(float(np.median(values)), 4),
        }
    q = benjamini_hochberg({name: item["p"] for name, item in results.items() if item["p"] is not None})
    q_neutral = benjamini_hochberg({name: item["p_topic_neutral"] for name, item in results.items()
                                    if item["p_topic_neutral"] is not None})
    for name, item in results.items():
        item["q"] = round(q[name], 4) if name in q else None
        item["q_topic_neutral"] = round(q_neutral[name], 4) if name in q_neutral else None
        item["verdict"] = verdict(item)
    return {
        "texts": len(main), "authors": int(len(np.unique(authors))),
        "permutations": permutations,
        "topic_neutral_pairs_share": round(float(disjoint_all.mean()), 4),
        "by_metric": dict(sorted(results.items(), key=lambda kv: -(kv[1]["auc"] or 0))),
    }


def verdict(item: dict) -> str:
    """Словесная оценка: держится ли различие после поправки и без общих тем."""
    if item["auc"] is None or item["q"] is None:
        return "нет данных"
    survives_topic = item["q_topic_neutral"] is not None and item["q_topic_neutral"] < 0.05
    if item["q"] < 0.05 and item["auc"] >= 0.6 and survives_topic:
        return "различает авторов"
    if item["q"] < 0.05 and survives_topic:
        return "слабо различает"
    if item["q"] < 0.05:
        return "различает, но не без общих тем"
    return "не отличается от случайного"


# ── проверка 2 ────────────────────────────────────────────────────────────────

def author_streams(corpus: Path, documents: list[dict]) -> dict[str, list[Token]]:
    """Все тексты автора подряд; номера предложений сдвигаются, чтобы не слипались."""
    streams: dict[str, list[Token]] = defaultdict(list)
    offsets: dict[str, int] = defaultdict(int)
    for doc in documents:
        tokens = load_tokens(corpus, doc)
        shift = offsets[doc["author"]]
        top = 0
        for token in tokens:
            streams[doc["author"]].append(Token(token.text, token.lemma, token.pos, token.feats,
                                                token.dependency, token.head, token.sentence + shift,
                                                token.index, None))
            top = max(top, token.sentence + shift)
        offsets[doc["author"]] = top + 1
    return streams


def window(tokens: list[Token], word_positions: list[int], start_word: int, length: int) -> list[Token]:
    """Фрагмент из `length` слов подряд (с пунктуацией между ними)."""
    begin = word_positions[start_word]
    end = word_positions[start_word + length - 1] + 1
    return tokens[begin:end]


def study_length(corpus: Path, documents: list[dict], repetitions: int, lengths=LENGTHS) -> dict:
    streams = author_streams(corpus, documents)
    authors = sorted(streams)
    positions = {author: [i for i, t in enumerate(streams[author]) if is_word(t)] for author in authors}
    full, groups = {}, {}
    for author in authors:
        full[author], author_groups = numeric_metrics(streams[author])
        groups.update(author_groups)
    fill_absent_shares(list(full.values()), groups)
    rng = random.Random(SEED)
    result: dict[str, dict] = defaultdict(dict)
    for length in lengths:
        eligible = [a for a in authors if len(positions[a]) >= 2 * length]
        aucs: dict[str, list[float]] = defaultdict(list)
        deviations: dict[str, list[float]] = defaultdict(list)
        for _ in range(repetitions):
            fragment_values, fragment_authors = [], []
            for author in eligible:
                total = len(positions[author])
                first = rng.randrange(0, total - 2 * length + 1)
                second = rng.randrange(first + length, total - length + 1)
                for start in (first, second):
                    values, fragment_groups = numeric_metrics(
                        window(streams[author], positions[author], start, length))
                    groups.update(fragment_groups)
                    fragment_values.append(values)
                    fragment_authors.append(author)
            fill_absent_shares(fragment_values, groups)
            for values, author in zip(fragment_values, fragment_authors):
                for name, value in values.items():
                    reference = full[author].get(name)
                    if reference:
                        deviations[name].append(abs(value - reference) / abs(reference))
            labels = np.array(fragment_authors)
            for name in {n for values in fragment_values for n in values}:
                present = [i for i, values in enumerate(fragment_values) if name in values]
                if len(present) < 0.8 * len(fragment_values):
                    continue
                values = np.array([fragment_values[i][name] for i in present])
                if np.allclose(values, values[0]):
                    continue
                value = fragment_auc(values, labels[present])
                if value is not None:
                    aucs[name].append(value)
        for name in set(aucs) | set(deviations):
            result[name][str(length)] = {
                "auc": round(float(np.mean(aucs[name])), 4) if aucs.get(name) else None,
                "deviation": round(float(np.median(deviations[name])), 4) if deviations.get(name) else None,
                "authors": len(eligible),
            }
    summary = {}
    for name, by_length in result.items():
        summary[name] = {
            "by_length": by_length,
            "min_words_20": minimum_length(by_length, 0.20),
            "min_words_10": minimum_length(by_length, 0.10),
        }
    return {"lengths": list(lengths), "repetitions": repetitions,
            "authors": len(authors), "by_metric": summary}


def minimum_length(by_length: dict, tolerance: float) -> int | None:
    """Наименьший объём, начиная с которого отклонение не превышает допуска."""
    lengths = sorted(int(key) for key in by_length)
    answer = None
    for length in reversed(lengths):
        deviation = by_length[str(length)]["deviation"]
        if deviation is None or deviation > tolerance:
            break
        answer = length
    return answer


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--permutations", type=int, default=999)
    parser.add_argument("--repetitions", type=int, default=20)
    parser.add_argument("--output", type=Path,
                        default=Path("authoroved_core/artifacts/coefficient_validity.json"))
    args = parser.parse_args()
    started = perf_counter()
    documents = read_documents(args.corpus)
    print("Проверка 1: различительная сила…", flush=True)
    first = study_discrimination(args.corpus, documents, args.permutations)
    print(f"  готово за {perf_counter() - started:.0f} с; проверка 2: объём текста…", flush=True)
    second = study_length(args.corpus, documents, args.repetitions)
    report = {
        "kind": "Проверка пригодности морфологических коэффициентов; не оценка точности установления автора",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "corpus": str(args.corpus), "seed": SEED,
        "seconds": round(perf_counter() - started, 1),
        "discrimination": first, "length": second,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"отчёт: {args.output} · {report['seconds']} с")


if __name__ == "__main__":
    main()
