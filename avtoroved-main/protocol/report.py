"""
protocol/report.py — экспорт отчёта исследования в DOCX.

Отчёт — вставляемая исследовательская часть заключения, а не целостное
заключение: без титула, реквизитов дела и раздела ВЫВОДЫ (их эксперт
оформляет в своём документе). Структура раздела ИССЛЕДОВАНИЕ — по методике
Рубцовой 2007: объекты → четыре стадии (пригодность, раздельное,
сравнительное, оценка результатов). В конце — техническая справка
воспроизводимости (версии, хэши).

Зафиксированный вывод не обязателен: если он есть, стадия 4 берёт
счётчики из снапшота фиксации и упоминает форму; иначе — живой расчёт
и авто-рекомендация. Файл регистрируется в таблице reports с sha256
+ запись в audit_log.
"""
from __future__ import annotations

import json
from typing import Optional

from protocol import db as protocol_db
from protocol import comparison as cmp
from protocol import conclusion as concl
from protocol import detector_filter
from protocol import feature_map as fm


# Порядок групп признаков в разделе сравнительного исследования — как в
# методике (4 группы); группы вне списка идут после, по алфавиту.
_GROUP_ORDER = ("смысловые", "текстологические", "языковые",
                "психолингвистические")

# Иллюстрация длиннее не помогает читателю заключения — обрезаем по слову.
_FRAGMENT_LIMIT = 220


def _shorten_fragment(fragment: str) -> str:
    frag = " ".join(fragment.split())
    if len(frag) <= _FRAGMENT_LIMIT:
        return frag
    cut = frag[:_FRAGMENT_LIMIT].rsplit(" ", 1)[0]
    return cut + "…"


def _fill_illustrated(cell, value: Optional[str], fragment: Optional[str]) -> None:
    """Ячейка таблицы сравнения: значение признака + цитата-иллюстрация."""
    cell.text = value if value not in (None, "") else "—"
    if fragment:
        run = cell.add_paragraph().add_run(f"«{_shorten_fragment(fragment)}»")
        run.italic = True


def _by_group(rows) -> list[tuple[str, list]]:
    """Сгруппировать позиции сравнения по группам в методическом порядке."""
    grouped: dict[str, list] = {}
    for r in rows:
        grouped.setdefault(r["group_name"] or "прочие", []).append(r)
    ordered = [g for g in _GROUP_ORDER if g in grouped]
    ordered += sorted(g for g in grouped if g not in _GROUP_ORDER)
    return [(g, grouped[g]) for g in ordered]


