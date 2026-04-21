"""
Вкладка 2: Статистика и POS-биграммы.
"""
from __future__ import annotations
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit,
    QPushButton, QSplitter, QLabel, QTableWidget,
    QTableWidgetItem, QHeaderView, QGroupBox
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont


class StatisticsTab(QWidget):
    """Лингвостатистические показатели и POS-биграммы."""

    show_pie_requested = pyqtSignal()
    show_heatmap_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        # Кнопки графиков
        btn_row = QHBoxLayout()
        self.btn_pie = QPushButton("📊 Диаграмма частей речи")
        self.btn_pie.setObjectName("secondary")
        self.btn_pie.clicked.connect(self.show_pie_requested)
        self.btn_heatmap = QPushButton("🔥 Heatmap биграмм")
        self.btn_heatmap.setObjectName("secondary")
        self.btn_heatmap.clicked.connect(self.show_heatmap_requested)
        btn_row.addWidget(self.btn_pie)
        btn_row.addWidget(self.btn_heatmap)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        splitter = QSplitter(Qt.Orientation.Vertical)

        # Верхняя часть: числовые показатели
        top_widget = QWidget()
        top_layout = QVBoxLayout(top_widget)
        top_layout.setContentsMargins(0, 0, 0, 0)

        metrics_group = QGroupBox("Лингвостатистические показатели")
        metrics_layout = QVBoxLayout(metrics_group)
        self.metrics_table = QTableWidget()
        self.metrics_table.setColumnCount(2)
        self.metrics_table.setHorizontalHeaderLabels(["Показатель", "Значение"])
        self.metrics_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.metrics_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.metrics_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.metrics_table.verticalHeader().setVisible(False)
        self.metrics_table.setAlternatingRowColors(True)
        metrics_layout.addWidget(self.metrics_table)
        top_layout.addWidget(metrics_group)
        splitter.addWidget(top_widget)

        # Средняя часть: коэффициенты САЭ
        sae_widget = QWidget()
        sae_layout = QVBoxLayout(sae_widget)
        sae_layout.setContentsMargins(0, 0, 0, 0)

        sae_group = QGroupBox(
            "Морфологические коэффициенты (методика судебной автороведческой экспертизы)")
        sae_inner = QVBoxLayout(sae_group)
        sae_inner.addWidget(QLabel(
            "По С.М. Вул, Е.И. Галяшиной. Местоимения = PRON + DET "
            "(соответствует традиционной русской грамматике)."))
        self.sae_table = QTableWidget()
        self.sae_table.setColumnCount(4)
        self.sae_table.setHorizontalHeaderLabels(
            ["№", "Показатель", "Числитель / знаменатель", "Коэффициент"])
        sae_hdr = self.sae_table.horizontalHeader()
        sae_hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        sae_hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        sae_hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        sae_hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.sae_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.sae_table.verticalHeader().setVisible(False)
        self.sae_table.setAlternatingRowColors(True)
        sae_inner.addWidget(self.sae_table)
        sae_layout.addWidget(sae_group)
        splitter.addWidget(sae_widget)

        # Нижняя часть: POS-биграммы
        bottom_widget = QWidget()
        bottom_layout = QVBoxLayout(bottom_widget)
        bottom_layout.setContentsMargins(0, 0, 0, 0)

        bigram_group = QGroupBox("Коэффициенты сочетаемости частеречных пар (POS-биграммы)")
        bigram_layout = QVBoxLayout(bigram_group)
        bigram_layout.addWidget(QLabel(
            "Метод Litvinova et al. (2015–2016): частотное распределение POS-пар "
            "отражает грамматические привычки автора."))
        self.bigram_table = QTableWidget()
        self.bigram_table.setColumnCount(4)
        self.bigram_table.setHorizontalHeaderLabels(["№", "Пара (кратко)", "Пара (полная)", "Коэффициент"])
        self.bigram_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.bigram_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.bigram_table.verticalHeader().setVisible(False)
        self.bigram_table.setAlternatingRowColors(True)
        bigram_layout.addWidget(self.bigram_table)
        bottom_layout.addWidget(bigram_group)
        splitter.addWidget(bottom_widget)

        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter)

    def populate(self, metrics: dict):
        """Заполнить вкладку метриками."""
        # Числовые показатели
        additional = metrics.get("дополнительно", {})
        freq = metrics.get("частоты", {})
        style = metrics.get("профиль_служебных_слов", {})

        rows = []
        for k, v in additional.items():
            rows.append((k, str(v)))
        rows.append(("", ""))
        rows.append(("--- ЧАСТИ РЕЧИ ---", ""))
        for p, v in freq.items():
            rows.append((p, f"{v['количество']} ({v['коэффициент']:.2%})"))
        rows.append(("", ""))
        rows.append(("--- СЛУЖЕБНЫЕ СЛОВА ---", ""))
        for group, markers in style.items():
            found = [f"{k}={v}" for k, v in markers.items() if v > 0]
            if found:
                rows.append((group, ", ".join(found)))

        self.metrics_table.setRowCount(len(rows))
        for i, (k, v) in enumerate(rows):
            ki = QTableWidgetItem(k)
            ki.setFlags(ki.flags() & ~Qt.ItemFlag.ItemIsEditable)
            vi = QTableWidgetItem(v)
            vi.setFlags(vi.flags() & ~Qt.ItemFlag.ItemIsEditable)
            if k.startswith("---"):
                ki.setForeground(Qt.GlobalColor.cyan if self._is_dark() else Qt.GlobalColor.blue)
            self.metrics_table.setItem(i, 0, ki)
            self.metrics_table.setItem(i, 1, vi)

        # САЭ-коэффициенты
        sae = metrics.get("sae_coefficients", {})
        sae_rows = sae.get("rows", [])
        base = sae.get("base_counts", {})
        all_sae = []
        # Сначала базовые счётчики
        all_sae.append(("", "── Базовые счётчики ──", "", ""))
        for lbl, cnt in base.items():
            all_sae.append(("", lbl, str(cnt), ""))
        all_sae.append(("", "", "", ""))
        all_sae.append(("", "── Коэффициенты ──", "", ""))
        for r in sae_rows:
            val_str = f"{r['value']:.3f}" if r["value"] is not None else "н/д"
            frac_str = f"{r['numerator']}/{r['denominator']}"
            all_sae.append((str(r["n"]), r["label"], frac_str, val_str))

        self.sae_table.setRowCount(len(all_sae))
        for i, (n, lbl, frac, val) in enumerate(all_sae):
            for col, txt in enumerate([n, lbl, frac, val]):
                item = QTableWidgetItem(txt)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if lbl.startswith("──"):
                    item.setForeground(
                        Qt.GlobalColor.cyan if self._is_dark() else Qt.GlobalColor.blue)
                self.sae_table.setItem(i, col, item)

        # POS-биграммы
        pos_bg = metrics.get("pos_bigrams", {})
        top_bg = pos_bg.get("top_bigrams", [])
        self.bigram_table.setRowCount(len(top_bg))
        for i, bg in enumerate(top_bg):
            for col, val in enumerate([str(i + 1), bg["pair_ru"], bg["pair_full"], f"{bg['freq']:.4f}"]):
                item = QTableWidgetItem(val)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.bigram_table.setItem(i, col, item)

    def _is_dark(self) -> bool:
        palette = self.palette()
        bg = palette.color(palette.ColorRole.Window)
        return bg.lightness() < 128

    def clear(self):
        self.metrics_table.setRowCount(0)
        self.sae_table.setRowCount(0)
        self.bigram_table.setRowCount(0)
