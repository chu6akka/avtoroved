"""
Вкладка 2: Статистика, POS-биграммы и морфологические признаки.
"""
from __future__ import annotations
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit,
    QPushButton, QSplitter, QLabel, QTableWidget,
    QTableWidgetItem, QHeaderView, QGroupBox, QTabWidget,
    QProgressBar, QFrame,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QColor


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

        # Три вкладки: Показатели / Морфемы / Биграммы
        self._inner_tabs = QTabWidget()
        layout.addWidget(self._inner_tabs)

        # ── Вкладка 1: Лингвостатистика ──────────────────────────────
        tab_stats = QWidget()
        tl = QVBoxLayout(tab_stats)
        tl.setContentsMargins(4, 4, 4, 4)
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
        tl.addWidget(metrics_group)
        self._inner_tabs.addTab(tab_stats, "📊 Показатели")

        # ── Вкладка 2: Морфологические признаки ──────────────────────
        tab_morph = QWidget()
        ml = QVBoxLayout(tab_morph)
        ml.setContentsMargins(4, 4, 4, 4)

        morph_hdr = QLabel(
            "Встречаемость морфологических признаков на 100 слов.\n"
            "Методология: Богданова С.Ю. (2010), Levchenko M.N. (2012) — "
            "распределение падежей, видов и времён как маркер идиостиля автора."
        )
        morph_hdr.setObjectName("caption")
        morph_hdr.setWordWrap(True)
        ml.addWidget(morph_hdr)

        self._morph_container = QWidget()
        self._morph_layout = QVBoxLayout(self._morph_container)
        self._morph_layout.setContentsMargins(0, 4, 0, 0)
        self._morph_layout.setSpacing(10)
        ml.addWidget(self._morph_container, stretch=1)
        self._inner_tabs.addTab(tab_morph, "🧬 Морфемы / 100 слов")

        # ── Вкладка 3: POS-биграммы ───────────────────────────────────
        tab_bigrams = QWidget()
        bl = QVBoxLayout(tab_bigrams)
        bl.setContentsMargins(4, 4, 4, 4)
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
        bl.addWidget(bigram_group)
        self._inner_tabs.addTab(tab_bigrams, "🔗 POS-биграммы")

        # ── Вкладка 4: Морфологические индексы идиостиля ─────────────
        tab_idx = QWidget()
        il = QVBoxLayout(tab_idx)
        il.setContentsMargins(4, 4, 4, 4)
        idx_hdr = QLabel(
            "20 морфологических индексов идиостиля автора.\n"
            "Источник: Лаб. работа № 11, СФЭ / Соколова Т.П. (МГЮА).\n"
            "Индекс #7 требует семантической разметки и рассчитывается отдельно."
        )
        idx_hdr.setObjectName("caption")
        idx_hdr.setWordWrap(True)
        il.addWidget(idx_hdr)
        idx_group = QGroupBox("Индексы")
        idx_lay = QVBoxLayout(idx_group)
        self.indices_table = QTableWidget()
        self.indices_table.setColumnCount(4)
        self.indices_table.setHorizontalHeaderLabels(["Индекс", "Числитель", "Знаменатель", "Значение"])
        self.indices_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.indices_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.indices_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.indices_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.indices_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.indices_table.verticalHeader().setVisible(False)
        self.indices_table.setAlternatingRowColors(True)
        idx_lay.addWidget(self.indices_table)
        il.addWidget(idx_group)
        self._inner_tabs.addTab(tab_idx, "📐 Индексы идиостиля")

    # Цвета для морфологических категорий
    _CAT_COLORS = {
        "Падеж":          "#89b4fa",
        "Число":          "#a6e3a1",
        "Род":            "#f9e2af",
        "Вид":            "#cba6f7",
        "Время":          "#fab387",
        "Наклонение":     "#89dceb",
        "Форма глагола":  "#f38ba8",
        "Одушевлённость": "#a6adc8",
    }

    def populate(self, metrics: dict):
        """Заполнить вкладку метриками."""
        # ── Показатели ────────────────────────────────────────────────
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

        # ── Морфемы на 100 слов ───────────────────────────────────────
        self._populate_morph(metrics.get("morph_stats", {}))

        # ── Морфологические индексы ───────────────────────────────────
        self._populate_indices(metrics.get("morph_indices", {}))

        # ── POS-биграммы ──────────────────────────────────────────────
        pos_bg = metrics.get("pos_bigrams", {})
        top_bg = pos_bg.get("top_bigrams", [])
        self.bigram_table.setRowCount(len(top_bg))
        for i, bg in enumerate(top_bg):
            for col, val in enumerate([str(i + 1), bg["pair_ru"], bg["pair_full"], f"{bg['freq']:.4f}"]):
                item = QTableWidgetItem(val)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.bigram_table.setItem(i, col, item)

    def _populate_morph(self, morph_stats: dict):
        """Отрисовать блоки морфологической статистики."""
        # Очистить предыдущее содержимое
        while self._morph_layout.count():
            child = self._morph_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        if not morph_stats:
            lbl = QLabel("Нет данных — запустите анализ.")
            lbl.setObjectName("caption")
            self._morph_layout.addWidget(lbl)
            return

        for cat, values in morph_stats.items():
            color = self._CAT_COLORS.get(cat, "#cdd6f4")
            box = QGroupBox(cat)
            box_lay = QVBoxLayout(box)
            box_lay.setContentsMargins(6, 4, 6, 4)
            box_lay.setSpacing(3)

            max_val = max(values.values()) if values else 1

            for val_name, per100 in values.items():
                row = QHBoxLayout()

                name_lbl = QLabel(val_name)
                name_lbl.setFixedWidth(160)
                name_lbl.setObjectName("caption")
                row.addWidget(name_lbl)

                bar = QProgressBar()
                bar.setRange(0, int(max_val * 10) or 1)
                bar.setValue(int(per100 * 10))
                bar.setFixedHeight(16)
                bar.setTextVisible(False)
                bar.setStyleSheet(
                    f"QProgressBar::chunk {{ background: {color}; border-radius: 2px; }}"
                    "QProgressBar { background: #0d1117; border: 1px solid #3d4555; border-radius: 2px; }"
                )
                row.addWidget(bar, stretch=1)

                cnt_lbl = QLabel(f"{per100:.1f}")
                cnt_lbl.setFixedWidth(46)
                cnt_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                cnt_lbl.setObjectName("caption")
                cnt_lbl.setStyleSheet(f"color: {color};")
                row.addWidget(cnt_lbl)

                box_lay.addLayout(row)

            self._morph_layout.addWidget(box)

        self._morph_layout.addStretch()

    def _populate_indices(self, morph_indices: dict):
        """Заполнить таблицу морфологических индексов идиостиля."""
        indices = morph_indices.get("indices", [])
        self.indices_table.setRowCount(len(indices))
        for row, (name, num, den, val) in enumerate(indices):
            num_s = str(num) if num is not None else "—"
            den_s = str(den) if den is not None else "—"
            val_s = str(val) if val is not None else "нет данных"

            items = [
                QTableWidgetItem(name),
                QTableWidgetItem(num_s),
                QTableWidgetItem(den_s),
                QTableWidgetItem(val_s),
            ]
            for col, item in enumerate(items):
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if col == 3 and val is not None:
                    item.setForeground(QColor("#e8a030"))
                elif val is None:
                    item.setForeground(QColor("#6b7280"))
                self.indices_table.setItem(row, col, item)

    def _is_dark(self) -> bool:
        palette = self.palette()
        bg = palette.color(palette.ColorRole.Window)
        return bg.lightness() < 128

    def clear(self):
        self.metrics_table.setRowCount(0)
        self.bigram_table.setRowCount(0)
        self.indices_table.setRowCount(0)
        while self._morph_layout.count():
            child = self._morph_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
