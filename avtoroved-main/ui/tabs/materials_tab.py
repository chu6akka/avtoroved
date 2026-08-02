"""
ui/tabs/materials_tab.py — вкладка «Материалы» раздела «Экспертный протокол».

Создание проекта, импорт спорных текстов и образцов (TXT/DOCX/PDF), просмотр
сводки по документам и журнала действий. NLP-разметка идёт в фоновом потоке,
переиспользуя уже инициализированный в приложении бэкенд (StanzaBackend),
поэтому интерфейс не блокируется на загрузке модели.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
    QLineEdit, QTableWidget, QTableWidgetItem, QHeaderView, QFileDialog,
    QMessageBox, QDialog, QDialogButtonBox, QFormLayout, QTextEdit,
    QAbstractItemView,
)

from protocol import db as protocol_db
from protocol import ingest
from protocol import PROGRAM_VERSION


class _ImportThread(QThread):
    """Фоновый импорт одного документа (sha256, слои, NLP-разметка)."""
    status = pyqtSignal(str)
    done = pyqtSignal(dict)
    failed = pyqtSignal(str)

    def __init__(self, pdb, project_id, filepath, role, backend,
                 provenance, genre, note, parent=None):
        super().__init__(parent)
        self.pdb = pdb
        self.project_id = project_id
        self.filepath = filepath
        self.role = role
        self.backend = backend
        self.provenance = provenance
        self.genre = genre
        self.note = note

    def run(self):
        try:
            summary = ingest.import_document(
                self.pdb, self.project_id, self.filepath, self.role,
                self.backend, provenance=self.provenance, genre=self.genre,
                note=self.note, program_version=PROGRAM_VERSION,
                status_cb=self.status.emit)
            self.done.emit(summary)
        except Exception as e:  # noqa: BLE001 — показываем пользователю
            self.failed.emit(str(e))


class _NewProjectDialog(QDialog):
    """Диалог создания проекта."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Создать проект")
        self.resize(420, 200)
        form = QFormLayout(self)
        self.name_edit = QLineEdit()
        self.expert_edit = QLineEdit()
        self.note_edit = QLineEdit()
        form.addRow("Название дела:", self.name_edit)
        form.addRow("Эксперт:", self.expert_edit)
        form.addRow("Примечание:", self.note_edit)
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        form.addRow(btns)

    def values(self) -> dict:
        return {
            "name": self.name_edit.text().strip(),
            "expert_name": self.expert_edit.text().strip() or None,
            "note": self.note_edit.text().strip() or None,
        }


