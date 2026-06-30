"""Семантический слой на Navec-эмбеддингах (оффлайн, поставляются с Natasha).

Определяет тематику/контекст по близости центроида текста к центроиду словаря темы,
а не по точному совпадению слов — ловит синонимы и родственную лексику.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from threading import Lock

import numpy as np

_NAVEC = None
_LOCK = Lock()
_CONTENT_POS = {"NOUN", "ADJ", "VERB", "ADV", "PROPN"}


def _navec_path() -> Path:
    import natasha

    base = Path(natasha.__file__).resolve().parent / "data" / "emb"
    direct = base / "navec_news_v1_1B_250K_300d_100q.tar"
    if direct.exists():
        return direct
    found = list(base.glob("navec_*.tar"))
    if not found:
        raise FileNotFoundError("не найдена модель navec в составе natasha")
    return found[0]


def get_navec():
    global _NAVEC
    with _LOCK:
        if _NAVEC is None:
            from navec import Navec

            _NAVEC = Navec.load(str(_navec_path()))
    return _NAVEC


def _mean_vector(words) -> np.ndarray | None:
    nav = get_navec()
    vecs = [nav[w] for w in words if w in nav]
    if not vecs:
        return None
    v = np.mean(vecs, axis=0)
    norm = np.linalg.norm(v)
    return v / norm if norm else None


@lru_cache(maxsize=64)
def lexicon_centroid(path_str: str) -> np.ndarray | None:
    p = Path(path_str)
    if not p.exists():
        return None
    words: list[str] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        t = line.strip().lower()
        if t and not t.startswith("#"):
            words.extend(t.split())
    return _mean_vector(words)


def text_centroid(ctx) -> np.ndarray | None:
    def compute():
        from aved.nlp.frequency import informativeness

        nav = get_navec()
        vecs, weights = [], []
        for t in ctx.doc.words:
            if t.pos in _CONTENT_POS and t.lemma in nav:
                vecs.append(nav[t.lemma])
                weights.append(informativeness(t.lemma))  # редкие слова весомее
        if not vecs:
            return None
        v = np.average(vecs, axis=0, weights=weights)
        norm = np.linalg.norm(v)
        return v / norm if norm else None

    return ctx.cached("text_centroid", compute)


def theme_score(ctx, lexicon_path: str) -> float:
    """Косинусная близость текста к теме словаря, приведённая к [0, 1]."""
    tc = text_centroid(ctx)
    lc = lexicon_centroid(lexicon_path)
    if tc is None or lc is None:
        return 0.0
    return max(0.0, float(np.dot(tc, lc)))
