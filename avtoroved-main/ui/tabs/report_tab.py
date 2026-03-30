"""
Вкладка 10: Сводный отчёт с экспортом в DOCX.
"""
from __future__ import annotations
import re
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QTextEdit, QLabel, QFileDialog, QMessageBox
)
from PyQt6.QtCore import pyqtSignal
from analyzer.stratification_engine import LAYER_META


class ReportTab(QWidget):
    """Сводный отчёт и экспорт в DOCX."""

    export_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        btn_row = QHBoxLayout()
        self.btn_export = QPushButton("📄 Экспорт отчёта в DOCX")
        self.btn_export.clicked.connect(self.export_requested)
        btn_row.addWidget(self.btn_export)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self.report_text = QTextEdit()
        self.report_text.setReadOnly(True)
        layout.addWidget(self.report_text)

    def generate_report(self, text: str, metrics: dict, error_result,
                        strat_result=None, thematic_result=None):
        """Сформировать текстовый сводный отчёт."""
        lines = ["=" * 70, "СВОДНЫЙ ОТЧЁТ АВТОРОВЕДЧЕСКОГО АНАЛИЗА", "=" * 70, ""]

        words_l = re.findall(r"[А-Яа-яЁё]+", text)
        first_w = " ".join(words_l[:5]) + "..." if len(words_l) > 5 else " ".join(words_l)
        last_w = "..." + " ".join(words_l[-5:]) if len(words_l) > 5 else ""
        lines.append("1. ОПИСАНИЕ РЕЧЕВОГО ПРОДУКТА")
        lines.append(f"   Начало: «{first_w}»")
        if last_w:
            lines.append(f"   Конец: «{last_w}»")
        lines.append(f"   Объём: {metrics['дополнительно']['Всего слов']} слов")

        lines.append("\n2. КОЛИЧЕСТВЕННЫЕ ХАРАКТЕРИСТИКИ")
        for k, v in metrics["дополнительно"].items():
            lines.append(f"   {k}: {v}")

        pos_bg = metrics.get("pos_bigrams", {})
        top_bg = pos_bg.get("top_bigrams", [])
        if top_bg:
            lines.append("\n2.1. ЧАСТЕРЕЧНЫЕ БИГРАММЫ (топ-10)")
            for i, bg in enumerate(top_bg[:10], 1):
                lines.append(f"   {i}. {bg['pair_full']}: {bg['count']} ({bg['freq']:.4f})")

        if error_result:
            lines.append("\n3. СТЕПЕНИ РАЗВИТИЯ НАВЫКОВ (по С.М. Вул)")
            for s in error_result.skill_levels:
                lines.append(f"   {s.skill_name}: {s.level.upper()} ({s.description})")
            lines.append(f"\n4. ОШИБКИ: {len(error_result.errors)}")
            by_type = {}
            for e in error_result.errors:
                by_type.setdefault(e.error_type, []).append(e)
            for et, errs in by_type.items():
                lines.append(f"   {et}: {len(errs)}")
                for i, e in enumerate(errs[:5], 1):
                    ref = f" [{e.rule_ref}]" if e.rule_ref else ""
                    lines.append(f"     {i}. «{e.fragment}» — {e.description}{ref}")

        if strat_result:
            lines.append("\n5. ЛЕКСИЧЕСКАЯ СТРАТИФИКАЦИЯ (ЭКЦ МВД России)")
            lines.append(f"   Маркированных единиц: {strat_result.marked_words} из {strat_result.total_words} слов")
            for layer, meta in LAYER_META.items():
                if layer == "literary_standard":
                    continue
                cnt = strat_result.layer_counts.get(layer, 0)
                if cnt == 0:
                    continue
                ratio = strat_result.layer_ratios.get(layer, 0.0)
                lines.append(f"   {meta['label']}: {cnt} ({ratio:.1%})")

        if thematic_result and thematic_result.top_domains:
            lines.append("\n6. ТЕМАТИЧЕСКАЯ АТРИБУЦИЯ")
            for domain in thematic_result.top_domains:
                data = thematic_result.domains.get(domain, {})
                lines.append(f"   {data.get('label', domain)}: "
                              f"{data.get('count', 0)} слов "
                              f"(k={data.get('density', 0):.2f} на 1000)")

        wc = metrics["дополнительно"]["Всего слов"]
        lines.append("\n7. ВЫВОД")
        if wc >= 500:
            lines.append("   Текст ПРИГОДЕН для судебной автороведческой экспертизы.")
        elif wc >= 200:
            lines.append("   Текст пригоден для предварительного анализа.")
        else:
            lines.append("   Текст НЕДОСТАТОЧЕН для экспертизы (мин. 500 слов).")

        self.report_text.setPlainText("\n".join(lines))

    def clear(self):
        self.report_text.clear()
