"""
ui/tabs/nkrya_tab.py — Вкладка «Частотный анализ по НКРЯ».

Методология: Ляшевская О.Н., Шаров С.А. «Частотный словарь
современного русского языка (на материалах НКРЯ)». М.: Азбуковник, 2009.
"""
from __future__ import annotations

import os
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QFrame,
    QSplitter, QScrollArea, QProgressBar, QGroupBox,
    QComboBox, QStackedWidget, QSizePolicy,
)
from PyQt6.QtCore import Qt, pyqtSignal, QThread
from PyQt6.QtGui import QColor, QFont

from analyzer.freq_engine import FreqResult, BANDS, get as get_engine


# ── Поток загрузки словаря ─────────────────────────────────────────────────

class DictLoadThread(QThread):
    finished = pyqtSignal(bool, str)  # (success, message)

    def __init__(self, path: str = ""):
        super().__init__()
        self._path = path

    def run(self):
        engine = get_engine()
        if self._path:
            ok = engine.load(self._path)
        else:
            ok = engine.load()
        msg = f"Загружено лемм: {engine.dict_size:,}" if ok else (engine.load_error or "Ошибка")
        self.finished.emit(ok, msg)


# ── Вспомогательный виджет: горизонтальная полоса диапазона ───────────────

class BandBar(QWidget):
    """Одна строка в частотном профиле: имя + цветная полоса + число."""

    def __init__(self, label: str, color: str, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 1, 0, 1)
        lay.setSpacing(8)

        lbl = QLabel(label)
        lbl.setFixedWidth(230)
        lbl.setObjectName("caption")
        lay.addWidget(lbl)

        self._bar = QProgressBar()
        self._bar.setRange(0, 100)
        self._bar.setValue(0)
        self._bar.setFixedHeight(18)
        self._bar.setTextVisible(False)
        self._bar.setStyleSheet(
            f"QProgressBar::chunk {{ background: {color}; border-radius: 3px; }}"
            "QProgressBar { background: #0d1117; border: 1px solid #3d4555; border-radius: 3px; }"
        )
        lay.addWidget(self._bar, stretch=1)

        self._cnt = QLabel("—")
        self._cnt.setObjectName("caption")
        self._cnt.setFixedWidth(70)
        self._cnt.setAlignment(Qt.AlignmentFlag.AlignRight)
        lay.addWidget(self._cnt)

        self._pct = QLabel("")
        self._pct.setObjectName("caption")
        self._pct.setFixedWidth(50)
        self._pct.setAlignment(Qt.AlignmentFlag.AlignRight)
        lay.addWidget(self._pct)

    def update_value(self, count: int, total: int):
        pct = round(count / total * 100) if total else 0
        self._bar.setValue(pct)
        self._cnt.setText(f"{count:,}")
        self._pct.setText(f"{pct} %")


# ── Основная вкладка ───────────────────────────────────────────────────────

