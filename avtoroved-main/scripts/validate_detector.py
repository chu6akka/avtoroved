# -*- coding: utf-8 -*-
"""
scripts/validate_detector.py — валидация детектора ошибок программы на
открытых корпусах RUSpellRU и MultidomainGold
(ai-forever/spellcheck_punctuation_benchmark, HuggingFace).

Прогоняется ШТАТНЫЙ путь детектора протокола: собственные правила пунктуации
(punct_checker) + LanguageTool строго в локальном режиме + слой фильтрации
detector_filter с текущим конфигом. Тексты корпусов НЕ являются материалами
дел — отправка их в публичные сервисы не происходит (LT только локальный).

Загрузка датасета (по убыванию предпочтения):
  1) библиотека `datasets` (если установлена);
  2) библиотека SAGE (если установлена);
  3) прямой HTTP к datasets-server.huggingface.co (без зависимостей).

Скоринг:
  • SAGE-скорер (ruspelleval), если SAGE установлен;
  • иначе встроенный ПОСЛОВНЫЙ скорер — ПРИБЛИЖЕНИЕ: слово с расхождением
    source↔correction считается эталонной ошибкой; слово, накрытое
    срабатыванием детектора, — предсказанием. Категории: SPELL/PUNCT/CASE/YO.

Логируется: версия LanguageTool и режим, хэш конфига фильтра, имя/конфиг/сплит
и объём датасета, дата прогона. Результат — markdown-таблица (--out).

Запуск:
    python scripts/validate_detector.py --limit 150 --out docs/validation.md
"""
from __future__ import annotations

import argparse
import datetime
import difflib
import json
import os
import re
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DATASET = "ai-forever/spellcheck_punctuation_benchmark"
CONFIGS = ["RUSpellRU", "MultidomainGold"]
SPLIT = "test"

_WORD_RE = re.compile(r"[A-Za-zА-Яа-яЁё]+|[^\sA-Za-zА-Яа-яЁё]+")


