"""
protocol/suitability.py — стадия «оценка пригодности» (гейт перед анализом).

Методическая опора: Огорелков И.В., Моисеева Т.Ф. — стадия оценки пригодности
объектов автороведческой экспертизы (достаточность и надёжность речевого
материала, корректность сопоставления). Это НЕ карта признаков и НЕ сравнение —
только защитный гейт: можно ли вообще строить выводы по этим материалам.

Все пороги собраны здесь, в одном месте. Тяжёлых зависимостей нет — только
стандартный re. Извлечение текста переиспользуется из Этапа 1 (ingest.assess_extraction).
"""
from __future__ import annotations

import re
from typing import Any, Optional

from protocol import ingest
from protocol import db as protocol_db

# ── Пороги (в одном месте) ────────────────────────────────────────────────────
MIN_WORDS_SAMPLE = 100     # методический минимум образца (словоформы)
MIN_WORDS_RELIABLE = 150   # объём, при котором признаки надёжны

# Пороги по ЗНАМЕНАТЕЛЬНЫМ словоформам (методика МИЦ/Минюста): считаются по
# POS из разметки (tokens.pos): существительные, глаголы, прилагательные,
# наречия, имена собственные. Спорный текст ≥100, образец ≥600.
SIGNIFICANT_POS = ("NOUN", "VERB", "ADJ", "ADV", "PROPN")
MIN_SIGNIFICANT_DISPUTED = 100
MIN_SIGNIFICANT_SAMPLE = 600
MIN_SENTENCES_RELIABLE = 10  # минимум предложений для устойчивых оценок
QUOTE_SHARE_FLAG = 0.30    # доля символов в цитатах выше → флаг «чужая речь»
REPEAT_SHARE_FLAG = 0.30   # доля повторяющихся блоков выше → флаг «шаблон»
SENT_LEN_RATIO_FLAG = 2.0  # различие средней длины предложения в паре выше → флаг

# ── Вердикты ─────────────────────────────────────────────────────────────────
VERDICT_FIT = "пригоден"
VERDICT_LIMITED = "пригоден_с_ограничениями"
VERDICT_UNFIT = "непригоден"

# ── Уровни флагов ────────────────────────────────────────────────────────────
LEVEL_UNFIT = "непригоден"     # красный — блокирует пригодность
LEVEL_LIMIT = "ограничение"    # жёлтый — пригоден с ограничениями

# Происхождения, при которых орфография/пунктуация искажены автокоррекцией.
_AUTOCORRECT_PROVENANCE = ("цифровой", "опубликованный")

_WORD_RE = re.compile(r"[A-Za-zА-Яа-яЁё]+")
# Цитаты: парные кавычки разных видов.
_QUOTE_RE = re.compile(r"«[^»]*»|“[^”]*”|\"[^\"]*\"|„[^“]*“")
# Маркеры устной речи: хезитации, типичные филлеры, пометы расшифровки.
_ORAL_RE = re.compile(
    r"\bэ{2,}\b|\bм{2,}\b|\bэ+м+\b|\bну вот\b|\bкак бы\b|\bэто самое\b|"
    r"\(нрзб\)|\(неразборчиво\)|\(пауза\)",
    re.IGNORECASE,
)


def _flag(code: str, level: str, message: str) -> dict:
    return {"code": code, "level": level, "message": message}


# ── детекторы (чистые функции над текстом) ───────────────────────────────────
def quote_share(text: str) -> float:
    """Доля символов внутри цитат от общей длины (0..1)."""
    if not text:
        return 0.0
    quoted = sum(len(m.group(0)) for m in _QUOTE_RE.finditer(text))
    return round(quoted / len(text), 3)


def repeat_share(text: str) -> float:
    """
    Доля словоформ в повторяющихся предложениях (0..1) — индикатор
    шаблонности/копипаста. Предложение, встретившееся не впервые, считается
    повтором; его словоформы идут в числитель.
    """
    if not text:
        return 0.0
    sents = [s.strip().lower() for s in re.split(r"[.!?\n]+", text) if s.strip()]
    if not sents:
        return 0.0
    seen: set[str] = set()
    repeated_words = 0
    total_words = 0
    for s in sents:
        w = len(_WORD_RE.findall(s))
        total_words += w
        if s in seen:
            repeated_words += w
        else:
            seen.add(s)
    if total_words == 0:
        return 0.0
    return round(repeated_words / total_words, 3)


def oral_markers(text: str) -> list[str]:
    """Найденные маркеры устной речи (для флага транскрибации)."""
    if not text:
        return []
    return [m.group(0) for m in _ORAL_RE.finditer(text)]


