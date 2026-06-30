"""NLP-фасад: единая точка доступа к морфологии и синтаксису (оффлайн).

Скрывает razdel / Natasha / pymorphy3 за устойчивой моделью ``Document / Sentence /
Token``, которой пользуются экстракторы признаков. Модели Natasha грузятся лениво и
кэшируются (singleton); работают полностью оффлайн (поставляются с пакетами).

Лемматизация — через pymorphy3 (а не natasha.MorphVocab, который тянет pymorphy2 и
падает на Python 3.13 из-за pkg_resources). От Natasha берём POS, морфопризнаки и
синтаксис зависимостей (они основаны на slovnet и от pymorphy2 не зависят).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock
from typing import Optional


@dataclass(slots=True)
class Token:
    """Слово или знак препинания с морфо-синтаксическим разбором."""

    text: str
    start: int                      # смещение начала в исходном тексте (символы)
    stop: int                       # смещение конца
    lemma: str
    pos: str                        # UD-часть речи (Natasha): NOUN, VERB, ADJ, ...
    feats: dict[str, str] = field(default_factory=dict)   # UD-морфопризнаки
    head: int = -1                  # локальный индекс вершины в предложении; -1 = корень
    rel: str = "dep"                # тип синтаксической связи (UD): root, amod, obj, ...
    pm_tag: str = ""                # строковый тег pymorphy3 (детальная морфология)

    @property
    def is_word(self) -> bool:
        """Является ли токен словом (содержит буквы), а не пунктуацией/числом."""
        return any(ch.isalpha() for ch in self.text)


@dataclass(slots=True)
class Sentence:
    text: str
    start: int
    stop: int
    tokens: list[Token]

    @property
    def words(self) -> list[Token]:
        return [t for t in self.tokens if t.is_word]


@dataclass(slots=True)
class Document:
    """Результат полного разбора текста."""

    text: str
    sentences: list[Sentence]

    @property
    def tokens(self) -> list[Token]:
        return [t for s in self.sentences for t in s.tokens]

    @property
    def words(self) -> list[Token]:
        return [t for t in self.tokens if t.is_word]

    def word_count(self) -> int:
        return len(self.words)


# Соответствие UD-части речи (Natasha) грамемам pymorphy3 — для выбора леммы у омонимов.
_UD_TO_PYMORPHY: dict[str, set[str]] = {
    "NOUN": {"NOUN"},
    "VERB": {"VERB", "INFN", "GRND", "PRTF", "PRTS"},
    "ADJ": {"ADJF", "ADJS", "COMP"},
    "ADV": {"ADVB"},
    "PRON": {"NPRO"},
    "DET": {"ADJF", "NPRO"},
    "NUM": {"NUMR"},
    "ADP": {"PREP"},
    "CCONJ": {"CONJ"},
    "SCONJ": {"CONJ"},
    "PART": {"PRCL"},
    "INTJ": {"INTJ"},
}


class _Engine:
    """Лениво инициализируемые модели Natasha + pymorphy3 (потокобезопасно)."""

    _instance: Optional["_Engine"] = None
    _lock = Lock()

    def __init__(self) -> None:
        from natasha import (
            NewsEmbedding,
            NewsMorphTagger,
            NewsSyntaxParser,
            Segmenter,
        )
        import pymorphy3

        self.segmenter = Segmenter()
        emb = NewsEmbedding()
        self.morph_tagger = NewsMorphTagger(emb)
        self.syntax_parser = NewsSyntaxParser(emb)
        self.pymorphy = pymorphy3.MorphAnalyzer()

    @classmethod
    def get(cls) -> "_Engine":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def lemmatize(self, word: str, ud_pos: str) -> tuple[str, str]:
        """Лемма + тег pymorphy3; у омонимов выбираем разбор под UD-часть речи."""
        parses = self.pymorphy.parse(word)
        if not parses:
            return word.lower(), ""
        wanted = _UD_TO_PYMORPHY.get(ud_pos)
        best = parses[0]
        if wanted:
            for p in parses:
                if p.tag.POS in wanted:
                    best = p
                    break
        return best.normal_form, str(best.tag)


def _head_index(head_id: str) -> int:
    """'1_0' -> -1 (корень); '1_2' -> 1 (0-based локальный индекс в предложении)."""
    n = int(head_id.split("_")[1])
    return -1 if n == 0 else n - 1


def analyze(text: str) -> Document:
    """Полный разбор текста: сегментация + морфология + синтаксис зависимостей."""
    from natasha import Doc

    eng = _Engine.get()
    doc = Doc(text)
    doc.segment(eng.segmenter)
    doc.tag_morph(eng.morph_tagger)
    doc.parse_syntax(eng.syntax_parser)

    sentences: list[Sentence] = []
    for sent in doc.sents:
        toks: list[Token] = []
        for t in sent.tokens:
            pos = t.pos or "X"
            lemma, pm_tag = eng.lemmatize(t.text, pos)
            toks.append(
                Token(
                    text=t.text,
                    start=t.start,
                    stop=t.stop,
                    lemma=lemma,
                    pos=pos,
                    feats=dict(t.feats or {}),
                    head=_head_index(t.head_id),
                    rel=t.rel or "dep",
                    pm_tag=pm_tag,
                )
            )
        sentences.append(
            Sentence(text=sent.text, start=sent.start, stop=sent.stop, tokens=toks)
        )
    return Document(text=text, sentences=sentences)
