"""
Вкладка 7: ИИ-детектор (GigaCheck).
Определяет фрагменты текста, сгенерированные ИИ.
"""
from __future__ import annotations
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QPushButton, QLabel, QTextEdit, QProgressBar,
    QFrame, QMessageBox, QSizePolicy
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QTextCharFormat, QColor, QTextCursor


class LoadModelThread(QThread):
    status = pyqtSignal(str)
    finished = pyqtSignal(bool)

    def __init__(self, detector):
        super().__init__()
        self.detector = detector

    def run(self):
        ok = self.detector.load(status_callback=self.status.emit)
        self.finished.emit(ok)


class DetectThread(QThread):
    finished = pyqtSignal(object)  # GigaCheckResult
    error = pyqtSignal(str)

    def __init__(self, detector, text: str):
        super().__init__()
        self.detector = detector
        self.text = text

    def run(self):
        try:
            result = self.detector.detect(self.text)
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))


class GigaCheckTab(QWidget):
    """Вкладка детектора ИИ-контента."""

    def __init__(self, parent=None):
        super().__init__(parent)
        from analyzer.gigacheck_detector import GigaCheckDetector
        self.detector = GigaCheckDetector()
        self._current_text = ""
        self._load_thread = None
        self._detect_thread = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(8)

        # Предупреждение
        warn = QLabel(
            "⚠  GigaCheck является вспомогательным инструментом. "
            "Результаты не заменяют лингвистический анализ и не могут быть единственным "
            "основанием для судебно-экспертного вывода."
        )
        warn.setWordWrap(True)
        warn.setStyleSheet(
            "background: #45475a; color: #fab387; padding: 8px; border-radius: 4px; font-size: 11px;")
        layout.addWidget(warn)

        # Панель управления
        ctrl_group = QGroupBox("Модель: iitolstykh/GigaCheck-Detector-Multi (HuggingFace)")
        ctrl_layout = QVBoxLayout(ctrl_group)

        btn_row = QHBoxLayout()
        self.btn_load = QPushButton("⬇ Загрузить модель (~1–4 ГБ)")
        self.btn_load.clicked.connect(self._load_model)
        self.btn_detect = QPushButton("🔍 Проверить текст на ИИ")
        self.btn_detect.setEnabled(False)
        self.btn_detect.clicked.connect(self._run_detect)
        btn_install = QPushButton("📦 Установить зависимости")
        btn_install.setObjectName("secondary")
        btn_install.setToolTip(
            "Автоматически установит:\n"
            "  pip install git+https://github.com/ai-forever/gigacheck\n"
            "  pip install transformers torch")
        btn_install.clicked.connect(self._install_deps)
        btn_row.addWidget(self.btn_load)
        btn_row.addWidget(self.btn_detect)
        btn_row.addWidget(btn_install)
        btn_row.addStretch()
        ctrl_layout.addLayout(btn_row)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)  # indeterminate
        self.progress.setVisible(False)
        ctrl_layout.addWidget(self.progress)

        self.status_label = QLabel("Модель не загружена")
        self.status_label.setObjectName("subtitle")
        ctrl_layout.addWidget(self.status_label)
        layout.addWidget(ctrl_group)

        # Результат
        result_group = QGroupBox("Результат анализа")
        result_layout = QVBoxLayout(result_group)

        score_row = QHBoxLayout()
        self.score_label = QLabel("—")
        self.score_label.setStyleSheet("font-size: 36px; font-weight: bold;")
        self.score_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.score_bar = QProgressBar()
        self.score_bar.setRange(0, 100)
        self.score_bar.setValue(0)
        self.score_bar.setMinimumWidth(300)
        score_row.addWidget(self.score_label)
        score_row.addWidget(self.score_bar)
        result_layout.addLayout(score_row)

        self.verdict_label = QLabel("Выполните анализ для получения результата")
        self.verdict_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.verdict_label.setStyleSheet("font-size: 14px; padding: 4px;")
        result_layout.addWidget(self.verdict_label)
        layout.addWidget(result_group)

        # Текст с подсветкой
        text_group = QGroupBox("Текст с выделенными ИИ-фрагментами")
        text_layout = QVBoxLayout(text_group)
        legend = QLabel(
            "Красный — высокая вероятность ИИ  |  Оранжевый — средняя  |  Без цвета — написан человеком")
        legend.setObjectName("subtitle")
        text_layout.addWidget(legend)
        self.highlighted_text = QTextEdit()
        self.highlighted_text.setReadOnly(True)
        text_layout.addWidget(self.highlighted_text)
        layout.addWidget(text_group)

    def set_text(self, text: str):
        """Установить текст для анализа (вызывается после основного анализа)."""
        self._current_text = text
        self.highlighted_text.setPlainText(text)
        self.score_label.setText("—")
        self.verdict_label.setText("Нажмите «Проверить текст на ИИ»")

    def _install_deps(self):
        """Автоматически установить gigacheck + transformers + torch."""
        import subprocess, sys
        self.status_label.setText("Устанавливаются зависимости...")
        self.progress.setVisible(True)

        class _InstallThread(QThread):
            done = pyqtSignal(bool, str)
            progress_msg = pyqtSignal(str)

            def run(self):
                # Проверяем, установлен ли torch
                try:
                    import torch as _  # noqa
                    torch_ok = True
                except ImportError:
                    torch_ok = False

                # --- torch: сначала пробуем CPU-wheel с официального индекса PyTorch ---
                if not torch_ok:
                    self.progress_msg.emit("Устанавливается torch (CPU-wheel)...")
                    r = subprocess.run(
                        [sys.executable, "-m", "pip", "install", "--quiet",
                         "torch", "--index-url",
                         "https://download.pytorch.org/whl/cpu"],
                        capture_output=True, text=True, timeout=600)
                    if r.returncode != 0:
                        # Запасной вариант — обычный PyPI (может быть медленнее)
                        self.progress_msg.emit("Пробуем torch из PyPI...")
                        r2 = subprocess.run(
                            [sys.executable, "-m", "pip", "install", "--quiet", "torch"],
                            capture_output=True, text=True, timeout=600)
                        if r2.returncode != 0:
                            self.done.emit(False, r2.stderr[-400:])
                            return

                # --- transformers ---
                self.progress_msg.emit("Устанавливается transformers...")
                r = subprocess.run(
                    [sys.executable, "-m", "pip", "install", "--quiet", "transformers"],
                    capture_output=True, text=True, timeout=300)
                if r.returncode != 0:
                    self.done.emit(False, r.stderr[-400:])
                    return

                # --- gigacheck (опционально, не блокирует при ошибке) ---
                self.progress_msg.emit("Устанавливается gigacheck (опционально)...")
                subprocess.run(
                    [sys.executable, "-m", "pip", "install", "--quiet",
                     "git+https://github.com/ai-forever/gigacheck"],
                    capture_output=True, text=True, timeout=300)

                self.done.emit(True, "")

        def _on_done(ok, err):
            self.progress.setVisible(False)
            if ok:
                self.status_label.setText("✓ Зависимости установлены. Нажмите «Загрузить модель».")
            else:
                self.status_label.setText(f"Ошибка установки: {err[:80]}")
                QMessageBox.critical(self, "Ошибка установки",
                    f"Не удалось установить torch/transformers:\n\n{err}\n\n"
                    "Попробуйте вручную в терминале:\n"
                    "  pip install torch --index-url https://download.pytorch.org/whl/cpu\n"
                    "  pip install transformers")

        self._install_thread = _InstallThread()
        self._install_thread.done.connect(_on_done)
        self._install_thread.progress_msg.connect(self.status_label.setText)
        self._install_thread.start()

    def _load_model(self):
        self.btn_load.setEnabled(False)
        self.progress.setVisible(True)
        self.status_label.setText("Загрузка модели...")

        self._load_thread = LoadModelThread(self.detector)
        self._load_thread.status.connect(self.status_label.setText)
        self._load_thread.finished.connect(self._on_model_loaded)
        self._load_thread.start()

    def _on_model_loaded(self, ok: bool):
        self.progress.setVisible(False)
        if ok:
            self.status_label.setText("✓ Модель загружена и готова к работе")
            self.btn_detect.setEnabled(True)
            self.btn_load.setText("✓ Модель загружена")
            self.btn_load.setEnabled(False)
        else:
            self.status_label.setText(f"✗ Ошибка: {self.detector.load_error}")
            self.btn_load.setEnabled(True)
            QMessageBox.critical(
                self, "Ошибка загрузки GigaCheck",
                self.detector.load_error or "Неизвестная ошибка")

    def _run_detect(self):
        if not self._current_text:
            QMessageBox.warning(self, "Нет текста", "Сначала выполните основной анализ текста.")
            return
        self.btn_detect.setEnabled(False)
        self.progress.setVisible(True)
        self.status_label.setText("Анализ текста...")

        self._detect_thread = DetectThread(self.detector, self._current_text)
        self._detect_thread.finished.connect(self._on_detect_done)
        self._detect_thread.error.connect(self._on_detect_error)
        self._detect_thread.start()

    def _on_detect_done(self, result):
        self.progress.setVisible(False)
        self.btn_detect.setEnabled(True)
        self.status_label.setText("Анализ завершён")

        if result.error:
            QMessageBox.warning(self, "Ошибка", result.error)
            return

        score_pct = int(result.overall_score * 100)
        self.score_label.setText(f"{score_pct}%")
        self.score_bar.setValue(score_pct)

        if score_pct >= 70:
            verdict = "Высокая вероятность ИИ-генерации"
            color = "#f38ba8"
        elif score_pct >= 40:
            verdict = "Умеренная вероятность ИИ-генерации"
            color = "#fab387"
        elif score_pct >= 15:
            verdict = "Низкая вероятность ИИ-генерации"
            color = "#f9e2af"
        else:
            verdict = "Текст преимущественно написан человеком"
            color = "#a6e3a1"

        self.score_label.setStyleSheet(
            f"font-size: 36px; font-weight: bold; color: {color};")
        self.verdict_label.setText(verdict)
        self.verdict_label.setStyleSheet(
            f"font-size: 14px; padding: 4px; color: {color};")
        self.score_bar.setStyleSheet(
            f"QProgressBar::chunk {{ background-color: {color}; }}")

        self._highlight_intervals(result.ai_intervals)

    def _highlight_intervals(self, intervals: list):
        """Подсветить ИИ-фрагменты в тексте."""
        self.highlighted_text.setPlainText(self._current_text)
        if not intervals:
            return

        cursor = self.highlighted_text.textCursor()
        for start, end, score in intervals:
            fmt = QTextCharFormat()
            if score >= 0.7:
                fmt.setBackground(QColor("#f38ba8"))
                fmt.setForeground(QColor("#1e1e2e"))
            elif score >= 0.4:
                fmt.setBackground(QColor("#fab387"))
                fmt.setForeground(QColor("#1e1e2e"))
            else:
                fmt.setBackground(QColor("#f9e2af"))
                fmt.setForeground(QColor("#1e1e2e"))
            cursor.setPosition(start)
            cursor.setPosition(min(end, len(self._current_text)),
                               QTextCursor.MoveMode.KeepAnchor)
            cursor.setCharFormat(fmt)

    def _on_detect_error(self, msg: str):
        self.progress.setVisible(False)
        self.btn_detect.setEnabled(True)
        QMessageBox.critical(self, "Ошибка анализа", msg)

    def clear(self):
        self._current_text = ""
        self.highlighted_text.clear()
        self.score_label.setText("—")
        self.verdict_label.setText("Выполните анализ для получения результата")
        self.score_bar.setValue(0)
