"""
Вкладка 11: Модель / Корпус — управление самообучением.
"""
from __future__ import annotations
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QLabel, QPushButton, QProgressBar, QTableWidget,
    QTableWidgetItem, QHeaderView, QMessageBox, QSplitter
)
from PyQt6.QtCore import Qt, pyqtSignal, QThread
from PyQt6.QtGui import QColor

from analyzer import corpus_manager, learning_backend as lb_module
from analyzer import rusvec_engine as rusvec_module


class TrainThread(QThread):
    """Фоновый поток обучения FastText — не блокирует UI."""
    status   = pyqtSignal(str)
    finished = pyqtSignal(bool)   # success

    def __init__(self, lb, sentences, parent=None):
        super().__init__(parent)
        self.lb = lb
        self.sentences = sentences

    def run(self):
        ok_ft = self.lb.update(self.sentences, status_cb=self.status.emit)
        self.finished.emit(ok_ft)


class ExpandThread(QThread):
    """Фоновый поток расширения словарей через Navec."""
    status   = pyqtSignal(str)
    finished = pyqtSignal(dict)   # {domain: added_count}

    def __init__(self, rusvec, parent=None):
        super().__init__(parent)
        self.rusvec = rusvec

    def run(self):
        if not self.rusvec.is_downloaded:
            ok = self.rusvec.download(status_cb=self.status.emit)
            if not ok:
                self.finished.emit({})
                return
        if not self.rusvec.is_ready:
            ok = self.rusvec.load(status_cb=self.status.emit)
            if not ok:
                self.finished.emit({})
                return
        added = self.rusvec.expand_all_domains(status_cb=self.status.emit)
        self.finished.emit(added)


class DownloadNavecThread(QThread):
    """Фоновый поток скачивания модели Navec."""
    status   = pyqtSignal(str)
    finished = pyqtSignal(bool)

    def __init__(self, rusvec, parent=None):
        super().__init__(parent)
        self.rusvec = rusvec

    def run(self):
        ok = self.rusvec.download(status_cb=self.status.emit)
        if ok:
            ok = self.rusvec.load(status_cb=self.status.emit)
        self.finished.emit(ok)


