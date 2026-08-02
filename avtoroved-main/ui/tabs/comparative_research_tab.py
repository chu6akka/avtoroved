"""
ui/tabs/comparative_research_tab.py — вкладка «Сравнительное исслед.» протокола.

Сопоставление ПРИНЯТЫХ признаков пары спорный↔образец (стадия 3 методики
Рубцовой 2007). Автоматика — только черновик; эксперт подтверждает тип
(совпадение/различие) и уровень НН/НС/НСВ. Вывода об авторстве здесь нет.
Не путать со старой вкладкой «Сравнение» (comparison_tab.py) — та работает
по сырым текстам вне протокола и не изменялась.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QMessageBox, QDialog, QDialogButtonBox, QFormLayout, QTextEdit, QSplitter,
    QTabWidget, QCheckBox,
)

from protocol import db as protocol_db
from protocol import comparison as cmp_mod
from protocol import PROGRAM_VERSION

_TYPE_COLOR = {
    cmp_mod.MATCH_COINCIDENCE: "#a6e3a1",   # зелёный
    cmp_mod.MATCH_DIFFERENCE: "#f38ba8",    # красный
    cmp_mod.MATCH_ONLY_A: "#89dceb",        # голубой
    cmp_mod.MATCH_ONLY_B: "#cba6f7",        # фиолетовый
}


class _ConfirmDialog(QDialog):
    """Диалог подтверждения позиции: тип, уровень НН/НС/НСВ, примечание."""

    def __init__(self, default_type: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Подтвердить позицию сопоставления")
        self.resize(460, 240)
        form = QFormLayout(self)
        self.type_combo = QComboBox()
        self.type_combo.addItems(list(cmp_mod.MATCH_TYPES))
        if default_type in cmp_mod.MATCH_TYPES:
            self.type_combo.setCurrentText(default_type)
        form.addRow("Тип:", self.type_combo)
        self.level_combo = QComboBox()
        self.level_combo.addItem("— не задан —", "")
        for lv in cmp_mod.LEVELS:
            self.level_combo.addItem(lv, lv)
        form.addRow("Уровень (НН/НС/НСВ):", self.level_combo)
        self.note_edit = QTextEdit()
        self.note_edit.setPlaceholderText("Примечание эксперта (необязательно)…")
        self.note_edit.setMaximumHeight(80)
        form.addRow("Примечание:", self.note_edit)
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        form.addRow(btns)

    def values(self) -> tuple[str, str, str]:
        return (self.type_combo.currentText(),
                self.level_combo.currentData() or "",
                self.note_edit.toPlainText().strip())


class ComparativeResearchTab(QWidget):
    """Вкладка «Сравнительное исслед.»: пары спорный↔образец по принятым признакам."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pdb = protocol_db.ProtocolDB()
        self._project_id: int | None = None
        self._rows: list = []           # comparisons-строки в порядке таблицы
        self._build_ui()
        self._reload_projects()

    # ── UI ───────────────────────────────────────────────────────────────────
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        title = QLabel("Сравнительное исследование: принятые признаки пары (без вывода)")
        title.setObjectName("subtitle")
        layout.addWidget(title)

        top = QHBoxLayout()
        top.addWidget(QLabel("Проект:"))
        self.project_combo = QComboBox()
        self.project_combo.setMinimumWidth(200)
        self.project_combo.currentIndexChanged.connect(self._on_project_changed)
        top.addWidget(self.project_combo)
        top.addWidget(QLabel("Спорный:"))
        self.doc_a_combo = QComboBox()
        self.doc_a_combo.setMinimumWidth(200)
        self.doc_a_combo.currentIndexChanged.connect(lambda _i: self._reload_table())
        top.addWidget(self.doc_a_combo)
        top.addWidget(QLabel("Образец:"))
        self.doc_b_combo = QComboBox()
        self.doc_b_combo.setMinimumWidth(200)
        self.doc_b_combo.currentIndexChanged.connect(lambda _i: self._reload_table())
        top.addWidget(self.doc_b_combo)
        self.btn_match = QPushButton("⚙ Сопоставить автоматически")
        self.btn_match.clicked.connect(self._auto_match)
        top.addWidget(self.btn_match)
        top.addStretch()
        layout.addLayout(top)

        # Плашка блокировки категорического вывода (из стадии пригодности).
        self.block_label = QLabel("")
        self.block_label.setWordWrap(True)
        self.block_label.setStyleSheet(
            "color: #f9e2af; background: #45403d; padding: 6px; border-radius: 4px;")
        self.block_label.setVisible(False)
        layout.addWidget(self.block_label)

        filt = QHBoxLayout()
        filt.addWidget(QLabel("Показать:"))
        self.type_filter = QComboBox()
        self.type_filter.addItem("все типы", None)
        for t in cmp_mod.MATCH_TYPES:
            self.type_filter.addItem(t, t)
        self.type_filter.currentIndexChanged.connect(lambda _i: self._reload_table())
        filt.addWidget(self.type_filter)
        filt.addStretch()
        layout.addLayout(filt)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            ["Признак", "Группа", "У спорного", "У образца", "Тип", "Уровень", "Статус"])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setAlternatingRowColors(True)
        self.table.setStyleSheet("QTableWidget::item { padding: 5px 7px; }")
        self.table.verticalHeader().setVisible(False)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        hh.resizeSection(0, 260)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        for c in (1, 4, 5, 6):
            hh.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
        self.table.itemSelectionChanged.connect(self._on_selection)

        self.detail = QTextEdit()
        self.detail.setReadOnly(True)
        self.detail.setMaximumHeight(130)
        self.detail.setPlaceholderText("Выберите позицию — здесь полные значения и фрагменты.")

        # Вкладки: позиции сопоставления признаков и служебная лексика.
        self.tabs = QTabWidget()
        self.tabs.addTab(self.table, "Позиции сопоставления")
        self.tabs.addTab(self._build_ogorelkov_block(),
                         "Служебная лексика (Огорелков)")

        split = QSplitter(Qt.Orientation.Vertical)
        split.setChildrenCollapsible(False)
        split.addWidget(self.tabs)
        split.addWidget(self.detail)
        split.setSizes([520, 110])
        layout.addWidget(split, stretch=1)

        btns = QHBoxLayout()
        self.btn_confirm = QPushButton("✔ Подтвердить (тип/уровень)…")
        self.btn_confirm.clicked.connect(self._confirm_selected)
        btns.addWidget(self.btn_confirm)
        self.btn_reset = QPushButton("↺ Сбросить подтверждение")
        self.btn_reset.clicked.connect(self._reset_selected)
        btns.addWidget(self.btn_reset)
        btns.addStretch()
        layout.addLayout(btns)

        self.progress_label = QLabel("")
        self.progress_label.setObjectName("caption")
        layout.addWidget(self.progress_label)

    # ── блок «Служебная лексика (Огорелков)» ─────────────────────────────────
    def _build_ogorelkov_block(self) -> QWidget:
        """
        Две таблицы наблюдаемых частот: по категориям и по леммам.
        Никакой цветовой маркировки «совпадает/не совпадает» и никакой
        агрегированной меры сходства — только числа (граница компетенции).
        """
        box = QWidget()
        v = QVBoxLayout(box)
        v.setContentsMargins(0, 6, 0, 0)
        v.setSpacing(6)

        hint = QLabel(
            "Относительные частоты (ipm) служебных лексико-грамматических "
            "классов; норма — частотный словарь Ляшевской–Шарова. "
            "A — спорный текст, B — образец.")
        hint.setObjectName("caption")
        hint.setWordWrap(True)
        v.addWidget(hint)

        row = QHBoxLayout()
        self.chk_og_detail = QCheckBox("Таблицу лемм — в DOCX-заключение")
        row.addWidget(self.chk_og_detail)
        row.addStretch()
        v.addLayout(row)

        self.og_cat_table = QTableWidget(0, 7)
        self.og_cat_table.setHorizontalHeaderLabels(
            ["Категория", "ipm A", "ipm B", "ipm НКРЯ",
             "коэф. A", "коэф. B", "разность ipm A−B"])
        self._tune_table(self.og_cat_table, stretch_col=0)
        v.addWidget(self.og_cat_table, stretch=1)

        self.og_lem_table = QTableWidget(0, 8)
        self.og_lem_table.setHorizontalHeaderLabels(
            ["Лемма", "вхожд. A", "ipm A", "вхожд. B", "ipm B",
             "ipm НКРЯ", "коэф. A", "коэф. B"])
        self._tune_table(self.og_lem_table, stretch_col=0)
        v.addWidget(self.og_lem_table, stretch=2)
        return box

    @staticmethod
    def _tune_table(table: QTableWidget, stretch_col: int = 0):
        """Единое оформление таблиц блока служебной лексики."""
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setAlternatingRowColors(True)
        table.setStyleSheet("QTableWidget::item { padding: 4px 6px; }")
        table.verticalHeader().setVisible(False)
        hh = table.horizontalHeader()
        for c in range(table.columnCount()):
            hh.setSectionResizeMode(
                c, QHeaderView.ResizeMode.Stretch if c == stretch_col
                else QHeaderView.ResizeMode.ResizeToContents)

    @staticmethod
    def _na(v) -> str:
        """Прочерк для отсутствующих величин («н/д», не ноль)."""
        return "—" if v is None else f"{v:g}"

    def _reload_ogorelkov(self, doc_a: int, doc_b: int):
        self.og_cat_table.setRowCount(0)
        self.og_lem_table.setRowCount(0)
        data = cmp_mod.ogorelkov_for_pair(self._pdb, doc_a, doc_b)
        if not data:
            return
        for r in data["categories"]:
            i = self.og_cat_table.rowCount()
            self.og_cat_table.insertRow(i)
            cells = [r["category"].replace("_", " "),
                     self._na(r["ipm_a"]), self._na(r["ipm_b"]),
                     self._na(r["ipm_rnc"]), self._na(r["ratio_a"]),
                     self._na(r["ratio_b"]), self._na(r["diff_ipm"])]
            for c, text in enumerate(cells):
                self.og_cat_table.setItem(i, c, QTableWidgetItem(text))
        # Таблица лемм уже отсортирована по |ipm A − ipm B| по убыванию.
        for r in data["lemmas"]:
            i = self.og_lem_table.rowCount()
            self.og_lem_table.insertRow(i)
            cells = [r["lemma"], str(r["count_a"]), self._na(r["ipm_a"]),
                     str(r["count_b"]), self._na(r["ipm_b"]),
                     self._na(r["ipm_rnc"]), self._na(r["ratio_a"]),
                     self._na(r["ratio_b"])]
            for c, text in enumerate(cells):
                self.og_lem_table.setItem(i, c, QTableWidgetItem(text))

    def ogorelkov_export_settings(self) -> tuple[bool]:
        """Включать ли таблицу лемм в DOCX-заключение."""
        return (self.chk_og_detail.isChecked(),)

    # ── выбор проекта/пары ───────────────────────────────────────────────────
    def _reload_projects(self):
        self.project_combo.blockSignals(True)
        self.project_combo.clear()
        projects = self._pdb.fetch_projects()
        for p in projects:
            self.project_combo.addItem(f"{p['name']} (#{p['id']})", p["id"])
        self.project_combo.blockSignals(False)
        if projects:
            self.project_combo.setCurrentIndex(0)
            self._project_id = projects[0]["id"]
            self._reload_documents()
        else:
            self._project_id = None
            self.doc_a_combo.clear()
            self.doc_b_combo.clear()

    def _on_project_changed(self, index: int):
        self._project_id = self.project_combo.itemData(index) if index >= 0 else None
        self._reload_documents()

    def _reload_documents(self):
        for combo, role in ((self.doc_a_combo, protocol_db.ROLE_DISPUTED),
                            (self.doc_b_combo, protocol_db.ROLE_SAMPLE)):
            combo.blockSignals(True)
            combo.clear()
            if self._project_id is not None:
                for d in self._pdb.fetch_documents(self._project_id):
                    if d["role"] == role:
                        combo.addItem(d["filename"], d["id"])
            combo.blockSignals(False)
            if combo.count():
                combo.setCurrentIndex(0)
        self._reload_table()

    def _pair(self) -> tuple[int | None, int | None]:
        return self.doc_a_combo.currentData(), self.doc_b_combo.currentData()

    def showEvent(self, event):
        super().showEvent(event)
        self._reload_projects()

    # ── авто-сопоставление ───────────────────────────────────────────────────
    def _auto_match(self):
        doc_a, doc_b = self._pair()
        if self._project_id is None or doc_a is None or doc_b is None:
            QMessageBox.information(
                self, "Нет пары",
                "Нужны спорный текст и образец с принятыми признаками "
                "(вкладка «Карта признаков»).")
            return
        summary = cmp_mod.auto_match(self._pdb, self._project_id, doc_a, doc_b,
                                     program_version=PROGRAM_VERSION)
        self._reload_table()
        if summary["positions"] == 0:
            QMessageBox.information(
                self, "Нет принятых признаков",
                "У пары нет принятых признаков. Сначала утвердите признаки "
                "во вкладке «Карта признаков».")

    # ── таблица ──────────────────────────────────────────────────────────────
    def _reload_table(self):
        self.table.setRowCount(0)
        self.detail.clear()
        self._rows = []
        doc_a, doc_b = self._pair()
        if self._project_id is None or doc_a is None or doc_b is None:
            self.progress_label.setText("Выберите пару спорный↔образец.")
            self.block_label.setVisible(False)
            self.og_cat_table.setRowCount(0)
            self.og_lem_table.setRowCount(0)
            return

        # Служебная лексика: таблицы обновляются вместе с парой.
        self._reload_ogorelkov(doc_a, doc_b)

        st = cmp_mod.stats(self._pdb, self._project_id, doc_a, doc_b)
        # Плашка блокировки.
        if st["blocks_strong_conclusion"]:
            self.block_label.setText(
                "⚠ По стадии пригодности категорический вывод для этой пары "
                "ЗАБЛОКИРОВАН (blocks_strong_conclusion = 1) — результаты сравнения "
                "смогут дать только вероятную форму вывода.")
            self.block_label.setVisible(True)
        else:
            self.block_label.setVisible(False)

        type_filter = self.type_filter.currentData()
        for r in self._pdb.fetch_comparisons(doc_a, doc_b):
            if type_filter and r["match_type"] != type_filter:
                continue
            self._add_row(r)
            self._rows.append(r)

        if st["всего"] == 0:
            self.progress_label.setText(
                "Позиций нет — нажмите «Сопоставить автоматически».")
        else:
            # Общие признаки (степени навыков) и покатегорийная разбивка
            # (Моисеева/Огорелков, 2021, с. 89–93) — компактно, одной строкой.
            gen = st.get("общие_признаки") or {}
            gen_txt = ""
            if gen:
                gen_txt = " Навыки: " + ", ".join(
                    f"{k} — {v.replace('навык_', '').replace('_', ' ')}"
                    for k, v in gen.items()) + "."
            short = st.get("недобор_категорический") or []
            cat_txt = (" Покатегорийные минимумы выполнены."
                       if not short else
                       f" Недобор для категорического: {', '.join(short)}.")
            self.progress_label.setText(
                f"Позиций {st['всего']}: совпадений {st[cmp_mod.MATCH_COINCIDENCE]}, "
                f"различий {st[cmp_mod.MATCH_DIFFERENCE]}, "
                f"только у спорного {st[cmp_mod.MATCH_ONLY_A]}, "
                f"только у образца {st[cmp_mod.MATCH_ONLY_B]}. "
                f"Подтверждено {st['подтверждено']} "
                f"(НН {st['уровень_НН']}, НС {st['уровень_НС']}, НСВ {st['уровень_НСВ']}). "
                f"До суммарного порога ≥{st['порог_методики']}: {st['до_порога']}."
                f"{gen_txt}{cat_txt}")

    def _add_row(self, r):
        row = self.table.rowCount()
        self.table.insertRow(row)
        cells = [
            r["label"], r["group_name"] or "",
            r["value_a"] or ("—" if r["match_type"] == cmp_mod.MATCH_ONLY_B else ""),
            r["value_b"] or ("—" if r["match_type"] == cmp_mod.MATCH_ONLY_A else ""),
            r["match_type"], r["level"] or "", r["status"],
        ]
        for col, text in enumerate(cells):
            item = QTableWidgetItem(str(text))
            if text:
                item.setToolTip(str(text))
            if col == 4:
                color = _TYPE_COLOR.get(r["match_type"])
                if color:
                    item.setForeground(QColor(color))
            if col == 6 and r["status"] == cmp_mod.STATUS_CONFIRMED:
                item.setForeground(QColor("#a6e3a1"))
            self.table.setItem(row, col, item)

    def _selected_rows(self) -> list:
        rows = sorted({i.row() for i in self.table.selectedItems()})
        return [self._rows[r] for r in rows if 0 <= r < len(self._rows)]

    def _on_selection(self):
        sel = self._selected_rows()
        if not sel:
            self.detail.clear()
            return
        r = sel[0]
        parts = [f"<b>{r['label']}</b>",
                 f"<span style='color:#a6adc8'>{r['group_name'] or ''} · "
                 f"{r['subgroup'] or ''} · {r['match_type']} · статус: {r['status']}</span>"]
        if r["value_a"] or r["fragment_a"]:
            parts.append(f"<b>Спорный:</b> {r['value_a'] or ''}"
                         + (f" — «{r['fragment_a']}»" if r["fragment_a"] else ""))
        if r["value_b"] or r["fragment_b"]:
            parts.append(f"<b>Образец:</b> {r['value_b'] or ''}"
                         + (f" — «{r['fragment_b']}»" if r["fragment_b"] else ""))
        if r["status"] == cmp_mod.STATUS_CONFIRMED:
            note = f" · примечание: {r['expert_note']}" if r["expert_note"] else ""
            parts.append(f"<b>Решение:</b> уровень {r['level'] or '—'} "
                         f"({r['decided_at']}){note}")
        self.detail.setHtml("<br>".join(parts))

    # ── решения ──────────────────────────────────────────────────────────────
    def _confirm_selected(self):
        sel = self._selected_rows()
        doc_a, doc_b = self._pair()
        if not sel or doc_a is None:
            QMessageBox.information(self, "Нет выбора", "Выделите позиции в таблице.")
            return
        dlg = _ConfirmDialog(sel[0]["match_type"], self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        mtype, level, note = dlg.values()
        for r in sel:
            cmp_mod.decide(self._pdb, self._project_id, doc_a, doc_b,
                           r["position_key"], match_type=mtype, level=level,
                           expert_note=note, program_version=PROGRAM_VERSION)
        self._reload_table()

    def _reset_selected(self):
        sel = self._selected_rows()
        doc_a, doc_b = self._pair()
        if not sel or doc_a is None:
            QMessageBox.information(self, "Нет выбора", "Выделите позиции в таблице.")
            return
        for r in sel:
            cmp_mod.reset(self._pdb, self._project_id, doc_a, doc_b,
                          r["position_key"], program_version=PROGRAM_VERSION)
        self._reload_table()
