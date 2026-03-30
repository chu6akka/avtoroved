"""
ui/tabs/senti_tab.py — Вкладка «Тональный профиль».

Методология: Loukachevitch N., Levchik A. (2016)
  «Creating a General Sentiment Lexicon for Russian», LREC-2016.
Лексикон: RuSentiLex 2017 (13 295 лемм).
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QFrame,
    QSplitter, QGroupBox, QProgressBar, QStackedWidget,
    QTabWidget, QSizePolicy,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor, QFont

from analyzer.senti_engine import SentiResult, SENTIMENTS, TYPES, get as get_engine


# ─── Поток загрузки ──────────────────────────────────────────────────────────

class SentiLoadThread(QThread):
    finished = pyqtSignal(bool, str)

    def run(self):
        engine = get_engine()
        ok = engine.load()
        msg = f"Загружено лемм: {engine.size:,}" if ok else (engine._load_error or "Ошибка")
        self.finished.emit(ok, msg)


# ─── Виджет балансовой полосы ─────────────────────────────────────────────────

class BalanceBar(QWidget):
    """Двусторонняя полоса neg ← центр → pos."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(28)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)

        self._neg_bar = QProgressBar()
        self._neg_bar.setRange(0, 100)
        self._neg_bar.setValue(0)
        self._neg_bar.setTextVisible(False)
        self._neg_bar.setFixedHeight(18)
        self._neg_bar.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self._neg_bar.setStyleSheet(
            "QProgressBar::chunk { background: #f38ba8; border-radius: 3px; }"
            "QProgressBar { background: #313244; border-radius: 3px; }"
        )
        self._neg_bar.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self._center = QLabel("◆")
        self._center.setFixedWidth(14)
        self._center.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._center.setObjectName("caption")

        self._pos_bar = QProgressBar()
        self._pos_bar.setRange(0, 100)
        self._pos_bar.setValue(0)
        self._pos_bar.setTextVisible(False)
        self._pos_bar.setFixedHeight(18)
        self._pos_bar.setStyleSheet(
            "QProgressBar::chunk { background: #a6e3a1; border-radius: 3px; }"
            "QProgressBar { background: #313244; border-radius: 3px; }"
        )
        self._pos_bar.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        lay.addWidget(self._neg_bar)
        lay.addWidget(self._center)
        lay.addWidget(self._pos_bar)

    def set_values(self, neg_pct: int, pos_pct: int):
        self._neg_bar.setValue(neg_pct)
        self._pos_bar.setValue(pos_pct)


# ─── Таблица тональных слов ───────────────────────────────────────────────────

class SentiWordTable(QTableWidget):
    def __init__(self, sentiment: str, parent=None):
        super().__init__(0, 4, parent)
        self._sentiment = sentiment
        self.setHorizontalHeaderLabels(["Слово", "Лемма", "Тип", "Встреч."])
        self.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch)
        self.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch)
        self.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.ResizeToContents)
        self.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.ResizeMode.ResizeToContents)
        self.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.verticalHeader().setVisible(False)
        self.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.setAlternatingRowColors(True)

    def populate(self, words):
        color = QColor(SENTIMENTS[self._sentiment]["color"])
        self.setRowCount(0)
        self.setRowCount(len(words))
        for row, w in enumerate(words):
            def _item(txt, align=Qt.AlignmentFlag.AlignLeft):
                it = QTableWidgetItem(str(txt))
                it.setForeground(color)
                it.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                it.setTextAlignment(align | Qt.AlignmentFlag.AlignVCenter)
                return it
            self.setItem(row, 0, _item(w.form))
            self.setItem(row, 1, _item(w.lemma))
            self.setItem(row, 2, _item(TYPES.get(w.stype, w.stype)))
            self.setItem(row, 3, _item(str(w.count), Qt.AlignmentFlag.AlignRight))


# ─── Главная вкладка ─────────────────────────────────────────────────────────

