"""Детерминированная справка по нераспознанной словоформе.

Считается на Python до обращения к модели и без него. Замер по корпусу
показал, что свободное суждение модели ненадёжно, поэтому решаемое решается
арифметикой, а модели остаётся только то, что арифметикой не решается.

Справка даёт числа и не даёт вердикта. Автоматические метки здесь были и
сняты по результатам контрольного набора 18 сентября: из 37 вердиктов верными
оказались 4. Причина в том, что LanguageTool предлагает исправление любому
незнакомому слову — фамилии, жаргонизму, окказионализму, — поэтому близость к
его подсказке не является доводом в пользу опечатки. Ужесточение не помогло:
лучшая точность 12,5 % ценой потери пяти опечаток из шести.

Что справка даёт и чего не даёт:

* частота леммы по снимку НКРЯ отличает слово, известное общему языку, от
  слова вне его;
* повторяемость формы в самом тексте — довод, а не правило: на контрольном
  наборе «Мисной» повторяется дважды и при этом остаётся ошибкой, потому что
  автор цитирует чужую безграмотность;
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
# Доля совпадающего начала, ниже которой лемма Stanza не принимается.
LEMMA_PREFIX_RATIO = 0.6

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


def is_space_split(form: str, replacement: str) -> bool:
    """LanguageTool разбивает незнакомое сложное слово пробелом.

    «вахтовика» превращается в «вахт овика», «авиаохрана» в «авиа охрана».
    Это эвристика разбиения, а не исправление: отличие ровно в одном пробеле,
    поэтому такое предложение стояло в одной правке и давало ложный вердикт
    «орфографическая ошибка» на совершенно нормальных словах.
    """
    return (" " in replacement
            and replacement.replace(" ", "").casefold() == form.casefold())


def nearest_replacement(form: str, replacements: Iterable[str]) -> tuple[str, int | None]:
    """Ближайшее исправление LanguageTool и расстояние до него."""
    best, best_distance = "", None
    for value in replacements:
        # Нулевое расстояние означает, что предложено само исходное слово.
        if is_space_split(form, value):
            continue
        distance = damerau_levenshtein(form, value)
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


def plausible_lemma(form: str, lemma: str) -> bool:
    """Похожа ли лемма на лемму именно этой словоформы.

    Stanza лемматизирует и незнакомое слово, выдавая правдоподобную догадку:
    «бзди» превращается в «брать», «бля» в «брать». Такая лемма находится в
    снимке НКРЯ, и слово ошибочно объявляется известным корпусу. Форма и её
    лемма обязаны совпадать заметной начальной частью.
    """
    first, second = form.casefold(), lemma.casefold()
    if not first or not second:
        return False
    shared = 0
    while shared < min(len(first), len(second)) and first[shared] == second[shared]:
        shared += 1
    return shared / min(len(first), len(second)) >= LEMMA_PREFIX_RATIO


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


def collect(candidate: Candidate, text: str, tokens: Iterable[Token] = (),
            dictionary: FrequencyDictionary | None = None) -> WordEvidence:
    dictionary = dictionary or FrequencyDictionary.empty()
    form = candidate.fragment
    guessed = lemma_for(candidate, tokens)
    lemma = guessed if plausible_lemma(form, guessed) else form
    capitalized = _capitalized_inside_sentence(text, candidate)
    # Слово с заглавной внутри предложения — обычно имя собственное, и
    # совпадение его леммы со словарём нарицательных ничего не означает
    # («Бойе» и «бой»).
    found = None if capitalized else (dictionary.lookup(lemma) or dictionary.lookup(form))
    replacements = tuple(candidate.replacements[:5])
    nearest, distance = ("", None) if found else nearest_replacement(form, replacements)
    return WordEvidence(
        form=form, lemma=lemma,
        frequency_rank=found[0] if found else None,
        frequency_ipm=found[1] if found else None,
        word_class=found[2] if found else "",
        repeats_in_text=count_occurrences(text, form),
        nearest_replacement=nearest, edit_distance=distance,
        lt_replacements=replacements,
        has_latin=bool(LATIN.search(form)),
        has_tripled_letter=bool(TRIPLED_LETTER.search(form)),
        capitalized_inside_sentence=capitalized,
    )
    return evidence


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
