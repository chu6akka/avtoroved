"""Transparent feature detectors for shadow-only StyleEngineV2.

No detector assigns forensic significance.  AUTO means reproducible detection,
not methodological acceptance.  CANDIDATE_ONLY evidence always requires human
confirmation; EXPERT_ONLY specifications are documented but never asserted.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Iterable, Sequence

from analyzer.semantic_layers.contracts import (
    StyleDetectedFeatureV2,
    StyleFeatureEvidenceV2,
)


STYLE_LABELS = {
    "official_business": "Официально-деловой",
    "scientific": "Научный",
    "publicistic": "Публицистический",
    "oratorical": "Ораторский",
    "conversational": "Разговорный",
}
STYLE_FAMILIES = ("lexical", "morphological", "syntactic", "discourse", "punctuation")
AUTOMATION_STATUSES = {"AUTO", "CANDIDATE_ONLY", "EXPERT_ONLY"}


@dataclass(frozen=True)
class StyleDetectorSpec:
    feature_id: str
    label: str
    style_ids: tuple[str, ...]
    family: str
    automation_status: str
    method_status: str = "AUXILIARY"
    method_feature_id: str | None = None
    role: str = "AUX_METRIC"
    limitations: tuple[str, ...] = ()


STYLE_DETECTOR_SPECS: dict[str, StyleDetectorSpec] = {}


def _spec(feature_id: str, label: str, styles: Sequence[str], family: str,
          automation: str = "AUTO", *, method_status: str = "AUXILIARY",
          limitations: Sequence[str] = ()) -> StyleDetectorSpec:
    item = StyleDetectorSpec(
        feature_id, label, tuple(styles), family, automation,
        method_status=method_status, limitations=tuple(limitations))
    STYLE_DETECTOR_SPECS[feature_id] = item
    return item


SPECS = {
    # official-business
    "abbreviation": _spec("v2.official.abbreviation", "Сокращения и аббревиатуры",
                          ("official_business",), "lexical"),
    "official_cliche": _spec("v2.official.cliche", "Официально-деловые клише",
                             ("official_business",), "discourse"),
    "deverbal": _spec("v2.shared.deverbal_nouns", "Отглагольные существительные",
                      ("official_business", "scientific"), "morphological"),
    "reflexive": _spec("v2.official.reflexive_verbs", "Возвратные глаголы",
                       ("official_business",), "morphological"),
    "participial": _spec("v2.official.participial", "Причастные конструкции",
                         ("official_business",), "syntactic", "CANDIDATE_ONLY",
                         limitations=("Надёжнее при переданной Stanza-разметке.",)),
    "adverbial_participial": _spec(
        "v2.official.adverbial_participial", "Деепричастные конструкции",
        ("official_business",), "syntactic", "CANDIDATE_ONLY",
        limitations=("Надёжнее при переданной Stanza-разметке.",)),
    "enumeration": _spec("v2.official.enumeration", "Сложные перечисления",
                         ("official_business",), "punctuation"),
    # scientific
    "definition": _spec("v2.scientific.definition", "Определительные конструкции",
                        ("scientific",), "syntactic"),
    "logical": _spec("v2.scientific.logical_connectors", "Логические связки",
                     ("scientific",), "discourse"),
    "citation": _spec("v2.scientific.citation", "Ссылки и цитирование",
                      ("scientific",), "punctuation"),
    "terminology": _spec(
        "v2.scientific.terminology_candidate", "Терминологическая лексика",
        ("scientific",), "lexical", "CANDIDATE_ONLY",
        limitations=("Редкое слово само по себе не считается термином.",)),
    "genitive_chain": _spec(
        "v2.scientific.genitive_chain", "Цепочка родительного падежа",
        ("scientific",), "syntactic", "CANDIDATE_ONLY",
        limitations=("Доступно только при переданной морфологической разметке.",)),
    "repetition": _spec(
        "v2.shared.lexical_repetition", "Лексический повтор-кандидат",
        ("scientific", "publicistic", "oratorical"), "discourse",
        "CANDIDATE_ONLY", limitations=("Функцию повтора подтверждает эксперт.",)),
    # publicistic
    "evaluative": _spec(
        "v2.publicistic.evaluative_lexicon", "Оценочная/эмоциональная лексика",
        ("publicistic",), "lexical", "CANDIDATE_ONLY",
        limitations=("Используется существующий RuSentiLex; контекст проверяет эксперт.",)),
    "quotation": _spec("v2.publicistic.quotation", "Кавычки и цитирование",
                       ("publicistic",), "punctuation"),
    "exclamation": _spec("v2.publicistic.exclamation", "Экспрессивная пунктуация",
                         ("publicistic",), "punctuation"),
    "parceling": _spec(
        "v2.publicistic.parceling_candidate", "Парцелляция-кандидат",
        ("publicistic",), "syntactic", "CANDIDATE_ONLY",
        limitations=("Короткое предложение не равно парцелляции.",)),
    "metaphor": _spec(
        "v2.publicistic.metaphor", "Метафора", ("publicistic",), "discourse",
        "EXPERT_ONLY", limitations=("Автоматически не устанавливается.",)),
    # oratorical
    "direct_address": _spec("v2.oratorical.direct_address", "Прямое обращение",
                            ("oratorical",), "discourse"),
    "question_answer": _spec("v2.oratorical.question_answer", "Вопросно-ответная форма",
                             ("oratorical",), "discourse"),
    "rhetorical_question": _spec(
        "v2.oratorical.rhetorical_question_candidate", "Риторический вопрос-кандидат",
        ("oratorical",), "discourse", "CANDIDATE_ONLY",
        limitations=("Обычный вопрос не является риторическим.",)),
    "imperative": _spec("v2.oratorical.imperative", "Императивность",
                        ("oratorical",), "morphological"),
    "audience": _spec("v2.oratorical.audience_address", "Обращение к аудитории",
                      ("oratorical",), "lexical"),
    # conversational
    "particles": _spec("v2.conversational.particles", "Разговорные частицы",
                       ("conversational",), "lexical"),
    "stratified": _spec(
        "v2.conversational.stratified_lexicon", "Разговорная/сниженная лексика",
        ("conversational",), "lexical", "CANDIDATE_ONLY",
        limitations=("Используется существующая стратификация и её фильтры.",)),
    "ellipsis": _spec("v2.conversational.ellipsis_candidate", "Эллипсис-кандидат",
                      ("conversational",), "punctuation", "CANDIDATE_ONLY"),
    "incomplete": _spec(
        "v2.conversational.incomplete_sentence", "Неполное предложение-кандидат",
        ("conversational",), "syntactic", "CANDIDATE_ONLY",
        limitations=("Формальный proxy не устанавливает эллипсис.",)),
    "internet": _spec(
        "v2.experimental.internet_marker", "Интернет-маркер",
        ("conversational",), "punctuation", "AUTO", method_status="EXPERIMENTAL",
        limitations=("Не является METHOD_FEATURE разговорного стиля.",)),
    "communicative_tone": _spec(
        "v2.expert.communicative_tone", "Коммуникативный тон",
        ("oratorical", "conversational"), "discourse", "EXPERT_ONLY",
        limitations=("Требует экспертного исследования.",)),
}


_WORD_RE = re.compile(r"[A-Za-zА-Яа-яЁё]+", re.UNICODE)


def _matches(pattern: str, text: str, flags: int = re.IGNORECASE) -> list[re.Match]:
    return list(re.finditer(pattern, text, flags))


def _literal_matches(values: Iterable[str], text: str) -> list[re.Match]:
    escaped = sorted((re.escape(value) for value in values), key=len, reverse=True)
    if not escaped:
        return []
    return _matches(r"(?<!\w)(?:" + "|".join(escaped) + r")(?!\w)", text)


def _make_features(spec: StyleDetectorSpec, matches: Sequence[object], text: str,
                   base_offset: int, raw_count: int | None = None
                   ) -> list[StyleDetectedFeatureV2]:
    if spec.automation_status == "EXPERT_ONLY":
        return []
    count = raw_count if raw_count is not None else len(matches)
    if count <= 0:
        return []
    normalized = round(min(1.0, count / 3.0), 6)
    output: list[StyleDetectedFeatureV2] = []
    for style_id in spec.style_ids:
        evidence: list[StyleFeatureEvidenceV2] = []
        for match in matches[:12]:
            start = int(getattr(match, "start")()) if callable(getattr(match, "start", None)) else int(match[0])
            end = int(getattr(match, "end")()) if callable(getattr(match, "end", None)) else int(match[1])
            fragment = text[start:end]
            evidence.append(StyleFeatureEvidenceV2(
                feature_id=spec.feature_id, style_id=style_id, family=spec.family,
                automation_status=spec.automation_status, role="EVIDENCE",
                start=base_offset + start, end=base_offset + end, fragment=fragment,
                raw_value=1.0, normalized_value=normalized,
                method_status=spec.method_status,
                method_feature_id=spec.method_feature_id, accepted=False))
        output.append(StyleDetectedFeatureV2(
            feature_id=spec.feature_id, label=spec.label, style_id=style_id,
            family=spec.family, automation_status=spec.automation_status,
            role=spec.role, raw_count=count, normalized_value=normalized,
            evidence=tuple(evidence), method_status=spec.method_status,
            method_feature_id=spec.method_feature_id, accepted=False,
            limitations=spec.limitations, expert_identification_value=None))
    return output


def _token_spans(tokens: Sequence[object], segment_start: int,
                 segment_end: int, predicate: Callable[[object], bool]
                 ) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    for token in tokens:
        start = int(getattr(token, "char_start", 0) or 0)
        end = int(getattr(token, "char_end", 0) or 0)
        if start >= segment_start and end <= segment_end and end > start and predicate(token):
            spans.append((start - segment_start, end - segment_start))
    return spans


def detect_style_features(text: str, *, base_offset: int = 0,
                          parsed_tokens: Sequence[object] = (),
                          stratification_result=None, sentiment_result=None
                          ) -> tuple[StyleDetectedFeatureV2, ...]:
    """Detect formal signals once, then map shared signals to style rows."""
    found: list[StyleDetectedFeatureV2] = []

    def add(key: str, matches: Sequence[object], raw_count: int | None = None):
        found.extend(_make_features(SPECS[key], matches, text, base_offset, raw_count))

    add("abbreviation", _matches(r"(?<![А-ЯЁA-Z])[А-ЯЁA-Z]{2,6}(?![А-ЯЁA-Z])", text, 0))
    add("official_cliche", _literal_matches((
        "в соответствии с", "на основании", "в установленном порядке",
        "настоящим уведомляем", "подлежит исполнению", "приказываю",
    ), text))
    add("deverbal", _matches(
        r"\b[А-Яа-яЁё]{4,}(?:ние|ция|ство|ание|ение|ирование|изация)(?:м|ми|х|ю|я|е|ы|и|й)?\b", text))
    add("reflexive", _matches(r"\b[А-Яа-яЁё]{3,}(?:ться|тся)\b", text))
    add("enumeration", _matches(r"(?:^|\n)\s*(?:\d+[.)]|[-–—•])\s+|:[^.!?\n]+(?:;[^.!?\n]+){1,}", text))

    part_spans = _token_spans(parsed_tokens, base_offset, base_offset + len(text),
        lambda token: ("VerbForm=Part" in str(getattr(token, "feats", ""))
                       or getattr(token, "pos_label", "") == "Причастие"))
    conv_spans = _token_spans(parsed_tokens, base_offset, base_offset + len(text),
        lambda token: ("VerbForm=Conv" in str(getattr(token, "feats", ""))
                       or getattr(token, "pos_label", "") == "Деепричастие"))
    add("participial", part_spans)
    add("adverbial_participial", conv_spans)

    add("definition", _matches(
        r"\b(?:определяется|называется|понимается)\s+(?:как|под)|"
        r"\bпод\s+[^.!?]{2,80}\s+понимается\b", text))
    add("logical", _literal_matches((
        "следовательно", "таким образом", "во-первых", "во-вторых",
        "поскольку", "исходя из этого", "как показано", "так как",
    ), text))
    add("citation", _matches(
        r"\[\s*\d+(?:\s*[-,;]\s*\d+)*\s*\]|\([^()]{2,40},\s*(?:19|20)\d{2}\)|"
        r"\b(?:ГОСТ|doi)\s*[:№]?\s*[\w./-]+", text))
    add("terminology", _matches(
        r"\b(?:термин|понятие|методология|гипотеза|корреляция|выборка|эмпирическ\w*|"
        r"[А-Яа-яЁё]{4,}(?:логия|метрия|скопия))\b", text))

    genitive = _token_spans(parsed_tokens, base_offset, base_offset + len(text),
        lambda token: ("Case=Gen" in str(getattr(token, "feats", ""))
                       or "родительный" in str(getattr(token, "feats", "")).lower()))
    adjacent_genitive: list[tuple[int, int]] = []
    for left, right in zip(genitive, genitive[1:]):
        between = text[left[1]:right[0]]
        if len(_WORD_RE.findall(between)) <= 1:
            adjacent_genitive.append((left[0], right[1]))
    add("genitive_chain", adjacent_genitive)

    words = [(m.group().lower(), m.start(), m.end()) for m in _WORD_RE.finditer(text)]
    positions: dict[str, list[tuple[int, int]]] = {}
    for word, start, end in words:
        if len(word) >= 5:
            positions.setdefault(word, []).append((start, end))
    repeated = [span for spans in positions.values() if len(spans) >= 3 for span in spans]
    add("repetition", repeated, raw_count=len({word for word, spans in positions.items()
                                               if len(spans) >= 3}))

    sentiment_spans: list[tuple[int, int]] = []
    if sentiment_result is not None:
        opinion_forms = {
            word.form.lower() for word in (
                list(getattr(sentiment_result, "positive_words", ()))
                + list(getattr(sentiment_result, "negative_words", ())))
            if getattr(word, "stype", "") in {"opinion", "feeling"}
        }
        sentiment_spans = [(m.start(), m.end()) for m in _WORD_RE.finditer(text)
                           if m.group().lower() in opinion_forms]
    add("evaluative", sentiment_spans)
    add("quotation", _matches(r"[«„\"](?:[^»“\"]{2,160})[»“\"]", text))
    add("exclamation", _matches(r"!+", text))

    sentences = list(re.finditer(r"(?:^|(?<=[.!?…]))\s*([^.!?…]+[.!?…]?)", text))
    short_sentences = [m for m in sentences
                       if 1 <= len(_WORD_RE.findall(m.group(1))) <= 3]
    # Один короткий фрагмент не образует парцелляцию и не должен превращать
    # одиночный знак препинания во второе независимое семейство.
    add("parceling", short_sentences if len(short_sentences) >= 2 else ())

    add("direct_address", _matches(
        r"\b(?:уважаемые|дорогие)\s+[А-Яа-яЁё -]{2,40}[,!]|"
        r"\b(?:граждане|коллеги|друзья|товарищи)[,!]", text))
    add("question_answer", _matches(r"[^.!?]{3,120}\?\s*(?:Да|Нет|Ответ|Конечно|Итак)[,!:.]?", text))
    add("rhetorical_question", _matches(r"\b(?:разве|неужели|кто же|как же)\b[^?]{0,120}\?", text))

    imperative_spans = _token_spans(parsed_tokens, base_offset, base_offset + len(text),
        lambda token: ("Mood=Imp" in str(getattr(token, "feats", ""))
                       or "повелитель" in str(getattr(token, "feats", "")).lower()))
    imperative_spans.extend((m.start(), m.end()) for m in _literal_matches(
        ("давайте", "позвольте", "помните", "встаньте", "обратимся"), text))
    add("imperative", imperative_spans)
    add("audience", _literal_matches((
        "мы с вами", "каждый из нас", "обращаюсь к вам", "перед нами",
        "наша общая", "наши сердца",
    ), text))

    add("particles", _literal_matches((
        "ну", "вот", "уж", "короче", "как бы", "так сказать", "в общем",
    ), text))
    if stratification_result is not None:
        reduced_layers = {
            "obscene", "criminal_jargon", "drug_jargon", "youth_jargon",
            "general_jargon", "vernacular", "colloquial_reduced",
        }
        spans = []
        for token in getattr(stratification_result, "tokens", ()):
            if getattr(token, "layer", "") in reduced_layers:
                start = int(getattr(token, "start", 0)) - base_offset
                end = int(getattr(token, "end", 0)) - base_offset
                if 0 <= start < end <= len(text):
                    spans.append((start, end))
        add("stratified", spans)
    add("ellipsis", _matches(r"…|\.\.\.", text))
    incomplete = [m for m in short_sentences if not re.search(
        r"\b[А-Яа-яЁё]{3,}(?:ет|ут|ют|ит|ат|ят|ал|ала|али|ил|ила|или|ть|ться)\b",
        m.group(1), re.IGNORECASE)]
    add("incomplete", incomplete)
    add("internet", _matches(r"(?:[:;]-?[)(DР]|\){2,}|\b(?:лол|имхо|кек)\b|#[\wА-Яа-яЁё]+)", text))

    return tuple(found)