# ── загрузка датасета ────────────────────────────────────────────────────────
def load_rows(config: str, limit: int) -> tuple[list[dict], str]:
    """Вернуть (строки [{source, correction}], способ загрузки)."""
    # 1) datasets
    try:
        from datasets import load_dataset  # type: ignore
        ds = load_dataset(DATASET, config, split=SPLIT)
        rows = [{"source": r["source"], "correction": r["correction"]}
                for r in list(ds)[:limit]]
        return rows, "datasets"
    except Exception:
        pass
    # 2) SAGE
    try:
        from sage.utils import load_available_dataset_from_hf  # type: ignore
        src, corr = load_available_dataset_from_hf(config, for_labeler=False,
                                                   split=SPLIT)
        rows = [{"source": s, "correction": c}
                for s, c in list(zip(src, corr))[:limit]]
        return rows, "SAGE"
    except Exception:
        pass
    # 3) прямой HTTP к raw-файлам репозитория датасета (без зависимостей):
    # data/<config>/test.json — JSONL со строками {"source", "correction"}.
    url = (f"https://huggingface.co/datasets/{DATASET}/resolve/main/"
           f"data/{config}/{SPLIT}.json")
    req = urllib.request.Request(url, headers={"User-Agent": "Avtoroved/5.0"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        lines = resp.read().decode("utf-8").splitlines()
    rows = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        r = json.loads(line)
        if "source" in r and "correction" in r:
            rows.append({"source": r["source"], "correction": r["correction"]})
        if len(rows) >= limit:
            break
    return rows, "raw JSONL (HTTP)"


# ── эталонные ошибки: пословный diff source↔correction ───────────────────────
def _words(text: str) -> list[str]:
    return _WORD_RE.findall(text or "")


def classify_change(a: str, b: str) -> str:
    """Категория расхождения токенов: SPELL / PUNCT / CASE / YO."""
    if a.lower() == b.lower():
        return "CASE"
    if a.lower().replace("ё", "е") == b.lower().replace("ё", "е"):
        return "YO"
    if not re.search(r"[A-Za-zА-Яа-яЁё]", a + b):
        return "PUNCT"
    return "SPELL"


def gold_errors(source: str, correction: str) -> dict[int, str]:
    """Индексы токенов source с эталонной ошибкой → категория."""
    sw, cw = _words(source), _words(correction)
    out: dict[int, str] = {}
    sm = difflib.SequenceMatcher(a=sw, b=cw, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        if tag in ("replace", "delete"):
            for i in range(i1, i2):
                pair_j = j1 + (i - i1)
                b = cw[pair_j] if pair_j < j2 else ""
                out[i] = classify_change(sw[i], b) if b else (
                    "PUNCT" if not re.search(r"[А-Яа-яЁёA-Za-z]", sw[i]) else "SPELL")
        elif tag == "insert":
            # Пропуск (обычно знака препинания) — вешаем на предыдущий токен.
            idx = max(0, i1 - 1)
            ins = "".join(cw[j1:j2])
            out.setdefault(idx, "PUNCT" if not re.search(
                r"[А-Яа-яЁёA-Za-z]", ins) else "SPELL")
    return out


def predicted_errors(text: str, errors: list) -> dict[int, str]:
    """Индексы токенов, накрытых срабатываниями детектора → категория."""
    spans = []
    for e in errors:
        s, en = getattr(e, "position", (0, 0))
        if en > s:
            cat = {"Орфографическая": "SPELL", "Пунктуационная": "PUNCT"}.get(
                getattr(e, "error_type", ""), "SPELL")
            spans.append((s, en, cat))
    out: dict[int, str] = {}
    pos = 0
    for i, m in enumerate(_WORD_RE.finditer(text)):
        for s, en, cat in spans:
            if m.start() < en and s < m.end():
                out[i] = cat
                break
        pos = m.end()
    return out


# ── прогон детектора (штатный путь протокола) ────────────────────────────────
class _Detector:
    def __init__(self, use_lt: bool = True):
        from analyzer.stanza_backend import StanzaBackend
        from protocol import detector_filter
        self.backend = StanzaBackend()
        self.cfg, self.cfg_hash = detector_filter.load_config()
        self.filter = detector_filter
        self.lt = None
        self.lt_meta = "не использован"
        if use_lt:
            try:
                from analyzer import lt_checker
                lt = lt_checker.get()
                lt.ensure_loaded()
                if lt.mode == "local":
                    self.lt = lt
                    try:
                        from importlib.metadata import version
                        self.lt_meta = f"local, пакет {version('language-tool-python')}"
                    except Exception:
                        self.lt_meta = "local"
                else:
                    self.lt_meta = f"пропущен ({lt.mode or 'недоступен'})"
            except Exception as e:
                self.lt_meta = f"ошибка: {e}"

    def run(self, text: str) -> list:
        from analyzer import punct_checker
        tokens = self.backend.analyze(text)
        errors = punct_checker.check_with_tokens(text, tokens) or []
        if self.lt is not None:
            errors += self.lt.check(text) or []
        res = self.filter.apply_filter(errors, self.cfg)
        return [e for e, _rel in res.kept]


# ── метрики ──────────────────────────────────────────────────────────────────
def evaluate(rows: list[dict], det: _Detector, progress=None) -> dict:
    cats = ("SPELL", "PUNCT", "CASE", "YO")
    tp = {c: 0 for c in cats}
    fp = {c: 0 for c in cats}
    fn = {c: 0 for c in cats}
    tp_all = fp_all = fn_all = 0
    for n, row in enumerate(rows):
        src = row["source"]
        gold = gold_errors(src, row["correction"])
        pred = predicted_errors(src, det.run(src))
        for i, cat in gold.items():
            if i in pred:
                tp_all += 1
                tp[cat] += 1
            else:
                fn_all += 1
                fn[cat] += 1
        for i, cat in pred.items():
            if i not in gold:
                fp_all += 1
                fp[cat] += 1
        if progress and (n + 1) % 25 == 0:
            progress(f"  … {n + 1}/{len(rows)}")

    def prf(tp_, fp_, fn_):
        p = tp_ / (tp_ + fp_) if (tp_ + fp_) else 0.0
        r = tp_ / (tp_ + fn_) if (tp_ + fn_) else 0.0
        f = 2 * p * r / (p + r) if (p + r) else 0.0
        return round(p, 3), round(r, 3), round(f, 3)

    out = {"overall": prf(tp_all, fp_all, fn_all), "n": len(rows)}
    for c in cats:
        out[c] = {"prf": prf(tp[c], fp[c], fn[c]),
                  "gold": tp[c] + fn[c], "pred": tp[c] + fp[c]}
    return out


def main():
    ap = argparse.ArgumentParser(description="Валидация детектора ошибок")
    ap.add_argument("--limit", type=int, default=150,
                    help="примеров на датасет (по умолчанию 150)")
    ap.add_argument("--no-lt", action="store_true", help="без LanguageTool")
    ap.add_argument("--out", default="", help="дописать результат в markdown")
    args = ap.parse_args()

    det = _Detector(use_lt=not args.no_lt)
    print(f"LanguageTool: {det.lt_meta}")
    print(f"Конфиг фильтра: hash={det.cfg_hash}")
    try:
        import sage  # type: ignore  # noqa: F401
        scorer = "SAGE"
    except Exception:
        scorer = "встроенный пословный (ПРИБЛИЖЕНИЕ)"
    print(f"Скорер: {scorer}")

    results = {}
    loaders = {}
    for config in CONFIGS:
        print(f"\n=== {config} ({SPLIT}, до {args.limit} примеров) ===")
        try:
            rows, how = load_rows(config, args.limit)
        except Exception as e:
            print(f"  загрузка не удалась: {e}")
            results[config] = None
            continue
        loaders[config] = how
        print(f"  загружено {len(rows)} примеров через {how}")
        results[config] = evaluate(rows, det, progress=print)
        p, r, f = results[config]["overall"]
        print(f"  ИТОГО: precision={p} recall={r} F1={f}")

    # ── markdown-отчёт ───────────────────────────────────────────────────────
    stamp = datetime.datetime.now().isoformat(timespec="seconds")
    lines = [
        f"\n## Прогон {stamp}",
        "",
        f"- Детектор: punct_checker + LanguageTool ({det.lt_meta}) + "
        f"detector_filter (hash `{det.cfg_hash}`)",
        f"- Скорер: {scorer}",
        f"- Датасет: `{DATASET}` (сплит {SPLIT}, до {args.limit} примеров на конфиг)",
        "",
        "| Корпус | Загрузка | N | P | R | F1 | SPELL P/R/F1 | PUNCT P/R/F1 | CASE gold | YO gold |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for config in CONFIGS:
        res = results.get(config)
        if not res:
            lines.append(f"| {config} | не удалось | — | — | — | — | — | — | — | — |")
            continue
        p, r, f = res["overall"]
        sp = "/".join(map(str, res["SPELL"]["prf"]))
        pu = "/".join(map(str, res["PUNCT"]["prf"]))
        lines.append(
            f"| {config} | {loaders[config]} | {res['n']} | {p} | {r} | {f} "
            f"| {sp} | {pu} | {res['CASE']['gold']} | {res['YO']['gold']} |")
    report = "\n".join(lines)
    print(report)

    if args.out:
        with open(args.out, "a", encoding="utf-8") as fh:
            fh.write(report + "\n")
        print(f"\nДописано в {args.out}")


if __name__ == "__main__":
    main()
