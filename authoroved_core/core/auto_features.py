"""Детерминированные вычислители первого среза из десяти AUTO-показателей."""
from __future__ import annotations

from collections import Counter, defaultdict
from statistics import mean, median, pstdev
import re
from typing import Callable

from authoroved_core.core.document import Document
from authoroved_core.core.feature_models import (
    Applicability,
    AutomationMode,
    FeatureDefinition,
    FeatureEvidence,
    FeatureObservation,
)
from authoroved_core.core.feature_registry import FeatureRegistry
from authoroved_core.core.models import Span, Token
from authoroved_core.core.russian_word_classes import (
    CLASS_BY_KEY,
    is_service_word,
    russian_word_class_key,
)


NOMINAL_POS = {"NOUN", "PROPN", "ADJ", "PRON", "DET", "NUM"}
WORD_POS_EXCLUDED = {"PUNCT", "SYM"}
WORD_RE = re.compile(r"[^\W\d_]+(?:[-’'][^\W\d_]+)*", re.UNICODE)
PUNCT_RE = re.compile(r"\.{3,}|…|[.,;:!?—–()]|[\[\]{}]|(?<!\w)-(?!\w)|[«»„“”\"]")
EMPHATIC_RE = re.compile(r"[!?]{2,}")

CASE_RU = {
    "Nom": "именительный", "Gen": "родительный", "Dat": "дательный",
    "Acc": "винительный", "Ins": "творительный", "Loc": "предложный/местный",
    "Par": "частичный", "Voc": "звательный",
}
FEATURE_VALUE_RU = {
    "Person": {"1": "1-е лицо", "2": "2-е лицо", "3": "3-е лицо"},
    "Number": {"Sing": "единственное число", "Plur": "множественное число"},
    "PronType": {
        "Prs": "личные", "Rel": "относительные", "Int": "вопросительные",
        "Dem": "указательные", "Neg": "отрицательные", "Ind": "неопределённые",
        "Tot": "определительные", "Rcp": "взаимные",
    },
    "Tense": {"Past": "прошедшее", "Pres": "настоящее", "Fut": "будущее"},
    "Aspect": {"Perf": "совершенный вид", "Imp": "несовершенный вид"},
    "Mood": {"Ind": "изъявительное", "Imp": "повелительное", "Cnd": "условное"},
}
FEATURE_NAME_RU = {
    "Person": "лицо", "Number": "число", "PronType": "тип местоименного слова",
    "Tense": "время", "Aspect": "вид", "Mood": "наклонение",
}


def _words(tokens: list[Token]) -> list[Token]:
    return [token for token in tokens if token.pos not in WORD_POS_EXCLUDED
            and any(char.isalpha() for char in token.text)]


def _rate(count: int, total: int, multiplier: float) -> float:
    return round(count / total * multiplier, 6) if total else 0.0


def _token_evidence(tokens: list[Token], text: str,
                    label: Callable[[Token], str] | None = None) -> tuple[FeatureEvidence, ...]:
    result = []
    for token in tokens:
        if token.span is None or not token.span.valid_for(text):
            continue
        quote = text[token.span.start:token.span.end]
        if quote != token.text:
            continue
        result.append(FeatureEvidence(quote, token.span, label(token) if label else ""))
    return tuple(result)


def _observation(definition: FeatureDefinition, raw, normalized,
                 evidence: tuple[FeatureEvidence, ...],
                 limitations: tuple[str, ...] = ()) -> FeatureObservation:
    return FeatureObservation(
        feature_id=definition.id, raw_value=raw, normalized_value=normalized,
        evidence=evidence, applicability=Applicability.APPLICABLE,
        limitations=limitations, method_version=definition.method_version,
        source=definition.sources,
    )


def _insufficient(definition: FeatureDefinition, word_count: int, reason: str) -> FeatureObservation:
    return FeatureObservation(
        feature_id=definition.id,
        raw_value={"word_count": word_count}, normalized_value=None, evidence=(),
        applicability=Applicability.INSUFFICIENT_DATA,
        limitations=(reason,), method_version=definition.method_version,
        source=definition.sources,
    )


