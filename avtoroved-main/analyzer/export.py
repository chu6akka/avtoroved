"""
Модуль экспорта отчётов в DOCX и загрузки файлов.
"""
from __future__ import annotations
import os
import re
from datetime import datetime
from typing import List

from analyzer.stanza_backend import TokenInfo


def load_text_from_file(filepath: str) -> str:
    """Загрузить текст из .txt или .docx файла."""
    ext = os.path.splitext(filepath)[1].lower()
    if ext == '.txt':
        for enc in ('utf-8', 'cp1251', 'cp866', 'latin-1'):
            try:
                with open(filepath, 'r', encoding=enc) as f:
                    return f.read()
            except UnicodeDecodeError:
                continue
        raise ValueError(f"Не удалось прочитать: {filepath}")
    elif ext == '.docx':
        from docx import Document
        doc = Document(filepath)
        return '\n'.join(p.text for p in doc.paragraphs if p.text.strip())
    else:
        raise ValueError(f"Неподдерживаемый формат: {ext}")


def export_report_docx(filepath: str, text: str, metrics: dict,
                       error_result, tokens: List[TokenInfo],
                       strat_result=None, gigacheck_result=None,
                       thematic_result=None):
    """Экспорт полного отчёта в DOCX."""
    from docx import Document
    from docx.shared import Pt, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    doc = Document()
    style = doc.styles['Normal']
    style.font.name = 'Times New Roman'
    style.font.size = Pt(12)

    h = doc.add_heading('СВОДНЫЙ ОТЧЁТ АВТОРОВЕДЧЕСКОГО АНАЛИЗА', level=1)
    h.alignment = WD_ALIGN_PARAGRAPH.CENTER
    doc.add_paragraph(f'Дата: {datetime.now().strftime("%d.%m.%Y %H:%M")}')

    # 1. Описание
    doc.add_heading('1. Описание речевого продукта', level=2)
    words_list = re.findall(r"[А-Яа-яЁё]+", text)
    first_w = " ".join(words_list[:6]) + "..." if len(words_list) > 6 else " ".join(words_list)
    last_w = "..." + " ".join(words_list[-6:]) if len(words_list) > 6 else ""
    doc.add_paragraph(f'Текст на русском языке. Начало: «{first_w}»')
    if last_w:
        doc.add_paragraph(f'Окончание: «{last_w}»')
    doc.add_paragraph(f'Вербальный объём: {metrics["дополнительно"]["Всего слов"]} слов.')

    # 2. Количественные характеристики
    doc.add_heading('2. Количественные характеристики', level=2)
    table = doc.add_table(rows=1, cols=2)
    table.style = 'Light Grid Accent 1'
    table.rows[0].cells[0].text = 'Показатель'
    table.rows[0].cells[1].text = 'Значение'
    for k, v in metrics["дополнительно"].items():
        row = table.add_row().cells
        row[0].text = str(k)
        row[1].text = str(v)

    # 3. Распределение частей речи
    doc.add_heading('3. Распределение частей речи', level=2)
    if metrics["частоты"]:
        t2 = doc.add_table(rows=1, cols=3)
        t2.style = 'Light Grid Accent 1'
        t2.rows[0].cells[0].text = 'Часть речи'
        t2.rows[0].cells[1].text = 'Количество'
        t2.rows[0].cells[2].text = 'Доля'
        for p, v in metrics["частоты"].items():
            row = t2.add_row().cells
            row[0].text = p
            row[1].text = str(v['количество'])
            row[2].text = f"{v['коэффициент']:.2%}"

    # 3.1. Морфологические коэффициенты (методика САЭ)
    sae = metrics.get("sae_coefficients", {})
    sae_rows = sae.get("rows", [])
    base_cnt = sae.get("base_counts", {})
    if sae_rows:
        doc.add_heading('3.1. Морфологические коэффициенты (САЭ)', level=2)
        doc.add_paragraph(
            'По методике С.М. Вул, Е.И. Галяшиной. '
            'Местоимения = PRON + DET (соответствует традиционной русской грамматике). '
            'Глаголы — личные формы (без причастий и деепричастий).'
        )
        # Базовые счётчики
        doc.add_paragraph('Базовые счётчики:').bold = True
        t_base = doc.add_table(rows=1, cols=2)
        t_base.style = 'Light Grid Accent 1'
        t_base.rows[0].cells[0].text = 'Категория'
        t_base.rows[0].cells[1].text = 'Количество'
        for lbl, cnt in base_cnt.items():
            row = t_base.add_row().cells
            row[0].text = str(lbl)
            row[1].text = str(cnt)
        doc.add_paragraph('')
        # 20 коэффициентов
        t_sae = doc.add_table(rows=1, cols=4)
        t_sae.style = 'Light Grid Accent 1'
        hdr = t_sae.rows[0].cells
        hdr[0].text = '№'
        hdr[1].text = 'Показатель'
        hdr[2].text = 'Числ./знаменатель'
        hdr[3].text = 'Коэффициент'
        for r in sae_rows:
            row = t_sae.add_row().cells
            row[0].text = str(r["n"])
            row[1].text = r["label"]
            row[2].text = f"{r['numerator']}/{r['denominator']}"
            row[3].text = f"{r['value']:.3f}" if r["value"] is not None else "н/д"

    # 3.2. POS-биграммы
    pos_bg = metrics.get("pos_bigrams", {})
    top_bg = pos_bg.get("top_bigrams", [])
    if top_bg:
        doc.add_heading('3.2. Коэффициенты сочетаемости частеречных пар (POS-биграммы)', level=2)
        doc.add_paragraph(
            'Метод POS-биграмм: частотное распределение последовательных пар '
            'частей речи отражает грамматические привычки автора. '
            '(Litvinova et al., 2015–2016).'
        )
        t3 = doc.add_table(rows=1, cols=4)
        t3.style = 'Light Grid Accent 1'
        hdr = t3.rows[0].cells
        hdr[0].text = '№'
        hdr[1].text = 'Пара'
        hdr[2].text = 'Количество'
        hdr[3].text = 'Коэффициент'
        for i, bg in enumerate(top_bg[:15], 1):
            row = t3.add_row().cells
            row[0].text = str(i)
            row[1].text = bg["pair_full"]
            row[2].text = str(bg["count"])
            row[3].text = f'{bg["freq"]:.4f}'

    # 4. Навыки
    if error_result and error_result.skill_levels:
        doc.add_heading('4. Степени развития языковых навыков (по С.М. Вул)', level=2)
        for skill in error_result.skill_levels:
            p = doc.add_paragraph()
            run = p.add_run(f'{skill.skill_name}: ')
            run.bold = True
            p.add_run(f'{skill.level.upper()} ({skill.description})')

    # 5. Ошибки
    if error_result and error_result.errors:
        doc.add_heading('5. Выявленные речевые ошибки', level=2)
        by_type = {}
        for e in error_result.errors:
            by_type.setdefault(e.error_type, []).append(e)
        for etype, errs in by_type.items():
            doc.add_heading(f'{etype.upper()} ({len(errs)})', level=3)
            for i, e in enumerate(errs[:10], 1):
                txt = f'{i}. «{e.fragment}» — {e.description}'
                if e.suggestion:
                    txt += f' → {e.suggestion}'
                if e.rule_ref:
                    txt += f' [{e.rule_ref}]'
                doc.add_paragraph(txt)

    # 6. Лексическая стратификация
    if strat_result:
        doc.add_heading('6. Лексическая стратификация', level=2)
        doc.add_paragraph(
            f'Маркированных единиц: {strat_result.marked_words} из {strat_result.total_words} слов.')
        t4 = doc.add_table(rows=1, cols=3)
        t4.style = 'Light Grid Accent 1'
        t4.rows[0].cells[0].text = 'Пласт'
        t4.rows[0].cells[1].text = 'Кол-во'
        t4.rows[0].cells[2].text = 'Доля'
        try:
            from lexical_stratification import LAYER_ORDER, LAYER_LABELS
            for layer in LAYER_ORDER:
                cnt = strat_result.layer_counts.get(layer, 0)
                if cnt == 0:
                    continue
                row = t4.add_row().cells
                row[0].text = LAYER_LABELS.get(layer, layer)
                row[1].text = str(cnt)
                row[2].text = f"{strat_result.layer_ratios.get(layer, 0):.1%}"
        except ImportError:
            pass

    # 7. GigaCheck (если есть)
    if gigacheck_result:
        doc.add_heading('7. Анализ ИИ-генерации (GigaCheck)', level=2)
        doc.add_paragraph(
            f'Вероятность ИИ-генерации: {gigacheck_result.get("overall_score", 0):.1%}')
        doc.add_paragraph(
            'Примечание: результат является вспомогательным инструментом и '
            'не заменяет лингвистический анализ.')

    # 8. Тематические словари (если есть)
    if thematic_result:
        doc.add_heading('8. Тематическая атрибуция', level=2)
        for domain, data in list(thematic_result.items())[:3]:
            doc.add_paragraph(
                f'{data["label"]}: {data["count"]} слов '
                f'(k={data["density"]:.4f} на 1000 слов)')

    # Вывод
    doc.add_heading('Вывод', level=2)
    wc = metrics["дополнительно"]["Всего слов"]
    if wc >= 500:
        doc.add_paragraph(f'Объём текста ({wc} слов) пригоден для судебной автороведческой экспертизы.')
    elif wc >= 200:
        doc.add_paragraph(f'Объём текста ({wc} слов) пригоден для предварительного анализа.')
    else:
        doc.add_paragraph(f'Объём текста ({wc} слов) недостаточен (минимум 500 слов).')
    doc.save(filepath)


