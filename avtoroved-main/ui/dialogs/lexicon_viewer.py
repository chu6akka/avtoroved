"""
ui/dialogs/lexicon_viewer.py — Просмотр словарей тематик и пластов.

Позволяет видеть, какие слова включены в каждую тематическую область
и в каждый стилистический пласт. Поиск по словам.
"""
from __future__ import annotations

import json
import os
from typing import Dict, List

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget,
    QSplitter, QListWidget, QListWidgetItem, QLineEdit,
    QLabel, QTextEdit, QGroupBox, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView,
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QFont


class LexiconViewerDialog(QDialog):
    """Окно просмотра словарей тематик и пластов."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Справочник словарей")
        self.setMinimumSize(900, 620)
        self.resize(1050, 700)
        if parent:
            self.setStyleSheet(parent.styleSheet())

        self._thematic_data: Dict[str, List[str]] = {}
        self._strat_data: Dict[str, List[str]] = {}

        self._setup_ui()
        self._load_data()

    # ── Интерфейс ─────────────────────────────────────────────────────────

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        hdr = QLabel("Справочник: слова тематических доменов и стилистических пластов")
        hdr.setObjectName("subtitle")
        root.addWidget(hdr)

        self._tabs = QTabWidget()
        self._tabs.addTab(self._build_thematic_tab(), "🗂 Тематические домены")
        self._tabs.addTab(self._build_strat_tab(),    "🎨 Стилистические пласты")
        root.addWidget(self._tabs)

        close_btn = QPushButton("Закрыть")
        close_btn.setObjectName("secondary")
        close_btn.setFixedHeight(30)
        close_btn.clicked.connect(self.close)
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(close_btn)
        root.addLayout(row)

    # ── Вкладка тематик ───────────────────────────────────────────────────

    def _build_thematic_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(6)

        # Поиск
        search_row = QHBoxLayout()
        search_row.addWidget(QLabel("Поиск:"))
        self._t_search = QLineEdit()
        self._t_search.setPlaceholderText("введите слово для поиска по всем доменам…")
        self._t_search.textChanged.connect(self._on_thematic_search)
        search_row.addWidget(self._t_search)
        lay.addLayout(search_row)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Список доменов
        domain_box = QGroupBox("Домены")
        domain_box.setFixedWidth(230)
        domain_lay = QVBoxLayout(domain_box)
        domain_lay.setContentsMargins(4, 4, 4, 4)
        self._t_domain_list = QListWidget()
        self._t_domain_list.currentItemChanged.connect(self._on_thematic_domain_selected)
        domain_lay.addWidget(self._t_domain_list)
        splitter.addWidget(domain_box)

        # Слова выбранного домена
        words_box = QGroupBox("Слова домена")
        words_lay = QVBoxLayout(words_box)
        words_lay.setContentsMargins(4, 4, 4, 4)
        self._t_count_lbl = QLabel("")
        self._t_count_lbl.setObjectName("caption")
        words_lay.addWidget(self._t_count_lbl)
        self._t_word_table = QTableWidget(0, 2)
        self._t_word_table.setHorizontalHeaderLabels(["Слово", "Домен"])
        self._t_word_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch)
        self._t_word_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.ResizeToContents)
        self._t_word_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._t_word_table.verticalHeader().setVisible(False)
        self._t_word_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        words_lay.addWidget(self._t_word_table)
        splitter.addWidget(words_box)

        splitter.setSizes([230, 700])
        lay.addWidget(splitter)
        return w

    # ── Вкладка пластов ───────────────────────────────────────────────────

    def _build_strat_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(6)

        # Поиск
        search_row = QHBoxLayout()
        search_row.addWidget(QLabel("Поиск:"))
        self._s_search = QLineEdit()
        self._s_search.setPlaceholderText("введите слово для поиска по всем пластам…")
        self._s_search.textChanged.connect(self._on_strat_search)
        search_row.addWidget(self._s_search)
        lay.addLayout(search_row)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Список пластов
        layer_box = QGroupBox("Пласты")
        layer_box.setFixedWidth(230)
        layer_lay = QVBoxLayout(layer_box)
        layer_lay.setContentsMargins(4, 4, 4, 4)
        self._s_layer_list = QListWidget()
        self._s_layer_list.currentItemChanged.connect(self._on_strat_layer_selected)
        layer_lay.addWidget(self._s_layer_list)
        splitter.addWidget(layer_box)

        # Слова выбранного пласта
        words_box = QGroupBox("Слова пласта")
        words_lay = QVBoxLayout(words_box)
        words_lay.setContentsMargins(4, 4, 4, 4)
        self._s_count_lbl = QLabel("")
        self._s_count_lbl.setObjectName("caption")
        words_lay.addWidget(self._s_count_lbl)
        self._s_word_table = QTableWidget(0, 3)
        self._s_word_table.setHorizontalHeaderLabels(["Слово / форма", "Лемма", "Пласт"])
        self._s_word_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch)
        self._s_word_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.ResizeToContents)
        self._s_word_table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.ResizeToContents)
        self._s_word_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._s_word_table.verticalHeader().setVisible(False)
        self._s_word_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        words_lay.addWidget(self._s_word_table)
        splitter.addWidget(words_box)

        splitter.setSizes([230, 700])
        lay.addWidget(splitter)
        return w

    # ── Загрузка данных ───────────────────────────────────────────────────

    def _load_data(self):
        # Тематические словари
        from analyzer.thematic_engine import DOMAIN_META, _DATA_DIR
        for key, meta in DOMAIN_META.items():
            path = os.path.join(_DATA_DIR, f"{key}.json")
            if not os.path.exists(path):
                self._thematic_data[key] = []
                continue
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            self._thematic_data[key] = sorted(
                data if isinstance(data, list) else list(data.keys()))

        # Заполнить список доменов
        for key, meta in DOMAIN_META.items():
            words = self._thematic_data.get(key, [])
            item = QListWidgetItem(f"{meta['label']}  ({len(words)})")
            item.setData(Qt.ItemDataRole.UserRole, key)
            item.setForeground(QColor(meta["color"]))
            self._t_domain_list.addItem(item)
        if self._t_domain_list.count():
            self._t_domain_list.setCurrentRow(0)

        # Стратификация
        from analyzer.stratification_engine import get as get_strat, LAYER_META
        engine = get_strat()
        engine.load()

        # Сгруппировать леммы по слоям
        layer_words: Dict[str, List[str]] = {k: [] for k in LAYER_META}
        for lemma, layer in engine._lemma_to_layer.items():
            if layer in layer_words:
                layer_words[layer].append(lemma)
        # Добавить фразы
        for phrase, layer in engine._phrase_to_layer.items():
            if layer in layer_words:
                layer_words[layer].append(phrase)
        for key in layer_words:
            layer_words[key] = sorted(layer_words[key])
        self._strat_data = layer_words

        # Заполнить список пластов
        for key, meta in LAYER_META.items():
            if key == "literary_standard":
                continue
            words = layer_words.get(key, [])
            item = QListWidgetItem(f"{meta['label']}  ({len(words)})")
            item.setData(Qt.ItemDataRole.UserRole, key)
            item.setForeground(QColor(meta["color"]))
            self._s_layer_list.addItem(item)
        if self._s_layer_list.count():
            self._s_layer_list.setCurrentRow(0)

    # ── Обработчики тематик ───────────────────────────────────────────────

    def _on_thematic_domain_selected(self, current, _):
        if current is None:
            return
        from analyzer.thematic_engine import DOMAIN_META
        key = current.data(Qt.ItemDataRole.UserRole)
        words = self._thematic_data.get(key, [])
        meta = DOMAIN_META.get(key, {})
        self._fill_thematic_table(words, meta.get("label", key), meta.get("color", "#cdd6f4"))

    def _fill_thematic_table(self, words: List[str], domain_label: str, color: str):
        self._t_word_table.setRowCount(0)
        self._t_word_table.setRowCount(len(words))
        qcolor = QColor(color)
        for row, word in enumerate(words):
            w_item = QTableWidgetItem(word)
            w_item.setForeground(qcolor)
            w_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
            d_item = QTableWidgetItem(domain_label)
            d_item.setForeground(QColor("#6c7086"))
            d_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
            self._t_word_table.setItem(row, 0, w_item)
            self._t_word_table.setItem(row, 1, d_item)
        self._t_count_lbl.setText(f"Слов: {len(words)}")

    def _on_thematic_search(self, query: str):
        query = query.strip().lower()
        if not query:
            # Восстановить текущий домен
            self._on_thematic_domain_selected(
                self._t_domain_list.currentItem(), None)
            return
        from analyzer.thematic_engine import DOMAIN_META
        results = []
        for key, meta in DOMAIN_META.items():
            for word in self._thematic_data.get(key, []):
                if query in word.lower():
                    results.append((word, meta["label"], meta["color"]))
        results.sort(key=lambda x: x[0])
        self._t_word_table.setRowCount(0)
        self._t_word_table.setRowCount(len(results))
        for row, (word, label, color) in enumerate(results):
            w_item = QTableWidgetItem(word)
            w_item.setForeground(QColor(color))
            w_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
            d_item = QTableWidgetItem(label)
            d_item.setForeground(QColor("#6c7086"))
            d_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
            self._t_word_table.setItem(row, 0, w_item)
            self._t_word_table.setItem(row, 1, d_item)
        self._t_count_lbl.setText(
            f"Найдено: {len(results)} (запрос: «{query}»)")

    # ── Обработчики пластов ───────────────────────────────────────────────

    def _on_strat_layer_selected(self, current, _):
        if current is None:
            return
        from analyzer.stratification_engine import LAYER_META
        key = current.data(Qt.ItemDataRole.UserRole)
        words = self._strat_data.get(key, [])
        meta = LAYER_META.get(key, {})
        self._fill_strat_table(words, meta.get("label", key), meta.get("color", "#cdd6f4"))

    def _fill_strat_table(self, words: List[str], layer_label: str, color: str):
        self._s_word_table.setRowCount(0)
        self._s_word_table.setRowCount(len(words))
        qcolor = QColor(color)
        for row, word in enumerate(words):
            w_item = QTableWidgetItem(word)
            w_item.setForeground(qcolor)
            w_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
            # Для фраз отображать и оригинал, и лемму одинаково
            l_item = QTableWidgetItem(word)
            l_item.setForeground(QColor("#6c7086"))
            l_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
            ly_item = QTableWidgetItem(layer_label)
            ly_item.setForeground(QColor("#6c7086"))
            ly_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
            self._s_word_table.setItem(row, 0, w_item)
            self._s_word_table.setItem(row, 1, l_item)
            self._s_word_table.setItem(row, 2, ly_item)
        self._s_count_lbl.setText(f"Слов: {len(words)}")

    def _on_strat_search(self, query: str):
        query = query.strip().lower()
        if not query:
            self._on_strat_layer_selected(
                self._s_layer_list.currentItem(), None)
            return
        from analyzer.stratification_engine import LAYER_META
        results = []
        for key, words in self._strat_data.items():
            if key not in LAYER_META or key == "literary_standard":
                continue
            meta = LAYER_META[key]
            for word in words:
                if query in word.lower():
                    results.append((word, meta["label"], meta["color"]))
        results.sort(key=lambda x: x[0])
        self._s_word_table.setRowCount(0)
        self._s_word_table.setRowCount(len(results))
        for row, (word, label, color) in enumerate(results):
            w_item = QTableWidgetItem(word)
            w_item.setForeground(QColor(color))
            w_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
            l_item = QTableWidgetItem(word)
            l_item.setForeground(QColor("#6c7086"))
            l_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
            ly_item = QTableWidgetItem(label)
            ly_item.setForeground(QColor("#6c7086"))
            ly_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
            self._s_word_table.setItem(row, 0, w_item)
            self._s_word_table.setItem(row, 1, l_item)
            self._s_word_table.setItem(row, 2, ly_item)
        self._s_count_lbl.setText(
            f"Найдено: {len(results)} (запрос: «{query}»)")