class SentiTab(QWidget):
    """Вкладка тонального профиля текста."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._result: Optional[SentiResult] = None
        self._load_thread: Optional[SentiLoadThread] = None
        self._setup_ui()
        self._auto_load()

    # ── Построение UI ────────────────────────────────────────────────────

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Заголовок
        hdr = QWidget()
        hdr.setObjectName("tab_header")
        hdr_lay = QVBoxLayout(hdr)
        hdr_lay.setContentsMargins(12, 8, 12, 8)
        hdr_lay.setSpacing(2)

        top_row = QHBoxLayout()
        title = QLabel("Тональный профиль текста")
        title.setObjectName("subtitle")
        top_row.addWidget(title)
        top_row.addStretch()

        self._status_lbl = QLabel("⏳ Загрузка лексикона...")
        self._status_lbl.setObjectName("caption")
        top_row.addWidget(self._status_lbl)

        hdr_lay.addLayout(top_row)
        meta = QLabel(
            "Методология: Loukachevitch N., Levchik A. (2016) · "
            "RuSentiLex 2017 · 13 295 лемм · Лемматизация: pymorphy3"
        )
        meta.setObjectName("caption")
        hdr_lay.addWidget(meta)
        root.addWidget(hdr)

        # Стек: нет данных / результаты
        self._stack = QStackedWidget()
        root.addWidget(self._stack, stretch=1)

        self._stack.addWidget(self._build_empty_page())   # 0
        self._stack.addWidget(self._build_result_page())  # 1

    def _build_empty_page(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon = QLabel("💬")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet("font-size: 48px;")
        lay.addWidget(icon)
        lbl = QLabel("Введите текст и нажмите «Анализировать».")
        lbl.setObjectName("caption")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(lbl)
        return w

    def _build_result_page(self) -> QWidget:
        w = QWidget()
        root = QVBoxLayout(w)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        # ── Верхняя панель: сводка + баланс ───────────────────────────
        top_split = QSplitter(Qt.Orientation.Horizontal)

        # Общая сводка
        summary_box = QGroupBox("Сводка")
        summary_lay = QVBoxLayout(summary_box)
        summary_lay.setSpacing(6)

        self._dominant_lbl = QLabel("—")
        self._dominant_lbl.setStyleSheet("font-size: 22px; font-weight: bold;")
        summary_lay.addWidget(self._dominant_lbl)

        def _row(key: str, label: str, tip: str = "") -> QLabel:
            r = QHBoxLayout()
            n = QLabel(label + ":")
            n.setObjectName("caption")
            n.setFixedWidth(200)
            if tip:
                n.setToolTip(tip)
            r.addWidget(n)
            v = QLabel("—")
            v.setObjectName("value_label")
            r.addWidget(v)
            summary_lay.addLayout(r)
            return v

        self._m: dict[str, QLabel] = {}
        self._m["total"]     = _row("total",   "Всего слов (рус.)")
        self._m["scored"]    = _row("scored",  "Тональных слов найдено")
        self._m["coverage"]  = _row("cov",     "Покрытие лексикона")
        self._m["pos_cnt"]   = _row("pos",     "Позитивных",   "Слов с позитивной коннотацией")
        self._m["neg_cnt"]   = _row("neg",     "Негативных",   "Слов с негативной коннотацией")
        self._m["neu_cnt"]   = _row("neu",     "Нейтральных")
        self._m["balance"]   = _row("bal",     "Баланс тональности",
            "+1.0 = полностью позитивный, -1.0 = полностью негативный")
        self._m["emot"]      = _row("emot",    "Эмоциональность",
            "Доля слов с явной тональностью (pos+neg) / total")
        summary_lay.addStretch()
        top_split.addWidget(summary_box)

        # Полоса баланса + распределение по PoS типу
        right_widget = QWidget()
        right_lay = QVBoxLayout(right_widget)
        right_lay.setContentsMargins(0, 0, 0, 0)

        balance_box = QGroupBox("Баланс тональности")
        balance_lay = QVBoxLayout(balance_box)
        balance_lay.setSpacing(4)

        row = QHBoxLayout()
        row.addWidget(QLabel("негат."))
        row.addStretch()
        row.addWidget(QLabel("позит."))
        balance_lay.addLayout(row)
        self._balance_bar = BalanceBar()
        balance_lay.addWidget(self._balance_bar)

        # Распределение по типу (факт / мнение / чувство)
        for key, label in [("fact","факт"), ("opinion","мнение"), ("feeling","чувство/эмоция")]:
            r2 = QHBoxLayout()
            lbl = QLabel(label + ":")
            lbl.setObjectName("caption")
            lbl.setFixedWidth(140)
            r2.addWidget(lbl)
            bar = QProgressBar()
            bar.setRange(0, 100)
            bar.setValue(0)
            bar.setFixedHeight(14)
            bar.setTextVisible(True)
            bar.setStyleSheet(
                "QProgressBar::chunk { background: #89dceb; border-radius: 2px; }"
                "QProgressBar { background: #313244; border-radius: 2px; font-size: 10px; }"
            )
            r2.addWidget(bar)
            setattr(self, f"_type_bar_{key}", bar)
            balance_lay.addLayout(r2)

        right_lay.addWidget(balance_box)
        right_lay.addStretch()
        top_split.addWidget(right_widget)
        top_split.setSizes([420, 320])
        root.addWidget(top_split)

        # ── Таблицы слов ───────────────────────────────────────────────
        self._word_tabs = QTabWidget()
        self._tbl_neg = SentiWordTable("negative")
        self._tbl_pos = SentiWordTable("positive")
        self._tbl_neu = SentiWordTable("neutral")
        self._word_tabs.addTab(self._tbl_neg, "😟 Негативные")
        self._word_tabs.addTab(self._tbl_pos, "😊 Позитивные")
        self._word_tabs.addTab(self._tbl_neu, "😐 Нейтральные")
        root.addWidget(self._word_tabs, stretch=1)
        return w

    # ── Загрузка ─────────────────────────────────────────────────────────

    def _auto_load(self):
        engine = get_engine()
        if engine.is_loaded:
            self._status_lbl.setText(f"✓ RuSentiLex: {engine.size:,} лемм")
            return
        self._load_thread = SentiLoadThread(self)
        self._load_thread.finished.connect(self._on_loaded)
        self._load_thread.start()

    def _on_loaded(self, ok: bool, msg: str):
        if ok:
            self._status_lbl.setText(f"✓ RuSentiLex: {msg}")
        else:
            self._status_lbl.setText(f"✗ {msg}")

    # ── Публичный API ────────────────────────────────────────────────────

    def show_result(self, result: SentiResult):
        self._result = result
        if result.is_empty:
            self._stack.setCurrentIndex(0)
            return
        self._fill(result)
        self._stack.setCurrentIndex(1)

    def clear(self):
        self._result = None
        self._stack.setCurrentIndex(0)

    # ── Заполнение ───────────────────────────────────────────────────────

    def _fill(self, r: SentiResult):
        meta = SENTIMENTS[r.dominant]
        self._dominant_lbl.setText(
            f"{meta['emoji']}  {meta['label']} тональность")
        self._dominant_lbl.setStyleSheet(
            f"font-size: 22px; font-weight: bold; color: {meta['color']};")

        self._m["total"].setText(f"{r.total_words:,}")
        self._m["scored"].setText(f"{r.scored_words:,}")
        self._m["coverage"].setText(f"{r.coverage_pct} %")
        self._m["pos_cnt"].setText(
            f"{r.positive_count}  ({round(r.positive_count/r.total_words*100,1) if r.total_words else 0} %)")
        self._m["neg_cnt"].setText(
            f"{r.negative_count}  ({round(r.negative_count/r.total_words*100,1) if r.total_words else 0} %)")
        self._m["neu_cnt"].setText(str(r.neutral_count))

        bal = r.balance
        sign = "+" if bal > 0 else ""
        self._m["balance"].setText(f"{sign}{bal:.3f}")
        bal_lbl = self._m["balance"]
        if bal > 0.1:
            bal_lbl.setStyleSheet("color: #a6e3a1;")
        elif bal < -0.1:
            bal_lbl.setStyleSheet("color: #f38ba8;")
        else:
            bal_lbl.setStyleSheet("")

        emot_pct = round(r.emotionality * 100, 1)
        self._m["emot"].setText(f"{emot_pct} %")

        # Баланс-полоска
        scored = r.scored_words or 1
        neg_pct = round(r.negative_count / scored * 100)
        pos_pct = round(r.positive_count / scored * 100)
        self._balance_bar.set_values(neg_pct, pos_pct)

        # Типы тональности
        all_typed = r.positive_words + r.negative_words + r.neutral_words
        type_counts = {"fact": 0, "opinion": 0, "feeling": 0}
        for w in all_typed:
            t = w.stype.lower()
            if t in type_counts:
                type_counts[t] += w.count
        type_total = sum(type_counts.values()) or 1
        for key, bar_attr in [("fact","_type_bar_fact"),
                               ("opinion","_type_bar_opinion"),
                               ("feeling","_type_bar_feeling")]:
            bar = getattr(self, bar_attr)
            pct = round(type_counts[key] / type_total * 100)
            bar.setValue(pct)
            bar.setFormat(f"{pct} %")

        # Заголовки вкладок с числами
        self._word_tabs.setTabText(
            0, f"😟 Негативные ({len(r.negative_words)})")
        self._word_tabs.setTabText(
            1, f"😊 Позитивные ({len(r.positive_words)})")
        self._word_tabs.setTabText(
            2, f"😐 Нейтральные ({len(r.neutral_words)})")

        self._tbl_neg.populate(r.negative_words)
        self._tbl_pos.populate(r.positive_words)
        self._tbl_neu.populate(r.neutral_words)
