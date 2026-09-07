"""Сравнительное исследование: два текста, evidence и решение эксперта."""
from __future__ import annotations

from html import escape

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPen, QTextCharFormat, QTextCursor
from PyQt6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout,
    QHeaderView, QLabel, QMessageBox, QPushButton, QSplitter, QTableWidget,
    QTableWidgetItem, QTabWidget, QTextBrowser, QTextEdit, QVBoxLayout, QWidget,
)

from protocol import PROGRAM_VERSION
from protocol import comparison as cmp_mod
from protocol import comparison_view as view_mod
from protocol import db as protocol_db


_RELATION_LABELS = {
    view_mod.COINCIDENCE: "совпадение", view_mod.DIFFERENCE: "различие",
    view_mod.PRESENT_ONLY_TEXT1: "только текст 1",
    view_mod.PRESENT_ONLY_TEXT2: "только текст 2",
    view_mod.AUXILIARY: "вспомогательный показатель",
}
_ROLE_LABELS = {
    view_mod.METHOD_FEATURE: "METHOD", view_mod.AUX_METRIC: "AUX",
    view_mod.EVIDENCE: "EVIDENCE", view_mod.GENERAL_SKILL: "GENERAL_SKILL",
}
_INFO_LABELS = {
    view_mod.INFO_HIGH: "высокая", view_mod.INFO_MEDIUM: "средняя",
    view_mod.INFO_LOW: "низкая",
    view_mod.INFO_NOT_SPECIFIED: "не задана источником",
}
_VALUE_LABELS = {
    view_mod.VALUE_HIGH: "высокая", view_mod.VALUE_MEDIUM: "средняя",
    view_mod.VALUE_LOW: "низкая", view_mod.VALUE_NOT_SET: "не задана",
}
_STATUS_LABELS = {
    view_mod.ACCEPTED: "принято", view_mod.REJECTED: "отклонено",
    view_mod.NOT_REVIEWED: "не просмотрено",
}
_ROW_COLORS = {
    view_mod.COINCIDENCE: "#dcefe2", view_mod.DIFFERENCE: "#f4dddd",
    view_mod.PRESENT_ONLY_TEXT1: "#f3e7cd",
    view_mod.PRESENT_ONLY_TEXT2: "#f3e7cd", view_mod.AUXILIARY: "#dce6ef",
}


class EvidenceTextPane(QWidget):
    """Исходный текст с точными evidence spans и локальной навигацией."""

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self._spans: list[view_mod.EvidenceSpan] = []
        self._index = -1
        layout = QVBoxLayout(self); layout.setContentsMargins(0, 0, 0, 0)
        header = QHBoxLayout()
        self.title = QLabel(title); self.title.setStyleSheet("font-weight:600")
        header.addWidget(self.title); header.addStretch()
        self.prev_btn = QPushButton("‹"); self.next_btn = QPushButton("›")
        self.counter = QLabel("нет evidence")
        self.prev_btn.clicked.connect(lambda: self.move(-1))
        self.next_btn.clicked.connect(lambda: self.move(1))
        header.addWidget(self.prev_btn); header.addWidget(self.counter)
        header.addWidget(self.next_btn); layout.addLayout(header)
        self.editor = QTextEdit(); self.editor.setReadOnly(True)
        self.editor.setAcceptRichText(False)
        self.editor.setStyleSheet(
            "QTextEdit{font-family:'Arial';font-size:13px;padding:10px}")
        layout.addWidget(self.editor); self._update_navigation()

    def set_document(self, title: str, text: str) -> None:
        self.title.setText(title); self.editor.setPlainText(text); self.set_spans([])

    def set_spans(self, spans: list[view_mod.EvidenceSpan]) -> None:
        self._spans = list(spans); self._index = 0 if spans else -1; self._render()

    def move(self, delta: int) -> None:
        if self._spans:
            self._index = (self._index + delta) % len(self._spans); self._render()

    def _render(self) -> None:
        selections = []
        for index, span in enumerate(self._spans):
            selection = QTextEdit.ExtraSelection(); cursor = self.editor.textCursor()
            cursor.setPosition(span.start)
            cursor.setPosition(span.end, QTextCursor.MoveMode.KeepAnchor)
            selection.cursor = cursor; fmt = QTextCharFormat()
            fmt.setBackground(QColor("#ffd166" if index == self._index else "#f5e7a6"))
            if index == self._index:
                fmt.setTextOutline(QPen(QColor("#8a5a00"), 0.7))
            selection.format = fmt; selections.append(selection)
        self.editor.setExtraSelections(selections)
        if self._index >= 0:
            cursor = self.editor.textCursor(); cursor.setPosition(self._spans[self._index].start)
            self.editor.setTextCursor(cursor); self.editor.ensureCursorVisible()
        self._update_navigation()

    def _update_navigation(self) -> None:
        has = bool(self._spans)
        self.prev_btn.setEnabled(has and len(self._spans) > 1)
        self.next_btn.setEnabled(has and len(self._spans) > 1)
        self.counter.setText(f"{self._index + 1} из {len(self._spans)}" if has
                             else "локальная подсветка неприменима")