def export_research_docx(
    pdb: "protocol_db.ProtocolDB",
    project_id: int,
    doc_a: int,
    doc_b: int,
    filepath: str,
    program_version: Optional[str] = None,
) -> dict:
    """Собрать и сохранить отчёт исследования по паре. Возвращает сводку."""
    from docx import Document
    from docx.shared import Pt

    conclusion_row = pdb.fetch_conclusion(doc_a, doc_b)
    project = pdb.get_project(project_id)
    da, db_ = pdb.get_document(doc_a), pdb.get_document(doc_b)

    doc = Document()
    style = doc.styles["Normal"]
    style.font.name = "Times New Roman"
    style.font.size = Pt(12)

    # ── ИССЛЕДОВАНИЕ (вставляемый фрагмент заключения) ───────────────────────
    doc.add_heading("ИССЛЕДОВАНИЕ", level=1)
    doc.add_paragraph(
        f"Автороведческое исследование проведено с применением программы "
        f"«Авторовед» v{program_version or project['program_version'] or '—'} "
        f"(проект «{project['name']}»).")

    doc.add_heading("Объекты исследования", level=2)
    for d, role_note in ((da, "спорный текст"), (db_, "образец")):
        doc.add_paragraph(
            f"• {d['filename']} — {role_note}; происхождение: {d['provenance'] or '—'}; "
            f"жанр: {d['genre'] or '—'}; объём: {d['word_count'] or 0} словоформ; "
            f"SHA-256: {d['file_sha256']}")

    # Стадия 1: пригодность.
    doc.add_heading("1. Оценка пригодности объектов", level=2)
    su_rows = [r for r in pdb.fetch_suitability(project_id)
               if r["document_id"] in (doc_a, doc_b)
               or (r["pair_doc_a"] == doc_a and r["pair_doc_b"] == doc_b)]
    if not su_rows:
        doc.add_paragraph("Стадия пригодности по паре не проводилась.")
    for r in su_rows:
        target = (f"документ #{r['document_id']}" if r["document_id"]
                  else "пара спорный↔образец")
        flags = json.loads(r["flags"]) if r["flags"] else []
        flag_txt = ("; ".join(f["message"] for f in flags)) or "без ограничений"
        doc.add_paragraph(f"{target}: {r['verdict']} ({flag_txt})")
    blocks = cmp.pair_blocks_strong_conclusion(pdb, project_id, doc_a, doc_b)
    if blocks:
        doc.add_paragraph("По результатам стадии пригодности категорическая форма "
                          "вывода недоступна (blocks_strong_conclusion = 1).")

    # Стадия 2: раздельное исследование.
    doc.add_heading("2. Раздельное исследование", level=2)
    for d in (da, db_):
        accepted = [f for f in pdb.fetch_features(document_id=d["id"])
                    if f["status"] == fm.STATUS_ACCEPTED]
        cand_total = len([c for c in pdb.fetch_feature_candidates(d["id"])
                          if c["kind"] == "кандидат_признак"])
        doc.add_paragraph(
            f"{d['filename']}: профиль построен, кандидатов признаков {cand_total}, "
            f"принято экспертом {len(accepted)}.")

    # Стадия 3: сравнительное исследование — подтверждённые позиции по группам,
    # каждая иллюстрируется проявлением признака в обоих текстах (методика
    # требует показать признак цитатой, а не только назвать его).
    doc.add_heading("3. Сравнительное исследование", level=2)

    # Общие признаки: объективное сопоставление степеней навыков с допусками
    # методики СЭУ Минюста (с. 19); участвует в решающем правиле Вула.
    gsv = cmp.general_skill_verdicts(pdb, doc_a, doc_b)
    if gsv:
        doc.add_heading("3.0. Общие признаки (степени развития навыков)", level=3)
        doc.add_paragraph(
            "Сопоставление по числу уникальных ошибок на 200 словоформ; "
            "допуски: ±2 — грамматический и лексико-фразеологический, "
            "±4 — орфографический и пунктуационный.")
        table = doc.add_table(rows=1, cols=5)
        table.style = "Table Grid"
        hdr = table.rows[0].cells
        for i, t in enumerate(("Навык", "Спорный текст", "Образец",
                               "Δ (допуск)", "Вердикт")):
            hdr[i].text = t
        for skill in sorted(gsv):
            v = gsv[skill]
            row = table.add_row().cells
            name = skill
            if v["reliability_a"] == "низкая" or v["reliability_b"] == "низкая":
                # Причина в value признака: автокоррекция или LT не использован.
                name += " (надёжность: низкая)"
            row[0].text = name
            row[1].text = v["value_a"] or "—"
            row[2].text = v["value_b"] or "—"
            row[3].text = f"{v['delta']:+.1f} (±{v['tolerance']:g})"
            row[4].text = v["verdict"].replace("_", " ")

    confirmed = [r for r in pdb.fetch_comparisons(doc_a, doc_b)
                 if r["status"] == cmp.STATUS_CONFIRMED]
    if confirmed:
        doc.add_paragraph(
            "Сопоставление принятых экспертом признаков спорного текста и "
            "образца. Для каждой позиции приводятся значение признака и "
            "фрагмент-иллюстрация из соответствующего текста. Уровень "
            "индивидуализации признака: НН < НС < НСВ, по возрастанию "
            "(Рубцова 2007, с. 11).")
        for sec_no, (group, rows_g) in enumerate(_by_group(confirmed), start=1):
            doc.add_heading(f"3.{sec_no}. Признаки: {group}", level=3)
            table = doc.add_table(rows=1, cols=4)
            table.style = "Table Grid"
            hdr = table.rows[0].cells
            for i, t in enumerate(("Признак", "Спорный текст",
                                   "Образец", "Результат")):
                hdr[i].text = t
            for r in rows_g:
                row = table.add_row().cells
                label = r["label"] or ""
                if r["subgroup"]:
                    label += f" ({r['subgroup']})"
                row[0].text = label
                _fill_illustrated(row[1], r["value_a"], r["fragment_a"])
                _fill_illustrated(row[2], r["value_b"], r["fragment_b"])
                result = r["match_type"]
                if r["level"]:
                    result += f", уровень {r['level']}"
                if r["explained"]:
                    result += " — признано объяснимым (из правила вывода исключено)"
                if r["expert_note"]:
                    result += f". {r['expert_note']}"
                row[3].text = result
    else:
        doc.add_paragraph("Подтверждённых позиций сравнения нет.")

    # Стадия 4: оценка результатов. Форму вывода эксперт формулирует в своём
    # заключении сам; здесь — счётчики и рекомендация методики (справочно).
    doc.add_heading("4. Оценка результатов", level=2)
    if conclusion_row is not None:
        bd = (json.loads(conclusion_row["stats_snapshot"])
              if conclusion_row["stats_snapshot"] else {})
        recommended = conclusion_row["recommended_form"]
    else:
        recommended, _reasons, bd = concl.recommend(pdb, project_id, doc_a, doc_b)
    if bd:
        coin, diff = bd.get("coincidence", {}), bd.get("difference", {})
        doc.add_paragraph(
            f"Подтверждено позиций: {bd.get('total_confirmed', 0)}; "
            f"совпадений {bd.get('total_coincidence', 0)} "
            f"(НН {coin.get('НН', 0)}, НС {coin.get('НС', 0)}, НСВ {coin.get('НСВ', 0)}); "
            f"различий {bd.get('total_difference', 0)} "
            f"(НН {diff.get('НН', 0)}, НС {diff.get('НС', 0)}, НСВ {diff.get('НСВ', 0)}). "
            f"Методический порог: ≥{cmp.MIN_FEATURES_FOR_CONCLUSION} признаков.")
    # Покатегорийные минимумы (Моисеева/Огорелков 2021, с. 89–93): из снапшота
    # фиксации, а для незафиксированного вывода — живой расчёт.
    buckets = bd.get("buckets") or cmp.bucket_breakdown(pdb, doc_a, doc_b)
    if buckets:
        doc.add_paragraph("Подтверждённые совпадения по группам признаков и "
                          "покатегорийные минимумы (Моисеева/Огорелков):")
        table = doc.add_table(rows=1, cols=4)
        table.style = "Table Grid"
        hdr = table.rows[0].cells
        for i, t in enumerate(("Группа", "Подтверждено",
                               "Мин. категорический", "Мин. вероятный")):
            hdr[i].text = t
        for b in buckets:
            row = table.add_row().cells
            row[0].text = b["bucket"]
            row[1].text = str(b["confirmed"])
            row[2].text = (f"{b['threshold_categorical']} "
                           f"({'достигнут' if b['meets_categorical'] else 'не достигнут'})")
            row[3].text = (f"{b['threshold_probable']} "
                           f"({'достигнут' if b['meets_probable'] else 'не достигнут'})")

    vul = [s for s in ("грамматический", "лексико-фразеологический")
           if s in gsv and gsv[s]["verdict"] == cmp.GENERAL_VERDICT_HIGHER_A]
    if vul:
        doc.add_paragraph(
            "Решающее правило Вула: степень развития навыка "
            f"({', '.join(vul)}) в спорном тексте выше, чем в образце, за "
            "пределами допуска — основание категорического отрицательного "
            "вывода [Минюст, с. 19; Вул 2007, с. 38].")

    if recommended:
        doc.add_paragraph(
            f"Рекомендация по правилу методики (с.85–86): "
            f"{concl.FORM_LABELS.get(recommended, recommended)}.")
    if conclusion_row is not None:
        doc.add_paragraph(
            f"Экспертом зафиксирована форма вывода: "
            f"{concl.FORM_LABELS.get(conclusion_row['form'], conclusion_row['form'])} "
            f"({conclusion_row['decided_at']})."
            + (f" Обоснование: {conclusion_row['justification']}"
               if conclusion_row["justification"] else ""))

    # ── Техническая справка воспроизводимости ────────────────────────────────
    doc.add_heading("Техническая справка (воспроизводимость)", level=2)
    _cfg, cfg_hash = detector_filter.load_config()
    try:
        from analyzer.punct_checker import RULES_VERSION as _punct_ver
    except Exception:
        _punct_ver = "—"
    doc.add_paragraph(
        f"Версия программы: {program_version or '—'}; "
        f"хэш конфига фильтра детектора: {cfg_hash}; "
        f"версия правил пунктуации: {_punct_ver}. "
        f"Полный журнал действий хранится в базе протокола (audit_log).")

    doc.save(filepath)

    # Регистрация экспорта.
    from protocol.ingest import file_sha256
    sha = file_sha256(filepath)
    fixed_form = conclusion_row["form"] if conclusion_row is not None else None
    pdb.record_report(project_id, filepath, sha, pair_doc_a=doc_a,
                      pair_doc_b=doc_b, program_version=program_version)
    pdb.log_action(
        "экспортирован отчёт исследования", project_id=project_id,
        details={"pair_doc_a": doc_a, "pair_doc_b": doc_b,
                 "файл": filepath, "sha256": sha,
                 "форма_вывода": fixed_form},
        program_version=program_version)
    return {"filepath": filepath, "sha256": sha, "form": fixed_form}