# ── оценка одного документа ──────────────────────────────────────────────────
def evaluate_document(doc: dict[str, Any]) -> tuple[str, list[dict], dict, bool]:
    """
    Оценить пригодность одного документа.

    doc: {filename, role, provenance, genre, word_count, sentence_count,
          token_count, text}.
    Возвращает (verdict, flags, metrics, blocks_strong_conclusion).
    """
    filename = doc.get("filename", "")
    provenance = doc.get("provenance") or ""
    wc = int(doc.get("word_count") or 0)
    sc = int(doc.get("sentence_count") or 0)
    tc = int(doc.get("token_count") or 0)
    text = doc.get("text") or ""

    q_share = quote_share(text)
    r_share = repeat_share(text)
    oral = oral_markers(text)

    flags: list[dict] = []

    # 1) Извлечение (переиспользуем Этап 1): пусто/мизер → непригоден.
    extr_status, extr_reason = ingest.assess_extraction(filename, wc, tc)
    if extr_status == ingest.STATUS_EMPTY:
        flags.append(_flag("извлечение", LEVEL_UNFIT, f"текст не извлечён: {extr_reason}"))

    # 2а) Объём по знаменательным словоформам (МИЦ/Минюст): спорный ≥100,
    # образец ≥600. None = разметки нет (юнит-контекст) — проверка пропускается.
    significant = doc.get("significant_count")
    if significant is not None:
        min_sig = (MIN_SIGNIFICANT_SAMPLE if doc.get("role") == protocol_db.ROLE_SAMPLE
                   else MIN_SIGNIFICANT_DISPUTED)
        if significant < min_sig:
            flags.append(_flag(
                "объём_знаменательных", LEVEL_LIMIT,
                f"объём ниже методического минимума: {significant} знаменательных "
                f"словоформ (требуется ≥{min_sig} для роли «{doc.get('role')}»)"))

    # 2) Объём (словоформы и предложения).
    if wc < MIN_WORDS_SAMPLE:
        flags.append(_flag("малый_объём", LEVEL_LIMIT,
                           f"объём {wc} словоформ ниже минимума образца ({MIN_WORDS_SAMPLE})"))
    elif wc < MIN_WORDS_RELIABLE:
        flags.append(_flag("объём_ненадёжный", LEVEL_LIMIT,
                           f"объём {wc} словоформ ниже надёжного ({MIN_WORDS_RELIABLE})"))
    if 0 < sc < MIN_SENTENCES_RELIABLE:
        flags.append(_flag("мало_предложений", LEVEL_LIMIT,
                           f"предложений {sc} ниже минимума ({MIN_SENTENCES_RELIABLE})"))

    # 3) Цитаты и повторы.
    if q_share >= QUOTE_SHARE_FLAG:
        flags.append(_flag("цитаты", LEVEL_LIMIT,
                           f"загрязнение чужой речью: доля цитат {q_share:.0%}"))
    if r_share >= REPEAT_SHARE_FLAG:
        flags.append(_flag("повторы", LEVEL_LIMIT,
                           f"шаблонность/повторы: доля повторов {r_share:.0%}"))

    # 4) Редактура/автокоррекция по происхождению.
    if provenance in _AUTOCORRECT_PROVENANCE:
        flags.append(_flag("автокоррекция", LEVEL_LIMIT,
                           "орфографические и пунктуационные признаки ненадёжны (автокоррекция)"))

    # 5) Транскрибация / устная речь.
    if provenance == "расшифровка_устной_речи" or oral:
        why = "происхождение — расшифровка устной речи" if provenance == "расшифровка_устной_речи" \
            else f"маркеры устной речи: {', '.join(sorted(set(oral))[:5])}"
        flags.append(_flag("устная_речь", LEVEL_LIMIT,
                           f"письменно-речевые признаки неприменимы ({why})"))

    metrics = {
        "word_count": wc, "sentence_count": sc, "token_count": tc,
        "significant_count": significant,
        "extraction_status": extr_status,
        "quote_share": q_share, "repeat_share": r_share,
        "oral_markers": len(oral), "provenance": provenance,
    }
    verdict, blocks = _verdict_from_flags(flags)
    return verdict, flags, metrics, blocks