def export_comparison_docx(filepath: str, comp: dict, text1: str, text2: str):
    """Экспорт сравнительного анализа в DOCX."""
    from docx import Document
    from docx.shared import Pt
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    doc = Document()
    style = doc.styles['Normal']
    style.font.name = 'Times New Roman'
    style.font.size = Pt(12)

    h = doc.add_heading('СРАВНИТЕЛЬНЫЙ АНАЛИЗ ТЕКСТОВ', level=1)
    h.alignment = WD_ALIGN_PARAGRAPH.CENTER
    doc.add_paragraph(f'Дата: {datetime.now().strftime("%d.%m.%Y %H:%M")}')

    doc.add_heading('1. Общее сходство', level=2)
    table = doc.add_table(rows=1, cols=2)
    table.style = 'Light Grid Accent 1'
    table.rows[0].cells[0].text = 'Компонент'
    table.rows[0].cells[1].text = 'Значение'
    for label, key in [("Общее сходство", "overall"), ("Лексическое (Jaccard)", "jaccard"),
                       ("Морфологическое (POS)", "pos_similarity"),
                       ("Синтаксическое", "syntactic_similarity"),
                       ("TTR-сходство", "ttr_similarity"),
                       ("POS-биграммное", "bigram_similarity")]:
        if key in comp:
            row = table.add_row().cells
            row[0].text = label
            row[1].text = f"{comp[key]:.1%}"

    doc.add_heading('2. Совпадающие леммы', level=2)
    if comp["common_lemmas"]:
        doc.add_paragraph(", ".join(comp["common_lemmas"]))
    else:
        doc.add_paragraph("Совпадений не обнаружено.")

    doc.add_heading('3. Вывод', level=2)
    sim = comp["overall"]
    if sim >= 0.7:
        conclusion = "Высокая степень сходства. Возможна принадлежность одному автору."
    elif sim >= 0.5:
        conclusion = "Средняя степень сходства. Необходимо расширение материала."
    elif sim >= 0.3:
        conclusion = "Умеренные различия. Разные авторы или ситуации."
    else:
        conclusion = "Существенные различия. Вероятно, разные авторы."
    doc.add_paragraph(conclusion)
    doc.save(filepath)


