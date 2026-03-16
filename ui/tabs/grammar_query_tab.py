"""
Вкладка 9: Менеджер грамматических запросов.
Поиск произвольных грамматических конструкций в тексте.
"""
from __future__ import annotations
import re
from typing import List, Optional
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QLabel, QLineEdit, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QTextEdit,
    QMessageBox, QComboBox
)
from PyQt6.QtCore import Qt

from analyzer.stanza_backend import TokenInfo, UPOS_RU, WORD_RE


EXAMPLES = [
    ("NOUN ADJ", "Существительное + Прилагательное"),
    ("VERB NOUN", "Глагол + Существительное"),
    ("ADV VERB", "Наречие + Глагол"),
    ("ADJ NOUN NOUN", "Прил. + Сущ. + Сущ. (цепочка)"),
    ("VERB VERB", "Глагол + Глагол (сложные формы)"),
    ("PART VERB", "Частица + Глагол"),
    ("ADP NOUN", "Предлог + Существительное"),
    ("NUM NOUN", "Числительное + Существительное"),
]

# Маппинг сокращений к UPOS
ALIAS_MAP = {
    "СУЩ": "NOUN", "ИМЯ": "PROPN", "ГЛ": "VERB", "ВСПГЛ": "AUX",
    "ПРИЛ": "ADJ", "НАР": "ADV", "МЕСТ": "PRON", "ЧИСЛ": "NUM",
    "ОПР": "DET", "ПРЕДЛ": "ADP", "ЧАСТ": "PART", "ССОЮЗ": "CCONJ",
    "ПСОЮЗ": "SCONJ", "МЕЖД": "INTJ", "ПУНКТ": "PUNCT",
    # Русские названия
    "СУЩЕСТВИТЕЛЬНОЕ": "NOUN", "ИМЯ СОБСТВЕННОЕ": "PROPN", "ГЛАГОЛ": "VERB",
    "ПРИЛАГАТЕЛЬНОЕ": "ADJ", "НАРЕЧИЕ": "ADV", "МЕСТОИМЕНИЕ": "PRON",
    "ЧИСЛИТЕЛЬНОЕ": "NUM", "ПРЕДЛОГ": "ADP", "ЧАСТИЦА": "PART",
    "СОЮЗ": "CCONJ",
}


def _normalize_tag(tag: str) -> Optional[str]:
    """Привести тег к UPOS."""
    upper = tag.upper().strip()
    if upper in UPOS_RU:
        return upper
    if upper in ALIAS_MAP:
        return ALIAS_MAP[upper]
    # Поиск по русскому названию
    for upos, name in UPOS_RU.items():
        if name.upper() == upper:
            return upos
    return None


def _parse_pattern(pattern_str: str) -> Optional[List[Optional[str]]]:
    """
    Разобрать паттерн вида "NOUN ADJ" или "VERB * NOUN".
    * — любой токен.
    Возвращает список UPOS-тегов или None для wildcard.
    """
    parts = pattern_str.strip().split()
    if not parts:
        return None
    result = []
    for p in parts:
        if p == "*":
            result.append(None)  # wildcard
        else:
            upos = _normalize_tag(p)
            if upos is None:
                return None  # неизвестный тег
            result.append(upos)
    return result


def _search_pattern(tokens: List[TokenInfo], pattern: List[Optional[str]],
                    context_size: int = 5) -> List[dict]:
    """Найти все вхождения паттерна в токенах."""
    words = [t for t in tokens if WORD_RE.search(t.text)]
    n = len(pattern)
    results = []
    for i in range(len(words) - n + 1):
        match = True
        for j, tag in enumerate(pattern):
            if tag is None:
                continue  # wildcard
            if words[i + j].pos != tag:
                match = False
                break
        if match:
            fragment = " ".join(w.text for w in words[i:i + n])
            ctx_start = max(0, i - context_size)
            ctx_end = min(len(words), i + n + context_size)
            context = " ".join(w.text for w in words[ctx_start:ctx_end])
            pos_sequence = " → ".join(
                f"{UPOS_RU.get(words[i + j].pos, words[i + j].pos)} ({words[i + j].text})"
                for j in range(n)
            )
            results.append({
                "position": i,
                "fragment": fragment,
                "pos_sequence": pos_sequence,
                "context": context,
            })
    return results


