"""
analyzer/learning_backend.py — Инкрементальное обучение на корпусе.

Модели:
  FastText  — векторные представления слов (морф. n-граммы, хорош для RU)
  LdaModel  — тематическое моделирование (авто-определение тем)

Жизненный цикл:
  1. LearningBackend.update(new_sentences) — дообучить на новых текстах
  2. expand_thematic_dicts()               — расширить JSON-словари через similar words
  3. get_similar(word, topn)               — семантически близкие слова

Хранение: models/fasttext.model, models/lda.model
Порог для расширения словарей: cosine ≥ 0.75
"""
from __future__ import annotations
import os
import json
import logging
from typing import List, Optional, Dict

logging.getLogger("gensim").setLevel(logging.WARNING)

_MODELS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "models")
_FT_PATH    = os.path.join(_MODELS_DIR, "fasttext.model")
_LDA_PATH   = os.path.join(_MODELS_DIR, "lda.model")
_DATA_DIR   = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "thematic")

SIMILARITY_THRESHOLD = 0.75   # минимальный cosine для добавления слова в словарь
MIN_VOCAB_SIZE       = 50     # минимум уникальных слов для обучения

os.makedirs(_MODELS_DIR, exist_ok=True)


class LearningBackend:
    """FastText + LDA с инкрементальным обучением."""

    def __init__(self):
        self._ft = None       # gensim FastText
        self._lda = None      # gensim LdaModel
        self._dictionary = None  # gensim Dictionary для LDA
        self._ft_ready = False
        self._lda_ready = False

    # ── FastText ──────────────────────────────────────────────────────────

    def load_or_init_fasttext(self) -> None:
        """Загрузить FastText и LDA из файлов при старте приложения."""
        # FastText
        try:
            from gensim.models import FastText
            if os.path.exists(_FT_PATH):
                self._ft = FastText.load(_FT_PATH)
                self._ft_ready = True
        except Exception:
            self._ft = None
            self._ft_ready = False

        # LDA + Dictionary (загружаются вместе)
        try:
            from gensim.models import LdaModel
            from gensim.corpora import Dictionary
            if os.path.exists(_LDA_PATH):
                self._lda = LdaModel.load(_LDA_PATH)
                # gensim сохраняет Dictionary рядом с моделью
                _dict_path = _LDA_PATH + ".id2word"
                if os.path.exists(_dict_path):
                    self._dictionary = Dictionary.load(_dict_path)
                else:
                    # Восстановить словарь из корпуса если отдельного файла нет
                    try:
                        from analyzer.corpus_manager import get_all_lemma_sentences
                        sents = get_all_lemma_sentences()
                        if sents:
                            self._dictionary = Dictionary(sents)
                    except Exception:
                        pass
                if self._dictionary is not None:
                    self._lda_ready = True
        except Exception:
            self._lda = None
            self._lda_ready = False

    def update(self, sentences: List[List[str]], status_cb=None) -> bool:
        """
        Дообучить FastText на новых предложениях.
        sentences: [[лемма1, лемма2, ...], ...]
        Возвращает True если обучение прошло успешно.
        """
        sentences = [s for s in sentences if len(s) >= 3]
        if not sentences:
            return False

        all_words = [w for s in sentences for w in s]
        if len(set(all_words)) < MIN_VOCAB_SIZE:
            return False

        try:
            from gensim.models import FastText

            if status_cb:
                status_cb("Обучение FastText модели...")

            if self._ft is None:
                # Первое обучение — создать с нуля
                self._ft = FastText(
                    sentences=sentences,
                    vector_size=100,
                    window=5,
                    min_count=2,
                    workers=2,
                    epochs=5,
                    min_n=2,   # символьные n-граммы от 2 до 6 (важно для RU)
                    max_n=6,
                )
            else:
                # Инкрементальное дообучение
                self._ft.build_vocab(sentences, update=True)
                self._ft.train(
                    sentences,
                    total_examples=len(sentences),
                    epochs=3,
                )

            self._ft.save(_FT_PATH)
            self._ft_ready = True

            if status_cb:
                status_cb(f"FastText обновлён: {len(self._ft.wv)} слов в словаре")
            return True

        except Exception as e:
            if status_cb:
                status_cb(f"Ошибка обучения FastText: {e}")
            return False

    # ── LDA ───────────────────────────────────────────────────────────────

    def update_lda(self, sentences: List[List[str]], num_topics: int = 10,
                   status_cb=None) -> bool:
        """Дообучить LDA-модель тематик."""
        if not sentences:
            return False
        try:
            from gensim.corpora import Dictionary
            from gensim.models import LdaModel

            if status_cb:
                status_cb("Обновление LDA тематической модели...")

            if self._dictionary is None:
                self._dictionary = Dictionary(sentences)
            else:
                self._dictionary.add_documents(sentences)

            self._dictionary.filter_extremes(no_below=2, no_above=0.9)
            corpus = [self._dictionary.doc2bow(s) for s in sentences]

            if self._lda is None:
                self._lda = LdaModel(
                    corpus=corpus,
                    id2word=self._dictionary,
                    num_topics=num_topics,
                    passes=3,
                    alpha="auto",
                )
            else:
                self._lda.update(corpus)

            self._lda.save(_LDA_PATH)
            # Сохраняем Dictionary рядом с моделью для загрузки при следующем запуске
            self._dictionary.save(_LDA_PATH + ".id2word")
            self._lda_ready = True

            if status_cb:
                status_cb("LDA модель обновлена")
            return True

        except Exception as e:
            if status_cb:
                status_cb(f"Ошибка LDA: {e}")
            return False

    # ── Расширение тематических словарей ─────────────────────────────────

    def expand_thematic_dicts(self, status_cb=None) -> Dict[str, int]:
        """
        Расширить JSON-словари в data/thematic/ через FastText similar words.
        Возвращает {domain: количество_добавленных_слов}.
        """
        if not self._ft_ready or self._ft is None:
            return {}

        added: Dict[str, int] = {}

        for fname in os.listdir(_DATA_DIR):
            if not fname.endswith(".json"):
                continue
            domain = fname[:-5]
            path = os.path.join(_DATA_DIR, fname)

            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    existing = set(data)
                else:
                    existing = set(data.keys())

                # Берём seed-слова которые есть в FastText-словаре
                seed = [w for w in list(existing)[:30]
                        if w in self._ft.wv]
                if not seed:
                    continue

                new_words = set()
                for seed_word in seed:
                    try:
                        similars = self._ft.wv.most_similar(seed_word, topn=20)
                        for word, score in similars:
                            if score >= SIMILARITY_THRESHOLD and word not in existing:
                                new_words.add(word)
                    except Exception:
                        continue

                if new_words:
                    if isinstance(data, list):
                        data.extend(sorted(new_words))
                    else:
                        for w in new_words:
                            data[w] = 1  # вес 1 для новых слов
                    with open(path, "w", encoding="utf-8") as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)
                    added[domain] = len(new_words)

            except Exception:
                continue

        if status_cb and added:
            total = sum(added.values())
            status_cb(f"Словари расширены: +{total} слов по {len(added)} доменам")

        return added

    # ── Запросы к модели ──────────────────────────────────────────────────

    def get_similar(self, word: str, topn: int = 10) -> List[tuple]:
        """Вернуть список (слово, similarity) для word."""
        if not self._ft_ready or self._ft is None:
            return []
        try:
            return self._ft.wv.most_similar(word, topn=topn)
        except Exception:
            return []

    def get_lda_topics(self, lemmas: List[str]) -> List[tuple]:
        """Определить темы для списка лемм. Возвращает [(тема, вес), ...]."""
        if not self._lda_ready or self._lda is None or self._dictionary is None:
            return []
        try:
            bow = self._dictionary.doc2bow(lemmas)
            return sorted(self._lda.get_document_topics(bow),
                          key=lambda x: -x[1])
        except Exception:
            return []

    def get_lda_topic_words(self, topic_id: int, topn: int = 5) -> List[str]:
        """Вернуть ключевые слова темы LDA."""
        if not self._lda_ready or self._lda is None:
            return []
        try:
            terms = self._lda.show_topic(topic_id, topn=topn)
            return [word for word, _ in terms]
        except Exception:
            return []

    def vector_similarity(self, lemmas1: List[str], lemmas2: List[str]) -> float:
        """Косинусное сходство двух текстов через усреднённые FastText-векторы."""
        if not self._ft_ready or self._ft is None:
            return 0.0
        try:
            import numpy as np
            def _mean_vec(lemmas):
                vecs = [self._ft.wv[w] for w in lemmas if w in self._ft.wv]
                return np.mean(vecs, axis=0) if vecs else None

            v1, v2 = _mean_vec(lemmas1), _mean_vec(lemmas2)
            if v1 is None or v2 is None:
                return 0.0
            cos = float(np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2) + 1e-9))
            return round(max(0.0, min(1.0, cos)), 3)
        except Exception:
            return 0.0

    @property
    def ft_ready(self) -> bool:
        return self._ft_ready

    @property
    def lda_ready(self) -> bool:
        return self._lda_ready

    @property
    def vocab_size(self) -> int:
        if self._ft_ready and self._ft:
            return len(self._ft.wv)
        return 0


# Singleton
_instance = LearningBackend()


def get() -> LearningBackend:
    return _instance
