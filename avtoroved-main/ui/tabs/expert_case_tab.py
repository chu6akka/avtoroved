from __future__ import annotations

from pathlib import Path
import uuid

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox, QFileDialog, QFormLayout, QHBoxLayout, QInputDialog, QLabel,
    QLineEdit, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem,
    QTextEdit, QVBoxLayout, QWidget,
)

from expert_core import (
    CaseRepository, ComparisonService, DecisionGuard, ExpertReview,
    FeatureExtractionService, MethodProfile, ReportService, SuitabilityService,
)
from expert_core.models import ExpertStatus, TextObject, TextRole, VerdictType


class ExpertCaseTab(QWidget):
    request_current_text = pyqtSignal(str)  # роль

    def __init__(self, parent=None):
        super().__init__(parent)
        self.repo = CaseRepository()
        self.case = None
        self._profile = None
        self._build_ui()
        self._new_case()

    def _build_ui(self):
        root = QVBoxLayout(self)
        title = QLabel("Экспертное дело: методический процесс")
        title.setObjectName("title")
        root.addWidget(title)
        form = QFormLayout()
        self.case_title = QLineEdit("Новое автороведческое исследование")
        self.profile = QComboBox()
        self.profile.addItem("ЭКЦ МВД России, 2007", "mvd_2007")
        self.profile.addItem("Методика Минюста", "minjust")
        form.addRow("Наименование дела", self.case_title)
        form.addRow("Профиль методики", self.profile)
        root.addLayout(form)

        actions = QHBoxLayout()
        for label, slot in (
            ("Новое", self._new_case), ("Открыть .avedcase", self._open_case),
            ("Сохранить", self._save_case), ("Добавить спорный текст", lambda: self.request_current_text.emit("disputed")),
            ("Добавить образец", lambda: self.request_current_text.emit("free_sample")),
        ):
            button = QPushButton(label); button.clicked.connect(slot); actions.addWidget(button)
        root.addLayout(actions)

        self.objects = QTableWidget(0, 5)
        self.objects.setHorizontalHeaderLabels(["ID", "Роль", "Название", "Жанр", "Слов"])
        root.addWidget(self.objects)

        run_row = QHBoxLayout()
        run = QPushButton("Выполнить стадии 3–5")
        run.clicked.connect(self._run)
        run_row.addWidget(run)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        run_row.addWidget(self.status, 1)
        root.addLayout(run_row)

        self.method_control = QTextEdit()
        self.method_control.setReadOnly(True)
        self.method_control.setMaximumHeight(150)
        self.method_control.setPlaceholderText("Методический контроль: НН/НС/НСВ, количественные ориентиры, правило Вула и ограничения материала")
        root.addWidget(self.method_control)

        self.features = QTableWidget(0, 6)
        self.features.setHorizontalHeaderLabels(["Объект", "Признак", "Значение", "Источник", "Статус", "Подтвердить"])
        self.features.itemChanged.connect(self._feature_changed)
        root.addWidget(self.features)

        decision = QFormLayout()
        self.verdict = QComboBox()
        self.expert = QLineEdit()
        self.rationale = QTextEdit(); self.rationale.setMaximumHeight(70)
        decision.addRow("Допустимый вывод", self.verdict)
        decision.addRow("Эксперт", self.expert)
        decision.addRow("Мотивировка", self.rationale)
        root.addLayout(decision)
        bottom = QHBoxLayout()
        approve = QPushButton("Утвердить вывод"); approve.clicked.connect(self._approve); bottom.addWidget(approve)
        docx = QPushButton("Экспорт DOCX"); docx.clicked.connect(self._export_docx); bottom.addWidget(docx)
        package = QPushButton("Пакет проверки"); package.clicked.connect(self._export_package); bottom.addWidget(package)
        bottom.addStretch(); root.addLayout(bottom)

    def _new_case(self):
        self._profile = MethodProfile.bundled(self.profile.currentData())
        self.case = self.repo.create(self.case_title.text().strip() or "Новое дело", self._profile.id)
        self._refresh()

    def add_current_text(self, text: str, role: str):
        if not text.strip():
            QMessageBox.warning(self, "Нет текста", "Основное поле текста пусто.")
            return
        role_enum = TextRole(role)
        prefix = "Q" if role_enum is TextRole.DISPUTED else "S"
        number = 1 + sum(o.role is role_enum for o in self.case.objects)
        genre, ok = QInputDialog.getText(self, "Метаданные объекта", "Жанр текста:")
        if not ok:
            return
        obj = TextObject(
            id=f"{prefix}{number}", title=f"{prefix}{number}", text=text,
            role=role_enum, genre=genre.strip(), independent_authorship=None,
            compilation_suspected=None,
        )
        self.repo.add_text(self.case, obj)
        self._refresh()

    def _refresh(self):
        self.objects.setRowCount(len(self.case.objects))
        for row, obj in enumerate(self.case.objects):
            values = (obj.id, obj.role.value, obj.title, obj.genre, str(SuitabilityService.word_count(obj.text)))
            for col, value in enumerate(values):
                self.objects.setItem(row, col, QTableWidgetItem(value))
        self._fill_features()

    def _run(self):
        self._profile = MethodProfile.bundled(self.profile.currentData())
        self.case.method_profile = self._profile.id
        self.case.suitability = SuitabilityService().assess(self.case.objects, self._profile)
        extractor = FeatureExtractionService()
        self.case.observations = {o.id: extractor.analyze_object(o, self._profile) for o in self.case.objects}
        samples = [o for o in self.case.objects if o.role.is_sample]
        self.case.comparisons = [
            ComparisonService().compare(o, samples, self.case.observations, self._profile)
            for o in self.case.objects if o.role is TextRole.DISPUTED and samples
        ]
        self.repo.append_audit(self.case, "analysis_run", self.expert.text() or "expert", {"profile": self._profile.id})
        issues = "; ".join(i.message for i in self.case.suitability.issues)
        self.status.setText("Материал прошёл формальные проверки" if self.case.suitability.suitable else "Ограничения материала: " + issues)
        self._render_method_control()
        self._refresh(); self._update_allowed()

    def _fill_features(self):
        rows = [(oid, obs) for oid, items in self.case.observations.items() for obs in items]
        self.features.blockSignals(True); self.features.setRowCount(len(rows))
        self._feature_rows = rows
        for row, (oid, obs) in enumerate(rows):
            vals = (oid, obs.feature_id, str(obs.value), obs.source, obs.expert_status.value)
            for col, value in enumerate(vals): self.features.setItem(row, col, QTableWidgetItem(value))
            check = QTableWidgetItem(); check.setCheckState(
                Qt.CheckState.Checked if obs.expert_status is ExpertStatus.CONFIRMED
                else Qt.CheckState.Unchecked)
            self.features.setItem(row, 5, check)
        self.features.blockSignals(False)

    def _feature_changed(self, item):
        if item.column() != 5 or item.row() >= len(getattr(self, "_feature_rows", [])):
            return
        oid, obs = self._feature_rows[item.row()]
        if item.checkState() is Qt.CheckState.Checked:
            ExpertReview.confirm(obs); action = "feature_confirmed"
        else:
            obs.expert_status = ExpertStatus.UNREVIEWED; action = "feature_unconfirmed"
        self.repo.append_audit(self.case, action, self.expert.text() or "expert", {"object": oid, "feature": obs.feature_id})
        self._update_allowed()

    def _update_allowed(self):
        self.verdict.clear()
        comparison = self.case.comparisons[0] if self.case.comparisons else None
        disputed = next((o for o in self.case.objects if o.role is TextRole.DISPUTED), None)
        observations = self.case.observations.get(disputed.id, []) if disputed else []
        forms, reasons = DecisionGuard().allowed_verdicts(self.case.suitability, comparison, observations, self._profile)
        for verdict in sorted(forms, key=lambda v: v.value): self.verdict.addItem(verdict.value, verdict.value)
        if reasons: self.status.setText((self.status.text() + "; " if self.status.text() else "") + "; ".join(reasons))

    def _approve(self):
        try:
            self.case.decision = ExpertReview.decide(
                VerdictType(self.verdict.currentData()), self.rationale.toPlainText(), self.expert.text())
            self.repo.append_audit(self.case, "decision_approved", self.expert.text(), {"verdict": self.case.decision.verdict.value})
            QMessageBox.information(self, "Готово", "Вывод утверждён экспертом.")
        except Exception as exc: QMessageBox.warning(self, "Вывод недоступен", str(exc))

    def _render_method_control(self):
        comparisons = self.case.comparisons
        matches = {lv: 0 for lv in ("NN", "NS", "NSV")}
        differences = dict(matches)
        if comparisons:
            for feature in comparisons[0].features:
                try: level = self._profile.feature(feature.feature_id).level
                except Exception: continue
                if feature.outcome == "match": matches[level] += 1
                elif feature.outcome == "difference": differences[level] += 1
        limitations = [i.message for i in self.case.suitability.issues] if self.case.suitability else ["Пригодность не проверена"]
        self.method_control.setPlainText(
            "МЕТОДИЧЕСКИЙ КОНТРОЛЬ (не рекомендация формы вывода)\n"
            f"A. Рубцова — совпадения НН/НС/НСВ: {matches}; различия: {differences}.\n"
            "B. Моисеева—Огорелков — количественные ориентиры предъявляются как справочные условия.\n"
            "C. Общие признаки и правило Вула — автоматический вывод не формируется.\n"
            "D. Ограничения материала: " + ("; ".join(limitations) or "не выявлены формальными проверками")
        )

    def _password(self):
        value, ok = QInputDialog.getText(self, "Пароль дела", "Пароль (не менее 8 символов):", QLineEdit.EchoMode.Password)
        return value if ok else None

    def _save_case(self):
        path, _ = QFileDialog.getSaveFileName(self, "Сохранить дело", "", "Дело Авторовед (*.avedcase)")
        password = self._password() if path else None
        if path and password:
            try: self.repo.save(self.case, path, password)
            except Exception as exc: QMessageBox.critical(self, "Ошибка", str(exc))

    def _open_case(self):
        path, _ = QFileDialog.getOpenFileName(self, "Открыть дело", "", "Дело Авторовед (*.avedcase)")
        password = self._password() if path else None
        if path and password:
            try:
                self.case = self.repo.open(path, password); self.case_title.setText(self.case.title)
                idx = self.profile.findData(self.case.method_profile); self.profile.setCurrentIndex(max(0, idx))
                self._profile = MethodProfile.bundled(self.case.method_profile); self._refresh(); self._update_allowed()
            except Exception as exc: QMessageBox.critical(self, "Ошибка", str(exc))

    def _export_docx(self):
        path, _ = QFileDialog.getSaveFileName(self, "Проект заключения", "", "Word (*.docx)")
        if path:
            try: ReportService().export_docx(self.case, path)
            except Exception as exc: QMessageBox.critical(self, "Ошибка", str(exc))

    def _export_package(self):
        path, _ = QFileDialog.getSaveFileName(self, "Пакет проверки", "", "ZIP (*.zip)")
        if path:
            try: ReportService().export_verification_package(self.case, path)
            except Exception as exc: QMessageBox.critical(self, "Ошибка", str(exc))
