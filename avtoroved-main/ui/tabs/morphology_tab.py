"""
Вкладка 1: Морфологический анализ.
"""
from __future__ import annotations
from typing import List, Dict
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QLabel
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont

from analyzer.stanza_backend import TokenInfo, WORD_RE


class MorphologyTab(QWidget):
    """Таблица токенов с морфологическим разбором."""

    token_hovered = pyqtSignal(int, int)  # start, end в исходном тексте

    def __init__(self, parent=None):
        super().__init__(parent)
        self._row_to_span: Dict[int, tuple] = {}
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        lbl = QLabel("Морфологический разбор токенов текста (Stanford Stanza):")
        lbl.setObjectName("subtitle")
        layout.addWidget(lbl)

        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Словоформа", "Лемма", "Часть речи", "Морф. признаки"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setMouseTracking(True)
        self.table.cellEntered.connect(self._on_cell_entered)
        layout.addWidget(self.table)

        self.count_label = QLabel("Токенов: 0")
        self.count_label.setObjectName("subtitle")
        layout.addWidget(self.count_label)

    def populate(self, tokens: List[TokenInfo], text: str):
        """Заполнить таблицу результатами морфологического анализа."""
        self.table.setRowCount(0)
        self._row_to_span.clear()

        words = [t for t in tokens if WORD_RE.search(t.text)]
        self.table.setRowCount(len(words))

        lower = text.lower()
        cursor = 0
        word_count = 0

        for row, tok in enumerate(words):
            found = lower.find(tok.text.lower(), cursor)
            if found == -1:
                found = lower.find(tok.text.lower())
            if found != -1:
                self._row_to_span[row] = (found, found + len(tok.text))
                cursor = found + len(tok.text)

            items = [tok.text, tok.lemma, tok.pos_label, tok.feats]
            for col, val in enumerate(items):
                item = QTableWidgetItem(val)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(row, col, item)

            if tok.pos != "PUNCT":
                word_count += 1

        self.count_label.setText(f"Токенов: {len(words)} | Слов (без пунктуации): {word_count}")

    def _on_cell_entered(self, row: int, col: int):
        if row in self._row_to_span:
            start, end = self._row_to_span[row]
            self.token_hovered.emit(start, end)

    def clear(self):
        self.table.setRowCount(0)
        self._row_to_span.clear()
        self.count_label.setText("Токенов: 0")
