"""
Вкладка 1: Морфологический анализ.
"""
from __future__ import annotations
from typing import List, Dict
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QLabel, QLineEdit, QPushButton
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont

from analyzer.stanza_backend import TokenInfo, WORD_RE, UPOS_RU

# Цвета POS-категорий (для удобства чтения)
POS_COLORS = {
    "NOUN":  "#89b4fa", "PROPN": "#74c7ec", "VERB":  "#a6e3a1",
    "AUX":   "#94e2d5", "ADJ":   "#cba6f7", "ADV":   "#f9e2af",
    "PRON":  "#fab387", "NUM":   "#f5c2e7", "DET":   "#eba0ac",
    "ADP":   "#6c7086", "PART":  "#7f849c", "CCONJ": "#9399b2",
    "SCONJ": "#9399b2", "INTJ":  "#f38ba8", "PUNCT": "#45475a",
    "SYM":   "#585b70", "X":     "#585b70",
}


class MorphologyTab(QWidget):
    """Таблица токенов с морфологическим разбором."""

    token_hovered = pyqtSignal(int, int)   # start, end в исходном тексте
    token_clicked = pyqtSignal(int, int)   # start, end — клик для навигации

    def __init__(self, parent=None):
        super().__init__(parent)
        self._row_to_span: Dict[int, tuple] = {}
        self._all_rows: List[dict] = []      # для фильтрации
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        # Заголовок + поиск
        top_row = QHBoxLayout()
        lbl = QLabel("Морфологический разбор токенов (Stanford Stanza):")
        lbl.setObjectName("subtitle")
        top_row.addWidget(lbl)
        top_row.addStretch()
        top_row.addWidget(QLabel("Фильтр:"))
        self.filter_input = QLineEdit()
        self.filter_input.setPlaceholderText("Словоформа или лемма...")
        self.filter_input.setMaximumWidth(180)
        self.filter_input.textChanged.connect(self._apply_filter)
        top_row.addWidget(self.filter_input)
        btn_clear_filter = QPushButton("✕")
        btn_clear_filter.setObjectName("secondary")
        btn_clear_filter.setFixedWidth(28)
        btn_clear_filter.setFixedHeight(28)
        btn_clear_filter.clicked.connect(lambda: self.filter_input.clear())
        top_row.addWidget(btn_clear_filter)
        layout.addLayout(top_row)

        # Таблица токенов
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(
            ["Словоформа", "Лемма", "Часть речи", "Морф. признаки"])
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setMouseTracking(True)
        # Hover → подсветка в тексте
        self.table.cellEntered.connect(self._on_cell_entered)
        # Клик → навигация в тексте
        self.table.itemSelectionChanged.connect(self._on_row_selected)
        layout.addWidget(self.table)

        self.count_label = QLabel("Токенов: 0")
        self.count_label.setObjectName("subtitle")
        layout.addWidget(self.count_label)

    # ─── Заполнение ───────────────────────────────────────────────────────────
    def populate(self, tokens: List[TokenInfo], text: str):
        """Заполнить таблицу результатами морфологического анализа."""
        self._all_rows.clear()
        self._row_to_span.clear()
        self.filter_input.clear()

        words = [t for t in tokens if WORD_RE.search(t.text)]
        lower = text.lower()
        cursor = 0
        word_count = 0

        for row_idx, tok in enumerate(words):
            found = lower.find(tok.text.lower(), cursor)
            if found == -1:
                found = lower.find(tok.text.lower())
            span = (found, found + len(tok.text)) if found != -1 else None
            if span:
                cursor = span[1]

            self._all_rows.append({
                "text": tok.text,
                "lemma": tok.lemma,
                "pos_label": tok.pos_label,
                "feats": tok.feats,
                "pos": tok.pos,
                "span": span,
            })
            if tok.pos != "PUNCT":
                word_count += 1

        self._render_rows(self._all_rows)
        self.count_label.setText(
            f"Токенов: {len(words)} | Слов (без пунктуации): {word_count}")

    def _render_rows(self, rows: List[dict]):
        self._row_to_span.clear()
        self.table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            color = QColor(POS_COLORS.get(r["pos"], "#cdd6f4"))
            items = [r["text"], r["lemma"], r["pos_label"], r["feats"]]
            for col, val in enumerate(items):
                item = QTableWidgetItem(val)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                # Подкрашиваем колонку «Часть речи»
                if col == 2:
                    item.setForeground(color)
                self.table.setItem(i, col, item)
            if r["span"]:
                self._row_to_span[i] = r["span"]

    # ─── Фильтрация ───────────────────────────────────────────────────────────
    def _apply_filter(self, text: str):
        query = text.lower().strip()
        if not query:
            self._render_rows(self._all_rows)
            return
        filtered = [r for r in self._all_rows
                    if query in r["text"].lower() or query in r["lemma"].lower()
                    or query in r["pos_label"].lower()]
        self._render_rows(filtered)

    # ─── Сигналы ──────────────────────────────────────────────────────────────
    def _on_cell_entered(self, row: int, col: int):
        """Hover: подсветить токен в тексте."""
        if row in self._row_to_span:
            start, end = self._row_to_span[row]
            self.token_hovered.emit(start, end)

    def _on_row_selected(self):
        """Клик по строке: перейти к токену в тексте."""
        rows = self.table.selectedItems()
        if not rows:
            return
        row = self.table.currentRow()
        if row in self._row_to_span:
            start, end = self._row_to_span[row]
            self.token_clicked.emit(start, end)

    def clear(self):
        self.table.setRowCount(0)
        self._row_to_span.clear()
        self._all_rows.clear()
        self.filter_input.clear()
        self.count_label.setText("Токенов: 0")
