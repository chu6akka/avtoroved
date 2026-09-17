"""Детерминированная справка по нераспознанной словоформе.

Считается на Python до обращения к модели и без него. Замер по корпусу
показал, что свободное суждение модели ненадёжно, поэтому решаемое решается
арифметикой, а модели остаётся только то, что арифметикой не решается.

Что справка даёт и чего не даёт:

* частота леммы по снимку НКРЯ отличает слово, известное общему языку, от
  слова вне его;
* повторяемость формы в самом тексте отличает **опечатку от не-опечатки**:
  опечатка случается один раз, устойчивое написание повторяется. Отличить
  окказионализм от неологизма повтор не может — `тимбилдинг` повторяется так
  же, как авторское образование;
* расстояние до исправлений, предложенных самим LanguageTool, показывает,
  похожа ли форма на порчу известного слова. Сравнение со снимком НКРЯ для
  этого не годится: снимок построен по леммам, и словоформа «пришол» даёт
  ближайшим «прикол», то есть верный вердикт при ложном обосновании.
  Морфологический словарь LanguageTool решает эту задачу правильно, и
  дублировать его хуже незачем.

Снимок словаря используется офлайн и с зафиксированной версией: живое
обращение к внешнему API отправляло бы фрагменты исследуемого документа
наружу и не воспроизводилось бы во времени.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import re
from typing import Iterable

from authoroved_core.core.models import Candidate, Token


DEFAULT_FREQUENCY = (Path(__file__).parents[2] / "avtoroved-main" / "data"
                     / "freq" / "freqrnc.json")
MAX_EDIT_DISTANCE = 2

LATIN = re.compile(r"[A-Za-z]")
TRIPLED_LETTER = re.compile(r"([^\W\d_])\1\1", re.UNICODE)
SENTENCE_START = re.compile(r"[.!?…]\s*$|^\s*$")


@dataclass(frozen=True)
class WordEvidence:
    """Проверяемые числа по словоформе. Ни одно не является выводом."""

    form: str
    lemma: str
    frequency_ipm: float | None
    frequency_rank: int | None
    word_class: str
    repeats_in_text: int
    nearest_replacement: str
    edit_distance: int | None
    lt_replacements: tuple[str, ...]
    has_latin: bool
    has_tripled_letter: bool
    capitalized_inside_sentence: bool
    verdict: str
    verdict_reason: str

    @property
    def known_to_corpus(self) -> bool:
        return self.frequency_ipm is not None


class FrequencyDictionary:
    """Снимок частотного словаря НКРЯ с индексом по длине слова."""

    def __init__(self, entries: dict[str, list]):
        self.entries = entries
        self.by_length: dict[int, list[str]] = {}
        for word in entries:
            self.by_length.setdefault(len(word), []).append(word)

    @classmethod
    def load(cls, path: str | Path = DEFAULT_FREQUENCY) -> "FrequencyDictionary":
        return cls(json.loads(Path(path).read_text(encoding="utf-8")))

    @classmethod
    def empty(cls) -> "FrequencyDictionary":
        """Справка обязана работать и без снимка словаря."""
        return cls({})

    def lookup(self, word: str) -> tuple[int, float, str] | None:
        value = self.entries.get(word.casefold())
        if not isinstance(value, list) or len(value) < 3:
            return None
        return int(value[0]), float(value[1]), str(value[2])


def damerau_levenshtein(first: str, second: str) -> int:
    """Расстояние с перестановкой соседних букв как одной правкой.

    Перестановка — обычная опечатка: «првиет» отстоит от «привет» на одну
    правку, а не на две, как считает обычное расстояние редактирования.
    """
    first, second = first.casefold(), second.casefold()
    rows = [[0] * (len(second) + 1) for _ in range(len(first) + 1)]
    for i in range(len(first) + 1):
        rows[i][0] = i
    for j in range(len(second) + 1):
        rows[0][j] = j
    for i in range(1, len(first) + 1):
        for j in range(1, len(second) + 1):
            cost = first[i - 1] != second[j - 1]
            rows[i][j] = min(rows[i - 1][j] + 1, rows[i][j - 1] + 1, rows[i - 1][j - 1] + cost)
            if (i > 1 and j > 1 and first[i - 1] == second[j - 2]
                    and first[i - 2] == second[j - 1]):
                rows[i][j] = min(rows[i][j], rows[i - 2][j - 2] + 1)
    return rows[-1][-1]


def nearest_replacement(form: str, replacements: Iterable[str]) -> tuple[str, int | None]:
    """Ближайшее исправление LanguageTool и расстояние до него."""
    best, best_distance = "", None
    for value in replacements:
        distance = damerau_levenshtein(form, value)
        # Нулевое расстояние означает, что предложено само исходное слово:
        # исправлением это не является.
        if distance == 0 or (best_distance is not None and distance >= best_distance):
            continue
        best, best_distance = value, distance
    return best, best_distance


def count_occurrences(text: str, form: str) -> int:
    """Вхождения формы как отдельного слова, без учёта регистра."""
    if not form.strip():
        return 0
    pattern = re.compile(rf"(?<!\w){re.escape(form)}(?!\w)", re.IGNORECASE | re.UNICODE)
    return len(pattern.findall(text))


def lemma_for(candidate: Candidate, tokens: Iterable[Token]) -> str:
    """Лемма Stanza того токена, который покрывает координаты кандидата."""
    for token in tokens or ():
        if token.span is None:
            continue
        if token.span.start <= candidate.span.start and candidate.span.end <= token.span.end:
            return token.lemma
    return ""


def _capitalized_inside_sentence(text: str, candidate: Candidate) -> bool:
    if not candidate.fragment[:1].isupper():
        return False
    return not SENTENCE_START.search(text[max(0, candidate.span.start - 40):candidate.span.start])


def deterministic_verdict(evidence: "WordEvidence") -> tuple[str, str]:
    """Метка, выводимая из чисел. Пустая строка — решает эксперт.

    Правила намеренно узкие: лучше промолчать, чем подсказать неверно.
    """
    if evidence.known_to_corpus:
        return "dictionary_gap", (
            f"лемма «{evidence.lemma or evidence.form}» есть в снимке НКРЯ "
            f"({evidence.frequency_ipm:.2f} на миллион), словарь LanguageTool её не знает"
        )
    if evidence.repeats_in_text > 1:
        return "", (
            f"форма повторяется в тексте {evidence.repeats_in_text} раза — "
            "на опечатку не похоже; окказионализм, неологизм и заимствование "
            "числами не различаются"
        )
    if evidence.edit_distance is not None and evidence.edit_distance <= MAX_EDIT_DISTANCE:
        правок = "правка" if evidence.edit_distance == 1 else "правки"
        return "spelling_error", (
            f"{evidence.edit_distance} {правок} до «{evidence.nearest_replacement}», "
            "которое предлагает сам LanguageTool; в тексте встречается один раз"
        )
    return "", ("числами не решается: слова нет в снимке НКРЯ, "
                "исправления LanguageTool далеки или отсутствуют")


def collect(candidate: Candidate, text: str, tokens: Iterable[Token] = (),
            dictionary: FrequencyDictionary | None = None) -> WordEvidence:
    dictionary = dictionary or FrequencyDictionary.empty()
    form = candidate.fragment
    lemma = lemma_for(candidate, tokens) or form
    found = dictionary.lookup(lemma) or dictionary.lookup(form)
    replacements = tuple(candidate.replacements[:5])
    nearest, distance = ("", None) if found else nearest_replacement(form, replacements)
    evidence = WordEvidence(
        form=form, lemma=lemma,
        frequency_rank=found[0] if found else None,
        frequency_ipm=found[1] if found else None,
        word_class=found[2] if found else "",
        repeats_in_text=count_occurrences(text, form),
        nearest_replacement=nearest, edit_distance=distance,
        lt_replacements=replacements,
        has_latin=bool(LATIN.search(form)),
        has_tripled_letter=bool(TRIPLED_LETTER.search(form)),
        capitalized_inside_sentence=_capitalized_inside_sentence(text, candidate),
        verdict="", verdict_reason="",
    )
    verdict, reason = deterministic_verdict(evidence)
    return WordEvidence(**{**evidence.__dict__, "verdict": verdict, "verdict_reason": reason})


def summary_lines(evidence: WordEvidence) -> tuple[str, ...]:
    """Строки для панели разбора: эксперт видит те же числа, что и модель."""
    lines = []
    if evidence.known_to_corpus:
        lines.append(f"НКРЯ: {evidence.frequency_ipm:.2f} на миллион, ранг {evidence.frequency_rank}")
    else:
        lines.append("НКРЯ: слова нет в снимке словаря")
    lines.append(f"В тексте встречается: {evidence.repeats_in_text}")
    if evidence.edit_distance is not None:
        lines.append(
            f"Ближайшее исправление LanguageTool: «{evidence.nearest_replacement}», "
            f"правок {evidence.edit_distance}"
        )
    if evidence.lt_replacements:
        lines.append("LanguageTool предлагает: " + ", ".join(evidence.lt_replacements))
    flags = [name for name, active in (
        ("латиница", evidence.has_latin),
        ("тройная буква", evidence.has_tripled_letter),
        ("заглавная не в начале предложения", evidence.capitalized_inside_sentence),
    ) if active]
    if flags:
        lines.append("Особенности написания: " + ", ".join(flags))
    return tuple(lines)