def _minimum_ok(definition: FeatureDefinition, word_count: int) -> bool:
    return definition.minimum_words is None or word_count >= definition.minimum_words


def _lex_001(definition: FeatureDefinition, text: str, words: list[Token]):
    selected = [token for token in words if is_service_word(token)]
    counts = Counter(token.text.casefold() for token in selected)
    normalized = {form: _rate(count, len(words), 1000) for form, count in sorted(counts.items())}
    return _observation(
        definition,
        {"word_count": len(words), "counts": dict(sorted(counts.items()))},
        {"per_1000_words": normalized},
        _token_evidence(selected, text, lambda token: token.text.casefold()),
        ("Части речи назначены Stanza; отсутствие словоформы не является различием без проверки возможности её проявления.",),
    )


def _lex_002(definition: FeatureDefinition, text: str, words: list[Token]):
    selected = [token for token in words if token.pos in {"PRON", "DET"}]
    forms = Counter(token.text.casefold() for token in selected)
    profiles: dict[str, Counter] = {name: Counter() for name in ("Person", "Number", "PronType")}
    for token in selected:
        for name in profiles:
            value = token.feats.get(name)
            if value:
                profiles[name][value] += 1
    normalized = {
        "словоформы_на_1000_слов": {
            form: _rate(count, len(words), 1000) for form, count in sorted(forms.items())
        },
        "характеристики_на_1000_слов": {
            FEATURE_NAME_RU[name]: {
                FEATURE_VALUE_RU.get(name, {}).get(value, value): _rate(count, len(words), 1000)
                for value, count in sorted(counts.items())
            } for name, counts in profiles.items()
        },
    }
    return _observation(
        definition,
        {"word_count": len(words), "forms": dict(sorted(forms.items())),
         "features": {
             FEATURE_NAME_RU[name]: {
                 FEATURE_VALUE_RU.get(name, {}).get(value, value): count
                 for value, count in sorted(counts.items())
             } for name, counts in profiles.items()
         }},
        normalized,
        _token_evidence(selected, text, lambda token: ", ".join(
            f"{FEATURE_NAME_RU[key]}: {FEATURE_VALUE_RU[key].get(token.feats[key], token.feats[key])}"
            for key in ("Person", "Number", "PronType")
            if key in token.feats
        )),
        ("Грамматические характеристики местоимений назначены Stanza и требуют проверки экспертом.",),
    )


def _lex_005(definition: FeatureDefinition, text: str, words: list[Token]):
    window = 50
    forms = [token.text.casefold() for token in words]
    values = [len(set(forms[index:index + window])) / window
              for index in range(len(forms) - window + 1)]
    return _observation(
        definition,
        {"word_count": len(words), "window": window, "window_count": len(values)},
        {"mattr": round(mean(values), 6)},
        _token_evidence(words, text),
        ("Окно 50 слов является параметром алгоритма MATTR, а не нормативным порогом пригодности текста.",),
    )


def _mor_001(definition: FeatureDefinition, text: str, words: list[Token]):
    counts = Counter(russian_word_class_key(token) for token in words)
    display_counts = dict(sorted(
        (CLASS_BY_KEY[key].title, count) for key, count in counts.items()
    ))
    normalized = {title: _rate(count, len(words), 100)
                  for title, count in display_counts.items()}
    return _observation(
        definition, {"word_count": len(words), "counts": dict(sorted(display_counts.items()))},
        {"percent_of_words": normalized},
        _token_evidence(words, text, lambda token: CLASS_BY_KEY[russian_word_class_key(token)].title),
        ("Классы укрупнены для русскоязычного представления; это автоматическая, а не ручная разметка.",),
    )


