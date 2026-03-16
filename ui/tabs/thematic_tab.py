"""
Вкладка 8: Тематические словари — профессиональная атрибуция.
"""
from __future__ import annotations
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QTextEdit, QLabel, QTableWidget, QTableWidgetItem,
    QHeaderView, QSplitter
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
    _MPL_AVAILABLE = True
except ImportError:
    _MPL_AVAILABLE = False


class ThematicTab(QWidget):
    """Анализ тематической принадлежности текста."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._result = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        lbl = QLabel(
            "Профессиональная атрибуция текста по 10 тематическим областям. "
            "Словари: юридическая, медицинская, IT, экономическая, военная, "
            "научная, религиозная, политическая, спортивная, бытовая."
        )
        lbl.setWordWrap(True)
        lbl.setObjectName("subtitle")
        layout.addWidget(lbl)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Левая: таблица
        left = QGroupBox("Плотность тематической лексики (слов на 1000)")
        left_layout = QVBoxLayout(left)
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Тематика", "Слов", "Плотность", "Примеры"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        left_layout.addWidget(self.table)
        splitter.addWidget(left)

        # Правая: гистограмма или отчёт
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)

        if _MPL_AVAILABLE:
            self.fig, self.ax = plt.subplots(figsize=(5, 6))
            self.fig.patch.set_facecolor("#1e1e2e")
            self.canvas = FigureCanvas(self.fig)
            right_layout.addWidget(self.canvas)
        else:
            self.canvas = None
            self.fig = None
            self.ax = None
            right_layout.addWidget(QLabel("matplotlib не установлен — гистограмма недоступна"))

        splitter.addWidget(right)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter)

        # Вывод
        conclusion_group = QGroupBox("Вывод тематической атрибуции")
        conclusion_layout = QVBoxLayout(conclusion_group)
        self.conclusion_label = QLabel("—")
        self.conclusion_label.setWordWrap(True)
        self.conclusion_label.setStyleSheet("font-size: 13px; padding: 4px;")
        conclusion_layout.addWidget(self.conclusion_label)
        layout.addWidget(conclusion_group)

    def populate(self, thematic_result, lemmas_count: int = 0):
        """Заполнить вкладку результатами тематического анализа."""
        self._result = thematic_result
        domains = thematic_result.domains
        top = thematic_result.top_domains

        # Таблица
        sorted_domains = sorted(domains.items(), key=lambda x: -x[1]["density"])
        self.table.setRowCount(len(sorted_domains))
        for i, (domain, data) in enumerate(sorted_domains):
            marker = "★ " if domain in top else ""
            vals = [
                marker + data["label"],
                str(data["count"]),
                f"{data['density']:.1f}",
                ", ".join(data["examples"][:4]),
            ]
            for col, val in enumerate(vals):
                item = QTableWidgetItem(val)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if domain in top[:1]:
                    item.setForeground(QColor("#a6e3a1"))
                elif domain in top[1:]:
                    item.setForeground(QColor("#89b4fa"))
                self.table.setItem(i, col, item)

        # Гистограмма
        if _MPL_AVAILABLE and self.ax is not None:
            self._draw_chart(sorted_domains, top)

        # Вывод
        if top:
            top_data = domains[top[0]]
            msg = f"Предположительная тематическая сфера: {top_data['label']} " \
                  f"(плотность: {top_data['density']:.1f} слов/1000)"
            if len(top) > 1:
                sec = domains[top[1]]
                msg += f"\nДополнительно: {sec['label']} ({sec['density']:.1f} слов/1000)"
            self.conclusion_label.setText(msg)
        else:
            self.conclusion_label.setText("Тематические словари не загружены или пусты.")

    def _draw_chart(self, sorted_domains: list, top: list):
        self.ax.clear()
        self.ax.set_facecolor("#181825")
        labels = [d[1]["label"] for d in sorted_domains]
        values = [d[1]["density"] for d in sorted_domains]
        colors = []
        for d in sorted_domains:
            domain_key = d[0]
            if domain_key in top[:1]:
                colors.append("#a6e3a1")
            elif domain_key in top[1:]:
                colors.append("#89b4fa")
            else:
                colors.append("#45475a")

        bars = self.ax.barh(labels, values, color=colors, edgecolor="#313244")
        self.ax.set_xlabel("Плотность (слов/1000)", color="#cdd6f4")
        self.ax.set_title("Тематическая атрибуция", color="#cdd6f4")
        self.ax.tick_params(colors="#cdd6f4")
        for spine in self.ax.spines.values():
            spine.set_color("#45475a")
        self.fig.tight_layout()
        self.canvas.draw()

    def clear(self):
        self.table.setRowCount(0)
        self.conclusion_label.setText("—")
        if _MPL_AVAILABLE and self.ax is not None:
            self.ax.clear()
            self.canvas.draw()
