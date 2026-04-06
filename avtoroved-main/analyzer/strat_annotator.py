"""
analyzer/strat_annotator.py — Контекстный ML-фильтр ложных срабатываний стратификации.

Логика:
  1. Эксперт в UI помечает слова как "exclude" (ложное) или "confirm" (верное).
  2. Аннотации хранятся в corpus.db (таблица strat_annotations).
  3. При наличии ≥MIN_SAMPLES примеров — обучается LogisticRegression
     на TF-IDF контекстных окон вокруг слова.
  4. Модель применяется автоматически при следующих анализах:
     слова с высокой уверенностью "exclude" убираются из результатов.

Зависимости: scikit-learn (необязательный, при отсутствии — модуль отключён).
"""
from __future__ import annotations
import os
import re
import pickle
from typing import Optional

_MODEL_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "models", "strat_clf.pkl"
)
MIN_SAMPLES = 10        # минимум аннотаций для запуска обучения
MIN_PER_LAYER = 6       # минимум на один пласт (нужны оба класса)
THRESHOLD = 0.72        # уверенность, при которой слово исключается

_WORD_RE = re.compile(r"[а-яёА-ЯЁa-zA-Z]+")


def _context_features(context: str, lemma: str) -> str:
    """
    Из контекстного окна сформировать строку признаков для TF-IDF.
    Добавляем специальный токен TARGET_<lemma> чтобы модель знала целевое слово.
    """
    words = _WORD_RE.findall(context.lower())
    lm = lemma.lower()
    bag = [w for w in words if w != lm]
    bag.append(f"TARGET_{lm}")
    return " ".join(bag)


class StratAnnotatorModel:
    """Обёртка над sklearn-пайплайнами (по одному на каждый пласт)."""

    def __init__(self):
        self._pipelines: dict = {}   # layer → sklearn Pipeline
        self._ready = False
        self._load()

    # ── Персистентность ───────────────────────────────────────────────────

    def _load(self) -> None:
        if os.path.exists(_MODEL_PATH):
            try:
                with open(_MODEL_PATH, "rb") as f:
                    data = pickle.load(f)
                if isinstance(data, dict):
                    self._pipelines = data
                    self._ready = bool(data)
            except Exception:
                pass

    def _save(self) -> None:
        os.makedirs(os.path.dirname(_MODEL_PATH), exist_ok=True)
        with open(_MODEL_PATH, "wb") as f:
            pickle.dump(self._pipelines, f)

    # ── Обучение ──────────────────────────────────────────────────────────

    def train(self, annotations: list) -> tuple[bool, str]:
        """
        Обучить по списку аннотаций из corpus_manager.get_all_strat_annotations().
        Возвращает (success: bool, message: str).
        """
        try:
            from sklearn.linear_model import LogisticRegression
            from sklearn.feature_extraction.text import TfidfVectorizer
            from sklearn.pipeline import Pipeline
        except ImportError:
            return False, "Установите scikit-learn: pip install scikit-learn"

        if len(annotations) < MIN_SAMPLES:
            return False, (
                f"Нужно минимум {MIN_SAMPLES} аннотаций "
                f"(сейчас: {len(annotations)})"
            )

        # Сгруппировать по пласту
        by_layer: dict[str, list] = {}
        for ann in annotations:
            by_layer.setdefault(ann["layer"], []).append(ann)

        new_pipes: dict = {}
        trained: list[str] = []
        skipped: list[str] = []

        for layer, anns in by_layer.items():
            if len(anns) < MIN_PER_LAYER:
                skipped.append(f"{layer}({len(anns)})")
                continue

            texts, labels = [], []
            for ann in anns:
                texts.append(_context_features(
                    ann.get("context", ""), ann.get("lemma", "")))
                labels.append(0 if ann["verdict"] == "exclude" else 1)

            if len(set(labels)) < 2:
                skipped.append(f"{layer}(один класс)")
                continue

            pipe = Pipeline([
                ("tfidf", TfidfVectorizer(max_features=500, ngram_range=(1, 2),
                                          min_df=1, sublinear_tf=True)),
                ("clf", LogisticRegression(C=1.0, max_iter=1000,
                                           class_weight="balanced",
                                           random_state=42)),
            ])
            pipe.fit(texts, labels)
            new_pipes[layer] = pipe
            trained.append(layer)

        if not new_pipes:
            return False, (
                "Недостаточно данных для обучения. Нужны примеры обоих классов "
                f"(exclude и confirm) на каждый пласт. Пропущено: {', '.join(skipped)}"
            )

        self._pipelines = new_pipes
        self._ready = True
        self._save()

        msg = f"Обучено пластов: {len(trained)}"
        if trained:
            msg += f" ({', '.join(trained)})"
        if skipped:
            msg += f". Пропущено: {', '.join(skipped)}"
        return True, msg

    # ── Инференс ──────────────────────────────────────────────────────────

    @property
    def is_ready(self) -> bool:
        return self._ready

    def is_false_positive(self, lemma: str, context: str, layer: str) -> bool:
        """
        True — модель считает, что слово является ложным срабатыванием.
        Вернёт False если нет модели для данного пласта или sklearn недоступен.
        """
        if not self._ready:
            return False
        pipe = self._pipelines.get(layer)
        if pipe is None:
            return False
        try:
            feat = _context_features(context, lemma)
            proba = pipe.predict_proba([feat])[0]
            # proba[0] = P(exclude/false positive), proba[1] = P(confirm)
            return float(proba[0]) > THRESHOLD
        except Exception:
            return False

    def layer_stats(self) -> dict:
        """Словарь layer→число обучающих примеров (для UI)."""
        if not self._pipelines:
            return {}
        result = {}
        for layer, pipe in self._pipelines.items():
            try:
                result[layer] = len(pipe.named_steps["clf"].classes_)
            except Exception:
                result[layer] = "?"
        return result


# ── Singleton ─────────────────────────────────────────────────────────────────

_instance: Optional[StratAnnotatorModel] = None


def get() -> StratAnnotatorModel:
    global _instance
    if _instance is None:
        _instance = StratAnnotatorModel()
    return _instance


def retrain(annotations: list) -> tuple[bool, str]:
    """Переобучить и обновить singleton."""
    global _instance
    if _instance is None:
        _instance = StratAnnotatorModel()
    ok, msg = _instance.train(annotations)
    return ok, msg
