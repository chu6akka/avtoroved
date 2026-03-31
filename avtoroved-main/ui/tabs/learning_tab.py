"""
Вкладка 11: Модель / Корпус — управление самообучением.
"""
from __future__ import annotations
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QLabel, QPushButton, QProgressBar, QTableWidget,
    QTableWidgetItem, QHeaderView, QMessageBox, QSplitter,
    QComboBox,
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
    """Фоновый поток расширения словарей (Navec / RusVectores / оба)."""
    status   = pyqtSignal(str)
    finished = pyqtSignal(dict)

    def __init__(self, rusvec, backend: str = "both", parent=None):
        super().__init__(parent)
        self.rusvec  = rusvec
        self.backend = backend

    def run(self):
        # Загрузить нужные модели если ещё не загружены
        if self.backend in ("navec", "both") and not self.rusvec.navec_ready:
            if self.rusvec.navec_downloaded:
                self.rusvec.load_navec(status_cb=self.status.emit)
            else:
                ok = self.rusvec.download_navec(status_cb=self.status.emit)
                if ok:
                    self.rusvec.load_navec(status_cb=self.status.emit)

        if self.backend in ("rusvec", "both") and not self.rusvec.rusvec_ready:
            if self.rusvec.rusvec_downloaded:
                self.rusvec.load_rusvec(status_cb=self.status.emit)
            else:
                ok = self.rusvec.download_rusvec(status_cb=self.status.emit)
                if ok:
                    self.rusvec.load_rusvec(status_cb=self.status.emit)

        added = self.rusvec.expand_all_domains(
            backend=self.backend, status_cb=self.status.emit
        )
        self.finished.emit(added)


class DownloadNavecThread(QThread):
    """Фоновый поток скачивания + загрузки Navec."""
    status   = pyqtSignal(str)
    finished = pyqtSignal(bool)

    def __init__(self, rusvec, parent=None):
        super().__init__(parent)
        self.rusvec = rusvec

    def run(self):
        ok = self.rusvec.download_navec(status_cb=self.status.emit)
        if ok:
            ok = self.rusvec.load_navec(status_cb=self.status.emit)
        self.finished.emit(ok)


class DownloadRusvecThread(QThread):
    """Фоновый поток скачивания + загрузки RusVectores."""
    status   = pyqtSignal(str)
    finished = pyqtSignal(bool)

    def __init__(self, rusvec, parent=None):
        super().__init__(parent)
        self.rusvec = rusvec

    def run(self):
        ok = self.rusvec.download_rusvec(status_cb=self.status.emit)
        if ok:
            ok = self.rusvec.load_rusvec(status_cb=self.status.emit)
        self.finished.emit(ok)


class LoadNavecThread(QThread):
    """Фоновый поток загрузки Navec из уже скачанного файла."""
    status   = pyqtSignal(str)
    finished = pyqtSignal(bool)

    def __init__(self, rusvec, parent=None):
        super().__init__(parent)
        self.rusvec = rusvec

    def run(self):
        ok = self.rusvec.load_navec(status_cb=self.status.emit)
        self.finished.emit(ok)