def export_morphology_docx(filepath: str, tokens: List[TokenInfo], morph_indices: dict):
    """
    Экспорт морфологической разметки + 20 индексов идиостиля в DOCX.
    Структура:
      1. Таблица морфологического разбора (Словоформа | Лемма | ЧР | Морф. признаки)
      2. Таблица морфологических индексов (20 позиций)
    """
    from docx import Document
    from docx.shared import Pt, RGBColor, Cm
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement

    doc = Document()
    style = doc.styles['Normal']
    style.font.name = 'Times New Roman'
    style.font.size = Pt(12)

    # ── Заголовок ──────────────────────────────────────────────────────
    h = doc.add_heading('МОРФОЛОГИЧЕСКИЙ РАЗБОР ТЕКСТА', level=1)
    h.alignment = WD_ALIGN_PARAGRAPH.CENTER
    doc.add_paragraph(
        f'Дата: {datetime.now().strftime("%d.%m.%Y %H:%M")}  |  '
        f'Токенов: {len(tokens)}'
    )

    # ── Раздел 1: Морфологическая таблица ─────────────────────────────
    doc.add_heading('1. Морфологический разбор', level=2)

    headers = ['Словоформа', 'Лемма', 'Часть речи', 'Морфологические признаки']
    col_widths_cm = [3.0, 3.0, 3.5, 8.5]

    tbl = doc.add_table(rows=1, cols=4)
    tbl.style = 'Table Grid'

    # Заголовочная строка
    hdr_row = tbl.rows[0]
    for i, (h_text, w) in enumerate(zip(headers, col_widths_cm)):
        cell = hdr_row.cells[i]
        cell.width = int(Cm(w))
        p = cell.paragraphs[0]
        run = p.add_run(h_text)
        run.bold = True
        run.font.size = Pt(10)
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        # Серый фон
        tc_pr = cell._tc.get_or_add_tcPr()
        shd = OxmlElement('w:shd')
        shd.set(qn('w:val'), 'clear')
        shd.set(qn('w:color'), 'auto')
        shd.set(qn('w:fill'), 'D9D9D9')
        tc_pr.append(shd)

    # Строки данных
    for tok in tokens:
        row_cells = tbl.add_row().cells
        vals = [tok.text, tok.lemma, tok.pos_label, tok.feats or '—']
        for i, (cell, val) in enumerate(zip(row_cells, vals)):
            cell.width = int(Cm(col_widths_cm[i]))
            p = cell.paragraphs[0]
            run = p.add_run(val)
            run.font.size = Pt(9)
            if i == 2:  # Часть речи — курсив
                run.italic = True

    doc.add_paragraph('')

    # ── Раздел 2: Морфологические индексы ─────────────────────────────
    doc.add_heading('2. Морфологические индексы идиостиля', level=2)
    doc.add_paragraph(
        'Источник: Лабораторная работа № 11, судебная автороведческая экспертиза / '
        'Соколова Т.П. (МГЮА). Индекс #7 (абстрактные/конкретные существительные) '
        'требует семантической разметки и в автоматическом режиме недоступен.'
    ).runs[0].font.size = Pt(10)

    total_w = morph_indices.get("total_words", 0)
    sent_c  = morph_indices.get("sent_count", 0)
    doc.add_paragraph(
        f'Вербальный объём: {total_w} слов  |  Предложений: {sent_c}'
    ).runs[0].font.size = Pt(10)

    idx_headers = ['№', 'Индекс', 'Числитель', 'Знаменатель', 'Значение']
    idx_widths  = [0.8, 8.2, 2.0, 2.2, 2.2]

    tbl2 = doc.add_table(rows=1, cols=5)
    tbl2.style = 'Table Grid'

    hdr2 = tbl2.rows[0]
    for i, (h_text, w) in enumerate(zip(idx_headers, idx_widths)):
        cell = hdr2.cells[i]
        cell.width = int(Cm(w))
        p = cell.paragraphs[0]
        run = p.add_run(h_text)
        run.bold = True
        run.font.size = Pt(10)
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        tc_pr = cell._tc.get_or_add_tcPr()
        shd = OxmlElement('w:shd')
        shd.set(qn('w:val'), 'clear')
        shd.set(qn('w:color'), 'auto')
        shd.set(qn('w:fill'), 'D9D9D9')
        tc_pr.append(shd)

    indices = morph_indices.get("indices", [])
    for idx, (name, num, den, val) in enumerate(indices, 1):
        row_cells = tbl2.add_row().cells
        num_s = str(num) if num is not None else '—'
        den_s = str(den) if den is not None else '—'
        val_s = str(val) if val is not None else 'нет данных'
        widths = idx_widths
        for i, (cell, txt) in enumerate(zip(row_cells,
                                            [str(idx), name, num_s, den_s, val_s])):
            cell.width = int(Cm(widths[i]))
            p = cell.paragraphs[0]
            run = p.add_run(txt)
            run.font.size = Pt(10)
            if i == 4 and val is not None:
                run.bold = True
            if i == 4 and val is None:
                run.font.color.rgb = RGBColor(0x88, 0x88, 0x88)
            if i in (2, 3, 4):
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER

    doc.save(filepath)
