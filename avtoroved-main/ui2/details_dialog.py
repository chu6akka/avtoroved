"""
Диалог «Подробно» — полная раздельная статистика по одному тексту.
Данные берутся из уже посчитанных metrics/tokens (analyzer/*), без пересчёта.

Вкладки:
  • Общие показатели    — metrics["дополнительно"]
  • Части речи          — metrics["частоты"] (количество + коэффициент)
  • Разбор по словам    — пословный морфоразбор (Stanza) + поиск по словам
  • 20 индексов идиостиля — metrics["morph_indices"]  (Соколова Т.П.)
  • SAE-коэффициенты (20) — metrics["sae_coefficients"] (Вул, Галяшина)
"""
from __future__ import annotations
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QTableWidget,
    QTableWidgetItem, QHeaderView, QWidget, QLabel, QLineEdit
)
from PyQt6.QtCore import Qt


# Светлая тема диалога (системная палитра Windows может быть тёмной — задаём явно)
DIALOG_QSS = """
QDialog { background: #f4f5f7; }
QTabWidget::pane { border: 1px solid #e3e6ea; background: white; border-radius: 6px; }
QTabBar::tab { background: #e7ebf0; color: #3a4150; padding: 7px 14px;
    border-top-left-radius: 6px; border-top-right-radius: 6px; margin-right: 2px; }
QTabBar::tab:selected { background: white; color: #1f2328; font-weight: 600; }
QTableWidget { background: white; color: #1f2328; gridline-color: #e9edf1;
    alternate-background-color: #f7f8fa; border: none; }
QTableWidget::item { color: #1f2328; padding: 2px 4px; }
QTableWidget::item:selected { background: #d8e6ff; color: #1f2328; }
QHeaderView::section { background: #eef1f4; color: #424a57; padding: 6px;
    border: none; border-right: 1px solid #e3e6ea; font-weight: 600; }
QLineEdit { background: white; border: 1px solid #cbd2da; border-radius: 7px;
    padding: 7px 10px; color: #1f2328; font-size: 13px; }
QLabel { color: #3a4150; }
"""


def _table(headers, rows, stretch_col=0) -> QTableWidget:
    t = QTableWidget()
    t.setColumnCount(len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.setRowCount(len(rows))
    t.verticalHeader().setVisible(False)
    t.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    t.setAlternatingRowColors(True)
    for r, row in enumerate(rows):
        for c, val in enumerate(row):
            it = QTableWidgetItem("" if val is None else str(val))
            it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
            t.setItem(r, c, it)
    hh = t.horizontalHeader()
    for c in range(len(headers)):
        hh.setSectionResizeMode(
            c, QHeaderView.ResizeMode.Stretch if c == stretch_col
            else QHeaderView.ResizeMode.ResizeToContents)
    return t


def _wrap(widget, caption: str = "") -> QWidget:
    w = QWidget()
    lay = QVBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    if caption:
        c = QLabel(caption)
        c.setStyleSheet("color:#6b7280; font-size:11px; padding:4px 2px;")
        c.setWordWrap(True)
        lay.addWidget(c)
    lay.addWidget(widget)
    return w


def _word_tab(tokens) -> QWidget:
    """Разбор по словам с живым поиском по словоформе и лемме."""
    rows = [(t.text, t.lemma, t.pos_label, t.feats)
            for t in (tokens or []) if t.pos != "PUNCT"]
    table = _table(["Словоформа", "Лемма", "Часть речи",
                    "Морфологические признаки"], rows, stretch_col=3)

    w = QWidget()
    lay = QVBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(6)

    bar = QHBoxLayout()
    search = QLineEdit()
    search.setPlaceholderText("🔎 Поиск по словам или леммам…")
    search.setClearButtonEnabled(True)
    bar.addWidget(search)
    counter = QLabel(f"{len(rows)} слов")
    counter.setStyleSheet("color:#6b7280; font-size:11px;")
    bar.addWidget(counter)
    lay.addLayout(bar)

    cap = QLabel("Пословный морфологический разбор (Stanford Stanza, Universal Dependencies).")
    cap.setStyleSheet("color:#6b7280; font-size:11px;")
    lay.addWidget(cap)
    lay.addWidget(table)

    def _filter(text: str):
        q = text.strip().lower()
        shown = 0
        for r in range(table.rowCount()):
            surface = (table.item(r, 0).text() if table.item(r, 0) else "").lower()
            lemma = (table.item(r, 1).text() if table.item(r, 1) else "").lower()
            match = (q in surface) or (q in lemma) if q else True
            table.setRowHidden(r, not match)
            if match:
                shown += 1
        counter.setText(f"{shown} из {len(rows)} слов" if q else f"{len(rows)} слов")

    search.textChanged.connect(_filter)
    return w


class DetailsDialog(QDialog):
    def __init__(self, slot, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Подробная статистика — {slot.name}")
        self.resize(900, 640)
        self.setStyleSheet(DIALOG_QSS)

        lay = QVBoxLayout(self)
        tabs = QTabWidget()
        lay.addWidget(tabs)

        m = slot.metrics or {}

        # ── Общие показатели ──────────────────────────────────────────
        add = m.get("дополнительно", {})
        gen_rows = [(k, v) for k, v in add.items()]
        tabs.addTab(_wrap(_table(["Показатель", "Значение"], gen_rows, stretch_col=0)),
                    "Общие показатели")

        # ── Части речи ────────────────────────────────────────────────
        freq = m.get("частоты", {})
        pos_rows = [(pos, d.get("количество"), d.get("коэффициент"))
                    for pos, d in freq.items()]
        tabs.addTab(_wrap(_table(["Часть речи", "Количество", "Коэффициент (доля)"],
                                 pos_rows, stretch_col=0),
                          "Доля каждой части речи в тексте."),
                    "Части речи")

        # ── Разбор по словам (с поиском) ──────────────────────────────
        word_count = sum(1 for t in (slot.tokens or []) if t.pos != "PUNCT")
        tabs.addTab(_word_tab(slot.tokens), f"Разбор по словам ({word_count})")

        # ── 20 индексов идиостиля ─────────────────────────────────────
        idx = m.get("morph_indices", {}).get("indices", [])
        idx_rows = [(name, num, den, val) for (name, num, den, val) in idx]
        tabs.addTab(_wrap(_table(["Индекс", "Числитель", "Знаменатель", "Значение"],
                                 idx_rows, stretch_col=0),
                          "20 морфологических индексов идиостиля (Соколова Т.П.). "
                          "«нет данных» — требует семантической разметки."),
                    "20 индексов")

        # ── SAE-коэффициенты ──────────────────────────────────────────
        sae = m.get("sae_coefficients", {})
        sae_rows = [(r["n"], r["label"], r["display"]) for r in sae.get("rows", [])]
        sae_tab = QWidget()
        sl = QVBoxLayout(sae_tab)
        sl.setContentsMargins(0, 0, 0, 0)
        cap = QLabel("20 морфологических коэффициентов СAЭ (С.М. Вул, Е.И. Галяшина).")
        cap.setStyleSheet("color:#6b7280; font-size:11px; padding:4px 2px;")
        sl.addWidget(cap)
        sl.addWidget(_table(["№", "Коэффициент", "Значение"], sae_rows, stretch_col=1))
        base = sae.get("base_counts", {})
        if base:
            sl.addWidget(QLabel("Базовые подсчёты:"))
            sl.addWidget(_table(["Категория", "Количество"],
                                [(k, v) for k, v in base.items()], stretch_col=0))
        tabs.addTab(sae_tab, "SAE (20)")
