"""
Stanza-бэкенд для автороведческого анализа.
Обёртка над Stanford Stanza для русского языка.
"""
from __future__ import annotations
import re
import os
import sys
from dataclasses import dataclass
from typing import List

# Добавляем корень проекта для импорта
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

WORD_RE = re.compile(r"[A-Za-zА-Яа-яЁё]+")

UPOS_RU = {
    "NOUN": "Существительное", "PROPN": "Имя собственное", "VERB": "Глагол",
    "AUX": "Вспомогательный глагол", "ADJ": "Прилагательное", "ADV": "Наречие",
    "PRON": "Местоимение", "NUM": "Числительное", "DET": "Определительное слово",
    "ADP": "Предлог", "PART": "Частица", "CCONJ": "Сочинительный союз",
    "SCONJ": "Подчинительный союз", "INTJ": "Междометие", "PUNCT": "Пунктуация",
    "SYM": "Символ", "X": "Другое",
}

UPOS_SHORT = {
    "NOUN": "СУЩ", "PROPN": "ИМЯ", "VERB": "ГЛ", "AUX": "ВСПГЛ",
    "ADJ": "ПРИЛ", "ADV": "НАР", "PRON": "МЕСТ", "NUM": "ЧИСЛ",
    "DET": "ОПР", "ADP": "ПРЕДЛ", "PART": "ЧАСТ", "CCONJ": "ССОЮЗ",
    "SCONJ": "ПСОЮЗ", "INTJ": "МЕЖД", "PUNCT": "ПУНКТ", "SYM": "СИМВ", "X": "ДР",
}

FEAT_RU = {
    "Animacy": "Одушевлённость", "Aspect": "Вид", "Case": "Падеж",
    "Degree": "Степень сравнения", "Gender": "Род", "Mood": "Наклонение",
    "Number": "Число", "Person": "Лицо", "Tense": "Время",
    "VerbForm": "Форма глагола", "Voice": "Залог",
    "Anim": "одушевлённое", "Inan": "неодушевлённое",
    "Imp": "несовершенный", "Perf": "совершенный",
    "Nom": "именительный", "Gen": "родительный", "Dat": "дательный",
    "Acc": "винительный", "Ins": "творительный", "Loc": "предложный",
    "Sing": "единственное", "Plur": "множественное",
    "Masc": "мужской", "Fem": "женский", "Neut": "средний",
    "Pres": "настоящее", "Past": "прошедшее", "Fut": "будущее",
    "Ind": "изъявительное", "Part": "причастие", "Conv": "деепричастие",
    "Inf": "инфинитив", "Fin": "финитная",
    "Act": "действительный", "Pass": "страдательный", "Mid": "средний",
}


@dataclass
class TokenInfo:
    text: str
    lemma: str
    pos: str         # UPOS tag
    pos_label: str   # русское название
    feats: str       # морфологические признаки (переведённые)
    deprel: str = ""      # синтаксическая роль (Universal Dependencies)
    head: int = 0         # id головного слова в предложении (0 = root)
    char_start: int = 0   # начальная позиция в тексте
    char_end: int = 0     # конечная позиция в тексте
    sent_id: int = 0      # индекс предложения
    token_id: int = 0     # id слова внутри предложения (1-indexed)


class StanzaBackend:
    """Обёртка над Stanford Stanza для русского языка."""

    def __init__(self):
        self.nlp = None
        self._ready = False

    def ensure_loaded(self, status_callback=None):
        if self._ready:
            return
        import stanza
        # Патч для PyTorch 2.6+
        try:
            import torch
            _original_torch_load = torch.load
            def _patched_torch_load(*args, **kwargs):
                kwargs.setdefault("weights_only", False)
                return _original_torch_load(*args, **kwargs)
            torch.load = _patched_torch_load
        except Exception:
            pass
        if status_callback:
            status_callback("Загрузка модели Stanza (при первом запуске скачивается ~100 МБ)...")
        try:
            self.nlp = stanza.Pipeline('ru', processors='tokenize,pos,lemma,depparse', verbose=False)
        except Exception:
            if status_callback:
                status_callback("Скачивание модели русского языка...")
            stanza.download('ru', verbose=False)
            self.nlp = stanza.Pipeline('ru', processors='tokenize,pos,lemma,depparse', verbose=False)
        self._ready = True
        if status_callback:
            status_callback("Stanza готова")

    def analyze(self, text: str) -> List[TokenInfo]:
        if not self._ready:
            self.ensure_loaded()
        doc = self.nlp(text)
        tokens = []
        for sent_idx, sent in enumerate(doc.sentences):
            for word in sent.words:
                tok_id = word.id if isinstance(word.id, int) else (
                    word.id[0] if isinstance(word.id, (list, tuple)) else 0
                )
                head = word.head if isinstance(word.head, int) else 0
                deprel = word.deprel or ""
                cs = getattr(word, 'start_char', None) or 0
                ce = getattr(word, 'end_char', None) or 0
                if not WORD_RE.search(word.text):
                    tokens.append(TokenInfo(
                        word.text, word.text, "PUNCT", "Пунктуация", "—",
                        deprel=deprel, head=head,
                        char_start=cs, char_end=ce,
                        sent_id=sent_idx, token_id=tok_id,
                    ))
                    continue
                upos = word.upos or "X"
                feats_str = word.feats if word.feats else "—"
                feats_ru = self._translate_feats(feats_str) if feats_str != "—" else "—"
                pos_label = UPOS_RU.get(upos, upos)
                if upos == "VERB" and feats_str:
                    if "VerbForm=Part" in feats_str:
                        pos_label = "Причастие"
                    elif "VerbForm=Conv" in feats_str:
                        pos_label = "Деепричастие"
                tokens.append(TokenInfo(
                    word.text, word.lemma or word.text.lower(),
                    upos, pos_label, feats_ru,
                    deprel=deprel, head=head,
                    char_start=cs, char_end=ce,
                    sent_id=sent_idx, token_id=tok_id,
                ))
        return tokens

    @staticmethod
    def _translate_feats(feats_str: str) -> str:
        if not feats_str or feats_str == "—":
            return "—"
        parts = []
        for pair in feats_str.split("|"):
            if "=" in pair:
                k, v = pair.split("=", 1)
                k_ru = FEAT_RU.get(k, k)
                v_ru = FEAT_RU.get(v, v)
                parts.append(f"{k_ru}: {v_ru}")
            else:
                parts.append(FEAT_RU.get(pair, pair))
        return "; ".join(parts)