class LoadRusvecThread(QThread):
    """Фоновый поток загрузки RusVectores из уже скачанного файла."""
    status   = pyqtSignal(str)
    finished = pyqtSignal(bool)

    def __init__(self, rusvec, parent=None):
        super().__init__(parent)
        self.rusvec = rusvec

    def run(self):
        ok = self.rusvec.load_rusvec(status_cb=self.status.emit)
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

        # Векторные модели
        vec_group  = QGroupBox("Векторные модели — расширение тематических словарей")
        vec_form   = QVBoxLayout(vec_group)

        # Статусы
        self.lbl_navec_status  = QLabel()
        self.lbl_rusvec_status = QLabel()
        self._update_vec_status_labels()
        for lbl in (self.lbl_navec_status, self.lbl_rusvec_status):
            lbl.setWordWrap(True)
            vec_form.addWidget(lbl)

        desc = QLabel(
            "Navec (Natasha/Яндекс): ~50 МБ · без POS · художественная литература\n"
            "RusVectores (НКРЯ ИРЯ РАН): ~462 МБ · UPOS-теги · авторитетный корпус"
        )
        desc.setObjectName("caption")
        desc.setWordWrap(True)
        vec_form.addWidget(desc)

        # Кнопки: скачать / загрузить / загружено (3 состояния)
        dl_row = QHBoxLayout()
        self.btn_download_navec  = QPushButton("⬇ Navec (~50 МБ)")
        self.btn_download_navec.setObjectName("secondary")
        self.btn_download_navec.clicked.connect(self._navec_btn_action)
        self.btn_download_rusvec = QPushButton("⬇ RusVectores (~462 МБ)")
        self.btn_download_rusvec.setObjectName("secondary")
        self.btn_download_rusvec.clicked.connect(self._rusvec_btn_action)
        dl_row.addWidget(self.btn_download_navec)
        dl_row.addWidget(self.btn_download_rusvec)
        vec_form.addLayout(dl_row)

        # Расширение
        expand_row = QHBoxLayout()
        expand_lbl = QLabel("Источник:")
        expand_lbl.setObjectName("caption")
        self.combo_backend = QComboBox()
        self.combo_backend.addItems(["Оба", "Navec", "RusVectores"])
        self.combo_backend.setFixedWidth(130)
        self.btn_expand = QPushButton("✨ Расширить словари")
        self.btn_expand.clicked.connect(self._run_expand)
        self.btn_expand.setToolTip(
            "Найти семантически близкие слова и добавить\n"
            "в тематические JSON-файлы."
        )
        expand_row.addWidget(expand_lbl)
        expand_row.addWidget(self.combo_backend)
        expand_row.addWidget(self.btn_expand, stretch=1)
        vec_form.addLayout(expand_row)

        self.navec_op_status = QLabel("")
        self.navec_op_status.setWordWrap(True)
        self.navec_op_status.setObjectName("subtitle")
        vec_form.addWidget(self.navec_op_status)
        right_layout.addWidget(vec_group)

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

    def _update_vec_status_labels(self):
        # Navec — статус + кнопка
        if self._rusvec.navec_ready:
            self.lbl_navec_status.setText("Navec: загружен ✓")
            self.lbl_navec_status.setStyleSheet("color: #a6e3a1;")
        elif self._rusvec.navec_downloaded:
            self.lbl_navec_status.setText("Navec: файл скачан, не загружен в память")
            self.lbl_navec_status.setStyleSheet("color: #fab387;")
        else:
            self.lbl_navec_status.setText("Navec: не скачан")
            self.lbl_navec_status.setStyleSheet("color: #f38ba8;")
        # RusVectores — статус + кнопка
        if self._rusvec.rusvec_ready:
            self.lbl_rusvec_status.setText("RusVectores (НКРЯ): загружен ✓")
            self.lbl_rusvec_status.setStyleSheet("color: #a6e3a1;")
        elif self._rusvec.rusvec_downloaded:
            self.lbl_rusvec_status.setText("RusVectores (НКРЯ): файл скачан, не загружен в память")
            self.lbl_rusvec_status.setStyleSheet("color: #fab387;")
        else:
            self.lbl_rusvec_status.setText("RusVectores (НКРЯ): не скачан")
            self.lbl_rusvec_status.setStyleSheet("color: #f38ba8;")

    def _sync_model_buttons(self, busy: bool):
        """Обновить текст и доступность кнопок моделей по их текущему состоянию."""
        # Navec
        if self._rusvec.navec_ready:
            self.btn_download_navec.setText("✓ Navec загружен")
            self.btn_download_navec.setEnabled(False)
        elif self._rusvec.navec_downloaded:
            self.btn_download_navec.setText("▶ Загрузить Navec в память")
            self.btn_download_navec.setEnabled(not busy)
        else:
            self.btn_download_navec.setText("⬇ Navec (~50 МБ)")
            self.btn_download_navec.setEnabled(not busy)
        # RusVectores
        if self._rusvec.rusvec_ready:
            self.btn_download_rusvec.setText("✓ RusVectores загружен")
            self.btn_download_rusvec.setEnabled(False)
        elif self._rusvec.rusvec_downloaded:
            self.btn_download_rusvec.setText("▶ Загрузить RusVectores в память")
            self.btn_download_rusvec.setEnabled(not busy)
        else:
            self.btn_download_rusvec.setText("⬇ RusVectores (~462 МБ)")
            self.btn_download_rusvec.setEnabled(not busy)

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

        self._update_vec_status_labels()
        busy = (self._expand_thread is not None
                or self._download_thread is not None)
        self._sync_model_buttons(busy)
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

    # ── Navec: универсальный обработчик кнопки ───────────────────────────

    def _navec_btn_action(self):
        """Скачать если нет; загрузить если скачан но не в памяти."""
        if self._rusvec.navec_downloaded and not self._rusvec.navec_ready:
            self._load_navec()
        else:
            self._download_navec()

    def _download_navec(self):
        self._set_buttons_busy(True)
        self.navec_op_status.setText("Navec: скачивание…")
        self._download_thread = DownloadNavecThread(self._rusvec, parent=self)
        self._download_thread.status.connect(self.navec_op_status.setText)
        self._download_thread.finished.connect(self._on_download_done)
        self._download_thread.start()

    def _load_navec(self):
        self._set_buttons_busy(True)
        self.navec_op_status.setText("Navec: загрузка в память…")
        self._download_thread = LoadNavecThread(self._rusvec, parent=self)
        self._download_thread.status.connect(self.navec_op_status.setText)
        self._download_thread.finished.connect(self._on_download_done)
        self._download_thread.start()

    # ── RusVectores: универсальный обработчик кнопки ─────────────────────

    def _rusvec_btn_action(self):
        """Скачать если нет; загрузить если скачан но не в памяти."""
        if self._rusvec.rusvec_downloaded and not self._rusvec.rusvec_ready:
            self._load_rusvec()
        else:
            self._download_rusvec()

    def _download_rusvec(self):
        self._set_buttons_busy(True)
        self.navec_op_status.setText("RusVectores: скачивание (~462 МБ)…")
        self._download_thread = DownloadRusvecThread(self._rusvec, parent=self)
        self._download_thread.status.connect(self.navec_op_status.setText)
        self._download_thread.finished.connect(self._on_download_done)
        self._download_thread.start()

    def _load_rusvec(self):
        self._set_buttons_busy(True)
        self.navec_op_status.setText("RusVectores: загрузка в память…")
        self._download_thread = LoadRusvecThread(self._rusvec, parent=self)
        self._download_thread.status.connect(self.navec_op_status.setText)
        self._download_thread.finished.connect(self._on_download_done)
        self._download_thread.start()

    def _on_download_done(self, success: bool):
        self._download_thread = None
        if not success:
            self.navec_op_status.setText(
                "Ошибка. Проверьте файл модели или интернет-соединение.")
        self.refresh()

    # ── Расширить словари ─────────────────────────────────────────────────

    def _run_expand(self):
        backend_map = {"Оба": "both", "Navec": "navec", "RusVectores": "rusvec"}
        backend = backend_map.get(self.combo_backend.currentText(), "both")
        self._set_buttons_busy(True)
        self.navec_op_status.setText("Запуск расширения словарей…")
        self._expand_thread = ExpandThread(
            self._rusvec, backend=backend, parent=self)
        self._expand_thread.status.connect(self.navec_op_status.setText)
        self._expand_thread.finished.connect(self._on_expand_done)
        self._expand_thread.start()

    def _on_expand_done(self, expanded: dict):
        self._expand_thread = None
        self.update_dict_table(expanded)
        self.refresh()

    def _set_buttons_busy(self, busy: bool):
        self._sync_model_buttons(busy)
        self.btn_expand.setEnabled(not busy)

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
