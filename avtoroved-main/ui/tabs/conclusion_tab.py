"""
ui/tabs/conclusion_tab.py — вкладка «Вывод и заключение» (стадия 4 протокола).

Показывает нейтральный методический контроль по четырём блокам. Программа
не выбирает и не выделяет форму вывода; решение фиксирует эксперт.
"""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
    QTextEdit, QMessageBox, QFileDialog, QDialog, QDialogButtonBox,
    QFormLayout, QLineEdit,
)

from protocol import db as protocol_db
from protocol import comparison as cmp_mod
from protocol import conclusion as concl
from protocol import PROGRAM_VERSION


class _HeaderDialog(QDialog):
    """Реквизиты заключения для экспорта."""

    def __init__(self, default_expert: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Реквизиты заключения")
        self.resize(480, 220)
        form = QFormLayout(self)
        self.expert_edit = QLineEdit(default_expert or "")
        form.addRow("Эксперт (ФИО):", self.expert_edit)
        self.case_edit = QLineEdit()
        form.addRow("Номер заключения/дела:", self.case_edit)
        self.questions_edit = QTextEdit()
        self.questions_edit.setMaximumHeight(70)
        self.questions_edit.setPlaceholderText(
            "Вопросы перед экспертом (пусто — стандартный вопрос об авторстве)")
        form.addRow("Вопросы:", self.questions_edit)
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        form.addRow(btns)

    def values(self) -> dict:
        return {"expert_name": self.expert_edit.text().strip(),
                "case_number": self.case_edit.text().strip(),
                "questions": self.questions_edit.toPlainText().strip()}


class ConclusionTab(QWidget):
    """Вкладка «Вывод и заключение»."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pdb = protocol_db.ProtocolDB()
        self._project_id: int | None = None
        self._build_ui()
        self._reload_projects()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        title = QLabel("Оценка результатов и вывод (стадия 4, Рубцова 2007)")
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
        self.doc_a_combo.currentIndexChanged.connect(lambda _i: self._refresh())
        top.addWidget(self.doc_a_combo)
        top.addWidget(QLabel("Образец:"))
        self.doc_b_combo = QComboBox()
        self.doc_b_combo.setMinimumWidth(200)
        self.doc_b_combo.currentIndexChanged.connect(lambda _i: self._refresh())
        top.addWidget(self.doc_b_combo)
        top.addStretch()
        layout.addLayout(top)

        layout.addWidget(QLabel("Методический контроль (без рекомендации формы вывода):"))
        self.checks_view = QTextEdit()
        self.checks_view.setReadOnly(True)
        self.checks_view.setMaximumHeight(240)
        layout.addWidget(self.checks_view)

        form_row = QHBoxLayout()
        form_row.addWidget(QLabel("Форма вывода эксперта:"))
        self.form_combo = QComboBox()
        self.form_combo.addItem("— выберите форму самостоятельно —", None)
        for f in concl.FORMS:
            self.form_combo.addItem(concl.FORM_LABELS[f], f)
        form_row.addWidget(self.form_combo, stretch=1)
        layout.addLayout(form_row)

        layout.addWidget(QLabel("Обоснование эксперта:"))
        self.justification_edit = QTextEdit()
        self.justification_edit.setMaximumHeight(90)
        layout.addWidget(self.justification_edit)

        btns = QHBoxLayout()
        self.btn_fix = QPushButton("📌 Зафиксировать вывод")
        self.btn_fix.clicked.connect(self._fix_conclusion)
        btns.addWidget(self.btn_fix)
        self.btn_export = QPushButton("📄 Экспорт заключения (DOCX)")
        self.btn_export.clicked.connect(self._export_docx)
        btns.addWidget(self.btn_export)
        btns.addStretch()
        layout.addLayout(btns)

        self.status_label = QLabel("")
        self.status_label.setObjectName("caption")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        layout.addStretch()

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
        self._refresh()

    def _pair(self):
        return self.doc_a_combo.currentData(), self.doc_b_combo.currentData()

    def showEvent(self, event):
        super().showEvent(event)
        self._reload_projects()

    # ── нейтральный методический контроль ───────────────────────────────────
    def _refresh(self):
        doc_a, doc_b = self._pair()
        if self._project_id is None or doc_a is None or doc_b is None:
            self.checks_view.setPlainText("Выберите пару спорный↔образец.")
            self.status_label.setText("")
            return
        checks = concl.methodological_checks(
            self._pdb, self._project_id, doc_a, doc_b)
        rub = checks["rubtsova"]
        mo = checks["moiseeva_ogorelkov"]
        vula = checks["vula"]
        suitability = checks["suitability"]
        category_lines = []
        for category, data in mo["coincidences_by_category"].items():
            cat = data["categorical"]
            prob = data["probable"]
            category_lines.append(
                f"{category}: всего {data['actual_count']}, высокой значимости "
                f"{data['high_identification_value_count']}; "
                f"ориентир {cat['reference_minimum']} — {cat['condition_met']}; "
                f"ориентир {prob['reference_minimum']} — {prob['condition_met']}")
        diff_counts = mo["difference_significance_counts"]
        observed = mo["observed_conditions"]
        html = [
            "<b>A. Уровни НН/НС/НСВ (Рубцова)</b>",
            f"Совпадения: {rub['coincidence']}, без уровня "
            f"{rub['coincidence_nolevel']}; различия: {rub['difference']}, "
            f"без уровня {rub['difference_nolevel']}.",
            "<b>B. Категории и количественные ориентиры (Моисеева—Огорелков)</b>",
            *category_lines,
            ("Различия по значимости: низкая {low}, средняя {medium}, "
             "высокая {high}, без оценки {unset}, всего {total}.").format(**diff_counts),
            "Наблюдаемые условия: " + ", ".join(
                f"{name}={value}" for name, value in observed.items()) + ".",
            "True/False означает только результат отдельной формализованной проверки, "
            "а не итоговую экспертную оценку.",
            "<b>C. Общие признаки и правило Вула</b>",
            vula["note"],
            "<b>D. Ограничения материала</b>",
            "; ".join(suitability["warnings"] + suitability["methodological"]
                      + suitability["instrumental"]) or "Не зафиксированы.",
        ]
        self.checks_view.setHtml("<br>".join(html))
        # Текущий зафиксированный вывод.
        row = self._pdb.fetch_conclusion(doc_a, doc_b)
        if row is not None:
            self.status_label.setText(
                f"Зафиксирован вывод: {concl.FORM_LABELS.get(row['form'], row['form'])} "
                f"({row['decided_at']}). Повторная фиксация перезапишет текущее "
                "состояние (история сохраняется).")
        else:
            self.status_label.setText("Вывод по паре ещё не зафиксирован.")

    # ── действия ─────────────────────────────────────────────────────────────
    def _fix_conclusion(self):
        doc_a, doc_b = self._pair()
        if self._project_id is None or doc_a is None or doc_b is None:
            return
        form = self.form_combo.currentData()
        if form is None:
            QMessageBox.information(
                self, "Форма не выбрана",
                "Выберите форму вывода самостоятельно.")
            return
        try:
            concl.decide(self._pdb, self._project_id, doc_a, doc_b, form,
                         justification=self.justification_edit.toPlainText().strip(),
                         program_version=PROGRAM_VERSION)
        except ValueError as e:
            QMessageBox.warning(self, "Невозможно зафиксировать", str(e))
            return
        self._refresh()
        QMessageBox.information(self, "Вывод зафиксирован",
                                f"Форма: {concl.FORM_LABELS[form]}")

    def _export_docx(self):
        doc_a, doc_b = self._pair()
        if self._project_id is None or doc_a is None or doc_b is None:
            return
        if self._pdb.fetch_conclusion(doc_a, doc_b) is None:
            QMessageBox.warning(self, "Нет вывода",
                                "Сначала зафиксируйте вывод по паре.")
            return
        project = self._pdb.get_project(self._project_id)
        dlg = _HeaderDialog(project["expert_name"] or "", self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        fp, _ = QFileDialog.getSaveFileName(
            self, "Сохранить заключение", "заключение_эксперта.docx", "Word (*.docx)")
        if not fp:
            return
        try:
            from protocol.report import export_conclusion_docx
            # Чекбокс полемной таблицы служебной лексики живёт на вкладке
            # сравнительного исследования — читаем его состояние, если она есть.
            og_detailed = False
            main_win = self.window()
            tab_cmp = getattr(main_win, "tab_comparative", None)
            if tab_cmp is not None and hasattr(tab_cmp, "ogorelkov_export_settings"):
                (og_detailed,) = tab_cmp.ogorelkov_export_settings()
            summary = export_conclusion_docx(
                self._pdb, self._project_id, doc_a, doc_b, fp,
                header=dlg.values(), program_version=PROGRAM_VERSION,
                ogorelkov_detailed=og_detailed)
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, "Ошибка экспорта", str(e))
            return
        QMessageBox.information(
            self, "Заключение сохранено",
            f"{summary['filepath']}\nSHA-256: {summary['sha256'][:16]}…")
