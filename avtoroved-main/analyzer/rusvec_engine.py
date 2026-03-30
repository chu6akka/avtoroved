"""
analyzer/rusvec_engine.py — Семантическое расширение тематических словарей.

Бэкенд: Navec (Natasha / Yandex Cloud)
  Модель: navec_hudlit_v1_12B_500K_300d_100q
  Обучена на 12 миллиардах токенов художественной литературы на русском языке.
  Размер: ~50 МБ (квантованные векторы, 500K слов).
  Лицензия: MIT

Использование:
    engine = get()
    engine.download(status_cb)      # скачать модель (один раз)
    engine.load()                   # загрузить в память
    words = engine.most_similar("лечение", topn=20, threshold=0.65)
    added = engine.expand_domain_file("data/thematic/medicine.json", topn=20, threshold=0.65)

Ref: Kuznetsov I., Tikhonov A. Navec: Compact Embeddings for Russian.
     github.com/natasha/navec
"""
from __future__ import annotations

import json
import logging
import os
import tarfile
import urllib.request
from typing import Callable, Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

_MODELS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "models")
_NAVEC_PATH = os.path.join(_MODELS_DIR, "navec_hudlit.tar")
_DATA_DIR   = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "thematic")

_NAVEC_URL = (
    "https://storage.yandexcloud.net/natasha-navec/packs/"
    "navec_hudlit_v1_12B_500K_300d_100q.tar"
)

SIMILARITY_THRESHOLD = 0.65   # ниже — слишком далёкие слова
os.makedirs(_MODELS_DIR, exist_ok=True)


class RusVecEngine:
    """Семантическое расширение словарей через предобученные векторы Navec."""

    def __init__(self):
        self._kv   = None      # gensim KeyedVectors
        self._ready = False

    # ── Загрузка ──────────────────────────────────────────────────────────

    @property
    def is_downloaded(self) -> bool:
        return os.path.exists(_NAVEC_PATH)

    @property
    def is_ready(self) -> bool:
        return self._ready

    def download(self, status_cb: Optional[Callable[[str], None]] = None) -> bool:
        """
        Скачать модель Navec (~50 МБ) с Yandex Cloud.
        Возвращает True при успехе.
        """
        if self.is_downloaded:
            if status_cb:
                status_cb("Navec: модель уже скачана.")
            return True

        try:
            if status_cb:
                status_cb("Navec: скачивание модели (~50 МБ)…")

            def _report(block, block_size, total):
                if total > 0 and status_cb:
                    pct = min(100, int(block * block_size / total * 100))
                    status_cb(f"Navec: скачивание… {pct}%")

            urllib.request.urlretrieve(_NAVEC_URL, _NAVEC_PATH, _report)

            if status_cb:
                status_cb("Navec: скачивание завершено.")
            return True

        except Exception as exc:
            log.error("Navec download failed: %s", exc)
            if os.path.exists(_NAVEC_PATH):
                os.remove(_NAVEC_PATH)
            if status_cb:
                status_cb(f"Navec: ошибка скачивания — {exc}")
            return False

    def load(self, status_cb: Optional[Callable[[str], None]] = None) -> bool:
        """Загрузить модель в память."""
        if self._ready:
            return True
        if not self.is_downloaded:
            if status_cb:
                status_cb("Navec: модель не скачана.")
            return False

        try:
            if status_cb:
                status_cb("Navec: загрузка модели…")
            from navec import Navec
            navec = Navec.load(_NAVEC_PATH)
            self._kv = navec.as_gensim
            self._ready = True
            if status_cb:
                vocab = len(self._kv)
                status_cb(f"Navec готов: {vocab:,} слов в словаре".replace(",", " "))
            return True

        except ImportError:
            if status_cb:
                status_cb("Navec: установите пакет navec (pip install navec)")
            return False
        except Exception as exc:
            log.error("Navec load failed: %s", exc)
            if status_cb:
                status_cb(f"Navec: ошибка загрузки — {exc}")
            return False

    # ── Семантический поиск ───────────────────────────────────────────────

    def most_similar(
        self,
        word: str,
        topn: int = 20,
        threshold: float = SIMILARITY_THRESHOLD,
    ) -> List[Tuple[str, float]]:
        """
        Вернуть список (слово, сходство) — только слова выше порога.
        Навек не использует POS-теги, работает с леммами напрямую.
        """
        if not self._ready or self._kv is None:
            return []
        if word not in self._kv:
            return []
        try:
            results = self._kv.most_similar(word, topn=topn)
            return [(w, s) for w, s in results if s >= threshold]
        except Exception as exc:
            log.debug("most_similar('%s'): %s", word, exc)
            return []

    # ── Расширение словарей ───────────────────────────────────────────────

    def expand_domain_file(
        self,
        json_path: str,
        topn: int = 20,
        threshold: float = SIMILARITY_THRESHOLD,
        seed_limit: int = 40,
        status_cb: Optional[Callable[[str], None]] = None,
    ) -> int:
        """
        Расширить один JSON-словарь через семантическое сходство.
        Возвращает количество добавленных слов.
        """
        if not self._ready:
            return 0

        try:
            with open(json_path, encoding="utf-8") as f:
                data = json.load(f)
        except Exception as exc:
            log.error("expand_domain_file read %s: %s", json_path, exc)
            return 0

        existing: set
        if isinstance(data, list):
            existing = set(data)
        else:
            existing = set(data.keys())

        # Берём первые seed_limit слов которые есть в словаре Navec
        seeds = [w for w in list(existing)[:seed_limit] if w in self._kv]
        if not seeds:
            return 0

        new_words: set = set()
        for seed in seeds:
            for word, score in self.most_similar(seed, topn=topn, threshold=threshold):
                # Только кириллица, минимум 3 буквы, не служебное
                if len(word) >= 3 and word.isalpha() and word not in existing:
                    new_words.add(word)

        if not new_words:
            return 0

        if isinstance(data, list):
            data.extend(sorted(new_words))
        else:
            for w in new_words:
                data[w] = 1

        try:
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as exc:
            log.error("expand_domain_file write %s: %s", json_path, exc)
            return 0

        return len(new_words)

    def expand_all_domains(
        self,
        topn: int = 20,
        threshold: float = SIMILARITY_THRESHOLD,
        status_cb: Optional[Callable[[str], None]] = None,
    ) -> Dict[str, int]:
        """
        Расширить все тематические словари в data/thematic/.
        Возвращает {domain: добавлено_слов}.
        """
        if not self._ready:
            return {}

        added: Dict[str, int] = {}
        for fname in sorted(os.listdir(_DATA_DIR)):
            if not fname.endswith(".json"):
                continue
            domain = fname[:-5]
            path   = os.path.join(_DATA_DIR, fname)

            if status_cb:
                status_cb(f"Navec: расширяю «{domain}»…")

            count = self.expand_domain_file(path, topn=topn, threshold=threshold)
            if count:
                added[domain] = count

        if status_cb:
            total = sum(added.values())
            if total:
                status_cb(f"Navec: добавлено {total} слов по {len(added)} доменам.")
            else:
                status_cb("Navec: новых слов не найдено (порог не преодолён).")

        return added


# ── Синглтон ─────────────────────────────────────────────────────────────────

_instance: Optional[RusVecEngine] = None


def get() -> RusVecEngine:
    global _instance
    if _instance is None:
        _instance = RusVecEngine()
    return _instance
