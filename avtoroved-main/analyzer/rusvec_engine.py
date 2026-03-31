"""
analyzer/rusvec_engine.py — Семантическое расширение тематических словарей.

Два бэкенда (можно использовать оба):

  Navec (Natasha / Yandex Cloud)
    Модель: navec_hudlit_v1_12B_500K_300d_100q
    ~50 МБ · 500K слов · без POS-тегов · MIT
    Ссылка: github.com/natasha/navec

  RusVectores (НКРЯ, ИРЯ РАН)
    Модель: ruscorpora_upos_cbow_300_20_2019
    ~462 МБ · НКРЯ 2019 · слова в формате лемма_UPOS · CC-BY
    Ссылка: rusvectores.org

Использование:
    engine = get()
    engine.download_navec(cb)          # скачать Navec (~50 МБ)
    engine.load_navec(cb)
    engine.download_rusvec(cb)         # скачать RusVectores (~462 МБ)
    engine.load_rusvec(cb)
    added = engine.expand_all_domains(backend="both", cb)
"""
from __future__ import annotations

import json
import logging
import os
import tarfile
import urllib.request
import zipfile
from typing import Callable, Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

_MODELS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "models")
_DATA_DIR   = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "thematic")

# ── Navec ─────────────────────────────────────────────────────────────────────
_NAVEC_PATH = os.path.join(_MODELS_DIR, "navec_hudlit.tar")
_NAVEC_URL  = (
    "https://storage.yandexcloud.net/natasha-navec/packs/"
    "navec_hudlit_v1_12B_500K_300d_100q.tar"
)

# ── RusVectores (НКРЯ 2019, UPOS, CBOW 300d) ─────────────────────────────────
_RUSVEC_ZIP  = os.path.join(_MODELS_DIR, "rusvec_2019.zip")
_RUSVEC_BIN  = os.path.join(_MODELS_DIR, "rusvec_2019.bin")
_RUSVEC_URL  = "https://vectors.nlpl.eu/repository/20/180.zip"

# POS-теги, которые пробуем при поиске в RusVectores
_UPOS_VARIANTS = ("NOUN", "VERB", "ADJ", "ADV")

SIMILARITY_THRESHOLD = 0.65

os.makedirs(_MODELS_DIR, exist_ok=True)


# ── Navec-совместимая обёртка (без gensim) ────────────────────────────────────