class ComparativeResearchTab(QWidget):
    """Единый рабочий экран пары спорный текст ↔ образец."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pdb = protocol_db.ProtocolDB(); self._project_id = None
        self._all_rows = []; self._rows = []; self._current = None
        self._syncing = False; self._build_ui(); self._reload_projects()

    def _build_ui(self):
        layout = QVBoxLayout(self); layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(7)
        title = QLabel("Сравнительное исследование: тексты, evidence и решение эксперта")
        title.setObjectName("subtitle"); layout.addWidget(title)
        top = QHBoxLayout(); top.addWidget(QLabel("Проект:"))
        self.project_combo = QComboBox(); self.project_combo.setMinimumWidth(190)
        self.project_combo.currentIndexChanged.connect(self._on_project_changed)
        top.addWidget(self.project_combo); top.addWidget(QLabel("Текст 1:"))
        self.doc_a_combo = QComboBox(); self.doc_a_combo.setMinimumWidth(170)
        self.doc_a_combo.currentIndexChanged.connect(lambda _i: self._reload_table())
        top.addWidget(self.doc_a_combo); top.addWidget(QLabel("Текст 2:"))
        self.doc_b_combo = QComboBox(); self.doc_b_combo.setMinimumWidth(170)
        self.doc_b_combo.currentIndexChanged.connect(lambda _i: self._reload_table())
        top.addWidget(self.doc_b_combo)
        self.btn_match = QPushButton("Собрать черновое сопоставление")
        self.btn_match.clicked.connect(self._auto_match); top.addWidget(self.btn_match)
        self.btn_export_docx = QPushButton("Экспорт DOCX")
        self.btn_export_docx.clicked.connect(lambda: self._export_comparison("docx"))
        top.addWidget(self.btn_export_docx)
        self.btn_export_xlsx = QPushButton("Экспорт XLSX")
        self.btn_export_xlsx.clicked.connect(lambda: self._export_comparison("xlsx"))
        top.addWidget(self.btn_export_xlsx)
        self.sync_scroll = QCheckBox("Синхронная прокрутка"); top.addWidget(self.sync_scroll)
        top.addStretch(); layout.addLayout(top)

        self.block_label = QLabel(""); self.block_label.setWordWrap(True)
        self.block_label.setStyleSheet(
            "color:#6d4c00;background:#fff1c7;padding:6px;border-radius:4px")
        self.block_label.setVisible(False); layout.addWidget(self.block_label)
        self.summary_label = QLabel(""); self.summary_label.setWordWrap(True)
        self.summary_label.setStyleSheet(
            "background:#edf2f7;padding:7px;border-radius:4px;color:#263238")
        layout.addWidget(self.summary_label)

        filters = QHBoxLayout()
        self.role_filter = self._filter_combo([
            ("METHOD", view_mod.METHOD_FEATURE), ("AUX", view_mod.AUX_METRIC),
            ("EVIDENCE", view_mod.EVIDENCE), ("GENERAL", view_mod.GENERAL_SKILL)])
        self.level_filter = self._filter_combo([(x, x) for x in ("NN", "NS", "NSV")])
        self.type_filter = self._filter_combo([(v, k) for k, v in _RELATION_LABELS.items()])
        self.status_filter = self._filter_combo([(v, k) for k, v in _STATUS_LABELS.items()])
        self.info_filter = self._filter_combo([(v, k) for k, v in _INFO_LABELS.items()])
        self.value_filter = self._filter_combo([(v, k) for k, v in _VALUE_LABELS.items()])
        for label, combo in (("Роль:", self.role_filter), ("Уровень:", self.level_filter),
                             ("Отношение:", self.type_filter), ("Решение:", self.status_filter),
                             ("Информативность:", self.info_filter),
                             ("Значимость:", self.value_filter)):
            filters.addWidget(QLabel(label)); filters.addWidget(combo)
        layout.addLayout(filters)
        shortcuts = QHBoxLayout()
        for text, callback in (
            ("Следующий непросмотренный", self._next_unreviewed),
            ("Предыдущий", lambda: self._move_selection(-1)),
            ("Только различия", lambda: self._quick_relation(view_mod.DIFFERENCE)),
            ("Только совпадения", lambda: self._quick_relation(view_mod.COINCIDENCE)),
            ("METHOD", lambda: self._quick_role(view_mod.METHOD_FEATURE)),
            ("AUX", lambda: self._quick_role(view_mod.AUX_METRIC)),
            ("Сбросить фильтры", self._clear_filters)):
            button = QPushButton(text); button.clicked.connect(callback); shortcuts.addWidget(button)
        shortcuts.addStretch(); layout.addLayout(shortcuts)

        self.text_a = EvidenceTextPane("ТЕКСТ 1"); self.text_b = EvidenceTextPane("ТЕКСТ 2")
        self.text_a.editor.verticalScrollBar().valueChanged.connect(
            lambda value: self._sync_scroll(self.text_b, value))
        self.text_b.editor.verticalScrollBar().valueChanged.connect(
            lambda value: self._sync_scroll(self.text_a, value))
        texts = QSplitter(Qt.Orientation.Horizontal); texts.setChildrenCollapsible(False)
        texts.addWidget(self.text_a); texts.addWidget(self.text_b); texts.setSizes([800, 800])

        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels([
            "Признак", "Роль", "Группа", "Отношение", "Уровень",
            "Информативность по методике", "Экспертная значимость", "Решение эксперта"])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(True); self.table.verticalHeader().setVisible(False)
        hh = self.table.horizontalHeader(); hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col in range(1, 8): hh.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        self.table.itemSelectionChanged.connect(self._on_selection)
        feature_area = QSplitter(Qt.Orientation.Horizontal); feature_area.setChildrenCollapsible(False)
        feature_area.addWidget(self.table); feature_area.addWidget(self._build_card())
        feature_area.setSizes([1050, 550])
        comparison_page = QWidget(); cp_layout = QVBoxLayout(comparison_page)
        cp_layout.setContentsMargins(0, 0, 0, 0); cp_layout.addWidget(feature_area)
        self.tabs = QTabWidget(); self.tabs.addTab(comparison_page, "Признаки и решения")
        self.tabs.addTab(self._build_ogorelkov_block(), "Служебная лексика (AUX)")
        split = QSplitter(Qt.Orientation.Vertical); split.setChildrenCollapsible(False)
        split.addWidget(texts); split.addWidget(self.tabs); split.setSizes([440, 420])
        layout.addWidget(split, stretch=1)
        self.progress_label = QLabel(
            "Методический ориентир 20–30 относится к квалифицированной совокупности. "
            "Программа не определяет автоматически достаточность комплекса.")
        self.progress_label.setObjectName("caption"); self.progress_label.setWordWrap(True)
        layout.addWidget(self.progress_label)

    def _filter_combo(self, values):
        combo = QComboBox(); combo.addItem("все", "")
        for label, value in values: combo.addItem(label, value)
        combo.currentIndexChanged.connect(lambda _i: self._apply_filters())
        return combo

    def _build_card(self):
        box = QGroupBox("Карточка признака"); form = QFormLayout(box)
        self.card_details = QTextBrowser(); self.card_details.setMinimumHeight(190)
        form.addRow(self.card_details)
        self.relation_combo = QComboBox()
        for value in cmp_mod.MATCH_TYPES: self.relation_combo.addItem(value.replace("_", " "), value)
        form.addRow("Квалификация отношения:", self.relation_combo)
        self.level_combo = QComboBox(); self.level_combo.addItem("— не задан —", "")
        for value in cmp_mod.LEVELS: self.level_combo.addItem(value, value)
        form.addRow("Уровень НН/НС/НСВ:", self.level_combo)
        self.id_value_combo = QComboBox(); self.id_value_combo.addItem("— не задана —", "")
        for value in ("низкая", "средняя", "высокая"): self.id_value_combo.addItem(value, value)
        form.addRow("Экспертная значимость:", self.id_value_combo)
        self.qualification_combo = QComboBox(); self.qualification_combo.addItem("—", "")
        for value in cmp_mod.DIFFERENCE_QUALIFICATIONS: self.qualification_combo.addItem(value, value)
        form.addRow("Квалификация различия:", self.qualification_combo)
        self.opportunity_combo = QComboBox()
        for value in cmp_mod.OPPORTUNITY_STATUSES: self.opportunity_combo.addItem(value, value)
        form.addRow("Возможность проявления:", self.opportunity_combo)
        self.note_edit = QTextEdit(); self.note_edit.setMaximumHeight(62)
        self.note_edit.setPlaceholderText("Комментарий эксперта")
        form.addRow("Комментарий:", self.note_edit)
        buttons = QHBoxLayout()
        self.btn_confirm = QPushButton("Принять"); self.btn_confirm.clicked.connect(self._accept_current)
        self.btn_reject = QPushButton("Отклонить"); self.btn_reject.clicked.connect(self._reject_current)
        self.btn_reset = QPushButton("Сбросить"); self.btn_reset.clicked.connect(self._reset_current)
        for button in (self.btn_confirm, self.btn_reject, self.btn_reset): buttons.addWidget(button)
        form.addRow(buttons); self._set_card_enabled(False); return box

    def _build_ogorelkov_block(self):
        box = QWidget(); layout = QVBoxLayout(box)
        hint = QLabel("AUX: наблюдаемые частоты служебной лексики не входят в методический счёт.")
        hint.setWordWrap(True); layout.addWidget(hint)
        self.chk_og_detail = QCheckBox("Таблицу лемм — в DOCX-заключение")
        layout.addWidget(self.chk_og_detail)
        self.og_cat_table = QTableWidget(0, 7); self.og_cat_table.setHorizontalHeaderLabels(
            ["Категория", "ipm 1", "ipm 2", "ipm НКРЯ", "коэф. 1", "коэф. 2", "разность"])
        self.og_lem_table = QTableWidget(0, 8); self.og_lem_table.setHorizontalHeaderLabels(
            ["Лемма", "вхожд. 1", "ipm 1", "вхожд. 2", "ipm 2", "ipm НКРЯ", "коэф. 1", "коэф. 2"])
        for table in (self.og_cat_table, self.og_lem_table):
            table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            table.verticalHeader().setVisible(False)
            table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
            layout.addWidget(table)
        return box

    @staticmethod
    def _na(value): return "—" if value is None else f"{value:g}"

    def _reload_ogorelkov(self, doc_a, doc_b):
        self.og_cat_table.setRowCount(0); self.og_lem_table.setRowCount(0)
        data = cmp_mod.ogorelkov_for_pair(self._pdb, doc_a, doc_b)
        if not data: return
        for row in data["categories"]:
            self._append_table_row(self.og_cat_table, [row["category"].replace("_", " "),
                self._na(row["ipm_a"]), self._na(row["ipm_b"]), self._na(row["ipm_rnc"]),
                self._na(row["ratio_a"]), self._na(row["ratio_b"]), self._na(row["diff_ipm"])])
        for row in data["lemmas"]:
            self._append_table_row(self.og_lem_table, [row["lemma"], str(row["count_a"]),
                self._na(row["ipm_a"]), str(row["count_b"]), self._na(row["ipm_b"]),
                self._na(row["ipm_rnc"]), self._na(row["ratio_a"]), self._na(row["ratio_b"])])

    @staticmethod
    def _append_table_row(table, values):
        row = table.rowCount(); table.insertRow(row)
        for col, value in enumerate(values): table.setItem(row, col, QTableWidgetItem(value))

    def ogorelkov_export_settings(self): return (self.chk_og_detail.isChecked(),)

    def _reload_projects(self):
        self.project_combo.blockSignals(True); self.project_combo.clear()
        projects = self._pdb.fetch_projects()
        for project in projects:
            self.project_combo.addItem(f"{project['name']} (#{project['id']})", project["id"])
        self.project_combo.blockSignals(False)
        self._project_id = projects[0]["id"] if projects else None
        if projects: self.project_combo.setCurrentIndex(0)
        self._reload_documents()

    def _on_project_changed(self, index):
        self._project_id = self.project_combo.itemData(index) if index >= 0 else None
        self._reload_documents()

    def _reload_documents(self):
        docs = self._pdb.fetch_documents(self._project_id) if self._project_id else []
        for combo, role in ((self.doc_a_combo, protocol_db.ROLE_DISPUTED),
                            (self.doc_b_combo, protocol_db.ROLE_SAMPLE)):
            combo.blockSignals(True); combo.clear()
            for document in docs:
                if document["role"] == role: combo.addItem(document["filename"], document["id"])
            combo.blockSignals(False)
            if combo.count(): combo.setCurrentIndex(0)
        self._reload_table()

    def _pair(self): return self.doc_a_combo.currentData(), self.doc_b_combo.currentData()
    def showEvent(self, event): super().showEvent(event); self._reload_projects()

    def _auto_match(self):
        doc_a, doc_b = self._pair()
        if self._project_id is None or doc_a is None or doc_b is None:
            QMessageBox.information(self, "Нет пары", "Выберите спорный текст и образец."); return
        cmp_mod.auto_match(self._pdb, self._project_id, doc_a, doc_b,
                           program_version=PROGRAM_VERSION); self._reload_table()

    def _export_comparison(self, kind):
        doc_a, doc_b = self._pair()
        if self._project_id is None or doc_a is None or doc_b is None: return
        extension = "docx" if kind == "docx" else "xlsx"
        filepath, _ = QFileDialog.getSaveFileName(
            self, "Экспорт сравнительного исследования",
            f"сравнительное_исследование.{extension}",
            "Word (*.docx)" if kind == "docx" else "Excel (*.xlsx)")
        if not filepath: return
        try:
            from protocol import comparison_export
            exporter = (comparison_export.export_comparison_docx if kind == "docx"
                        else comparison_export.export_comparison_xlsx)
            result = exporter(self._pdb, self._project_id, doc_a, doc_b,
                              filepath, program_version=PROGRAM_VERSION)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Ошибка экспорта", str(exc)); return
        QMessageBox.information(
            self, "Экспорт завершён",
            f"{result['filepath']}\nSHA-256: {result['sha256'][:16]}…")

    def _reload_table(self):
        doc_a, doc_b = self._pair(); self._current = None
        self.card_details.clear(); self._set_card_enabled(False)
        if self._project_id is None or doc_a is None or doc_b is None:
            self._all_rows = []; self._apply_filters()
            self.text_a.set_document("ТЕКСТ 1", ""); self.text_b.set_document("ТЕКСТ 2", "")
            self.summary_label.setText("Выберите пару текстов."); return
        da, db = self._pdb.get_document(doc_a), self._pdb.get_document(doc_b)
        self.text_a.set_document(f"ТЕКСТ 1 · {da['filename']}",
                                 self._pdb.get_layer(doc_a, protocol_db.LAYER_ORIGINAL) or "")
        self.text_b.set_document(f"ТЕКСТ 2 · {db['filename']}",
                                 self._pdb.get_layer(doc_b, protocol_db.LAYER_ORIGINAL) or "")
        self._all_rows = view_mod.build_feature_views(self._pdb, self._project_id, doc_a, doc_b)
        self._reload_ogorelkov(doc_a, doc_b); self._update_summary()
        blocked = cmp_mod.pair_blocks_strong_conclusion(self._pdb, self._project_id, doc_a, doc_b)
        self.block_label.setVisible(blocked)
        if blocked: self.block_label.setText("Есть ограничения пригодности; их влияние оценивает эксперт.")
        self._apply_filters()

    def _update_summary(self):
        stats = view_mod.summarize(self._all_rows); method = stats["method"]
        rel, levels, info = stats["relations"], stats["levels"], stats["method_informativeness"]
        self.summary_label.setText(
            f"Всего кандидатов: {stats['total_candidates']} · METHOD: принято {method[view_mod.ACCEPTED]}, "
            f"отклонено {method[view_mod.REJECTED]}, не просмотрено {method[view_mod.NOT_REVIEWED]} · AUX: {stats['aux']}\n"
            f"Совпадения: {rel[view_mod.COINCIDENCE]} · различия: {rel[view_mod.DIFFERENCE]} · "
            f"только текст 1: {rel[view_mod.PRESENT_ONLY_TEXT1]} · только текст 2: {rel[view_mod.PRESENT_ONLY_TEXT2]} · "
            f"уровни NN/NS/NSV: {levels['NN']}/{levels['NS']}/{levels['NSV']}\n"
            f"Информативность HIGH/MEDIUM/LOW/NOT SPECIFIED: {info[view_mod.INFO_HIGH]}/"
            f"{info[view_mod.INFO_MEDIUM]}/{info[view_mod.INFO_LOW]}/{info[view_mod.INFO_NOT_SPECIFIED]} · "
            f"экспертная высокая значимость: {stats['expert_high']}")

    def _apply_filters(self):
        self._rows = view_mod.filter_views(
            self._all_rows, role=self.role_filter.currentData() or "",
            level=self.level_filter.currentData() or "", relation=self.type_filter.currentData() or "",
            status=self.status_filter.currentData() or "",
            method_informativeness=self.info_filter.currentData() or "",
            expert_value=self.value_filter.currentData() or "")
        self.table.setRowCount(0)
        for item in self._rows: self._add_row(item)

    def _add_row(self, item):
        row = self.table.rowCount(); self.table.insertRow(row)
        values = [item.feature_name, _ROLE_LABELS[item.role],
                  " / ".join(x for x in (item.method_group, item.method_subgroup) if x),
                  _RELATION_LABELS[item.comparison_relation], item.individualization_level,
                  _INFO_LABELS[item.method_informativeness],
                  _VALUE_LABELS[item.expert_identification_value], _STATUS_LABELS[item.expert_status]]
        color = QColor(_ROW_COLORS[item.comparison_relation])
        for col, value in enumerate(values):
            cell = QTableWidgetItem(value); cell.setToolTip(value); cell.setBackground(color)
            self.table.setItem(row, col, cell)

    def _selected(self):
        row = self.table.currentRow(); return self._rows[row] if 0 <= row < len(self._rows) else None

    def _on_selection(self):
        item = self._selected()
        if item is None: return
        self._current = item; self.text_a.set_spans(item.evidence_spans_text1)
        self.text_b.set_spans(item.evidence_spans_text2); self._show_card(item)

    def _show_card(self, item):
        trace = item.method_trace
        summary = (escape(trace.quote_or_summary) if trace.quote_or_summary else
                   "<i>Конкретное положение не внесено в методреестр; информативность не выводится автоматически.</i>")
        evidence = ("Стрелки над текстом переключают evidence." if item.has_local_evidence else
                    "Агрегатный показатель — локальная подсветка неприменима.")
        self.card_details.setHtml(
            f"<h3>{escape(item.feature_name)}</h3><p><b>Роль:</b> {_ROLE_LABELS[item.role]} / {escape(item.source_kind)}<br>"
            f"<b>Группа:</b> {escape(item.method_group)} / {escape(item.method_subgroup)}<br>"
            f"<b>Уровень:</b> {escape(item.individualization_level)}<br>"
            f"<b>Текст 1:</b> {escape(item.value_text1 or '—')}<br><b>Текст 2:</b> {escape(item.value_text2 or '—')}<br>"
            f"<b>Результат:</b> {_RELATION_LABELS[item.comparison_relation]}</p>"
            f"<p><b>Обоснование:</b> {escape(item.comparison_explanation)}</p>"
            f"<p><b>Источник:</b> {escape(trace.title or '—')}<br><b>Раздел:</b> {escape(trace.section or '—')} · "
            f"<b>подраздел:</b> {escape(trace.subsection or '—')} · <b>страница:</b> {escape(trace.page or '—')}<br>"
            f"<b>Что устанавливает источник:</b> {summary}<br><b>Информативность:</b> {_INFO_LABELS[item.method_informativeness]}</p>"
            f"<p><b>Evidence:</b> {evidence}</p>")
        self._set_combo(self.relation_combo, {view_mod.COINCIDENCE: cmp_mod.MATCH_COINCIDENCE,
            view_mod.DIFFERENCE: cmp_mod.MATCH_DIFFERENCE, view_mod.PRESENT_ONLY_TEXT1: cmp_mod.MATCH_ONLY_A,
            view_mod.PRESENT_ONLY_TEXT2: cmp_mod.MATCH_ONLY_B}.get(item.comparison_relation, cmp_mod.MATCH_COINCIDENCE))
        self._set_combo(self.level_combo, {"NN": "НН", "NS": "НС", "NSV": "НСВ"}.get(item.individualization_level, ""))
        self._set_combo(self.id_value_combo, {view_mod.VALUE_LOW: "низкая", view_mod.VALUE_MEDIUM: "средняя",
            view_mod.VALUE_HIGH: "высокая"}.get(item.expert_identification_value, ""))
        self.note_edit.setPlainText(item.notes)
        self._set_card_enabled(item.role == view_mod.METHOD_FEATURE and bool(item.position_key))

    @staticmethod
    def _set_combo(combo, value):
        index = combo.findData(value); combo.setCurrentIndex(max(index, 0))

    def _set_card_enabled(self, enabled):
        for widget in (self.relation_combo, self.level_combo, self.id_value_combo,
                       self.qualification_combo, self.opportunity_combo, self.note_edit,
                       self.btn_confirm, self.btn_reject, self.btn_reset):
            widget.setEnabled(enabled)

    def _expert_id(self):
        project = self._pdb.get_project(self._project_id) if self._project_id else None
        return (project["expert_name"] or "") if project else ""

    def _accept_current(self):
        item = self._current; doc_a, doc_b = self._pair()
        if item is None or not item.position_key: return
        try:
            cmp_mod.decide(self._pdb, self._project_id, doc_a, doc_b, item.position_key,
                match_type=self.relation_combo.currentData(), level=self.level_combo.currentData() or "",
                identification_value=self.id_value_combo.currentData() or "",
                difference_qualification=self.qualification_combo.currentData() or "",
                opportunity_status=self.opportunity_combo.currentData() or "NOT_ASSESSED",
                expert_note=self.note_edit.toPlainText().strip(), program_version=PROGRAM_VERSION,
                expert_id=self._expert_id())
        except ValueError as exc:
            QMessageBox.warning(self, "Позиция не принята", str(exc)); return
        self._reload_table()

    def _reject_current(self):
        item = self._current; doc_a, doc_b = self._pair()
        if item is None or not item.position_key: return
        cmp_mod.reject(self._pdb, self._project_id, doc_a, doc_b, item.position_key,
            identification_value=self.id_value_combo.currentData() or "",
            expert_note=self.note_edit.toPlainText().strip(), program_version=PROGRAM_VERSION,
            expert_id=self._expert_id()); self._reload_table()

    def _reset_current(self):
        item = self._current; doc_a, doc_b = self._pair()
        if item is None or not item.position_key: return
        cmp_mod.reset(self._pdb, self._project_id, doc_a, doc_b, item.position_key,
                      program_version=PROGRAM_VERSION, expert_id=self._expert_id())
        self._reload_table()

    def _sync_scroll(self, target, value):
        if not self.sync_scroll.isChecked() or self._syncing: return
        self._syncing = True; source = self.sender(); target_bar = target.editor.verticalScrollBar()
        target_bar.setValue(round(value / max(1, source.maximum()) * target_bar.maximum()))
        self._syncing = False

    def _quick_role(self, value): self._set_combo(self.role_filter, value)
    def _quick_relation(self, value): self._set_combo(self.type_filter, value)

    def _clear_filters(self):
        for combo in (self.role_filter, self.level_filter, self.type_filter,
                      self.status_filter, self.info_filter, self.value_filter):
            combo.setCurrentIndex(0)

    def _move_selection(self, delta):
        if self._rows:
            row = self.table.currentRow()
            self.table.selectRow(max(0, min(len(self._rows) - 1, row + delta)))

    def _next_unreviewed(self):
        if not self._rows: return
        start = self.table.currentRow() + 1
        for offset in range(len(self._rows)):
            index = (start + offset) % len(self._rows)
            if self._rows[index].expert_status == view_mod.NOT_REVIEWED:
                self.table.selectRow(index); return
