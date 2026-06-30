# -*- coding: utf-8 -*-
"""
Сборщик корпуса с известным авторством (Habr) → data/corpus_auth/<автор>/<id>.txt

Использует открытый JSON-API Habr (автор = аккаунт). Берёт только статьи
индивидуальных авторов (не корпоративные блоги). HTML очищается до текста.

Запуск:
    python tools/gather_corpus.py                       # 12 авторов × 3 текста
    python tools/gather_corpus.py --authors 20 --per-author 4 --min-words 200
    python tools/gather_corpus.py --users alizar,ru_vds,...   # явный список

Замечание: это материал жанра «научпоп/IT-блог». Для судебной задачи нужен
корпус, близкий по жанру к исследуемым текстам (доменный сдвиг!). Здесь —
для отладки стенда валидации и демонстрации метода.
"""
from __future__ import annotations
import argparse
import html
import io
import os
import re
import sys
import time

import requests

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
except Exception:
    pass

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_OUT = os.path.join(_ROOT, "data", "corpus_auth")
_H = {"User-Agent": "Mozilla/5.0 (corpus-builder; research)"}
_API = "https://habr.com/kek/v2"


def _clean(html_text: str) -> str:
    t = re.sub(r"(?is)<(script|style|figure|pre|code).*?</\1>", " ", html_text)
    t = re.sub(r"(?s)<[^>]+>", " ", t)
    t = html.unescape(t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _get(url: str):
    r = requests.get(url, headers=_H, timeout=25)
    r.raise_for_status()
    return r.json()


def discover_authors(n_authors: int, pages: int = 12) -> list[str]:
    """Собрать индивидуальных авторов из общей ленты статей."""
    seen, order = set(), []
    for page in range(1, pages + 1):
        try:
            d = _get(f"{_API}/articles/?news=false&fl=ru&hl=ru&page={page}")
        except Exception:
            continue
        refs = d.get("publicationRefs", {})
        for pid in d.get("publicationIds", []):
            ref = refs.get(pid, {})
            if ref.get("isCorporative"):
                continue
            alias = (ref.get("author") or {}).get("alias")
            if alias and alias not in seen:
                seen.add(alias)
                order.append(alias)
        if len(order) >= n_authors * 3:
            break
        time.sleep(0.3)
    return order


def author_article_ids(alias: str, limit: int) -> list[str]:
    out = []
    for page in (1, 2):
        try:
            d = _get(f"{_API}/articles/?user={alias}&page={page}&fl=ru&hl=ru")
        except Exception:
            break
        out.extend(d.get("publicationIds", []))
        if len(out) >= limit * 2 or page >= d.get("pagesCount", 1):
            break
        time.sleep(0.2)
    return out


def fetch_article_text(aid: str) -> tuple[str, bool]:
    try:
        a = _get(f"{_API}/articles/{aid}/?fl=ru&hl=ru")
    except Exception:
        return "", False
    if a.get("isCorporative") or a.get("lang") != "ru":
        return "", False
    return _clean(a.get("textHtml") or ""), True


def gather(n_authors: int, per_author: int, min_words: int, users: list[str] | None):
    os.makedirs(_OUT, exist_ok=True)
    # глубже листаем ленту, если нужно много авторов (выход ~1/3 кандидатов)
    authors = users if users else discover_authors(n_authors, pages=max(15, n_authors * 3))
    print(f"Кандидатов в авторы: {len(authors)}")

    saved_authors = 0
    for alias in authors:
        if saved_authors >= n_authors:
            break
        ids = author_article_ids(alias, per_author + 4)
        texts = []
        for aid in ids:
            if len(texts) >= per_author:
                break
            txt, ok = fetch_article_text(aid)
            if ok and len(txt.split()) >= min_words:
                texts.append((aid, txt))
            time.sleep(0.2)
        if len(texts) < 2:        # автору нужно ≥2 текста для пар
            print(f"  — {alias}: мало пригодных текстов ({len(texts)}), пропуск")
            continue
        adir = os.path.join(_OUT, alias)
        os.makedirs(adir, exist_ok=True)
        for aid, txt in texts:
            with open(os.path.join(adir, f"{aid}.txt"), "w", encoding="utf-8") as f:
                f.write(txt)
        saved_authors += 1
        print(f"  ✓ {alias}: {len(texts)} текстов")
    print(f"\nГотово. Авторов сохранено: {saved_authors}. Папка: {_OUT}")
    print("Запустите стенд:  python tools/authorship_eval.py")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--authors", type=int, default=12)
    ap.add_argument("--per-author", type=int, default=3)
    ap.add_argument("--min-words", type=int, default=150)
    ap.add_argument("--users", type=str, default="")
    a = ap.parse_args()
    users = [u.strip() for u in a.users.split(",") if u.strip()] or None
    gather(a.authors, a.per_author, a.min_words, users)
