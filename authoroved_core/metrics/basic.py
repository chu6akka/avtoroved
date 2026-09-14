"""Описательные показатели. Пороги длины — определения, не правила авторства."""
import re
from collections import Counter, defaultdict
from statistics import mean, median

from authoroved_core.core.models import Metric, Span, Token
from authoroved_core.core.russian_word_classes import (
    WORD_CLASSES,
    russian_word_class_key,
)
WORD_PATTERN = re.compile(r"[^\W\d_]+(?:[-’'][^\W\d_]+)*", re.UNICODE)
GLOBAL_NOTE = "Этот показатель относится ко всему тексту и не имеет одного конкретного фрагмента."


def number(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".").replace(".", ",")


def structural_metrics(text: str) -> list[Metric]:
    paragraphs = [line for line in text.splitlines() if line.strip()]
    return [
        Metric("Символы", str(len(text)), "Символы Unicode, включая пробелы и переносы. Эмодзи может состоять из нескольких символов.", "Количественные показатели"),
        Metric("Абзацы", str(len(paragraphs)), "Непустые строки извлечённого текста; пустые строки не учитываются.", "Структура"),
        Metric("Средняя длина абзаца", number(mean([len(WORD_PATTERN.findall(p)) for p in paragraphs])) + " слова" if paragraphs else "Нет данных",
               "Среднее число буквенных последовательностей в непустой строке; внутренний дефис и апостроф сохраняются. Это технический подсчёт, до разметки Stanza.", "Структура"),
        Metric("Многоточия", str(len(re.findall(r"\.{3,}|…", text))), "Один знак … или непрерывная последовательность из трёх и более точек считается одним многоточием.", "Структура",
               tuple(Span(m.start(), m.end()) for m in re.finditer(r"\.{3,}|…", text))),
    ]


def calculate_metrics(text: str, tokens: list[Token]) -> list[Metric]:
    metrics = structural_metrics(text)
    words = [t for t in tokens if t.pos not in {"PUNCT", "SYM"} and any(c.isalpha() for c in t.text)]
    total = len(words)
    definition = "По разметке Stanza: токены с буквами, кроме пунктуации и символов. Чисто цифровые записи исключены."
    metrics.append(Metric("Слова", str(total), definition, "Количественные показатели"))
    forms = Counter(t.text.casefold() for t in words)
    lemmas = Counter(t.lemma.casefold() for t in words)
    metrics.extend([
        Metric("Уникальные словоформы", str(len(forms)), "Без различия регистра; ё и е не объединяются. " + definition, "Лексика"),
        Metric("Уникальные леммы", str(len(lemmas)), "По разметке Stanza, без различия регистра. Разметка может содержать ошибки.", "Лексика"),
        Metric("Лексическое разнообразие", number(len(forms) / total) if total else "Нет данных",
               "Отношение числа уникальных словоформ к общему числу слов. Показатель зависит от объёма текста; не является оценкой автора.", "Лексика"),
    ])
    for title, selected in [
        ("Частотные слова", words),
        ("Частотные знаменательные слова", [
            token for token in words
            if russian_word_class_key(token) in {"noun", "verb", "adjective", "adverb"}
        ]),
    ]:
        counts = Counter(t.text.casefold() for t in selected)
        for form, count in sorted(counts.items(), key=lambda p: (-p[1], p[0]))[:10]:
            metrics.append(Metric(f"{title}: {form}", str(count),
                                  "Число употреблений словоформы без различия регистра. Знаменательные слова отбираются по части речи, без словаря.", "Лексика",
                                  tuple(t.span for t in selected if t.text.casefold() == form and t.span is not None)))
    class_counts = Counter(russian_word_class_key(token) for token in words)
    for item in WORD_CLASSES:
        count = class_counts[item.key]
        if not count:
            continue
        metrics.append(Metric(
            item.title, f"{count} · {number(count / total * 100)} %",
            "Укрупнённая русскоязычная группа для чтения автоматической разметки: "
            f"{item.technical_basis}. Это не ручной морфологический разбор; модель может "
            "ошибочно классифицировать отдельные словоформы.",
            "Морфология",
            tuple(token.span for token in words
                  if russian_word_class_key(token) == item.key and token.span is not None),
        ))
    sentences = defaultdict(list)
    for token in tokens:
        sentences[token.sentence].append(token)
    word_ids = {(t.sentence, t.index) for t in words}
    lengths = [sum((t.sentence, t.index) in word_ids for t in sentence) for sentence in sentences.values()]
    metrics.append(Metric("Предложения", str(len(sentences)), "Границы определены Stanza и могут требовать проверки.", "Количественные показатели"))
    if lengths:
        metrics.extend([
            Metric("Средняя длина предложения", number(mean(lengths)) + " слова", "Число слов / число предложений Stanza. " + definition, "Предложения"),
            Metric("Медианная длина предложения", number(median(lengths)) + " слова", "Середина упорядоченного ряда длин предложений; для чётного числа — среднее двух центральных.", "Предложения"),
            Metric("Предложения до 5 слов", number(sum(n <= 5 for n in lengths) / len(lengths) * 100) + " %", "Доля предложений, содержащих не более 5 слов. Описательный диапазон длины, не экспертный порог.", "Предложения"),
            Metric("Предложения от 20 слов", number(sum(n >= 20 for n in lengths) / len(lengths) * 100) + " %", "Доля предложений, содержащих 20 и более слов. Описательный диапазон длины, не экспертный порог.", "Предложения"),
        ])
    for char, label in [("?", "Предложения с вопросительным знаком"), ("!", "Предложения с восклицательным знаком")]:
        matching = [s for s in sentences.values() if any(char in t.text for t in s)]
        spans = []
        for sentence in matching:
            located = [t.span for t in sentence if t.span is not None]
            if located:
                spans.append(Span(min(s.start for s in located), max(s.end for s in located)))
        metrics.append(Metric(label, str(len(matching)), "Предложения Stanza, содержащие соответствующий знак. Это подсчёт формы, а не коммуникативного намерения.", "Структура", tuple(spans)))
    return metrics
