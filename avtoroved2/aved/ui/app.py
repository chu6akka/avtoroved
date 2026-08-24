"""Главное окно: измерительный инструмент эксперта-автороведа (PyQt6).

Программа НЕ делает выводов об авторстве. Она даёт сухие верифицируемые показатели и
фактически найденные лексические маркеры (с примерами) — спорный текст и образцы рядом.
Оценку и выводы делает эксперт.
"""
from __future__ import annotations

import csv
import functools
import sys
import traceback
from pathlib import Path

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QListWidget,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from aved.core.models import Role
from aved.report import data_summary
from aved.ui.state import Session

_LOG_PATH = Path(__file__).resolve().parents[2] / "out" / "errors.log"


def _log_and_report(exc: BaseException, parent=None) -> None:
    tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    try:
        _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(_LOG_PATH, "a", encoding="utf-8") as fh:
            fh.write(tb + "\n" + "-" * 60 + "\n")
    except Exception:
        pass
    try:
        QMessageBox.critical(parent, "Ошибка",
                             f"Операция прервана:\n\n{type(exc).__name__}: {exc}\n\n"
                             f"Подробности: {_LOG_PATH}")
    except Exception:
        pass


def _excepthook(exc_type, exc, tb) -> None:
    exc.__traceback__ = tb
    _log_and_report(exc)


def slot_guard(method):
    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        try:
            return method(self, *args, **kwargs)
        except Exception as exc:  # noqa: BLE001
            QApplication.restoreOverrideCursor()
            _log_and_report(exc, self if isinstance(self, QWidget) else None)
    return wrapper


def _title(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setFont(QFont("", 15, QFont.Weight.Bold))
    return lbl


def _role_ru(role: str) -> str:
    return "спорный" if role == "disputed" else "образец"


class Worker(QThread):
    done = pyqtSignal()
    failed = pyqtSignal(object)

    def __init__(self, session: Session) -> None:
        super().__init__()
        self.session = session

    def run(self) -> None:
        try:
            self.session.compute_profiles()
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(exc)
            return
        self.done.emit()


class ObjectsPage(QWidget):
    def __init__(self, session: Session, on_done) -> None:
        super().__init__()
        self.session = session
        self.on_done = on_done
        lay = QVBoxLayout(self)
        lay.addWidget(_title("1. Объекты исследования"))
        lay.addWidget(QLabel("Добавьте спорный текст и тексты-образцы (.txt или вставкой)."))

        bar = QHBoxLayout()
        b1 = QPushButton("+ Спорный (файл)")
        b1.clicked.connect(lambda: self._add_files(Role.DISPUTED, False))
        b2 = QPushButton("+ Образцы (файлы)")
        b2.clicked.connect(lambda: self._add_files(Role.SAMPLE, True))
        b3 = QPushButton("+ Вставить текст…")
        b3.clicked.connect(lambda: self._add_pasted())
        for b in (b1, b2, b3):
            bar.addWidget(b)
        lay.addLayout(bar)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Роль", "Заголовок", "Символов"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        lay.addWidget(self.table)

        row = QHBoxLayout()
        rm = QPushButton("Удалить выбранный")
        rm.clicked.connect(lambda: self._remove())
        row.addWidget(rm)
        row.addStretch()
        go = QPushButton("Сформировать показатели →")
        go.clicked.connect(lambda: self._run())
        row.addWidget(go)
        lay.addLayout(row)

    @slot_guard
    def _add_files(self, role: Role, multi: bool) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "Текстовые файлы", "", "Текст (*.txt)")
        for p in (paths if multi else paths[:1]):
            self.session.add(Path(p).name, Path(p).read_text(encoding="utf-8", errors="ignore"), role)
        self.refresh()

    @slot_guard
    def _add_pasted(self) -> None:
        text, ok = QInputDialog.getMultiLineText(self, "Вставить текст", "Текст объекта:")
        if not ok or not text.strip():
            return
        roles = {"Спорный": Role.DISPUTED, "Образец": Role.SAMPLE}
        choice, ok = QInputDialog.getItem(self, "Роль", "Роль текста:", list(roles), 0, False)
        if ok:
            self.session.add("вставленный текст", text, roles[choice])
            self.refresh()

    @slot_guard
    def _remove(self) -> None:
        r = self.table.currentRow()
        if r >= 0:
            self.session.remove(r)
            self.refresh()

    @slot_guard
    def _run(self) -> None:
        if not self.session.objects:
            QMessageBox.warning(self, "Нет объектов", "Добавьте хотя бы один текст.")
            return
        self._progress = QProgressDialog("Идёт разбор текстов…", None, 0, 0, self)
        self._progress.setWindowModality(Qt.WindowModality.ApplicationModal)
        self._progress.setMinimumDuration(0)
        self._progress.show()
        self._worker = Worker(self.session)
        self._worker.done.connect(self._finish)
        self._worker.failed.connect(self._fail)
        self._worker.start()

    def _finish(self) -> None:
        self._progress.close()
        self.on_done()

    def _fail(self, exc) -> None:
        self._progress.close()
        _log_and_report(exc, self)

    def refresh(self) -> None:
        self.table.setRowCount(len(self.session.objects))
        for i, o in enumerate(self.session.objects):
            for col, val in enumerate([_role_ru(o.role.value), o.title, str(len(o.text))]):
                self.table.setItem(i, col, QTableWidgetItem(val))


