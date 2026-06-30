# -*- coding: utf-8 -*-
"""
Стенд валидации верификации авторства.
=====================================
Измеряет вероятность ошибки метода «один автор / разные авторы» на корпусе
с ИЗВЕСТНЫМ авторством — это превращает выводы в «выводы с известной надёжностью».

Корпус (папка на автора):
    data/corpus_auth/
        author_01/  text1.txt  text2.txt  text3.txt
        author_02/  ...
        ...

Признаки — те же, что считает программа (стилометрия, без «чёрного ящика»):
    POS-частоты · 20 индексов идиостиля · 20 SAE-коэффициентов · TTR · синтаксис.

Протокол (защитимый, без обучения «вслепую»):
    1. Каждый текст → числовой вектор признаков.
    2. Стандартизация (z-score по корпусу).
    3. Пары: «один автор» (внутри папки) и «разные» (между папками).
    4. Метрика близости пары → порог → решение.
    5. Author-disjoint оценка + отчёт: EER, AUC, FAR/FRR при равном пороге.

Запуск:
    python tools/authorship_eval.py                 # data/corpus_auth
    python tools/authorship_eval.py путь/к/корпусу
"""
from __future__ import annotations
import io
import os
import sys
import glob
import itertools
import random

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

import numpy as np

from analyzer.stanza_backend import StanzaBackend
from analyzer.metrics import calculate_metrics

_DEFAULT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "corpus_auth")

# Фиксированный порядок частей речи для вектора
_POS_ORDER = [
    "Существительное", "Имя собственное", "Глагол", "Прилагательное",
    "Наречие", "Местоимение", "Числительное", "Предлог", "Частица",
    "Сочинительный союз", "Подчинительный союз", "Определительное слово",
    "Причастие", "Деепричастие",
]
_ADD_KEYS = [
    "Средняя длина слова (буквы)", "Лексическое разнообразие (TTR)",
    "Лемматическое разнообразие", "Доля hapax-лемм",
    "Средняя длина предложения (слов)", "Дисперсия длины предложений",
]


def feature_vector(tokens, text) -> np.ndarray:
    """Метрики текста → фиксированный числовой вектор признаков."""
    m = calculate_metrics(tokens, text)
    freq = m.get("частоты", {})
    add = m.get("дополнительно", {})
    vec = []
    # доли частей речи
    for pos in _POS_ORDER:
        vec.append(float(freq.get(pos, {}).get("коэффициент", 0.0)))
    # числовые «дополнительно»
    for k in _ADD_KEYS:
        v = add.get(k, 0.0)
        vec.append(float(v) if isinstance(v, (int, float)) else 0.0)
    # 20 индексов идиостиля
    for (_n, _num, _den, val) in m.get("morph_indices", {}).get("indices", []):
        vec.append(float(val) if isinstance(val, (int, float)) else 0.0)
    # 20 SAE
    for r in m.get("sae_coefficients", {}).get("rows", []):
        v = r.get("value")
        vec.append(float(v) if isinstance(v, (int, float)) else 0.0)
    return np.array(vec, dtype=np.float64)


def load_corpus(root: str):
    """Вернуть {author: [(doc_path, text)]}."""
    corpus = {}
    for author in sorted(os.listdir(root)):
        adir = os.path.join(root, author)
        if not os.path.isdir(adir):
            continue
        docs = []
        for fp in sorted(glob.glob(os.path.join(adir, "*.txt"))):
            try:
                with open(fp, encoding="utf-8") as f:
                    t = f.read().strip()
                if len(t.split()) >= 50:      # отсекаем слишком короткие
                    docs.append((fp, t))
            except Exception:
                pass
        if len(docs) >= 2:
            corpus[author] = docs
    return corpus


def eer_and_auc(same_scores, diff_scores):
    """
    Меньший score = более похожи. «Один автор» должен иметь меньший score.
    Возвращает (EER, порог при EER, AUC).
    """
    same = np.array(same_scores)
    diff = np.array(diff_scores)
    thresholds = np.unique(np.concatenate([same, diff]))
    best = None
    for th in thresholds:
        far = np.mean(diff <= th)   # разные приняты как «один» (ложное совпадение)
        frr = np.mean(same > th)    # один отвергнут как «разные» (ложное различие)
        if best is None or abs(far - frr) < abs(best[1] - best[2]):
            best = (th, far, frr)
    eer = (best[1] + best[2]) / 2
    # AUC (ранговый): доля пар, где «один» ближе «разных»
    auc = np.mean([1.0 if s < d else 0.5 if s == d else 0.0
                   for s in same for d in diff]) if len(same) and len(diff) else float("nan")
    return eer, best[0], auc


def run(root: str):
    print(f"Корпус: {root}")
    corpus = load_corpus(root)
    if len(corpus) < 2:
        print("⚠ Нужно ≥2 авторов, у каждого ≥2 текста (≥50 слов).")
        print("  Структура: data/corpus_auth/<автор>/<текст>.txt")
        return
    n_docs = sum(len(v) for v in corpus.values())
    print(f"Авторов: {len(corpus)} · текстов: {n_docs}")

    print("Загрузка Stanza…")
    st = StanzaBackend(); st.ensure_loaded(lambda m: None)

    # Векторы признаков
    vecs, labels = [], []
    for author, docs in corpus.items():
        for fp, text in docs:
            vecs.append(feature_vector(st.analyze(text), text))
            labels.append(author)
    X = np.vstack(vecs)
    labels = np.array(labels)

    # Стандартизация (z-score), устойчивая к нулевой дисперсии
    mu = X.mean(0); sd = X.std(0); sd[sd == 0] = 1.0
    Xz = (X - mu) / sd

    # Пары
    same_scores, diff_scores = [], []
    n = len(Xz)
    for i, j in itertools.combinations(range(n), 2):
        d = float(np.linalg.norm(Xz[i] - Xz[j]))   # евклидово расстояние
        (same_scores if labels[i] == labels[j] else diff_scores).append(d)

    print(f"Пары: один автор {len(same_scores)} · разные {len(diff_scores)}")
    if not same_scores or not diff_scores:
        print("⚠ Недостаточно пар обоих типов.")
        return

    eer, th, auc = eer_and_auc(same_scores, diff_scores)
    same = np.array(same_scores); diff = np.array(diff_scores)
    far = np.mean(diff <= th); frr = np.mean(same > th)

    print("\n── РЕЗУЛЬТАТ ВАЛИДАЦИИ ──")
    print(f"  AUC (различающая способность): {auc:.3f}  (1.0 идеал, 0.5 = угадывание)")
    print(f"  EER (равная ошибка):            {eer:.1%}")
    print(f"  При пороге EER={th:.2f}:  FAR (ложное совпадение)={far:.1%}  "
          f"FRR (ложное различие)={frr:.1%}")
    print(f"  Ср. расстояние: один автор={same.mean():.2f}  разные={diff.mean():.2f}")
    print("\nИнтерпретация: EER — доля ошибок метода при равном балансе. "
          "Это число и сопровождает экспертный вывод как мера надёжности.")
    print("ВНИМАНИЕ: достоверность растёт с числом авторов/текстов и при совпадении "
          "жанра корпуса с исследуемым материалом (доменный сдвиг!).")


if __name__ == "__main__":
    root = sys.argv[1] if len(sys.argv) > 1 else _DEFAULT_DIR
    if not os.path.isdir(root):
        os.makedirs(root, exist_ok=True)
        print(f"Создана папка корпуса: {root}")
        print("Положите тексты: <автор>/<текст>.txt (≥2 авторов, ≥2 текста каждый) и запустите снова.")
    else:
        run(root)