def _mor_003(definition: FeatureDefinition, text: str, words: list[Token]):
    selected = [token for token in words if token.pos in NOMINAL_POS and token.feats.get("Case")]
    counts = Counter(CASE_RU.get(token.feats["Case"], token.feats["Case"]) for token in selected)
    return _observation(
        definition,
        {"word_count": len(words), "case_marked_nominals": len(selected),
         "counts": dict(sorted(counts.items()))},
        {
            "percent_of_case_marked_nominals": {
                value: _rate(count, len(selected), 100)
                for value, count in sorted(counts.items())
            },
            "per_1000_words": {
                value: _rate(count, len(words), 1000)
                for value, count in sorted(counts.items())
            },
        },
        _token_evidence(selected, text, lambda token: (
            "падеж: " + CASE_RU.get(token.feats["Case"], token.feats["Case"])
        )),
        ("Падеж назначен Stanza; формы без метки Case не включаются в знаменатель падежного профиля.",),
    )


def _mor_004(definition: FeatureDefinition, text: str, words: list[Token]):
    selected = [token for token in words if token.pos in {"VERB", "AUX"}]
    profiles: dict[str, Counter] = {name: Counter() for name in ("Tense", "Person", "Aspect", "Mood")}
    for token in selected:
        for name in profiles:
            if token.feats.get(name):
                profiles[name][token.feats[name]] += 1
    normalized = {}
    denominators = {}
    for name, counts in profiles.items():
        denominator = sum(counts.values())
        denominators[name] = denominator
        normalized[FEATURE_NAME_RU[name]] = {
            FEATURE_VALUE_RU.get(name, {}).get(value, value): _rate(count, denominator, 100)
            for value, count in sorted(counts.items())
        }
    return _observation(
        definition,
        {"word_count": len(words), "verb_forms": len(selected),
         "denominators": {FEATURE_NAME_RU[name]: value for name, value in denominators.items()},
         "counts": {
             FEATURE_NAME_RU[name]: {
                 FEATURE_VALUE_RU.get(name, {}).get(value, value): count
                 for value, count in sorted(counts.items())
             } for name, counts in profiles.items()
         }},
        {"percent_within_each_marked_feature": normalized},
        _token_evidence(selected, text, lambda token: ", ".join(
            f"{FEATURE_NAME_RU[name]}: {FEATURE_VALUE_RU[name].get(token.feats[name], token.feats[name])}"
            for name in profiles if name in token.feats
        )),
        ("Каждая доля рассчитывается только среди глагольных форм с соответствующей меткой Stanza.",),
    )


def _syn_001(definition: FeatureDefinition, text: str, words: list[Token]):
    by_sentence: dict[int, list[Token]] = defaultdict(list)
    for token in words:
        by_sentence[token.sentence].append(token)
    lengths = [len(items) for _, items in sorted(by_sentence.items()) if items]
    evidence = []
    for sentence, items in sorted(by_sentence.items()):
        spans = [token.span for token in items if token.span is not None and token.span.valid_for(text)]
        if spans:
            span = Span(min(item.start for item in spans), max(item.end for item in spans))
            evidence.append(FeatureEvidence(text[span.start:span.end], span, f"слов: {len(items)}"))
    return _observation(
        definition,
        {"sentence_count": len(lengths), "lengths": lengths},
        {"mean": round(mean(lengths), 6), "median": round(median(lengths), 6),
         "population_standard_deviation": round(pstdev(lengths), 6)},
        tuple(evidence),
        ("Границы предложений определены Stanza и могут требовать исправления экспертом.",),
    )


def _pun_label(value: str) -> str:
    if value == "…" or set(value) == {"."} and len(value) >= 3:
        return "многоточие"
    return value


def _pun_001(definition: FeatureDefinition, text: str, words: list[Token]):
    matches = list(PUNCT_RE.finditer(text))
    counts = Counter(_pun_label(match.group()) for match in matches)
    evidence = tuple(FeatureEvidence(match.group(), Span(match.start(), match.end()), _pun_label(match.group()))
                     for match in matches)
    return _observation(
        definition,
        {"word_count": len(words), "counts": dict(sorted(counts.items()))},
        {"per_1000_words": {key: _rate(value, len(words), 1000)
                            for key, value in sorted(counts.items())}},
        evidence,
        ("Внутрисловные дефисы и апострофы не считаются отдельными знаками.",),
    )