class ResultsPage(QWidget):
    def __init__(self, session: Session) -> None:
        super().__init__()
        self.session = session
        lay = QVBoxLayout(self)
        lay.addWidget(_title("2. Показатели — сухие данные для эксперта"))
        lay.addWidget(QLabel("Программа не делает выводов об авторстве. Сравнение и оценку "
                             "проводит эксперт."))

        lay.addWidget(QLabel("Количественные показатели (спорный и образцы рядом):"))
        self.table = QTableWidget(0, 1)
        lay.addWidget(self.table, 3)

        lay.addWidget(QLabel("Фактически найденные лексические маркеры (с примерами):"))
        self.markers = QTreeWidget()
        self.markers.setHeaderLabels(["Объект / маркер", "Найдено и примеры"])
        self.markers.setColumnWidth(0, 360)
        lay.addWidget(self.markers, 2)

        row = QHBoxLayout()
        row.addStretch()
        csv_btn = QPushButton("Экспорт таблицы (CSV)")
        csv_btn.clicked.connect(lambda: self._export_csv())
        row.addWidget(csv_btn)
        docx_btn = QPushButton("Экспорт сводки (DOCX)")
        docx_btn.clicked.connect(lambda: self._export_docx())
        row.addWidget(docx_btn)
        lay.addLayout(row)

    def refresh(self) -> None:
        profiles = self.session.profiles
        ids = list(profiles)
        names = list(profiles[ids[0]]["metrics"]) if ids else []

        self.table.setColumnCount(1 + len(ids))
        self.table.setRowCount(len(names))
        self.table.setHorizontalHeaderLabels(
            ["Показатель"] + [f"{profiles[i]['title']} ({_role_ru(profiles[i]['role'])})" for i in ids]
        )
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for r, name in enumerate(names):
            self.table.setItem(r, 0, QTableWidgetItem(name))
            for c, i in enumerate(ids):
                self.table.setItem(r, c + 1, QTableWidgetItem(str(profiles[i]["metrics"][name])))

        self.markers.clear()
        for i in ids:
            p = profiles[i]
            top = QTreeWidgetItem([f"{p['title']} ({_role_ru(p['role'])})", ""])
            if not p["markers"]:
                top.addChild(QTreeWidgetItem(["— маркеры не обнаружены", ""]))
            for m in p["markers"]:
                top.addChild(QTreeWidgetItem(
                    [f"{m['name']} ({m['source']})",
                     f"{m['count']} (на 1000: {m['rate']}) — {', '.join(m['examples'][:4])}"]
                ))
            self.markers.addTopLevelItem(top)
            top.setExpanded(True)

    @slot_guard
    def _export_docx(self) -> None:
        if not self.session.profiles:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Сохранить сводку", "svodka.docx", "Word (*.docx)")
        if path:
            data_summary.generate(self.session.profiles, path)
            QMessageBox.information(self, "Готово", f"Сводка сохранена:\n{path}")

    @slot_guard
    def _export_csv(self) -> None:
        profiles = self.session.profiles
        if not profiles:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Сохранить таблицу", "pokazateli.csv", "CSV (*.csv)")
        if not path:
            return
        ids = list(profiles)
        names = list(profiles[ids[0]]["metrics"])
        with open(path, "w", encoding="utf-8-sig", newline="") as fh:
            w = csv.writer(fh, delimiter=";")
            w.writerow(["Показатель"] + [profiles[i]["title"] for i in ids])
            for name in names:
                w.writerow([name] + [profiles[i]["metrics"][name] for i in ids])
        QMessageBox.information(self, "Готово", f"Таблица сохранена:\n{path}")


class MainWindow(QWidget):
    STEPS = ["1. Объекты", "2. Показатели"]

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Автороведческий анализатор — измерения для эксперта (методика 2007)")
        self.resize(1040, 720)
        self.session = Session()

        self.nav = QListWidget()
        self.nav.addItems(self.STEPS)
        self.nav.setMaximumWidth(170)
        self.nav.currentRowChanged.connect(lambda i: self.stack.setCurrentIndex(i))

        self.stack = QStackedWidget()
        self.objects_page = ObjectsPage(self.session, self._show_results)
        self.results_page = ResultsPage(self.session)
        self.stack.addWidget(self.objects_page)
        self.stack.addWidget(self.results_page)

        body = QHBoxLayout(self)
        body.addWidget(self.nav)
        body.addWidget(self.stack, 1)
        self.nav.setCurrentRow(0)

    def _show_results(self) -> None:
        self.results_page.refresh()
        self.nav.setCurrentRow(1)


def main() -> None:
    app = QApplication(sys.argv)
    sys.excepthook = _excepthook
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
