"""
ui/tabs/thematic_tab.py — Тематическая атрибуция текста.

Отображает результаты TF-IDF косинусного анализа тематической
принадлежности текста по 10 доменным словарям.

Методология:
  — Manning C.D., Raghavan P., Schütze H.
    «Introduction to Information Retrieval» (2008), гл. 6
  — Salton G. «A vector space model for automatic indexing» (1975)
"""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QTextEdit, QLabel, QProgressBar,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont

from analyzer.thematic_engine import DOMAIN_META, ThematicResult, DomainScore


class ThematicTab(QWidget):
    """Вкладка тематической атрибуции."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._result: ThematicResult | None = None
        self._setup_ui()

    # ── Интерфейс ─────────────────────────────────────────────────────────

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)

        # Заголовок
        hdr = QHBoxLayout()
        title = QLabel("Тематическая атрибуция")
        title.setObjectName("subtitle")
        hdr.addWidget(title)
        hdr.addStretch()
        self._lbl_summary = QLabel("")
        self._lbl_summary.setObjectName("caption")
        hdr.addWidget(self._lbl_summary)
        root.addLayout(hdr)

        method_lbl = QLabel(
            "Метод: TF-IDF + косинусное сходство с доменными центроидами "
            "(Manning et al., 2008) · 10 доменных словарей"
        )
        method_lbl.setObjectName("caption")
        method_lbl.setWordWrap(True)
        root.addWidget(method_lbl)

        # Топ-домены (выделены)
        self._top_box = QGroupBox("Основная тематическая принадлежность")
        top_lay = QVBoxLayout(self._top_box)
        top_lay.setSpacing(4)
        self._top_labels: list[QLabel] = []
        for _ in range(3):
            lbl = QLabel("")
            lbl.setWordWrap(True)
            lbl.setObjectName("caption")
            top_lay.addWidget(lbl)
            self._top_labels.append(lbl)
        root.addWidget(self._top_box)

        # Косинусные гистограммы по всем доменам
        bars_box = QGroupBox("Косинусное сходство по доменам")
        bars_lay = QVBoxLayout(bars_box)
        bars_lay.setSpacing(3)
        self._domain_bars: dict[str, tuple] = {}
        for key, meta in DOMAIN_META.items():
            row = QHBoxLayout()
            lbl = QLabel(meta["label"])
            lbl.setFixedWidth(230)
            lbl.setObjectName("caption")
            bar = QProgressBar()
            bar.setRange(0, 1000)
            bar.setValue(0)
            bar.setFixedHeight(14)
            bar.setTextVisible(False)
            bar.setStyleSheet(
                f"QProgressBar::chunk {{ background: {meta['color']}; border-radius: 2px; }}"
                "QProgressBar { border: 1px solid #313244; border-radius: 2px; "
                "background: #1e1e2e; }"
            )
            cos_lbl = QLabel("0.000")
            cos_lbl.setObjectName("caption")
            cos_lbl.setFixedWidth(48)
            cos_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            row.addWidget(lbl)
            row.addWidget(bar)
            row.addWidget(cos_lbl)
            bars_lay.addLayout(row)
            self._domain_bars[key] = (lbl, bar, cos_lbl)
        root.addWidget(bars_box)

        # Детальная таблица
        detail_box = QGroupBox("Детализация по доменам")
        detail_lay = QVBoxLayout(detail_box)
        detail_lay.setContentsMargins(4, 4, 4, 4)
        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(
            ["Домен", "Косинус", "Совпадений", "Примеры лексики"])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.verticalHeader().setVisible(False)
        detail_lay.addWidget(self._table)
        root.addWidget(detail_box, stretch=1)

        # Текстовый отчёт
        report_box = QGroupBox("Текстовый отчёт")
        report_lay = QVBoxLayout(report_box)
        report_lay.setContentsMargins(4, 4, 4, 4)
        self._report = QTextEdit()
        self._report.setReadOnly(True)
        self._report.setFont(QFont("Consolas", 9))
        self._report.setMaximumHeight(130)
        report_lay.addWidget(self._report)
        root.addWidget(report_box)

        self._show_placeholder()

    def _show_placeholder(self):
        self._report.setPlainText(
            "Выполните анализ текста, чтобы увидеть тематическую атрибуцию.\n\n"
            "Метод: TF-IDF + косинусное сходство.\n"
            "Словари: 10 тематических доменов (право, медицина, IT, экономика, "
            "военная, наука, религия, политика, спорт, быт)."
        )

    # ── Заполнение данными ────────────────────────────────────────────────

    def populate(self, result: ThematicResult) -> None:
        self._result = result
        self._fill_top(result)
        self._fill_bars(result)
        self._fill_table(result)
        self._fill_report(result)
        self._lbl_summary.setText(
            f"Слов: {result.total_words}  |  С тематической меткой: {result.matched_words}"
        )

    def _fill_top(self, result: ThematicResult) -> None:
        for i, lbl in enumerate(self._top_labels):
            if i < len(result.top_domains):
                s = result.top_domains[i]
                rank = ["★ Основная тема", "◆ Дополнительная тема", "◇ Сопутствующая тема"][i]
                lbl.setText(
                    f"<b style='color:{s.color};'>{rank}:</b> {s.label} "
                    f"&nbsp;|&nbsp; cos = {s.cosine:.4f} "
                    f"&nbsp;|&nbsp; слов: {s.match_count}"
                )
                lbl.setStyleSheet(f"color: {s.color};")
            else:
                lbl.setText("")
                lbl.setStyleSheet("")

    def _fill_bars(self, result: ThematicResult) -> None:
        max_cos = result.scores[0].cosine if result.scores else 1.0
        max_cos = max(max_cos, 1e-9)
        score_map = {s.key: s for s in result.scores}
        for key, (lbl, bar, cos_lbl) in self._domain_bars.items():
            s = score_map.get(key)
            if s is None:
                bar.setValue(0)
                cos_lbl.setText("0.000")
                continue
            pct = int(s.cosine / max_cos * 1000)
            bar.setValue(pct)
            cos_lbl.setText(f"{s.cosine:.4f}")

    def _fill_table(self, result: ThematicResult) -> None:
        self._table.setRowCount(0)
        self._table.setRowCount(len(result.scores))
        for row, s in enumerate(result.scores):
            color = QColor(s.color)
            items = [
                QTableWidgetItem(s.label),
                QTableWidgetItem(f"{s.cosine:.6f}"),
                QTableWidgetItem(str(s.match_count)),
                QTableWidgetItem(", ".join(s.examples[:6])),
            ]
            is_top = any(t.key == s.key for t in result.top_domains)
            for col, item in enumerate(items):
                item.setForeground(color)
                if is_top:
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)
                item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                self._table.setItem(row, col, item)

    def _fill_report(self, result: ThematicResult) -> None:
        lines = [
            "ТЕМАТИЧЕСКАЯ АТРИБУЦИЯ ТЕКСТА",
            "=" * 50,
            f"Метод: TF-IDF + косинусное сходство",
            f"Всего лемм в тексте: {result.total_words}",
            f"Лемм с тематической меткой: {result.matched_words}",
            "",
        ]
        if result.top_domains:
            lines.append("ВЫВОД:")
            for i, s in enumerate(result.top_domains):
                rank = ["Основная тема", "Дополнительная", "Сопутствующая"][i]
                lines.append(f"  {rank}: {s.label}")
                lines.append(f"    cos = {s.cosine:.6f} | слов: {s.match_count}")
                if s.examples:
                    lines.append(f"    Лексика: {', '.join(s.examples[:5])}")
            lines.append("")
        lines.append("ВСЕ ДОМЕНЫ (по убыванию сходства):")
        for s in result.scores:
            lines.append(
                f"  {s.label}: {s.cosine:.6f}  ({s.match_count} слов)"
            )
        self._report.setPlainText("\n".join(lines))
