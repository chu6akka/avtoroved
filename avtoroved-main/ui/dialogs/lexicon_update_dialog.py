"""
ui/dialogs/lexicon_update_dialog.py — диалог «Обновить словарные базы».

Обновление только по явной команде; перед заменой — бэкап; версия (sha256,
дата, число записей) фиксируется в data/lexicons_meta.json и в журнале.
"""
from __future__ import annotations

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView, QMessageBox,
)

from protocol import lexicon_update as lu


class _UpdateThread(QThread):
    status = pyqtSignal(str)
    done = pyqtSignal(dict)
    failed = pyqtSignal(str)

    def __init__(self, key: str, parent=None):
        super().__init__(parent)
        self.key = key

    def run(self):
        try:
            self.done.emit(lu.update_source(self.key, status_cb=self.status.emit))
        except Exception as e:  # noqa: BLE001
            self.failed.emit(str(e))


class LexiconUpdateDialog(QDialog):
    """Список источников словарей: текущая версия + кнопка обновления."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Обновление словарных баз")
        self.resize(720, 320)
        self._thread: _UpdateThread | None = None

        layout = QVBoxLayout(self)
        warn = QLabel(
            "⚠ Обновление словаря меняет результаты последующих анализов — "
            "прежние отчёты останутся воспроизводимыми только на старой базе "
            "(она сохраняется в бэкап). Версия базы фиксируется в журнале.")
        warn.setWordWrap(True)
        warn.setStyleSheet("color: #f9e2af;")
        layout.addWidget(warn)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(
            ["Словарь", "Обновлён", "Записей", "SHA-256"])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.verticalHeader().setVisible(False)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for c in (1, 2, 3):
            hh.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.table, stretch=1)

        btns = QHBoxLayout()
        self.btn_update = QPushButton("⬇ Обновить выбранный словарь")
        self.btn_update.clicked.connect(self._update_selected)
        btns.addWidget(self.btn_update)
        btns.addStretch()
        btn_close = QPushButton("Закрыть")
        btn_close.clicked.connect(self.reject)
        btns.addWidget(btn_close)
        layout.addLayout(btns)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self._keys: list[str] = []
        self._reload()

    def _reload(self):
        meta = lu.read_meta()
        self.table.setRowCount(0)
        self._keys = []
        for key, src in lu.SOURCES.items():
            m = meta.get(key, {})
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(src["name"]))
            self.table.setItem(row, 1, QTableWidgetItem(
                m.get("updated_at", "— (поставляется с программой)")))
            self.table.setItem(row, 2, QTableWidgetItem(str(m.get("entries", "—"))))
            self.table.setItem(row, 3, QTableWidgetItem(
                (m.get("sha256", "") or "")[:12] or "—"))
            self._keys.append(key)
        if self.table.rowCount():
            self.table.selectRow(0)

    def _update_selected(self):
        row = self.table.currentRow()
        if row < 0 or row >= len(self._keys):
            return
        if self._thread is not None and self._thread.isRunning():
            return
        key = self._keys[row]
        if QMessageBox.question(
                self, "Обновить словарь?",
                f"Скачать свежую версию «{lu.SOURCES[key]['name']}»?\n"
                "Текущая база будет сохранена в бэкап.") != QMessageBox.StandardButton.Yes:
            return
        self.btn_update.setEnabled(False)
        self._thread = _UpdateThread(key, parent=self)
        self._thread.status.connect(self.status_label.setText)
        self._thread.done.connect(self._on_done)
        self._thread.failed.connect(self._on_failed)
        self._thread.start()

    def _on_done(self, summary: dict):
        self.btn_update.setEnabled(True)
        self._reload()
        self.status_label.setText(
            f"Обновлено: {summary['entries']} записей, "
            f"sha256 {summary['sha256'][:12]}…"
            + (f" Бэкап: {summary['backup']}" if summary['backup'] else ""))
        QMessageBox.information(
            self, "Словарь обновлён",
            "Новая база вступит в силу после перезапуска программы "
            "(движки кэшируют словарь в памяти).")

    def _on_failed(self, msg: str):
        self.btn_update.setEnabled(True)
        self.status_label.setText(f"Ошибка: {msg}")
        QMessageBox.critical(self, "Ошибка обновления", msg)
