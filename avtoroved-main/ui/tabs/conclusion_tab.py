"""
ui/tabs/conclusion_tab.py — вкладка «Вывод и заключение» (стадия 4 протокола).

Показывает сводку сравнительного исследования пары, авто-рекомендацию формы
вывода по правилу Рубцовой 2007 (с.85–86) с обоснованием; эксперт фиксирует
форму (несогласие с рекомендацией требует обоснования) и экспортирует отчёт
исследования в DOCX — вставляемую исследовательскую часть заключения
(титул, реквизиты и ВЫВОДЫ эксперт оформляет в своём документе).
"""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
    QTextEdit, QMessageBox, QFileDialog,
)

from protocol import db as protocol_db
from protocol import comparison as cmp_mod
from protocol import conclusion as concl
from protocol import PROGRAM_VERSION


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

        layout.addWidget(QLabel("Рекомендация методики (автоматическая, справочно):"))
        self.recommend_view = QTextEdit()
        self.recommend_view.setReadOnly(True)
        self.recommend_view.setMaximumHeight(170)
        layout.addWidget(self.recommend_view)

        form_row = QHBoxLayout()
        form_row.addWidget(QLabel("Форма вывода эксперта:"))
        self.form_combo = QComboBox()
        for f in concl.FORMS:
            self.form_combo.addItem(concl.FORM_LABELS[f], f)
        form_row.addWidget(self.form_combo, stretch=1)
        layout.addLayout(form_row)

        layout.addWidget(QLabel("Обоснование (обязательно при несогласии с рекомендацией):"))
        self.justification_edit = QTextEdit()
        self.justification_edit.setMaximumHeight(90)
        layout.addWidget(self.justification_edit)

        btns = QHBoxLayout()
        self.btn_fix = QPushButton("📌 Зафиксировать вывод")
        self.btn_fix.clicked.connect(self._fix_conclusion)
        btns.addWidget(self.btn_fix)
        self.btn_export = QPushButton("📄 Экспорт отчёта исследования (DOCX)")
        self.btn_export.setToolTip(
            "Исследовательская часть для вставки в заключение: объекты, "
            "4 стадии с иллюстрациями признаков, техническая справка")
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

    # ── сводка и рекомендация ────────────────────────────────────────────────
    def _refresh(self):
        doc_a, doc_b = self._pair()
        if self._project_id is None or doc_a is None or doc_b is None:
            self.recommend_view.setPlainText("Выберите пару спорный↔образец.")
            self.status_label.setText("")
            return
        form, reasons, bd = concl.recommend(self._pdb, self._project_id, doc_a, doc_b)
        html = [f"<b>Рекомендуемая форма: {concl.FORM_LABELS[form]}</b>", ""]
        html += [f"• {r}" for r in reasons]
        self.recommend_view.setHtml("<br>".join(html))
        idx = self.form_combo.findData(form)
        if idx >= 0:
            self.form_combo.setCurrentIndex(idx)
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
        try:
            concl.decide(self._pdb, self._project_id, doc_a, doc_b, form,
                         justification=self.justification_edit.toPlainText().strip(),
                         program_version=PROGRAM_VERSION)
        except ValueError as e:
            QMessageBox.warning(self, "Требуется обоснование", str(e))
            return
        self._refresh()
        QMessageBox.information(self, "Вывод зафиксирован",
                                f"Форма: {concl.FORM_LABELS[form]}")

    def _export_docx(self):
        doc_a, doc_b = self._pair()
        if self._project_id is None or doc_a is None or doc_b is None:
            return
        fp, _ = QFileDialog.getSaveFileName(
            self, "Сохранить отчёт исследования", "отчет_исследования.docx",
            "Word (*.docx)")
        if not fp:
            return
        try:
            from protocol.report import export_research_docx
            summary = export_research_docx(
                self._pdb, self._project_id, doc_a, doc_b, fp,
                program_version=PROGRAM_VERSION)
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, "Ошибка экспорта", str(e))
            return
        QMessageBox.information(
            self, "Отчёт сохранён",
            f"{summary['filepath']}\nSHA-256: {summary['sha256'][:16]}…")
