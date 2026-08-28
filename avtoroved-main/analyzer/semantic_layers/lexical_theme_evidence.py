"""Лексические основания ThemeEngineV2 по ontology keywords."""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Callable, Iterable


_WORD_RE = re.compile(r"[A-Za-zА-Яа-яЁё0-9]+(?:[-'][A-Za-zА-Яа-яЁё0-9]+)*")


@dataclass(frozen=True)
class LexicalMatch:
    value: str
    fragment: str
    start: int
    end: int
    kind: str


@dataclass(frozen=True)
class LexicalEvidence:
    matched_lemmas: tuple[str, ...]
    matched_phrases: tuple[str, ...]
    match_count: int
    unique_match_count: int
    coverage: float
    fragments: tuple[LexicalMatch, ...]


class LazyRussianLemmatizer:
    """Лениво использует уже заявленный в проекте pymorphy3.

    Если пакет недоступен, применяется контролируемый lowercase fallback. Это
    сохраняет работоспособность shadow mode, не добавляя сетевых операций.
    """

    def __init__(self):
        self._morph = None
        self._load_attempted = False

    @lru_cache(maxsize=32768)
    def __call__(self, word: str) -> str:
        lowered = word.lower().replace("ё", "е")
        if not self._load_attempted:
            self._load_attempted = True
            try:
                import pymorphy3
                self._morph = pymorphy3.MorphAnalyzer()
            except Exception:  # pragma: no cover - зависит от окружения
                self._morph = None
        if self._morph is None:
            return lowered
        try:
            return self._morph.parse(lowered)[0].normal_form
        except Exception:
            return lowered


class LexicalThemeEvidenceExtractor:
    """Находит слова и фразы темы без превращения одного совпадения в вывод."""

    def __init__(self, ontology: dict[str, dict],
                 lemmatizer: Callable[[str], str] | None = None):
        self._ontology = ontology
        self._lemmatize = lemmatizer or LazyRussianLemmatizer()
        self._keywords = {
            theme_id: self._normalise_keywords(row.get("keywords", ()))
            for theme_id, row in ontology.items()
        }

    def lemmatize_text(self, text: str) -> list[str]:
        return [self._lemmatize(match.group()) for match in _WORD_RE.finditer(text)]

    def _normalise_keywords(self, keywords: Iterable[str]
                            ) -> tuple[tuple[str, tuple[str, ...]], ...]:
        normalised: list[tuple[str, tuple[str, ...]]] = []
        seen: set[tuple[str, ...]] = set()
        for keyword in keywords:
            parts = tuple(self._lemmatize(match.group())
                          for match in _WORD_RE.finditer(keyword))
            if not parts or parts in seen:
                continue
            seen.add(parts)
            normalised.append((keyword, parts))
        return tuple(normalised)

    def analyze(self, theme_id: str, text: str, base_offset: int = 0
                ) -> LexicalEvidence:
        matches = list(_WORD_RE.finditer(text))
        lemmas = [self._lemmatize(match.group()) for match in matches]
        fragments: list[LexicalMatch] = []
        matched_positions: set[int] = set()
        matched_lemmas: list[str] = []
        matched_phrases: list[str] = []

        for original, parts in self._keywords.get(theme_id, ()):
            width = len(parts)
            for index in range(0, len(lemmas) - width + 1):
                if tuple(lemmas[index:index + width]) != parts:
                    continue
                start_match = matches[index]
                end_match = matches[index + width - 1]
                start = base_offset + start_match.start()
                end = base_offset + end_match.end()
                fragment = text[start_match.start():end_match.end()]
                kind = "phrase" if width > 1 else "lemma"
                fragments.append(LexicalMatch(original, fragment, start, end, kind))
                matched_positions.update(range(index, index + width))
                if width > 1:
                    matched_phrases.append(original)
                else:
                    matched_lemmas.append(parts[0])

        unique_values = {
            (fragment.kind, fragment.value.lower()) for fragment in fragments
        }
        token_count = len(lemmas)
        coverage = len(matched_positions) / token_count if token_count else 0.0
        return LexicalEvidence(
            matched_lemmas=tuple(dict.fromkeys(matched_lemmas)),
            matched_phrases=tuple(dict.fromkeys(matched_phrases)),
            match_count=len(fragments),
            unique_match_count=len(unique_values),
            coverage=round(coverage, 6),
            fragments=tuple(fragments),
        )