class NkryaTab(QWidget):
    """Вкладка частотного анализа по корпусу НКРЯ."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._result: Optional[FreqResult] = None
        self._load_thread: Optional[DictLoadThread] = None
        self._band_bars: dict = {}
        self._setup_ui()
        self._check_dict_state()

    # ── Построение UI ─────────────────────────────────────────────────────

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Заголовок ──────────────────────────────────────────────────
        hdr_widget = QWidget()
        hdr_widget.setObjectName("tab_header")
        hdr_layout = QVBoxLayout(hdr_widget)
        hdr_layout.setContentsMargins(12, 8, 12, 8)
        hdr_layout.setSpacing(2)

        top_row = QHBoxLayout()
        title = QLabel("Частотный анализ по НКРЯ")
        title.setObjectName("subtitle")
        top_row.addWidget(title)
        top_row.addStretch()

        self._dict_status = QLabel("⏳ Словарь: проверка...")
        self._dict_status.setObjectName("caption")
        top_row.addWidget(self._dict_status)

        self._load_btn = QPushButton("📥 Загрузить словарь")
        self._load_btn.setObjectName("secondary")
        self._load_btn.setFixedHeight(26)
        self._load_btn.clicked.connect(self._on_load_btn)
        top_row.addWidget(self._load_btn)

        hdr_layout.addLayout(top_row)

        meta = QLabel(
            "Методология: Ляшевская О.Н., Шаров С.А. (2009) · "
            "Частотные диапазоны на основе ipm (instances per million) · "
            "Лемматизация: pymorphy3"
        )
        meta.setObjectName("caption")
        hdr_layout.addWidget(meta)
        root.addWidget(hdr_widget)

        # ── Стек: «нет словаря» / «нет анализа» / «результаты» ───────
        self._stack = QStackedWidget()
        root.addWidget(self._stack, stretch=1)

        self._stack.addWidget(self._build_no_dict_page())  # 0
        self._stack.addWidget(self._build_no_result_page()) # 1
        self._stack.addWidget(self._build_result_page())    # 2

    def _build_no_dict_page(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)

        icon = QLabel("📚")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet("font-size: 48px;")
        lay.addWidget(icon)

        lbl = QLabel("Частотный словарь НКРЯ не загружен")
        lbl.setObjectName("subtitle")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(lbl)

        desc = QLabel(
            "Для работы вкладки необходим частотный словарь\n"
            "Ляшевской-Шарова (на материалах НКРЯ, ~50 000 лемм).\n\n"
            "Нажмите кнопку «Загрузить словарь» выше,\n"
            "или скачайте файл вручную и укажите путь к нему."
        )
        desc.setObjectName("caption")
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(desc)

        inst_box = QGroupBox("Ручная установка")
        inst_box.setFixedWidth(480)
        inst_lay = QVBoxLayout(inst_box)
        inst = QLabel(
            "1. Скачайте: http://www.ruscorpora.ru/new/freq-dict.html\n"
            "2. Файл freqrnc2011.csv → поместите в data/freq/\n"
            "3. Запустите: python scripts/download_freq_dict.py --file data/freq/freqrnc2011.csv"
        )
        inst.setObjectName("caption")
        inst.setWordWrap(True)
        inst_lay.addWidget(inst)

        self._manual_path_btn = QPushButton("📂 Выбрать файл…")
        self._manual_path_btn.setObjectName("secondary")
        self._manual_path_btn.clicked.connect(self._pick_dict_file)
        inst_lay.addWidget(self._manual_path_btn)

        center = QHBoxLayout()
        center.addStretch()
        center.addWidget(inst_box)
        center.addStretch()
        lay.addLayout(center)

        return w

    def _build_no_result_page(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon = QLabel("📊")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet("font-size: 40px;")
        lay.addWidget(icon)
        lbl = QLabel("Словарь загружен. Введите текст и нажмите «Анализировать».")
        lbl.setObjectName("caption")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(lbl)
        return w

    def _build_result_page(self) -> QWidget:
        w = QWidget()
        root = QVBoxLayout(w)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        # ── Верхний сплиттер: профиль | метрики ────────────────────
        top_split = QSplitter(Qt.Orientation.Horizontal)

        # Частотный профиль
        profile_box = QGroupBox("Частотный профиль лексики")
        profile_lay = QVBoxLayout(profile_box)
        profile_lay.setSpacing(2)

        header_row = QHBoxLayout()
        for txt, width in [("Диапазон", 230), ("", -1), ("Слов", 70), ("%", 50)]:
            lbl = QLabel(txt)
            lbl.setObjectName("caption")
            if width > 0:
                lbl.setFixedWidth(width)
            header_row.addWidget(lbl, 0 if width > 0 else 1)
        profile_lay.addLayout(header_row)

        d = QFrame()
        d.setFrameShape(QFrame.Shape.HLine)
        d.setObjectName("sidebar_divider")
        profile_lay.addWidget(d)

        for key, meta in BANDS.items():
            bar = BandBar(meta["label"], meta["color"])
            self._band_bars[key] = bar
            profile_lay.addWidget(bar)

        profile_lay.addStretch()
        top_split.addWidget(profile_box)

        # Ключевые метрики
        metrics_box = QGroupBox("Ключевые показатели")
        metrics_lay = QVBoxLayout(metrics_box)
        metrics_lay.setSpacing(6)

        self._metric_labels: dict[str, QLabel] = {}

        def _metric(key: str, label: str, tooltip: str = "") -> QLabel:
            row = QHBoxLayout()
            name_lbl = QLabel(label + ":")
            name_lbl.setObjectName("caption")
            name_lbl.setFixedWidth(210)
            if tooltip:
                name_lbl.setToolTip(tooltip)
            row.addWidget(name_lbl)
            val_lbl = QLabel("—")
            val_lbl.setObjectName("value_label")
            row.addWidget(val_lbl)
            metrics_lay.addLayout(row)
            self._metric_labels[key] = val_lbl
            return val_lbl

        _metric("total",      "Всего слов в тексте")
        _metric("unique",     "Уникальных слов")
        _metric("avg_rank",   "Средний ранг словаря",
                "1 = самое частотное слово, 50000+ = редкое")
        _metric("avg_ipm",    "Средняя частота (ipm)",
                "ipm = вхождений на миллион слов корпуса")
        _metric("content_ipm","Средний ipm (без ядра)",
                "Для знаменательных слов — характеристика идиостиля")
        _metric("pct_absent", "Доля слов вне НКРЯ",
                "Неологизмы, авторская лексика, термины")
        _metric("pct_rare",   "Доля редкой лексики (>7000)",
                "Низкочастотная + раритетная")
        _metric("lexical_richness", "Лексическое богатство (TTR)",
                "Type-Token Ratio: уникальных / всего токенов")

        metrics_lay.addStretch()
        top_split.addWidget(metrics_box)
        top_split.setSizes([500, 300])
        root.addWidget(top_split)

        # ── Нижняя часть: таблица слов ─────────────────────────────
        table_box = QGroupBox("Словарь текста")
        table_lay = QVBoxLayout(table_box)
        table_lay.setContentsMargins(4, 4, 4, 4)

        # Фильтр по диапазону
        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Показать:"))
        self._band_filter = QComboBox()
        self._band_filter.addItem("Все слова", "all")
        for key, meta in BANDS.items():
            self._band_filter.addItem(meta["label"], key)
        self._band_filter.currentIndexChanged.connect(self._apply_table_filter)
        filter_row.addWidget(self._band_filter)

        self._sort_combo = QComboBox()
        self._sort_combo.addItem("По частоте (ранг ↑)", "rank_asc")
        self._sort_combo.addItem("По частоте (ранг ↓)", "rank_desc")
        self._sort_combo.addItem("По алфавиту", "alpha")
        self._sort_combo.addItem("По встречаемости в тексте ↓", "count_desc")
        self._sort_combo.currentIndexChanged.connect(self._apply_table_filter)
        filter_row.addWidget(QLabel("Сортировка:"))
        filter_row.addWidget(self._sort_combo)
        filter_row.addStretch()

        self._table_count_lbl = QLabel("")
        self._table_count_lbl.setObjectName("caption")
        filter_row.addWidget(self._table_count_lbl)
        table_lay.addLayout(filter_row)

        self._word_table = QTableWidget(0, 6)
        self._word_table.setHorizontalHeaderLabels([
            "Слово", "Лемма", "Ранг НКРЯ", "ipm", "PoS", "Встреч. в тексте"
        ])
        self._word_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch)
        self._word_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch)
        for col in (2, 3, 4, 5):
            self._word_table.horizontalHeader().setSectionResizeMode(
                col, QHeaderView.ResizeMode.ResizeToContents)
        self._word_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._word_table.verticalHeader().setVisible(False)
        self._word_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._word_table.setAlternatingRowColors(True)
        table_lay.addWidget(self._word_table)

        root.addWidget(table_box, stretch=1)
        return w

    # ── Состояние словаря ─────────────────────────────────────────────────

    def _check_dict_state(self):
        engine = get_engine()
        if engine.is_loaded:
            self._dict_status.setText(f"✓ Словарь: {engine.dict_size:,} лемм")
            self._load_btn.setVisible(False)
            self._stack.setCurrentIndex(1)
        else:
            # Попробовать загрузить молча
            self._start_load()

    def _start_load(self, path: str = ""):
        self._dict_status.setText("⏳ Загрузка словаря...")
        self._load_btn.setEnabled(False)
        self._load_thread = DictLoadThread(path)
        self._load_thread.finished.connect(self._on_load_done)
        self._load_thread.start()

    def _on_load_done(self, ok: bool, msg: str):
        self._load_btn.setEnabled(True)
        if ok:
            self._dict_status.setText(f"✓ Словарь: {msg}")
            self._load_btn.setVisible(False)
            if self._result is None:
                self._stack.setCurrentIndex(1)
            else:
                self._stack.setCurrentIndex(2)
        else:
            self._dict_status.setText("✗ Словарь не загружен")
            self._load_btn.setVisible(True)
            self._stack.setCurrentIndex(0)

    def _on_load_btn(self):
        self._start_load()

    def _pick_dict_file(self):
        from PyQt6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(
            self, "Выбрать файл словаря", "",
            "Частотный словарь (*.csv *.tsv *.txt *.json)"
        )
        if path:
            if path.endswith(".json"):
                # Уже готовый JSON — скопировать и загрузить
                import shutil
                dst = os.path.join(
                    os.path.dirname(os.path.dirname(
                        os.path.dirname(__file__))),
                    "data", "freq", "freqrnc.json"
                )
                shutil.copy(path, dst)
                self._start_load(dst)
            else:
                # CSV/TSV — нужно конвертировать через скрипт
                self._dict_status.setText("⏳ Конвертация файла...")
                self._start_convert_and_load(path)

    def _start_convert_and_load(self, src_path: str):
        """Запустить convert через subprocess."""
        import subprocess, sys
        scripts_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "scripts", "download_freq_dict.py"
        )
        dst = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "data", "freq", "freqrnc.json"
        )
        try:
            subprocess.run(
                [sys.executable, scripts_dir, "--file", src_path, "--out", dst],
                check=True, capture_output=True
            )
            self._start_load(dst)
        except subprocess.CalledProcessError as e:
            self._dict_status.setText(f"✗ Ошибка конвертации: {e.stderr.decode()[:60]}")

    # ── Публичный метод: передать результат анализа ───────────────────────

    def show_result(self, result: FreqResult):
        self._result = result
        if not get_engine().is_loaded:
            return
        self._fill_metrics(result)
        self._fill_bars(result)
        self._fill_table(result)
        self._stack.setCurrentIndex(2)

    def clear(self):
        self._result = None
        if get_engine().is_loaded:
            self._stack.setCurrentIndex(1)
        else:
            self._stack.setCurrentIndex(0)

    # ── Заполнение результатов ────────────────────────────────────────────

    def _fill_metrics(self, r: FreqResult):
        total = r.total_tokens
        unique = len(r.words)
        pct_absent = round(r.bands.get("absent", 0) / total * 100, 1) if total else 0
        pct_rare = round(
            (r.bands.get("low", 0) + r.bands.get("rare", 0)) / total * 100, 1
        ) if total else 0
        ttr = round(unique / total * 100, 1) if total else 0

        self._metric_labels["total"].setText(f"{total:,}")
        self._metric_labels["unique"].setText(f"{unique:,}")
        self._metric_labels["avg_rank"].setText(
            f"{r.avg_rank:,.0f}" if r.avg_rank else "—")
        self._metric_labels["avg_ipm"].setText(
            f"{r.avg_ipm:.2f}" if r.avg_ipm else "—")
        self._metric_labels["content_ipm"].setText(
            f"{r.content_avg_ipm:.2f}" if r.content_avg_ipm else "—")
        self._metric_labels["pct_absent"].setText(f"{pct_absent} %")
        self._metric_labels["pct_rare"].setText(f"{pct_rare} %")
        self._metric_labels["lexical_richness"].setText(f"{ttr} %")

    def _fill_bars(self, r: FreqResult):
        total = r.total_tokens or 1
        for key, bar in self._band_bars.items():
            bar.update_value(r.bands.get(key, 0), total)

    def _fill_table(self, r: FreqResult):
        self._apply_table_filter()

    def _apply_table_filter(self):
        if self._result is None:
            return
        band_key = self._band_filter.currentData()
        sort_key = self._sort_combo.currentData()

        words = self._result.words
        if band_key != "all":
            words = [w for w in words if w.band == band_key]

        if sort_key == "rank_asc":
            words = sorted(words, key=lambda w: w.rank if w.rank > 0 else 10_000_000)
        elif sort_key == "rank_desc":
            words = sorted(words, key=lambda w: -(w.rank or 0))
        elif sort_key == "alpha":
            words = sorted(words, key=lambda w: w.form)
        elif sort_key == "count_desc":
            words = sorted(words, key=lambda w: -w.count)

        self._word_table.setRowCount(0)
        self._word_table.setRowCount(len(words))
        self._table_count_lbl.setText(f"Слов: {len(words):,}")

        for row, we in enumerate(words):
            meta = BANDS[we.band]
            color = QColor(meta["color"])

            def _item(txt: str, align=Qt.AlignmentFlag.AlignLeft) -> QTableWidgetItem:
                it = QTableWidgetItem(str(txt))
                it.setForeground(color)
                it.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                it.setTextAlignment(align | Qt.AlignmentFlag.AlignVCenter)
                return it

            self._word_table.setItem(row, 0, _item(we.form))
            self._word_table.setItem(row, 1, _item(we.lemma))
            self._word_table.setItem(
                row, 2,
                _item(f"{we.rank:,}" if we.rank else "—",
                      Qt.AlignmentFlag.AlignRight))
            self._word_table.setItem(
                row, 3,
                _item(f"{we.ipm:.2f}" if we.ipm else "—",
                      Qt.AlignmentFlag.AlignRight))
            self._word_table.setItem(row, 4, _item(we.pos or "—"))
            self._word_table.setItem(
                row, 5,
                _item(str(we.count), Qt.AlignmentFlag.AlignRight))
