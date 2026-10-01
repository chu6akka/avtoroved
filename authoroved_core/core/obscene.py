"""Распознавание обсценной (нецензурной) лексики по четырём корням русского мата.

Корни: хуй, пизд-, еб-/ёб-, бляд-/бля. Это детерминированный список форм, а не модель:
он не оценивает уместность или намерение и не заменяет решения эксперта. Корень
«еб» встречается в обычных словах («небо», «хлеб», «учеба», «себе»), поэтому он
распознаётся только в начале слова или после приставки, а также в сложных словах
на «-оёб». Слова-исключения перечислены явно.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from authoroved_core.core.models import Span

WORD_RE = re.compile(r"[^\W\d_]+(?:[-’'][^\W\d_]+)*", re.UNICODE)

# Приставки, после которых «еб» остаётся корнем: за-еб-ал, вы-еб-ываться, съ-еб-ать.
_PREFIXES = ("", "за", "вы", "у", "по", "от", "отъ", "на", "до", "раз", "разъ", "рас", "съ", "въ",
             "недо", "пере", "при", "про", "об", "объ", "обо", "под", "подъ", "ис", "изъ", "вз",
             "взъ", "не", "наи", "долбо", "охуе")
_EB_ROOT = re.compile(r"еб(?=[аеиклностуыюя]|$)")
_EB_COMPOUND = re.compile(r"[а-я]+оеб(ы|а|у|ом|ов|ам|ами|ах|е)?$")
# «хую» есть в «тихую», «сухую», «плохую», поэтому корень «ху-» — только в начале
# слова или после приставки; «блят» есть в «углублять», «ослаблять» — только в начале.
_ROOTS = (
    ("хуй", re.compile(r"^(?:на|по|за|от|до|о|ни|рас|раз|вы|при|про|пере|недо|под|у)?ху[йяеию]")),
    ("пизд", re.compile(r"пизд")),
    ("бляд", re.compile(r"бляд|^бля(?:ть?|$)")),
)
# Обычные слова, в которых встречаются те же сочетания букв.
_EXCEPTIONS = re.compile(r"страху|^небо|^себе|^требо|^хлеб|^учеб|^колеб|^ребен|^лебед|^служеб")


@dataclass(frozen=True)
class ObsceneWord:
    text: str
    span: Span
    root: str


def _normalized(word: str) -> str:
    return word.casefold().replace("ё", "е").replace("’", "").replace("'", "")


def obscene_root(word: str) -> str | None:
    """Корень мата в словоформе или None."""
    form = _normalized(word)
    if not form or _EXCEPTIONS.search(form):
        return None
    for root, pattern in _ROOTS:
        if pattern.search(form):
            return root
    for prefix in _PREFIXES:
        if form.startswith(prefix) and _EB_ROOT.match(form, len(prefix)):
            return "еб"
    if _EB_COMPOUND.search(form):
        return "еб"
    return None


def is_obscene(word: str) -> bool:
    return obscene_root(word) is not None


def find_obscene(text: str) -> list[ObsceneWord]:
    found = []
    for match in WORD_RE.finditer(text):
        root = obscene_root(match.group())
        if root:
            found.append(ObsceneWord(match.group(), Span(match.start(), match.end()), root))
    return found
