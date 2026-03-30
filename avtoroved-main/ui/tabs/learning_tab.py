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


class TrainThread(QThread):
    """Фоновый поток обучения — не блокирует UI."""
    status   = pyqtSignal(str)
    finished = pyqtSignal(bool, dict)   # success, expanded_domains

    def __init__(self, lb, sentences, parent=None):
        super().__init__(parent)
        self.lb = lb
        self.sentences = sentences

    def run(self):
        ok_ft  = self.lb.update(self.sentences, status_cb=self.status.emit)
        ok_lda = self.lb.update_lda(self.sentences, status_cb=self.status.emit)
        expanded = {}
        if ok_ft:
            expanded = self.lb.expand_thematic_dicts(status_cb=self.status.emit)
        self.finished.emit(ok_ft or ok_lda, expanded)


class LearningTab(QWidget):
    """Вкладка управления корпусом и моделью самообучения."""

    train_requested = pyqtSignal()   # сигнал для main_window (опционально)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._lb = lb_module.get()
        self._train_thread = None
        self._setup_ui()
        self.refresh()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        lbl = QLabel(
            "Программа автоматически накапливает корпус из анализируемых текстов "
            "и дообучает FastText + LDA модели после каждого анализа."
        )
        lbl.setWordWrap(True)
        lbl.setObjectName("subtitle")
        layout.addWidget(lbl)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # ── Левая панель: статус ──────────────────────────────────────────
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)

        # Корпус
        corpus_group = QGroupBox("Корпус текстов")
        corpus_form = QVBoxLayout(corpus_group)

        self.lbl_texts    = QLabel("Текстов: —")
        self.lbl_words    = QLabel("Слов: —")
        self.lbl_last     = QLabel("Последнее пополнение: —")
        self.lbl_status   = QLabel("Статус: —")
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

        # Модель
        model_group = QGroupBox("Модель FastText + LDA")
        model_form = QVBoxLayout(model_group)

        self.lbl_ft_status  = QLabel("FastText: не обучена")
        self.lbl_vocab      = QLabel("Словарь: —")
        self.lbl_lda_status = QLabel("LDA: не обучена")
        for w in [self.lbl_ft_status, self.lbl_vocab, self.lbl_lda_status]:
            model_form.addWidget(w)

        self.train_status = QLabel("")
        self.train_status.setWordWrap(True)
        self.train_status.setObjectName("subtitle")
        model_form.addWidget(self.train_status)

        self.btn_train = QPushButton("▶ Обучить сейчас")
        self.btn_train.clicked.connect(self._run_training)
        model_form.addWidget(self.btn_train)
        left_layout.addWidget(model_group)

        left_layout.addStretch()
        splitter.addWidget(left)

        # ── Правая панель: расширенные словари ───────────────────────────
        right = QGroupBox("Расширение тематических словарей")
        right_layout = QVBoxLayout(right)

        right_layout.addWidget(QLabel(
            "Слова, добавленные в тематические словари через FastText "
            f"(порог сходства ≥ {lb_module.LearningBackend.__init__.__doc__ and lb_module.SIMILARITY_THRESHOLD or 0.75}):"
        ))

        self.dict_table = QTableWidget()
        self.dict_table.setColumnCount(2)
        self.dict_table.setHorizontalHeaderLabels(["Домен", "Добавлено слов"])
        self.dict_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch)
        self.dict_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.ResizeToContents)
        self.dict_table.setAlternatingRowColors(True)
        self.dict_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.dict_table.verticalHeader().setVisible(False)
        right_layout.addWidget(self.dict_table)

        self.lbl_dict_status = QLabel(
            "После обучения FastText здесь появятся расширения словарей.")
        self.lbl_dict_status.setObjectName("subtitle")
        self.lbl_dict_status.setWordWrap(True)
        right_layout.addWidget(self.lbl_dict_status)

        splitter.addWidget(right)
        splitter.setSizes([380, 400])
        layout.addWidget(splitter)

    # ── Обновление данных ─────────────────────────────────────────────────

    def refresh(self):
        """Обновить отображение статистики корпуса и модели."""
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

        # Модель
        if self._lb.ft_ready:
            self.lbl_ft_status.setText("FastText: обучена ✓")
            self.lbl_ft_status.setStyleSheet("color: #a6e3a1;")
            self.lbl_vocab.setText(f"Словарь: {self._lb.vocab_size:,} слов".replace(",", " "))
        else:
            self.lbl_ft_status.setText("FastText: не обучена")
            self.lbl_ft_status.setStyleSheet("color: #f38ba8;")
            self.lbl_vocab.setText("Словарь: —")

        if self._lb.lda_ready:
            self.lbl_lda_status.setText("LDA: обучена ✓")
            self.lbl_lda_status.setStyleSheet("color: #a6e3a1;")
        else:
            self.lbl_lda_status.setText("LDA: не обучена")
            self.lbl_lda_status.setStyleSheet("color: #f38ba8;")

        can_train = s["ready_for_training"]
        self.btn_train.setEnabled(can_train and self._train_thread is None)
        if not can_train:
            self.btn_train.setToolTip(
                f"Нужно минимум {corpus_manager.MIN_WORDS_FOR_TRAINING:,} слов".replace(",", " "))

    def update_dict_table(self, expanded: dict):
        """Показать результаты расширения словарей."""
        if not expanded:
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
            f"Добавлено слов: {total} по {len(expanded)} доменам")

    # ── Обучение ─────────────────────────────────────────────────────────

    def _run_training(self):
        sentences = corpus_manager.get_all_lemma_sentences()
        if not sentences:
            QMessageBox.information(self, "Нет данных",
                                    "Корпус пуст. Проанализируйте несколько текстов.")
            return

        self.btn_train.setEnabled(False)
        self.train_status.setText("Обучение запущено...")

        self._train_thread = TrainThread(self._lb, sentences, parent=self)
        self._train_thread.status.connect(self.train_status.setText)
        self._train_thread.finished.connect(self._on_training_done)
        self._train_thread.start()

    def _on_training_done(self, success: bool, expanded: dict):
        self._train_thread = None
        if success:
            self.train_status.setText("Обучение завершено ✓")
            self.update_dict_table(expanded)
        else:
            self.train_status.setText("Обучение не удалось (мало данных?)")
        self.refresh()

    # ── Очистка ───────────────────────────────────────────────────────────

    def _clear_corpus(self):
        reply = QMessageBox.question(
            self, "Очистить корпус",
            "Удалить все тексты из корпуса?\nМодели FastText и LDA останутся.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            corpus_manager.clear()
            self.refresh()
