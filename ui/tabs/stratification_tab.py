"""
Вкладка 5: Лексическая стратификация.
"""
from __future__ import annotations
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QSplitter, QGroupBox,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QTextEdit, QLabel
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor


class StratificationTab(QWidget):
    """Распределение лексики по стилистическим пластам."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        splitter = QSplitter(Qt.Orientation.Vertical)

        # Верх: таблица пластов
        top = QGroupBox("Распределение по стилистическим пластам (ЭКЦ МВД России)")
        top_layout = QVBoxLayout(top)
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Стилистический пласт", "Ед.", "Доля", "Примеры"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        top_layout.addWidget(self.table)
        splitter.addWidget(top)

        # Низ: текстовый отчёт
        bottom = QGroupBox("Подробный отчёт и аналитический вывод")
        bottom_layout = QVBoxLayout(bottom)
        self.report_text = QTextEdit()
        self.report_text.setReadOnly(True)
        bottom_layout.addWidget(self.report_text)
        splitter.addWidget(bottom)

        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter)

        # Статус словаря
        try:
            from lexical_stratification import LAYER_ORDER
            status = "✓ Словарь загружен (12 251 лемма)"
            color = "#a6e3a1"
        except ImportError:
            status = "⚠ Файл lexicon_stratified.json не найден рядом с программой"
            color = "#f38ba8"
        lbl = QLabel(status)
        lbl.setStyleSheet(f"color: {color}; font-size: 11px;")
        layout.addWidget(lbl)

    def populate(self, strat_result):
        """Заполнить вкладку результатами стратификации."""
        try:
            from lexical_stratification import (
                LAYER_ORDER, LAYER_LABELS, LAYER_COLORS,
                format_stratification_report
            )
        except ImportError:
            self.report_text.setPlainText("Модуль стратификации недоступен.")
            return

        self.table.setRowCount(0)
        row_idx = 0

        for layer in LAYER_ORDER:
            count = strat_result.layer_counts.get(layer, 0)
            if count == 0:
                continue
            ratio = strat_result.layer_ratios.get(layer, 0.0)
            label = LAYER_LABELS.get(layer, layer)
            tokens = strat_result.by_layer.get(layer, [])
            seen: dict = {}
            for t in tokens:
                key = t.match_key if t.is_phrase else t.lemma
                seen[key] = seen.get(key, 0) + 1
            top = sorted(seen, key=lambda x: -seen[x])[:5]
            examples = ", ".join(top)

            self.table.insertRow(row_idx)
            vals = [label, str(count), f"{ratio:.1%}", examples]
            for col, val in enumerate(vals):
                item = QTableWidgetItem(val)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                color_hex = LAYER_COLORS.get(layer, "#cdd6f4")
                if col == 0:
                    item.setForeground(QColor(color_hex))
                self.table.setItem(row_idx, col, item)
            row_idx += 1

        self.report_text.setPlainText(format_stratification_report(strat_result))

    def clear(self):
        self.table.setRowCount(0)
        self.report_text.clear()
