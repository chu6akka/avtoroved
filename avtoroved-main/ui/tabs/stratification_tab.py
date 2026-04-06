"""
ui/tabs/stratification_tab.py — Лексическая стратификация.

Поддерживает экспертные аннотации: ПКМ по слову → пометить как ложное
срабатывание или подтвердить. Аннотации сохраняются в corpus.db и
применяются при отображении результатов. ML-фильтр применяется автоматически
при наличии обученной модели (strat_annotator).
"""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QGroupBox,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QTextEdit, QLabel, QPushButton, QProgressBar, QMenu,
)
from PyQt6.QtCore import Qt, QPoint
from PyQt6.QtGui import QColor, QFont

from analyzer.stratification_engine import LAYER_META, StratResult
from analyzer import corpus_manager
from analyzer import strat_annotator


class StratificationTab(QWidget):
    """Вкладка лексической стратификации с поддержкой экспертных аннотаций."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._result: StratResult | None = None
        self._text_hash: str = ""
        self._filtered_tokens: list = []
        self._base_summary: str = ""
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
        self._bars: dict[str, tuple] = {}
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
                "QProgressBar { border: 1px solid #3d4555; border-radius: 2px; "
                "background: #0d1117; }"
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
        tbl_box = QGroupBox("Маркированная лексика  (ПКМ = аннотация)")
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
        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._show_word_menu)
        tbl_lay.addWidget(self._table)
        splitter.addWidget(tbl_box)

        # Контекст выбранного слова
        ctx_box = QGroupBox("Контекст")
        ctx_lay = QVBoxLayout(ctx_box)
        ctx_lay.setContentsMargins(4, 4, 4, 4)
        self._ctx_text = QTextEdit()
        self._ctx_text.setReadOnly(True)
        self._ctx_text.setFont(QFont("Consolas", 10))
        self._ctx_text.setMinimumHeight(60)
        ctx_lay.addWidget(self._ctx_text, stretch=1)

        self._detail_lbl = QLabel("")
        self._detail_lbl.setWordWrap(True)
        self._detail_lbl.setObjectName("caption")
        ctx_lay.addWidget(self._detail_lbl)

        # Кнопки аннотации в правой панели
        ann_row = QHBoxLayout()
        self._btn_exclude = QPushButton("✗ Исключить")
        self._btn_exclude.setObjectName("danger")
        self._btn_exclude.setFixedHeight(28)
        self._btn_exclude.setEnabled(False)
        self._btn_exclude.setToolTip("Пометить как ложное срабатывание для этого текста")
        self._btn_exclude.clicked.connect(self._exclude_current)
        self._btn_confirm = QPushButton("✓ Подтвердить")
        self._btn_confirm.setObjectName("success")
        self._btn_confirm.setFixedHeight(28)
        self._btn_confirm.setEnabled(False)
        self._btn_confirm.setToolTip("Подтвердить как верное — учесть при обучении")
        self._btn_confirm.clicked.connect(self._confirm_current)
        self._btn_restore = QPushButton("↩ Снять пометку")
        self._btn_restore.setObjectName("secondary")
        self._btn_restore.setFixedHeight(28)
        self._btn_restore.setVisible(False)
        self._btn_restore.clicked.connect(self._restore_current)
        ann_row.addWidget(self._btn_exclude)
        ann_row.addWidget(self._btn_confirm)
        ann_row.addWidget(self._btn_restore)
        ctx_lay.addLayout(ann_row)
        splitter.addWidget(ctx_box)

        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 1)
        root.addWidget(splitter, stretch=1)

        # Полный текстовый отчёт
        report_box = QGroupBox("Текстовый отчёт")
        report_lay = QVBoxLayout(report_box)
        report_lay.setContentsMargins(4, 4, 4, 4)
        self._report = QTextEdit()
        self._report.setReadOnly(True)
        self._report.setFont(QFont("Consolas", 9))
        self._report.setMinimumHeight(80)
        self._report.setMaximumHeight(200)
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

    def populate(self, result: StratResult, text_hash: str = "") -> None:
        self._result = result
        self._text_hash = text_hash

        non_literary = sum(v for k, v in result.layer_counts.items()
                           if k != "literary_standard")
        pct = round(result.marked_ratio * 100, 1)
        self._base_summary = (
            f"Всего слов: {result.total_words}  |  "
            f"Маркировано: {non_literary} ({pct}%)"
        )

        self._refresh_display()

    def _refresh_display(self) -> None:
        """Применить аннотации и ML-фильтр, обновить все виджеты."""
        if self._result is None:
            return

        # 1. Исключения по аннотациям эксперта
        exclusions = (corpus_manager.get_strat_exclusions(self._text_hash)
                      if self._text_hash else set())

        # 2. ML-фильтр (если модель обучена)
        annotator = strat_annotator.get()

        filtered = []
        for tok in self._result.tokens:
            if (tok.lemma, tok.layer) in exclusions:
                continue
            if annotator.is_ready and annotator.is_false_positive(
                    tok.lemma, tok.context, tok.layer):
                continue
            filtered.append(tok)

        self._filtered_tokens = filtered

        # Счётчик исключений
        excl = len(self._result.tokens) - len(filtered)
        suffix = f"  ·  исключено: {excl}" if excl > 0 else ""
        self._lbl_summary.setText(self._base_summary + suffix)

        # Обновить таблицу
        self._fill_table(filtered)

        # Пересчитать количества по пластам из отфильтрованного списка
        layer_counts: dict[str, int] = {}
        for tok in filtered:
            layer_counts[tok.layer] = layer_counts.get(tok.layer, 0) + 1
        self._fill_bars(layer_counts)
        self._fill_report(filtered, layer_counts)

        # Обновить кнопки аннотации
        self._update_annotation_buttons()

    def _fill_table(self, tokens: list) -> None:
        self._table.setRowCount(0)
        self._table.setRowCount(len(tokens))
        for row, tok in enumerate(tokens):
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

    def _fill_bars(self, layer_counts: dict) -> None:
        non_literary = sum(layer_counts.values())
        for key, (lbl, bar, cnt_lbl) in self._bars.items():
            count = layer_counts.get(key, 0)
            pct = int(count / non_literary * 100) if non_literary > 0 else 0
            bar.setValue(pct)
            cnt_lbl.setText(str(count))

    def _fill_report(self, tokens: list, layer_counts: dict) -> None:
        lines = [
            "ЛЕКСИЧЕСКАЯ СТРАТИФИКАЦИЯ ТЕКСТА",
            "=" * 50,
            f"Всего слов: {self._result.total_words}",
            f"Нелитературная лексика: {len(tokens)} слов "
            f"({self._result.marked_ratio * 100:.1f}% до фильтрации)",
            "",
        ]
        sorted_layers = sorted(
            layer_counts.items(),
            key=lambda x: -LAYER_META.get(x[0], {}).get("priority", 0),
        )
        for layer_key, count in sorted_layers:
            if count == 0:
                continue
            meta = LAYER_META.get(layer_key, {})
            words = list({tok.lemma for tok in tokens if tok.layer == layer_key})
            lines.append(f"{meta.get('label', layer_key).upper()}: {count}")
            if words:
                lines.append(f"  Слова: {', '.join(words[:12])}" +
                             ("…" if len(words) > 12 else ""))
        excl = len(self._result.tokens) - len(tokens)
        if excl > 0:
            lines.append("")
            lines.append(f"[Исключено аннотациями/ML: {excl} слов]")
        self._report.setPlainText("\n".join(lines))

    # ── Аннотации: контекстное меню ───────────────────────────────────────

    def _show_word_menu(self, pos: QPoint) -> None:
        row = self._table.rowAt(pos.y())
        if row < 0 or row >= len(self._filtered_tokens) or not self._text_hash:
            return
        tok = self._filtered_tokens[row]
        verdict = corpus_manager.get_strat_annotation_verdict(
            self._text_hash, tok.lemma, tok.layer)
        meta = LAYER_META.get(tok.layer, {})
        layer_label = meta.get("label", tok.layer)

        menu = QMenu(self)

        title = menu.addAction(f"«{tok.surface}» → {layer_label}")
        title.setEnabled(False)
        menu.addSeparator()

        if verdict == "exclude":
            excl_info = menu.addAction("✗ Помечено как ложное срабатывание")
            excl_info.setEnabled(False)
            restore_a = menu.addAction("↩ Снять пометку (восстановить)")
            restore_a.triggered.connect(lambda: self._restore_word(tok))
        elif verdict == "confirm":
            conf_info = menu.addAction("✓ Подтверждено как верное")
            conf_info.setEnabled(False)
            restore_a = menu.addAction("↩ Снять пометку")
            restore_a.triggered.connect(lambda: self._restore_word(tok))
        else:
            excl_a = menu.addAction("✗ Ложное срабатывание — исключить из текста")
            excl_a.triggered.connect(lambda: self._exclude_word(tok))
            conf_a = menu.addAction("✓ Подтвердить как верное (обучающий пример)")
            conf_a.triggered.connect(lambda: self._confirm_word(tok))

        menu.exec(self._table.viewport().mapToGlobal(pos))

    def _exclude_word(self, tok) -> None:
        if not self._text_hash:
            return
        corpus_manager.save_strat_annotation(
            text_hash=self._text_hash, lemma=tok.lemma, surface=tok.surface,
            layer=tok.layer, verdict="exclude",
            context=tok.context, position=tok.start,
        )
        self._refresh_display()

    def _confirm_word(self, tok) -> None:
        if not self._text_hash:
            return
        corpus_manager.save_strat_annotation(
            text_hash=self._text_hash, lemma=tok.lemma, surface=tok.surface,
            layer=tok.layer, verdict="confirm",
            context=tok.context, position=tok.start,
        )

    def _restore_word(self, tok) -> None:
        if not self._text_hash:
            return
        corpus_manager.remove_strat_annotation(self._text_hash, tok.lemma, tok.layer)
        self._refresh_display()

    # ── Кнопки аннотации (правая панель) ─────────────────────────────────

    def _exclude_current(self) -> None:
        row = self._table.currentRow()
        if 0 <= row < len(self._filtered_tokens):
            self._exclude_word(self._filtered_tokens[row])

    def _confirm_current(self) -> None:
        row = self._table.currentRow()
        if 0 <= row < len(self._filtered_tokens):
            self._confirm_word(self._filtered_tokens[row])

    def _restore_current(self) -> None:
        row = self._table.currentRow()
        if 0 <= row < len(self._filtered_tokens):
            self._restore_word(self._filtered_tokens[row])

    def _update_annotation_buttons(self) -> None:
        row = self._table.currentRow()
        has_row = 0 <= row < len(self._filtered_tokens)
        has_hash = bool(self._text_hash)
        self._btn_exclude.setEnabled(has_row and has_hash)
        self._btn_confirm.setEnabled(has_row and has_hash)
        self._btn_restore.setVisible(False)

    # ── Контекст при выборе строки ────────────────────────────────────────

    def _on_row_changed(self, row: int) -> None:
        if self._result is None or row < 0 or row >= len(self._filtered_tokens):
            self._ctx_text.clear()
            self._detail_lbl.clear()
            self._btn_exclude.setEnabled(False)
            self._btn_confirm.setEnabled(False)
            self._btn_restore.setVisible(False)
            return

        tok = self._filtered_tokens[row]
        meta = LAYER_META.get(tok.layer, {})
        self._ctx_text.setPlainText(tok.context)
        self._detail_lbl.setText(
            f"«{tok.surface}» (лемма: {tok.lemma})  ·  "
            f"Пласт: {meta.get('label', tok.layer)}  ·  "
            f"Описание: {meta.get('desc', '')}"
        )

        # Состояние кнопок аннотации
        has_hash = bool(self._text_hash)
        verdict = (corpus_manager.get_strat_annotation_verdict(
            self._text_hash, tok.lemma, tok.layer) if has_hash else None)
        if verdict:
            self._btn_exclude.setEnabled(False)
            self._btn_confirm.setEnabled(False)
            self._btn_restore.setVisible(True)
            self._btn_restore.setText(
                f"↩ Снять пометку  ({'исключено' if verdict == 'exclude' else 'подтверждено'})"
            )
        else:
            self._btn_exclude.setEnabled(has_hash)
            self._btn_confirm.setEnabled(has_hash)
            self._btn_restore.setVisible(False)