class _NavecKV:
    """
    Лёгкая обёртка над navec, реализующая most_similar через numpy.

    Не зависит от gensim API (as_gensim сломан в gensim ≥ 4.0).
    При создании распаковывает все PQ-векторы (~600 МБ RAM) один раз —
    это необходимо для быстрого поиска ближайших соседей.
    """

    def __init__(self, navec_model):
        import numpy as np
        words = list(navec_model.vocab.words)
        self._words = words
        self._stoi: dict = {w: i for i, w in enumerate(words)}
        # Распаковать все PQ-сжатые векторы в float32-матрицу (N × 300)
        vecs = navec_model.pq.unpack().astype(np.float32)
        # Нормализовать для косинусного сходства
        norms = np.linalg.norm(vecs, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        self._vecs_norm = vecs / norms

    def __contains__(self, word: str) -> bool:
        return word in self._stoi

    def __len__(self) -> int:
        return len(self._words)

    def most_similar(self, word: str, topn: int = 10):
        """Вернуть список (word, score) — аналог gensim most_similar."""
        import numpy as np
        if word not in self._stoi:
            return []
        idx = self._stoi[word]
        sims = self._vecs_norm @ self._vecs_norm[idx]
        sims[idx] = -1.0  # исключить само слово
        top_k = np.argpartition(sims, -topn)[-topn:]
        top_k = top_k[np.argsort(sims[top_k])[::-1]]
        return [(self._words[i], float(sims[i])) for i in top_k]


# ── Вспомогательные функции ───────────────────────────────────────────────────

def _download_file(url: str, dest: str,
                   status_cb: Optional[Callable] = None) -> bool:
    """Скачать файл с прогрессом. Возвращает True при успехе."""
    try:
        def _report(block, bsize, total):
            if total > 0 and status_cb:
                pct = min(100, int(block * bsize / total * 100))
                mb  = total // (1024 * 1024)
                status_cb(f"Скачивание… {pct}%  ({mb} МБ)")

        urllib.request.urlretrieve(url, dest, _report)
        return True
    except Exception as exc:
        log.error("download %s → %s: %s", url, dest, exc)
        if os.path.exists(dest):
            os.remove(dest)
        if status_cb:
            status_cb(f"Ошибка скачивания: {exc}")
        return False


class RusVecEngine:
    """Два семантических бэкенда для расширения словарей."""

    def __init__(self):
        self._kv_navec:  Optional[object] = None
        self._kv_rusvec: Optional[object] = None

    # ── Navec: состояние ─────────────────────────────────────────────────────

    @property
    def navec_downloaded(self) -> bool:
        return os.path.exists(_NAVEC_PATH)

    @property
    def navec_ready(self) -> bool:
        return self._kv_navec is not None

    # ── Navec: скачать + загрузить ────────────────────────────────────────────

    def download_navec(self, status_cb=None) -> bool:
        if self.navec_downloaded:
            if status_cb:
                status_cb("Navec: уже скачан.")
            return True
        if status_cb:
            status_cb("Navec: скачивание (~50 МБ)…")
        return _download_file(_NAVEC_URL, _NAVEC_PATH, status_cb)

    def load_navec(self, status_cb=None) -> bool:
        if self.navec_ready:
            return True
        if not self.navec_downloaded:
            if status_cb:
                status_cb("Navec: не скачан.")
            return False
        try:
            if status_cb:
                status_cb("Navec: загрузка файла…")
            from navec import Navec
            navec_model = Navec.load(_NAVEC_PATH)
            if status_cb:
                status_cb("Navec: распаковка векторов (~30 сек.)…")
            self._kv_navec = _NavecKV(navec_model)
            if status_cb:
                status_cb(f"Navec готов: {len(self._kv_navec):,} слов".replace(",", " "))
            return True
        except ImportError:
            if status_cb:
                status_cb("Navec: установите пакет  pip install navec")
            return False
        except Exception as exc:
            if status_cb:
                status_cb(f"Navec: ошибка загрузки — {exc}")
            return False

    # ── RusVectores: состояние ────────────────────────────────────────────────

    @property
    def rusvec_downloaded(self) -> bool:
        if os.path.exists(_RUSVEC_BIN):
            return True
        # ZIP считается скачанным только если он валидный
        if os.path.exists(_RUSVEC_ZIP):
            try:
                with zipfile.ZipFile(_RUSVEC_ZIP) as zf:
                    return bool(zf.namelist())
            except Exception:
                # Повреждённый ZIP — удаляем
                try:
                    os.remove(_RUSVEC_ZIP)
                except Exception:
                    pass
                return False
        return False

    @property
    def rusvec_ready(self) -> bool:
        return self._kv_rusvec is not None

    # ── RusVectores: скачать + загрузить ─────────────────────────────────────

    def download_rusvec(self, status_cb=None) -> bool:
        if os.path.exists(_RUSVEC_BIN):
            if status_cb:
                status_cb("RusVectores: уже скачан.")
            return True
        if not os.path.exists(_RUSVEC_ZIP):
            if status_cb:
                status_cb("RusVectores: скачивание (~462 МБ)…")
            if not _download_file(_RUSVEC_URL, _RUSVEC_ZIP, status_cb):
                return False
        # Извлечь model.bin из ZIP
        if status_cb:
            status_cb("RusVectores: распаковка…")
        try:
            with zipfile.ZipFile(_RUSVEC_ZIP) as zf:
                names = zf.namelist()
                bin_name = next((n for n in names if n.endswith(".bin")), None)
                if bin_name is None:
                    # Попробовать .txt / .vec
                    bin_name = next(
                        (n for n in names if n.endswith((".txt", ".vec"))), None
                    )
                if bin_name is None:
                    if status_cb:
                        status_cb(f"RusVectores: не найден model.bin в архиве. Файлы: {names}")
                    return False
                zf.extract(bin_name, _MODELS_DIR)
                extracted = os.path.join(_MODELS_DIR, bin_name)
                if extracted != _RUSVEC_BIN:
                    os.rename(extracted, _RUSVEC_BIN)
            # Удалить ZIP (он больше не нужен)
            os.remove(_RUSVEC_ZIP)
            if status_cb:
                status_cb("RusVectores: распаковка завершена.")
            return True
        except Exception as exc:
            if status_cb:
                status_cb(f"RusVectores: ошибка распаковки — {exc}")
            return False

    def load_rusvec(self, status_cb=None) -> bool:
        if self.rusvec_ready:
            return True
        if not os.path.exists(_RUSVEC_BIN):
            if status_cb:
                status_cb("RusVectores: модель не скачана.")
            return False
        try:
            if status_cb:
                status_cb("RusVectores: загрузка (~1-2 мин.)…")
            from gensim.models import KeyedVectors
            # Пробуем бинарный формат; если не сработает — текстовый
            try:
                self._kv_rusvec = KeyedVectors.load_word2vec_format(
                    _RUSVEC_BIN, binary=True
                )
            except Exception:
                self._kv_rusvec = KeyedVectors.load_word2vec_format(
                    _RUSVEC_BIN, binary=False
                )
            if status_cb:
                status_cb(
                    f"RusVectores готов: "
                    f"{len(self._kv_rusvec):,} слов".replace(",", " ")
                )
            return True
        except Exception as exc:
            if status_cb:
                status_cb(f"RusVectores: ошибка загрузки — {exc}")
            return False

    # ── Поиск похожих слов ────────────────────────────────────────────────────

    def _similar_navec(self, word: str, topn: int,
                       threshold: float) -> List[str]:
        if self._kv_navec is None or word not in self._kv_navec:
            return []
        try:
            results = self._kv_navec.most_similar(word, topn=topn)
            return [w for w, s in results if s >= threshold]
        except Exception:
            return []

    def _similar_rusvec(self, word: str, topn: int,
                        threshold: float) -> List[str]:
        """Пробуем word_NOUN, word_VERB, word_ADJ, word_ADV."""
        if self._kv_rusvec is None:
            return []
        found: List[str] = []
        for pos in _UPOS_VARIANTS:
            key = f"{word}_{pos}"
            if key not in self._kv_rusvec:
                continue
            try:
                results = self._kv_rusvec.most_similar(key, topn=topn)
                for w, s in results:
                    if s >= threshold:
                        # Снять POS-тег: "лечение_NOUN" → "лечение"
                        clean = w.rsplit("_", 1)[0]
                        found.append(clean)
            except Exception:
                continue
            break   # взяли первый подходящий POS
        return found

    # ── Расширение словарей ───────────────────────────────────────────────────

    def expand_domain_file(
        self,
        json_path: str,
        backend: str = "both",          # "navec" | "rusvec" | "both"
        topn: int = 20,
        threshold: float = SIMILARITY_THRESHOLD,
        seed_limit: int = 40,
    ) -> int:
        try:
            with open(json_path, encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return 0

        existing = set(data) if isinstance(data, list) else set(data.keys())
        seeds = [w for w in list(existing)[:seed_limit]
                 if len(w) >= 3 and w.isalpha()]

        new_words: set = set()
        for seed in seeds:
            if backend in ("navec", "both"):
                new_words.update(self._similar_navec(seed, topn, threshold))
            if backend in ("rusvec", "both"):
                new_words.update(self._similar_rusvec(seed, topn, threshold))

        # Оставить только новые кириллические слова длиной ≥ 3
        new_words = {
            w for w in new_words
            if len(w) >= 3 and w.isalpha() and w not in existing
        }
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
        except Exception:
            return 0
        return len(new_words)

    def expand_all_domains(
        self,
        backend: str = "both",
        topn: int = 20,
        threshold: float = SIMILARITY_THRESHOLD,
        status_cb=None,
    ) -> Dict[str, int]:
        if not self.navec_ready and not self.rusvec_ready:
            if status_cb:
                status_cb("Нет загруженных моделей.")
            return {}

        added: Dict[str, int] = {}
        for fname in sorted(os.listdir(_DATA_DIR)):
            if not fname.endswith(".json"):
                continue
            domain = fname[:-5]
            path   = os.path.join(_DATA_DIR, fname)
            if status_cb:
                status_cb(f"Расширяю «{domain}»…")
            count = self.expand_domain_file(
                path, backend=backend, topn=topn, threshold=threshold
            )
            if count:
                added[domain] = count

        if status_cb:
            total = sum(added.values())
            if total:
                status_cb(
                    f"Готово: +{total} слов по {len(added)} доменам.")
            else:
                status_cb("Новых слов не найдено (порог не преодолён).")
        return added

    # ── Статус ────────────────────────────────────────────────────────────────

    def status_text(self) -> str:
        parts = []
        if self.navec_ready:
            parts.append("Navec ✓")
        elif self.navec_downloaded:
            parts.append("Navec (скачан)")
        else:
            parts.append("Navec ✗")
        if self.rusvec_ready:
            parts.append("RusVectores ✓")
        elif self.rusvec_downloaded:
            parts.append("RusVectores (скачан)")
        else:
            parts.append("RusVectores ✗")
        return "  |  ".join(parts)


# ── Синглтон ─────────────────────────────────────────────────────────────────

_instance: Optional[RusVecEngine] = None


def get() -> RusVecEngine:
    global _instance
    if _instance is None:
        _instance = RusVecEngine()
    return _instance