# ── оценка пары спорный ↔ образец ────────────────────────────────────────────
def evaluate_pair(doc_a: dict[str, Any], doc_b: dict[str, Any]) -> tuple[str, list[dict], dict, bool]:
    """
    Оценить сопоставимость пары документов (обычно спорный ↔ образец).

    Сравнивает жанр, происхождение (форму) и простой стилевой индикатор —
    среднюю длину предложения. Несопоставимость → флаг «сравнение некорректно».
    """
    flags: list[dict] = []

    genre_a = (doc_a.get("genre") or "").strip().lower()
    genre_b = (doc_b.get("genre") or "").strip().lower()
    prov_a = doc_a.get("provenance") or ""
    prov_b = doc_b.get("provenance") or ""

    if genre_a and genre_b and genre_a != genre_b:
        flags.append(_flag("несопоставимость_жанр", LEVEL_LIMIT,
                           f"сравнение некорректно: разные жанры ({genre_a} ↔ {genre_b})"))
    if prov_a and prov_b and prov_a != prov_b:
        flags.append(_flag("несопоставимость_форма", LEVEL_LIMIT,
                           f"сравнение некорректно: разное происхождение/форма ({prov_a} ↔ {prov_b})"))

    awl_a = _avg_sentence_len(doc_a)
    awl_b = _avg_sentence_len(doc_b)
    if awl_a and awl_b:
        ratio = max(awl_a, awl_b) / min(awl_a, awl_b)
        if ratio >= SENT_LEN_RATIO_FLAG:
            flags.append(_flag("несопоставимость_стиль", LEVEL_LIMIT,
                               f"сравнение некорректно: резко разная средняя длина предложения "
                               f"({awl_a:.1f} ↔ {awl_b:.1f} слов)"))

    metrics = {
        "genre_a": genre_a, "genre_b": genre_b,
        "provenance_a": prov_a, "provenance_b": prov_b,
        "avg_sent_len_a": awl_a, "avg_sent_len_b": awl_b,
    }
    verdict, blocks = _verdict_from_flags(flags)
    return verdict, flags, metrics, blocks


def _avg_sentence_len(doc: dict[str, Any]) -> float:
    wc = int(doc.get("word_count") or 0)
    sc = int(doc.get("sentence_count") or 0)
    return round(wc / sc, 2) if sc > 0 else 0.0


def _verdict_from_flags(flags: list[dict]) -> tuple[str, bool]:
    """Свести флаги к вердикту и признаку блокировки категорического вывода."""
    if any(f["level"] == LEVEL_UNFIT for f in flags):
        return VERDICT_UNFIT, True
    if any(f["level"] == LEVEL_LIMIT for f in flags):
        return VERDICT_LIMITED, True
    return VERDICT_FIT, False


# ── оркестрация по проекту (загрузка из БД, запись, журнал) ───────────────────
def _load_doc(pdb: "protocol_db.ProtocolDB", doc_row) -> dict:
    did = doc_row["id"]
    return {
        "id": did,
        "filename": doc_row["filename"],
        "role": doc_row["role"],
        "provenance": doc_row["provenance"],
        "genre": doc_row["genre"],
        "word_count": doc_row["word_count"],
        "sentence_count": pdb.count_sentences(did),
        "token_count": pdb.count_tokens(did),
        "significant_count": pdb.count_tokens_by_pos(did, SIGNIFICANT_POS),
        "text": pdb.get_layer(did, protocol_db.LAYER_CLEANED) or "",
    }


def run_for_project(
    pdb: "protocol_db.ProtocolDB",
    project_id: int,
    program_version: Optional[str] = None,
) -> dict:
    """
    Пересчитать пригодность всех документов и пар спорный×образец проекта:
    очистить прежние оценки, оценить заново, записать в suitability и в журнал.

    Возвращает сводку {documents: [...], pairs: [...]}.
    """
    pdb.clear_suitability(project_id)
    rows = pdb.fetch_documents(project_id)
    docs = [_load_doc(pdb, r) for r in rows]

    doc_results = []
    for d in docs:
        verdict, flags, metrics, blocks = evaluate_document(d)
        pdb.save_suitability(
            project_id, verdict=verdict, blocks_strong_conclusion=blocks,
            document_id=d["id"], flags=flags, metrics=metrics)
        pdb.log_action(
            "оценка пригодности", project_id=project_id,
            details={"document_id": d["id"], "filename": d["filename"],
                     "вердикт": verdict, "флаги": [f["code"] for f in flags],
                     "blocks_strong_conclusion": blocks},
            program_version=program_version)
        doc_results.append({"document": d, "verdict": verdict,
                            "flags": flags, "metrics": metrics, "blocks": blocks})

    disputed = [d for d in docs if d["role"] == protocol_db.ROLE_DISPUTED]
    samples = [d for d in docs if d["role"] == protocol_db.ROLE_SAMPLE]
    pair_results = []
    for a in disputed:
        for b in samples:
            verdict, flags, metrics, blocks = evaluate_pair(a, b)
            pdb.save_suitability(
                project_id, verdict=verdict, blocks_strong_conclusion=blocks,
                pair_doc_a=a["id"], pair_doc_b=b["id"], flags=flags, metrics=metrics)
            pdb.log_action(
                "оценка пригодности (пара)", project_id=project_id,
                details={"pair_doc_a": a["id"], "pair_doc_b": b["id"],
                         "вердикт": verdict, "флаги": [f["code"] for f in flags],
                         "blocks_strong_conclusion": blocks},
                program_version=program_version)
            pair_results.append({"a": a, "b": b, "verdict": verdict,
                                 "flags": flags, "metrics": metrics, "blocks": blocks})

    return {"documents": doc_results, "pairs": pair_results}
