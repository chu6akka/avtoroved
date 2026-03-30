"""
analyzer/spacy_backend.py — spaCy-бэкенд для морфологического анализа.

Альтернатива StanzaBackend: в 5-10× быстрее, меньше памяти.
Возвращает тот же List[TokenInfo], поэтому полностью взаимозаменяем.

Модели (по убыванию качества):
  ru_core_news_lg  — большая (~560 МБ), точнее
  ru_core_news_md  — средняя (~120 МБ)
  ru_core_news_sm  — малая  (~15 МБ),  быстрее всего

Установка:
  pip install spacy
  python -m spacy download ru_core_news_lg   # или sm/md
"""
from __future__ import annotations
import re
from typing import List, Callable, Optional

from analyzer.stanza_backend import TokenInfo, UPOS_RU, WORD_RE, FEAT_RU

# spaCy использует те же UPOS-теги и CoNLL-U морф. признаки что и Stanza,
# поэтому переиспользуем все словари напрямую.

_MODELS_PRIORITY = ["ru_core_news_lg", "ru_core_news_md", "ru_core_news_sm"]


def _translate_feats(morph_str: str) -> str:
    """Перевести CoNLL-U морф. строку на русский (та же логика что в Stanza)."""
    if not morph_str:
        return "—"
    parts = []
    for pair in morph_str.split("|"):
        if "=" in pair:
            k, v = pair.split("=", 1)
            parts.append(f"{FEAT_RU.get(k, k)}: {FEAT_RU.get(v, v)}")
        else:
            parts.append(FEAT_RU.get(pair, pair))
    return "; ".join(parts) if parts else "—"


class SpacyBackend:
    """spaCy-бэкенд с тем же интерфейсом, что StanzaBackend."""

    def __init__(self):
        self.nlp = None
        self._model_name: str = ""
        self._ready = False

    def ensure_loaded(self, status_callback: Optional[Callable] = None) -> None:
        if self._ready:
            return

        try:
            import spacy
        except ImportError:
            raise RuntimeError(
                "spaCy не установлен. Выполните: pip install spacy")

        for model in _MODELS_PRIORITY:
            try:
                if status_callback:
                    status_callback(f"Загрузка spaCy модели {model}...")
                self.nlp = spacy.load(model, disable=["parser", "ner"])
                self._model_name = model
                self._ready = True
                if status_callback:
                    status_callback(f"spaCy готов ({model})")
                return
            except OSError:
                continue

        # Ни одна модель не найдена — попробуем скачать sm
        if status_callback:
            status_callback("Скачивание ru_core_news_sm (~15 МБ)...")
        try:
            import subprocess, sys
            subprocess.run(
                [sys.executable, "-m", "spacy", "download", "ru_core_news_sm"],
                check=True, capture_output=True,
            )
            self.nlp = spacy.load("ru_core_news_sm", disable=["parser", "ner"])
            self._model_name = "ru_core_news_sm"
            self._ready = True
            if status_callback:
                status_callback("spaCy готов (ru_core_news_sm)")
        except Exception as e:
            raise RuntimeError(
                "Не удалось загрузить модель spaCy.\n"
                "Выполните вручную: python -m spacy download ru_core_news_sm"
            ) from e

    def analyze(self, text: str) -> List[TokenInfo]:
        if not self._ready:
            self.ensure_loaded()

        doc = self.nlp(text)
        tokens: List[TokenInfo] = []

        for token in doc:
            if not WORD_RE.search(token.text):
                tokens.append(TokenInfo(
                    text=token.text,
                    lemma=token.text,
                    pos="PUNCT",
                    pos_label="Пунктуация",
                    feats="—",
                ))
                continue

            upos = token.pos_ or "X"
            morph_str = str(token.morph) if token.morph else ""
            feats_ru = _translate_feats(morph_str) if morph_str else "—"

            pos_label = UPOS_RU.get(upos, upos)
            if upos == "VERB" and morph_str:
                if "VerbForm=Part" in morph_str:
                    pos_label = "Причастие"
                elif "VerbForm=Conv" in morph_str:
                    pos_label = "Деепричастие"

            tokens.append(TokenInfo(
                text=token.text,
                lemma=token.lemma_ or token.text.lower(),
                pos=upos,
                pos_label=pos_label,
                feats=feats_ru,
            ))

        return tokens

    @property
    def model_name(self) -> str:
        return self._model_name