class LearningTab(QWidget):
    """Вкладка управления корпусом и моделью самообучения."""

    train_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._lb        = lb_module.get()
        self._rusvec    = rusvec_module.get()
        self._train_thread   = None
        self._expand_thread  = None
        self._download_thread = None
        self._setup_ui()
        self.refresh()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        lbl = QLabel(
            "Программа накапливает корпус из анализируемых текстов и дообучает "
            "FastText для сравнения текстов. Расширение тематических словарей — "
            "через Navec (предобученные векторы на 12 млрд токенов)."
        )
        lbl.setWordWrap(True)
        lbl.setObjectName("subtitle")
        layout.addWidget(lbl)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # ── Левая панель ──────────────────────────────────────────────────
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)

        # Корпус
        corpus_group = QGroupBox("Корпус текстов")
        corpus_form = QVBoxLayout(corpus_group)
        self.lbl_texts  = QLabel("Текстов: —")
        self.lbl_words  = QLabel("Слов: —")
        self.lbl_last   = QLabel("Последнее пополнение: —")
        self.lbl_status = QLabel("Статус: —")
        self.lbl_status.setWordWrap(True)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, corpus_manager.MIN_WORDS_FOR_TRAINING)
        self.progress_bar.setFormat("%v / %m слов до первого обучения")
        self.progress_bar.setTextVisible(True)
        for w in [self.lbl_texts, self.lbl_words, self.lbl_last,
                  self.lbl_status, self.progress_bar]:
            corpus_form.addWidget(w)
        btn_row = QHBoxLayout()
        self.btn_refresh = QPushButton("🔄 Обновить")
        self.btn_refresh.setObjectName("secondary")
        self.btn_refresh.clicked.connect(self.refresh)
        btn_row.addWidget(self.btn_refresh)
        self.btn_clear_corpus = QPushButton("🗑 Очистить корпус")
        self.btn_clear_corpus.setObjectName("danger")
        self.btn_clear_corpus.clicked.connect(self._clear_corpus)
        btn_row.addWidget(self.btn_clear_corpus)
        corpus_form.addLayout(btn_row)
        left_layout.addWidget(corpus_group)

        # FastText (только для сравнения текстов)
        ft_group = QGroupBox("FastText — сравнение текстов")
        ft_form  = QVBoxLayout(ft_group)
        self.lbl_ft_status = QLabel("FastText: не обучена")
        self.lbl_vocab     = QLabel("Словарь: —")
        note = QLabel("Используется для семантического сходства в «Сравнении».\nТематические словари НЕ изменяет.")
        note.setObjectName("caption")
        note.setWordWrap(True)
        self.train_status = QLabel("")
        self.train_status.setWordWrap(True)
        self.train_status.setObjectName("subtitle")
        for w in [self.lbl_ft_status, self.lbl_vocab, note, self.train_status]:
            ft_form.addWidget(w)
        self.btn_train = QPushButton("▶ Обучить FastText")
        self.btn_train.clicked.connect(self._run_training)
        ft_form.addWidget(self.btn_train)
        left_layout.addWidget(ft_group)

        left_layout.addStretch()
        splitter.addWidget(left)

        # ── Правая панель: Navec ──────────────────────────────────────────
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(6)

        # Navec статус
        navec_group = QGroupBox("Navec — расширение тематических словарей")
        navec_form  = QVBoxLayout(navec_group)
        self.lbl_navec_status = QLabel()
        self._update_navec_status_label()
        self.lbl_navec_status.setWordWrap(True)
        navec_desc = QLabel(
            "Предобученные векторы (Natasha / Яндекс).\n"
            "12 млрд токенов · 500 тыс. слов · ~50 МБ.\n"
            "Скачивается один раз, хранится локально."
        )
        navec_desc.setObjectName("caption")
        navec_desc.setWordWrap(True)
        self.navec_op_status = QLabel("")
        self.navec_op_status.setWordWrap(True)
        self.navec_op_status.setObjectName("subtitle")
        for w in [self.lbl_navec_status, navec_desc, self.navec_op_status]:
            navec_form.addWidget(w)

        navec_btn_row = QHBoxLayout()
        self.btn_download_navec = QPushButton("⬇ Скачать Navec (~50 МБ)")
        self.btn_download_navec.setObjectName("primary")
        self.btn_download_navec.clicked.connect(self._download_navec)
        navec_btn_row.addWidget(self.btn_download_navec)
        self.btn_expand = QPushButton("✨ Расширить словари")
        self.btn_expand.setObjectName("secondary")
        self.btn_expand.clicked.connect(self._run_expand)
        self.btn_expand.setToolTip(
            "Найти слова, семантически близкие к словам словарей,\n"
            "и добавить их в тематические JSON-файлы."
        )
        navec_btn_row.addWidget(self.btn_expand)
        navec_form.addLayout(navec_btn_row)
        right_layout.addWidget(navec_group)

        # Таблица результатов расширения
        result_group = QGroupBox("Результат расширения")
        result_layout = QVBoxLayout(result_group)
        self.dict_table = QTableWidget(0, 2)
        self.dict_table.setHorizontalHeaderLabels(["Домен", "Добавлено слов"])
        self.dict_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch)
        self.dict_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.ResizeToContents)
        self.dict_table.setAlternatingRowColors(True)
        self.dict_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.dict_table.verticalHeader().setVisible(False)
        result_layout.addWidget(self.dict_table)
        self.lbl_dict_status = QLabel("Нажмите «Расширить словари» для запуска.")
        self.lbl_dict_status.setObjectName("subtitle")
        self.lbl_dict_status.setWordWrap(True)
        result_layout.addWidget(self.lbl_dict_status)
        right_layout.addWidget(result_group)

        splitter.addWidget(right)
        splitter.setSizes([380, 420])
        layout.addWidget(splitter)

    # ── Обновление ────────────────────────────────────────────────────────

    def _update_navec_status_label(self):
        if self._rusvec.is_ready:
            self.lbl_navec_status.setText("Navec: загружен ✓")
            self.lbl_navec_status.setStyleSheet("color: #a6e3a1;")
        elif self._rusvec.is_downloaded:
            self.lbl_navec_status.setText("Navec: скачан, не загружен в память")
            self.lbl_navec_status.setStyleSheet("color: #fab387;")
        else:
            self.lbl_navec_status.setText("Navec: не скачан")
            self.lbl_navec_status.setStyleSheet("color: #f38ba8;")

    def refresh(self):
        s = corpus_manager.stats()
        self.lbl_texts.setText(f"Текстов: {s['total_texts']}")
        self.lbl_words.setText(f"Слов: {s['total_words']:,}".replace(",", " "))
        self.lbl_last.setText(f"Последнее пополнение: {s['last_added']}")

        if s["ready_for_training"]:
            self.lbl_status.setText("Статус: корпус готов к обучению")
            self.lbl_status.setStyleSheet("color: #a6e3a1;")
            self.progress_bar.setValue(corpus_manager.MIN_WORDS_FOR_TRAINING)
        else:
            need = s["words_needed"]
            self.lbl_status.setText(f"Статус: накопление — ещё ~{need:,} слов".replace(",", " "))
            self.lbl_status.setStyleSheet("color: #fab387;")
            self.progress_bar.setValue(s["total_words"])

        if self._lb.ft_ready:
            self.lbl_ft_status.setText("FastText: обучена ✓")
            self.lbl_ft_status.setStyleSheet("color: #a6e3a1;")
            self.lbl_vocab.setText(f"Словарь: {self._lb.vocab_size:,} слов".replace(",", " "))
        else:
            self.lbl_ft_status.setText("FastText: не обучена")
            self.lbl_ft_status.setStyleSheet("color: #f38ba8;")
            self.lbl_vocab.setText("Словарь: —")

        can_train = s["ready_for_training"]
        self.btn_train.setEnabled(can_train and self._train_thread is None)
        if not can_train:
            self.btn_train.setToolTip(
                f"Нужно минимум {corpus_manager.MIN_WORDS_FOR_TRAINING:,} слов".replace(",", " "))

        self._update_navec_status_label()
        busy = self._expand_thread is not None or self._download_thread is not None
        self.btn_download_navec.setEnabled(not self._rusvec.is_downloaded and not busy)
        self.btn_expand.setEnabled(not busy)

    def update_dict_table(self, expanded: dict):
        self.dict_table.setRowCount(0)
        if not expanded:
            self.lbl_dict_status.setText("Новых слов не найдено.")
            return
        self.dict_table.setRowCount(len(expanded))
        for row, (domain, count) in enumerate(sorted(expanded.items())):
            self.dict_table.setItem(row, 0, QTableWidgetItem(domain))
            cnt = QTableWidgetItem(f"+{count}")
            cnt.setForeground(QColor("#a6e3a1"))
            cnt.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.dict_table.setItem(row, 1, cnt)
        total = sum(expanded.values())
        self.lbl_dict_status.setText(
            f"Добавлено слов: {total} по {len(expanded)} доменам.")

    # ── FastText обучение ─────────────────────────────────────────────────

    def _run_training(self):
        sentences = corpus_manager.get_all_lemma_sentences()
        if not sentences:
            QMessageBox.information(self, "Нет данных",
                                    "Корпус пуст. Проанализируйте несколько текстов.")
            return
        self.btn_train.setEnabled(False)
        self.train_status.setText("Обучение запущено…")
        self._train_thread = TrainThread(self._lb, sentences, parent=self)
        self._train_thread.status.connect(self.train_status.setText)
        self._train_thread.finished.connect(self._on_training_done)
        self._train_thread.start()

    def _on_training_done(self, success: bool):
        self._train_thread = None
        if success:
            self.train_status.setText("FastText обучен ✓")
        else:
            self.train_status.setText("Обучение не удалось (мало данных?)")
        self.refresh()

    # ── Navec: скачать ────────────────────────────────────────────────────

    def _download_navec(self):
        self.btn_download_navec.setEnabled(False)
        self.btn_expand.setEnabled(False)
        self.navec_op_status.setText("Скачивание…")
        self._download_thread = DownloadNavecThread(self._rusvec, parent=self)
        self._download_thread.status.connect(self.navec_op_status.setText)
        self._download_thread.finished.connect(self._on_download_done)
        self._download_thread.start()

    def _on_download_done(self, success: bool):
        self._download_thread = None
        if success:
            self.navec_op_status.setText("Navec скачан и загружен ✓")
        else:
            self.navec_op_status.setText("Ошибка скачивания. Проверьте интернет-соединение.")
        self.refresh()

    # ── Navec: расширить словари ──────────────────────────────────────────

    def _run_expand(self):
        self.btn_expand.setEnabled(False)
        self.btn_download_navec.setEnabled(False)
        self.navec_op_status.setText("Запуск расширения словарей…")
        self._expand_thread = ExpandThread(self._rusvec, parent=self)
        self._expand_thread.status.connect(self.navec_op_status.setText)
        self._expand_thread.finished.connect(self._on_expand_done)
        self._expand_thread.start()

    def _on_expand_done(self, expanded: dict):
        self._expand_thread = None
        self.update_dict_table(expanded)
        self.refresh()

    # ── Очистка корпуса ───────────────────────────────────────────────────

    def _clear_corpus(self):
        reply = QMessageBox.question(
            self, "Очистить корпус",
            "Удалить все тексты из корпуса?\nМодель FastText останется.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            corpus_manager.clear()
            self.refresh()
