"""
ui/tabs/stratification_tab.py — Лексическая стратификация.

Отображает распределение лексики текста по стилистическим пластам,
основанное на точном морфологическом анализе через pymorphy3.

Методология:
  — Виноградов В.В. «Русский язык» (1947)
  — Химик В.В. «Поэтика сниженной речи» (2000)
  — Ожегов С.И. «Словарь русского языка»
"""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QGroupBox,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QTextEdit, QLabel, QPushButton, QProgressBar,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont

from analyzer.stratification_engine import LAYER_META, StratResult


class StratificationTab(QWidget):
    """Вкладка лексической стратификации."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._result: StratResult | None = None
        self._setup_ui()

    # ── Интерфейс ─────────────────────────────────────────────────────────

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)

        # Заголовок и описание методологии
        hdr = QHBoxLayout()
        title = QLabel("Лексическая стратификация")
        title.setObjectName("subtitle")
        hdr.addWidget(title)
        hdr.addStretch()
        self._lbl_summary = QLabel("")
        self._lbl_summary.setObjectName("caption")
        hdr.addWidget(self._lbl_summary)
        root.addLayout(hdr)

        method_lbl = QLabel(
            "Методология: Виноградов В.В. (1947), Химик В.В. (2000), Ожегов С.И. "
            "· Лемматизация: pymorphy3"
        )
        method_lbl.setObjectName("caption")
        method_lbl.setWordWrap(True)
        root.addWidget(method_lbl)

        # Прогрессбар по пластам
        self._bar_group = QGroupBox("Соотношение пластов (% от нелитературной лексики)")
        bar_layout = QVBoxLayout(self._bar_group)
        bar_layout.setSpacing(4)
        self._bars: dict[str, tuple] = {}  # layer → (QLabel, QProgressBar, QLabel)
        for key, meta in LAYER_META.items():
            if key == "literary_standard":
                continue
            row = QHBoxLayout()
            lbl = QLabel(meta["label"])
            lbl.setFixedWidth(200)
            lbl.setObjectName("caption")
            bar = QProgressBar()
            bar.setRange(0, 100)
            bar.setValue(0)
            bar.setFixedHeight(14)
            bar.setTextVisible(False)
            bar.setStyleSheet(
                f"QProgressBar::chunk {{ background: {meta['color']}; border-radius: 2px; }}"
                "QProgressBar { border: 1px solid #313244; border-radius: 2px; "
                "background: #1e1e2e; }"
            )
            cnt_lbl = QLabel("0")
            cnt_lbl.setObjectName("caption")
            cnt_lbl.setFixedWidth(40)
            cnt_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            row.addWidget(lbl)
            row.addWidget(bar)
            row.addWidget(cnt_lbl)
            bar_layout.addLayout(row)
            self._bars[key] = (lbl, bar, cnt_lbl)
        root.addWidget(self._bar_group)

        # Сплиттер: таблица слов | контекст
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Таблица найденных слов
        tbl_box = QGroupBox("Маркированная лексика")
        tbl_lay = QVBoxLayout(tbl_box)
        tbl_lay.setContentsMargins(4, 4, 4, 4)
        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(["Слово", "Лемма", "Пласт", "Позиция"])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.verticalHeader().setVisible(False)
        self._table.currentItemChanged.connect(
            lambda cur, _: self._on_row_changed(self._table.currentRow()))
        tbl_lay.addWidget(self._table)
        splitter.addWidget(tbl_box)

        # Контекст выбранного слова
        ctx_box = QGroupBox("Контекст")
        ctx_lay = QVBoxLayout(ctx_box)
        ctx_lay.setContentsMargins(4, 4, 4, 4)
        self._ctx_text = QTextEdit()
        self._ctx_text.setReadOnly(True)
        self._ctx_text.setFont(QFont("Consolas", 10))
        self._ctx_text.setMaximumHeight(120)
        ctx_lay.addWidget(self._ctx_text)

        # Детали слова
        self._detail_lbl = QLabel("")
        self._detail_lbl.setWordWrap(True)
        self._detail_lbl.setObjectName("caption")
        ctx_lay.addWidget(self._detail_lbl)
        ctx_lay.addStretch()
        splitter.addWidget(ctx_box)

        splitter.setSizes([500, 300])
        root.addWidget(splitter, stretch=1)

        # Полный текстовый отчёт
        report_box = QGroupBox("Текстовый отчёт")
        report_lay = QVBoxLayout(report_box)
        report_lay.setContentsMargins(4, 4, 4, 4)
        self._report = QTextEdit()
        self._report.setReadOnly(True)
        self._report.setFont(QFont("Consolas", 9))
        self._report.setMaximumHeight(150)
        report_lay.addWidget(self._report)
        root.addWidget(report_box)

        self._show_placeholder()

    def _show_placeholder(self):
        self._report.setPlainText(
            "Выполните анализ текста, чтобы увидеть распределение по стилистическим пластам.\n\n"
            "Анализатор использует pymorphy3 для точной лемматизации каждого слова,\n"
            "затем ищет леммы в словаре из ~9000 единиц с приоритизацией пластов."
        )

    # ── Заполнение данными ────────────────────────────────────────────────

    def populate(self, result: StratResult) -> None:
        self._result = result
        self._fill_table(result)
        self._fill_bars(result)
        self._fill_report(result)

        non_literary = sum(v for k, v in result.layer_counts.items() if k != "literary_standard")
        pct = round(result.marked_ratio * 100, 1)
        self._lbl_summary.setText(
            f"Всего слов: {result.total_words}  |  Маркировано: {non_literary} ({pct}%)"
        )

    def _fill_table(self, result: StratResult) -> None:
        self._table.setRowCount(0)
        self._table.setRowCount(len(result.tokens))
        for row, tok in enumerate(result.tokens):
            meta = LAYER_META.get(tok.layer, {})
            color = QColor(meta.get("color", "#cdd6f4"))
            label = meta.get("label", tok.layer)

            items = [
                QTableWidgetItem(tok.surface),
                QTableWidgetItem(tok.lemma),
                QTableWidgetItem(label),
                QTableWidgetItem(f"{tok.start}–{tok.end}"),
            ]
            for col, item in enumerate(items):
                item.setForeground(color)
                item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                self._table.setItem(row, col, item)

        self._table.resizeRowsToContents()

    def _fill_bars(self, result: StratResult) -> None:
        non_literary = sum(v for k, v in result.layer_counts.items() if k != "literary_standard")
        for key, (lbl, bar, cnt_lbl) in self._bars.items():
            count = result.layer_counts.get(key, 0)
            pct = int(count / non_literary * 100) if non_literary > 0 else 0
            bar.setValue(pct)
            cnt_lbl.setText(str(count))

    def _fill_report(self, result: StratResult) -> None:
        lines = [
            "ЛЕКСИЧЕСКАЯ СТРАТИФИКАЦИЯ ТЕКСТА",
            "=" * 50,
            f"Всего слов: {result.total_words}",
            f"Нелитературная лексика: {len(result.tokens)} слов "
            f"({result.marked_ratio * 100:.1f}%)",
            "",
        ]
        sorted_layers = sorted(
            result.layer_counts.items(),
            key=lambda x: -LAYER_META.get(x[0], {}).get("priority", 0),
        )
        for layer_key, count in sorted_layers:
            if count == 0:
                continue
            meta = LAYER_META.get(layer_key, {})
            words = result.layer_words.get(layer_key, [])
            lines.append(f"{meta.get('label', layer_key).upper()}: {count}")
            if words:
                lines.append(f"  Слова: {', '.join(words[:12])}" +
                              ("…" if len(words) > 12 else ""))
        self._report.setPlainText("\n".join(lines))

    # ── Контекст ──────────────────────────────────────────────────────────

    def _on_row_changed(self, row: int) -> None:
        if self._result is None or row < 0 or row >= len(self._result.tokens):
            self._ctx_text.clear()
            self._detail_lbl.clear()
            return
        tok = self._result.tokens[row]
        meta = LAYER_META.get(tok.layer, {})
        self._ctx_text.setPlainText(tok.context)
        self._detail_lbl.setText(
            f"«{tok.surface}» (лемма: {tok.lemma})  ·  "
            f"Пласт: {meta.get('label', tok.layer)}  ·  "
            f"Описание: {meta.get('desc', '')}"
        )