class GrammarQueryTab(QWidget):
    """Менеджер грамматических запросов (аналог Lingster 3.0)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tokens: List[TokenInfo] = []
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        lbl = QLabel(
            "Поиск грамматических конструкций по POS-шаблонам. "
            "Используйте английские UPOS-теги (NOUN, VERB, ADJ, ADV, ADP...) "
            "или звёздочку (*) как wildcard."
        )
        lbl.setWordWrap(True)
        lbl.setObjectName("subtitle")
        layout.addWidget(lbl)

        # Строка запроса
        query_group = QGroupBox("Запрос")
        query_layout = QVBoxLayout(query_group)

        input_row = QHBoxLayout()
        self.query_input = QLineEdit()
        self.query_input.setPlaceholderText("Например: NOUN ADJ   или   VERB NOUN   или   ADP * NOUN")
        self.query_input.returnPressed.connect(self._run_search)
        input_row.addWidget(self.query_input)
        self.btn_search = QPushButton("🔍 Найти")
        self.btn_search.clicked.connect(self._run_search)
        input_row.addWidget(self.btn_search)
        query_layout.addLayout(input_row)

        # Примеры
        examples_row = QHBoxLayout()
        examples_row.addWidget(QLabel("Примеры:"))
        self.examples_combo = QComboBox()
        for pattern, desc in EXAMPLES:
            self.examples_combo.addItem(f"{pattern}  —  {desc}", pattern)
        self.examples_combo.setCurrentIndex(-1)
        self.examples_combo.setPlaceholderText("Выбрать пример...")
        self.examples_combo.currentIndexChanged.connect(self._load_example)
        examples_row.addWidget(self.examples_combo)
        examples_row.addStretch()
        query_layout.addLayout(examples_row)

        # Доступные теги
        tags_info = QLabel(
            "Теги: NOUN СУЩ | PROPN ИМЯ | VERB ГЛ | AUX ВСПГЛ | ADJ ПРИЛ | ADV НАР | "
            "PRON МЕСТ | NUM ЧИСЛ | DET ОПР | ADP ПРЕДЛ | PART ЧАСТ | CCONJ ССОЮЗ | SCONJ ПСОЮЗ")
        tags_info.setWordWrap(True)
        tags_info.setObjectName("subtitle")
        query_layout.addWidget(tags_info)
        layout.addWidget(query_group)

        # Результаты
        result_group = QGroupBox("Результаты поиска")
        result_layout = QVBoxLayout(result_group)

        self.result_table = QTableWidget()
        self.result_table.setColumnCount(4)
        self.result_table.setHorizontalHeaderLabels(
            ["№", "Фрагмент", "Структура", "Контекст"])
        header = self.result_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.result_table.setAlternatingRowColors(True)
        self.result_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.result_table.verticalHeader().setVisible(False)
        result_layout.addWidget(self.result_table)

        self.count_label = QLabel("Найдено: 0")
        self.count_label.setObjectName("subtitle")
        result_layout.addWidget(self.count_label)
        layout.addWidget(result_group)

    def set_tokens(self, tokens: List[TokenInfo]):
        """Загрузить токены после анализа текста."""
        self._tokens = tokens
        self.result_table.setRowCount(0)
        n = len([t for t in tokens if WORD_RE.search(t.text)])
        self.count_label.setText(f"Загружено токенов: {n} (введите запрос и нажмите «Найти»)")

    def _load_example(self, index: int):
        if index >= 0:
            pattern = self.examples_combo.itemData(index)
            if pattern:
                self.query_input.setText(pattern)

    def _run_search(self):
        query = self.query_input.text().strip()
        if not query:
            return

        if not self._tokens:
            QMessageBox.warning(
                self, "Нет данных",
                "Сначала выполните анализ текста во вкладке основного ввода.")
            return

        pattern = _parse_pattern(query)
        if pattern is None:
            QMessageBox.warning(
                self, "Неизвестный тег",
                f"Не удалось распознать все теги в запросе «{query}».\n"
                "Используйте UPOS-теги: NOUN, VERB, ADJ, ADV, ADP, PRON, NUM, DET, "
                "PART, CCONJ, SCONJ, AUX, INTJ или * для wildcard.")
            return

        results = _search_pattern(self._tokens, pattern)
        self.result_table.setRowCount(len(results))
        for i, r in enumerate(results):
            vals = [str(i + 1), r["fragment"], r["pos_sequence"], r["context"]]
            for col, val in enumerate(vals):
                item = QTableWidgetItem(val)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.result_table.setItem(i, col, item)

        self.count_label.setText(
            f"Найдено вхождений: {len(results)} по шаблону «{query}»")

    def clear(self):
        self._tokens = []
        self.result_table.setRowCount(0)
        self.count_label.setText("Найдено: 0")