class MaterialsTab(QWidget):
    """Вкладка «Материалы»: проекты, документы, слои, журнал."""

    def __init__(self, nlp_backend, parent=None):
        super().__init__(parent)
        self._backend = nlp_backend          # переиспользуемый StanzaBackend/SpacyBackend
        self._pdb = protocol_db.ProtocolDB()  # protocol.db рядом с программой
        self._project_id: int | None = None
        self._import_thread: _ImportThread | None = None

        self._build_ui()
        self._reload_projects()

    # ── построение UI ────────────────────────────────────────────────────────
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        title = QLabel("Материалы экспертизы")
        title.setObjectName("subtitle")
        layout.addWidget(title)

        # ── Строка проекта ───────────────────────────────────────────────────
        prj_row = QHBoxLayout()
        prj_row.addWidget(QLabel("Проект:"))
        self.project_combo = QComboBox()
        self.project_combo.setMinimumWidth(280)
        self.project_combo.currentIndexChanged.connect(self._on_project_changed)
        prj_row.addWidget(self.project_combo)
        btn_new = QPushButton("➕ Создать проект")
        btn_new.clicked.connect(self._create_project)
        prj_row.addWidget(btn_new)
        self.btn_del_project = QPushButton("🗑 Удалить проект")
        self.btn_del_project.setObjectName("danger")
        self.btn_del_project.setToolTip(
            "Удалить дело целиком: материалы, разметку, признаки, решения, "
            "сравнения и выводы. Действие необратимо.")
        self.btn_del_project.clicked.connect(self._delete_project)
        prj_row.addWidget(self.btn_del_project)
        prj_row.addStretch()
        layout.addLayout(prj_row)

        # ── Метаданные следующего импорта ────────────────────────────────────
        meta_row = QHBoxLayout()
        meta_row.addWidget(QLabel("Происхождение:"))
        self.provenance_combo = QComboBox()
        self.provenance_combo.addItems(protocol_db.PROVENANCE_VALUES)
        meta_row.addWidget(self.provenance_combo)
        meta_row.addWidget(QLabel("Жанр:"))
        self.genre_edit = QLineEdit()
        self.genre_edit.setPlaceholderText("напр. письмо, статья…")
        self.genre_edit.setMaximumWidth(160)
        meta_row.addWidget(self.genre_edit)
        meta_row.addWidget(QLabel("Примечание:"))
        self.note_edit = QLineEdit()
        self.note_edit.setPlaceholderText("необязательно")
        meta_row.addWidget(self.note_edit)
        layout.addLayout(meta_row)

        # ── Кнопки импорта / журнала ─────────────────────────────────────────
        btn_row = QHBoxLayout()
        self.btn_disputed = QPushButton("📄 Добавить спорный текст")
        self.btn_disputed.clicked.connect(lambda: self._add_document(protocol_db.ROLE_DISPUTED))
        btn_row.addWidget(self.btn_disputed)
        self.btn_sample = QPushButton("📑 Добавить образец")
        self.btn_sample.clicked.connect(lambda: self._add_document(protocol_db.ROLE_SAMPLE))
        btn_row.addWidget(self.btn_sample)
        self.btn_delete = QPushButton("🗑 Удалить материал")
        self.btn_delete.setObjectName("danger")
        self.btn_delete.setToolTip(
            "Удалить выбранный в таблице материал со всеми производными "
            "данными. Действие необратимо.")
        self.btn_delete.clicked.connect(self._delete_document)
        btn_row.addWidget(self.btn_delete)
        btn_row.addStretch()
        self.btn_journal = QPushButton("🧾 Открыть журнал")
        self.btn_journal.clicked.connect(self._open_journal)
        btn_row.addWidget(self.btn_journal)
        layout.addLayout(btn_row)

        # ── Таблица документов ───────────────────────────────────────────────
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            ["Имя файла", "Роль", "SHA-256", "Словоформы", "Предлож.", "Токены", "Статус"])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setStyleSheet("QTableWidget::item { padding: 6px 8px; }")
        self.table.verticalHeader().setVisible(False)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for c in range(1, 7):
            hh.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.table, stretch=1)

        # ── Строка статуса ───────────────────────────────────────────────────
        self.status_label = QLabel("Создайте проект, чтобы начать.")
        self.status_label.setObjectName("caption")
        layout.addWidget(self.status_label)

    # ── проекты ──────────────────────────────────────────────────────────────
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
        self._update_buttons()

    def _on_project_changed(self, index: int):
        if index < 0:
            self._project_id = None
        else:
            self._project_id = self.project_combo.itemData(index)
            self._reload_documents()
        self._update_buttons()

    def _create_project(self):
        dlg = _NewProjectDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        vals = dlg.values()
        if not vals["name"]:
            QMessageBox.warning(self, "Нет названия", "Укажите название дела.")
            return
        pid = self._pdb.create_project(
            vals["name"], expert_name=vals["expert_name"],
            program_version=PROGRAM_VERSION, note=vals["note"])
        self._pdb.log_action("создан проект", project_id=pid,
                             details={"name": vals["name"]},
                             program_version=PROGRAM_VERSION)
        self._reload_projects()
        # Выбрать только что созданный проект.
        idx = self.project_combo.findData(pid)
        if idx >= 0:
            self.project_combo.setCurrentIndex(idx)
        self.status_label.setText(f"Проект «{vals['name']}» создан.")

    # ── документы ────────────────────────────────────────────────────────────
    def _add_document(self, role: str):
        if self._project_id is None:
            QMessageBox.warning(self, "Нет проекта", "Сначала создайте проект.")
            return
        if self._import_thread is not None and self._import_thread.isRunning():
            QMessageBox.information(self, "Идёт импорт", "Дождитесь завершения текущего импорта.")
            return

        exts = " ".join(f"*{e}" for e in ingest.SUPPORTED_EXTS)
        pdf_note = "" if ingest.PDF_AVAILABLE else "  (PDF недоступен: установите pypdf)"
        fp, _ = QFileDialog.getOpenFileName(
            self, f"Выбрать файл — {role}", "",
            f"Тексты ({exts});;Все файлы (*)")
        if not fp:
            return

        provenance = self.provenance_combo.currentText()
        genre = self.genre_edit.text().strip() or None
        note = self.note_edit.text().strip() or None

        self._set_busy(True)
        self.status_label.setText(f"Импорт ({role})…{pdf_note}")
        self._import_thread = _ImportThread(
            self._pdb, self._project_id, fp, role, self._backend,
            provenance, genre, note, parent=self)
        self._import_thread.status.connect(self.status_label.setText)
        self._import_thread.done.connect(self._on_import_done)
        self._import_thread.failed.connect(self._on_import_failed)
        self._import_thread.start()

    def _on_import_done(self, summary: dict):
        self._set_busy(False)
        status = summary.get("extraction_status", ingest.STATUS_OK)
        reason = summary.get("extraction_reason", "")
        self.status_label.setText(
            f"Импортирован «{summary['filename']}»: "
            f"{summary['word_count']} словоформ, "
            f"{summary['sentence_count']} предлож., {summary['token_count']} токенов "
            f"— статус извлечения: {status}.")
        self._reload_documents()
        # Не даём пустому документу молча «уехать дальше».
        if status == ingest.STATUS_EMPTY:
            QMessageBox.warning(
                self, "Текст не извлечён",
                f"«{summary['filename']}»: {reason}.\n\n"
                "Документ сохранён, но помечен красным — для экспертизы он непригоден "
                "без повторного извлечения текста (например, OCR для скана).")
        elif status == ingest.STATUS_LOW:
            QMessageBox.information(
                self, "Малый объём",
                f"«{summary['filename']}»: {reason}.")

    def _on_import_failed(self, msg: str):
        self._set_busy(False)
        self.status_label.setText("Ошибка импорта.")
        QMessageBox.critical(self, "Ошибка импорта", msg)

    def _reload_documents(self):
        self.table.setRowCount(0)
        self._doc_ids = []          # id материалов по строкам таблицы
        if self._project_id is None:
            return
        docs = self._pdb.fetch_documents(self._project_id)
        for doc in docs:
            did = doc["id"]
            self._doc_ids.append(did)
            n_sent = self._pdb.count_sentences(did)
            n_tok = self._pdb.count_tokens(did)
            # Оценка извлечения (единый источник истины — ingest.assess_extraction).
            status, reason = ingest.assess_extraction(
                doc["filename"], doc["word_count"], n_tok)
            sha_short = (doc["file_sha256"] or "")[:12]
            row = self.table.rowCount()
            self.table.insertRow(row)
            self._set_cell(row, 0, doc["filename"])
            self._set_cell(row, 1, doc["role"])
            self._set_cell(row, 2, sha_short)
            self._set_cell(row, 3, str(doc["word_count"] if doc["word_count"] is not None else "—"))
            self._set_cell(row, 4, str(n_sent))
            self._set_cell(row, 5, str(n_tok))
            self._set_status_cell(row, 6, status, reason)
        self._update_buttons()

    # Цвета статуса извлечения: пусто — красный, мало — жёлтый, ок — обычный.
    _STATUS_ICON = {
        ingest.STATUS_EMPTY: "❌ пусто",
        ingest.STATUS_LOW: "⚠ мало",
        ingest.STATUS_OK: "✓ ок",
    }
    _STATUS_COLOR = {
        ingest.STATUS_EMPTY: "#f38ba8",
        ingest.STATUS_LOW: "#f9e2af",
        ingest.STATUS_OK: None,
    }

    def _set_status_cell(self, row: int, col: int, status: str, reason: str):
        item = QTableWidgetItem(self._STATUS_ICON.get(status, status))
        item.setToolTip(reason)
        color = self._STATUS_COLOR.get(status)
        if color:
            item.setForeground(QColor(color))
        self.table.setItem(row, col, item)

    def _set_cell(self, row: int, col: int, text: str):
        item = QTableWidgetItem(text)
        if col in (3, 4, 5):
            item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.table.setItem(row, col, item)

    # ── удаление материалов и проектов ───────────────────────────────────────
    @staticmethod
    def _counts_text(counts: dict) -> str:
        return "\n".join(f"  • {k}: {v}" for k, v in counts.items() if v)

    def _confirm_destructive(self, title: str, head: str, counts: dict) -> bool:
        """Подтверждение с перечнем того, что будет удалено (по умолчанию — нет)."""
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle(title)
        box.setText(head)
        body = self._counts_text(counts)
        box.setInformativeText(
            (f"Будет удалено:\n{body}\n\n" if body else "")
            + "Действие необратимо. Факт удаления будет записан в журнал.")
        btn_del = box.addButton("Удалить", QMessageBox.ButtonRole.DestructiveRole)
        btn_cancel = box.addButton("Отмена", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(btn_cancel)
        box.exec()
        return box.clickedButton() is btn_del

    def _selected_document_id(self) -> int | None:
        row = self.table.currentRow()
        if row < 0 or row >= len(getattr(self, "_doc_ids", [])):
            return None
        return self._doc_ids[row]

    def _delete_document(self):
        did = self._selected_document_id()
        if did is None:
            QMessageBox.information(self, "Не выбран материал",
                                    "Выделите строку материала в таблице.")
            return
        doc = self._pdb.get_document(did)
        counts = self._pdb.document_deletion_preview(did)
        if not self._confirm_destructive(
                "Удалить материал?",
                f"Материал «{doc['filename']}» ({doc['role']}) будет удалён "
                "вместе со всеми производными данными.", counts):
            return
        try:
            summary = self._pdb.delete_document(did, program_version=PROGRAM_VERSION)
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, "Ошибка удаления", str(e))
            return
        self._reload_documents()
        self.status_label.setText(f"Материал «{summary['filename']}» удалён.")

    def _delete_project(self):
        if self._project_id is None:
            QMessageBox.information(self, "Нет проекта", "Проект не выбран.")
            return
        project = self._pdb.get_project(self._project_id)
        counts = self._pdb.project_deletion_preview(self._project_id)
        if not self._confirm_destructive(
                "Удалить проект?",
                f"Дело «{project['name']}» будет удалено целиком, включая "
                "журнал проекта.", counts):
            return
        try:
            summary = self._pdb.delete_project(self._project_id,
                                               program_version=PROGRAM_VERSION)
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, "Ошибка удаления", str(e))
            return
        self._reload_projects()
        self.status_label.setText(
            f"Проект «{summary['name']}» удалён. Запись об удалении — в журнале.")

    # ── журнал ───────────────────────────────────────────────────────────────
    def _open_journal(self):
        if self._project_id is None:
            QMessageBox.information(self, "Нет проекта", "Сначала создайте проект.")
            return
        rows = self._pdb.fetch_audit_log(self._project_id)

        dlg = QDialog(self)
        dlg.setWindowTitle("Журнал действий проекта")
        dlg.resize(760, 480)
        v = QVBoxLayout(dlg)
        table = QTableWidget(len(rows), 4)
        table.setHorizontalHeaderLabels(["Время", "Действие", "Детали", "Версия"])
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        for r, row in enumerate(rows):
            table.setItem(r, 0, QTableWidgetItem(row["ts"]))
            table.setItem(r, 1, QTableWidgetItem(row["action"]))
            table.setItem(r, 2, QTableWidgetItem(row["details"] or ""))
            table.setItem(r, 3, QTableWidgetItem(row["program_version"] or ""))
        v.addWidget(table)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btns.rejected.connect(dlg.reject)
        btns.accepted.connect(dlg.accept)
        v.addWidget(btns)
        dlg.exec()

    # ── вспомогательное ──────────────────────────────────────────────────────
    def _set_busy(self, busy: bool):
        self.btn_disputed.setEnabled(not busy)
        self.btn_sample.setEnabled(not busy)

    def _update_buttons(self):
        has_project = self._project_id is not None
        self.btn_disputed.setEnabled(has_project)
        self.btn_sample.setEnabled(has_project)
        self.btn_journal.setEnabled(has_project)
        self.btn_del_project.setEnabled(has_project)
        self.btn_delete.setEnabled(has_project and self.table.rowCount() > 0)
        if not has_project:
            self.status_label.setText("Создайте проект, чтобы начать.")