def _pun_002(definition: FeatureDefinition, text: str, words: list[Token]):
    sequences = list(EMPHATIC_RE.finditer(text))
    question = [match for match in re.finditer(r"\?", text)]
    exclamation = [match for match in re.finditer(r"!", text)]
    sequence_counts = Counter(match.group() for match in sequences)
    raw_counts = {"?": len(question), "!": len(exclamation),
                  "sequences": dict(sorted(sequence_counts.items()))}
    evidence = [FeatureEvidence(match.group(), Span(match.start(), match.end()), match.group())
                for match in question + exclamation]
    evidence.extend(FeatureEvidence(match.group(), Span(match.start(), match.end()), "сочетание/повтор")
                    for match in sequences)
    normalized_counts = {"?": _rate(len(question), len(words), 1000),
                         "!": _rate(len(exclamation), len(words), 1000)}
    normalized_counts.update({value: _rate(count, len(words), 1000)
                              for value, count in sorted(sequence_counts.items())})
    return _observation(
        definition, {"word_count": len(words), "counts": raw_counts},
        {"per_1000_words": normalized_counts}, tuple(evidence),
        ("Подсчёт фиксирует графическую форму и не определяет коммуникативное намерение.",),
    )


def _gra_001(definition: FeatureDefinition, text: str, words: list[Token]):
    selected = []
    kinds = Counter()
    for token in words:
        letters = [char for char in token.text if char.isalpha()]
        if len(letters) < 2:
            continue
        if all(char.isupper() for char in letters):
            selected.append(token)
            kinds["полностью прописные"] += 1
            continue
        if any(char.isupper() for char in letters[1:]) and any(char.islower() for char in letters):
            selected.append(token)
            kinds["смешанный внутренний регистр"] += 1
    return _observation(
        definition,
        {"word_count": len(words), "counts": dict(sorted(kinds.items()))},
        {"per_1000_words": {key: _rate(value, len(words), 1000)
                            for key, value in sorted(kinds.items())}},
        _token_evidence(selected, text, lambda token: (
            "полностью прописные" if token.text.upper() == token.text
            else "смешанный внутренний регистр"
        )),
        ("Аббревиатуры и намерение автора автоматически не квалифицируются; фиксируется только написание.",),
    )


CALCULATORS = {
    "LEX_001": _lex_001, "LEX_002": _lex_002, "LEX_005": _lex_005,
    "MOR_001": _mor_001, "MOR_003": _mor_003, "MOR_004": _mor_004,
    "SYN_001": _syn_001, "PUN_001": _pun_001, "PUN_002": _pun_002,
    "GRA_001": _gra_001,
}


class FeatureExtractionService:
    """Вычисляет зарегистрированные AUTO-показатели без экспертного вывода."""

    def __init__(self, registry: FeatureRegistry):
        self.registry = registry

    @classmethod
    def from_default_registry(cls) -> "FeatureExtractionService":
        return cls(FeatureRegistry.load())

    def analyze_object(self, document: Document, tokens: list[Token]) -> list[FeatureObservation]:
        words = _words(tokens)
        observations = []
        for definition in self.registry.by_mode(AutomationMode.AUTO):
            if definition.id not in CALCULATORS:
                raise ValueError(f"Для {definition.id} нет вычислителя.")
            if not words:
                observations.append(_insufficient(
                    definition, 0,
                    "Нет слов с проверенными координатами Stanza; показатель не вычислен.",
                ))
            elif not _minimum_ok(definition, len(words)):
                observations.append(_insufficient(
                    definition, len(words),
                    f"Для алгоритма нужно не менее {definition.minimum_words} слов; "
                    "это техническое условие вычисления, а не норматив пригодности.",
                ))
            else:
                observation = CALCULATORS[definition.id](definition, document.text, words)
                self._verify_evidence(document.text, observation)
                observations.append(observation)
        return observations

    @staticmethod
    def _verify_evidence(text: str, observation: FeatureObservation) -> None:
        for evidence in observation.evidence:
            if not evidence.span.valid_for(text) or text[evidence.span.start:evidence.span.end] != evidence.quote:
                raise ValueError(f"Некорректная координата evidence для {observation.feature_id}.")
