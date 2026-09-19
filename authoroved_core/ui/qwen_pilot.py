"""Пилотный интерфейс теневой проверки локальным Qwen."""
from __future__ import annotations

import logging
from pathlib import Path

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox, QDialog, QFrame, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QProgressBar, QPushButton, QSplitter, QTextEdit,
    QToolBox, QVBoxLayout, QWidget,
)

from authoroved_core.core.qwen_shadow import (
    DEFAULT_SHADOW_REGISTRY, QwenShadowService, load_shadow_profiles,
)
from authoroved_core.core.feature_registry import FeatureRegistry
from authoroved_core.core.qwen_theme import QwenThemeService
from authoroved_core.core.stanza_russian import explain_stanza_tokens
from authoroved_core.core.models import Token
from authoroved_core.nlp.qwen_local import LlamaCppLocalProvider, LocalQwenConfig
from authoroved_core.nlp.qwen_server import (
    LocalQwenServer, QwenServerSettings, file_sha256,
)
from authoroved_core.ui.text_view import SourceTextView


CORE_ROOT = Path(__file__).parents[1]
DEFAULT_QWEN_RUNTIME = (
    CORE_ROOT / ".local" / "qwen" / "llama-b10955-cuda13.3" / "llama-server.exe"
)
DEFAULT_QWEN_MODEL = CORE_ROOT / ".local" / "qwen" / "models" / "Qwen3-8B-Q5_K_M.gguf"
DEFAULT_QWEN_LOG = CORE_ROOT / ".local" / "qwen" / "llama-server.log"

# Подписи профилей кандидатов. Профиль реестра, которого здесь нет, всё равно
# попадает в список: подпись строится из его name_ru, поэтому расширение
# qwen_shadow_profiles.yaml не требует правки интерфейса.
PROFILE_LABELS = {
    "overview": "Кандидаты · обзор методического реестра",
    "internet_communication": "Кандидаты · интернет-коммуникация",
    "theme_assistance": "Тематика · помощь с определением",
    "stanza_explanation": "Stanza · объяснение по-русски",
}
NON_SHADOW_PROFILE_IDS = ("theme_assistance", "stanza_explanation")


def shadow_profile_choices(registry):
    """Подписи профилей теневого реестра в порядке их объявления в YAML."""
    return tuple(
        (PROFILE_LABELS.get(item.id, f"Кандидаты · {item.name_ru}"), item.id)
        for item in load_shadow_profiles(registry=registry)
    )
# Окрестность цитаты и общий предел длины строки контекста: подпись под текстом
# не должна разрастаться на пол-окна при нескольких далёких цитатах.
CONTEXT_MARGIN = 45
CONTEXT_LIMIT = 320

REVIEW_LABELS = {
    "new": "Не рассмотрен",
    "accepted": "Подтверждён только в пилоте",
    "rejected": "Отклонён",
}

_MODEL_HASH_CACHE: dict[tuple[str, int, int], str] = {}


def _label(text="", name=None):
    widget = QLabel(text)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    widget.setWordWrap(True)
    if name:
        widget.setObjectName(name)
    return widget


def _button(text, callback, primary=False):
    widget = QPushButton(text)
    widget.setCursor(Qt.CursorShape.PointingHandCursor)
    if primary:
        widget.setObjectName("primary")
    widget.clicked.connect(callback)
    return widget


def cached_model_sha256(path: Path) -> str:
    stat = path.stat()
    key = (str(path.resolve()), stat.st_size, stat.st_mtime_ns)
    if key not in _MODEL_HASH_CACHE:
        _MODEL_HASH_CACHE.clear()
        _MODEL_HASH_CACHE[key] = file_sha256(path)
    return _MODEL_HASH_CACHE[key]


class QwenPilotWorker(QThread):
    progress = pyqtSignal(str)
    completed = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, text: str, profile_id: str, *, runtime: Path, model: Path):
        super().__init__()
        self.text = text
        self.profile_id = profile_id
        self.runtime = runtime
        self.model = model

    def run(self):
        try:
            self.progress.emit("Проверяю локальную модель…")
            model_hash = cached_model_sha256(self.model)
            settings = QwenServerSettings(self.runtime.resolve(), self.model.resolve())
            server = LocalQwenServer(settings, DEFAULT_QWEN_LOG)
            runtime_version = server.version()
            self.progress.emit("Запускаю Qwen на этом компьютере…")
            with server:
                provider = LlamaCppLocalProvider(LocalQwenConfig(
                    endpoint=server.endpoint,
                    model_name=self.model.name,
                    model_sha256=model_hash,
                    runtime_version=runtime_version,
                    api_key=server.api_key,
                ))
                self.progress.emit("Проверяю текст…")
                if self.profile_id == "theme_assistance":
                    run = QwenThemeService(provider).analyze(self.text)
                else:
                    run = QwenShadowService(provider).analyze(
                        self.text, (self.profile_id,),
                    )[0]
            self.completed.emit(run)
        except Exception as exc:
            logging.exception("Qwen pilot worker failed")
            self.failed.emit(str(exc))


class QwenPilotDialog(QDialog):
    """Отдельная песочница: результаты не попадают в дело и заключение."""

    def __init__(self, text: str, document_name: str, parent=None, *,
                 tokens: list[Token] | None = None,
                 runtime: Path = DEFAULT_QWEN_RUNTIME,
                 model: Path = DEFAULT_QWEN_MODEL):
        super().__init__(parent)
        self.source_text = text
        self.runtime = Path(runtime)
        self.model = Path(model)
        self.tokens = list(tokens or [])
        self.worker = None
        self.current_run = None
        self.candidates = []
        self.stanza_items = []
        self.stanza_mode = False
        self.decisions: dict[tuple[str, str, int, int], str] = {}
        self.registry = FeatureRegistry.load(DEFAULT_SHADOW_REGISTRY)

        self.setWindowTitle("Дополнительная проверка — пилот")
        self.resize(1060, 760)
        self.setMinimumSize(900, 650)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(10)

        title = QHBoxLayout()
        title_box = QVBoxLayout()
        title_box.addWidget(_label("Дополнительная проверка · пилот", "sectionTitle"))
        title_box.addWidget(_label(document_name, "muted"))
        title.addLayout(title_box, 1)
        title.addWidget(_button("Закрыть", self.close))
        layout.addLayout(title)
        layout.addWidget(_label(
            "Qwen предлагает только проверяемые кандидаты и темы с дословными цитатами. "
            "Разметка Stanza объясняется детерминированно, без модели. Результаты окна "
            "не сохраняются в деле, сравнении или отчёте.",
            "notice",
        ))

        controls = QHBoxLayout()
        self.profile = QComboBox()
        for title, profile_id in shadow_profile_choices(self.registry):
            self.profile.addItem(title, profile_id)
        for profile_id in NON_SHADOW_PROFILE_IDS:
            self.profile.addItem(PROFILE_LABELS[profile_id], profile_id)
        self.profile.currentIndexChanged.connect(self.profile_changed)
        self.profile.setToolTip(
            "Кандидаты ограничены реестром; тематика требует дословных оснований; "
            "объяснение Stanza строит Python без обращения к Qwen."
        )
        controls.addWidget(self.profile, 1)
        self.run_button = _button("Запустить локальную проверку", self.start, True)
        controls.addWidget(self.run_button)
        layout.addLayout(controls)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.hide()
        layout.addWidget(self.progress_bar)
        self.status = _label(
            "Модель запускается только по этой кнопке. Первый запуск обычно занимает несколько секунд.",
            "muted",
        )
        layout.addWidget(self.status)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        source_panel = QFrame()
        source_panel.setObjectName("panel")
        source_layout = QVBoxLayout(source_panel)
        source_layout.addWidget(_label("ИССЛЕДУЕМЫЙ ТЕКСТ", "eyebrow"))
        self.text_view = SourceTextView()
        self.text_view.set_source(text)
        source_layout.addWidget(self.text_view, 1)
        self.context = _label(
            "Выберите кандидат справа — его точная цитата будет подсвечена.", "muted",
        )
        source_layout.addWidget(self.context)
        splitter.addWidget(source_panel)

        result_panel = QFrame()
        result_panel.setObjectName("panel")
        result_layout = QVBoxLayout(result_panel)
        self.result_eyebrow = _label("КАНДИДАТЫ QWEN", "eyebrow")
        result_layout.addWidget(self.result_eyebrow)
        self.result_summary = _label("Проверка ещё не запускалась.", "sectionTitle")
        result_layout.addWidget(self.result_summary)
        self.candidate_list = QListWidget()
        self.candidate_list.setWordWrap(True)
        # Без нижней границы список сжимался до полутора строк, и кандидат
        # оказывался обрезан по нижнему краю.
        self.candidate_list.setMinimumHeight(150)
        self.candidate_list.currentItemChanged.connect(self.select_candidate)
        result_layout.addWidget(self.candidate_list, 1)

        self.detail = QTextEdit()
        self.detail.setReadOnly(True)
        self.detail.setObjectName("explanation")
        self.detail.setMinimumHeight(150)
        result_layout.addWidget(self.detail)

        actions = QHBoxLayout()
        self.accept_button = _button(
            "Подтвердить в пилоте", lambda: self.review("accepted"), True,
        )
        self.reject_button = _button("Отклонить", lambda: self.review("rejected"))
        actions.addWidget(self.accept_button)
        actions.addWidget(self.reject_button)
        result_layout.addLayout(actions)
        self.reset_button = _button(
            "Вернуть на рассмотрение", lambda: self.review("new"),
        )
        self.reset_button.setObjectName("quiet")
        result_layout.addWidget(self.reset_button)

        raw_page = QWidget()
        raw_layout = QVBoxLayout(raw_page)
        self.raw_response = QTextEdit()
        self.raw_response.setReadOnly(True)
        self.raw_response.setPlaceholderText("После запуска здесь будет исходный JSON-ответ модели.")
        raw_layout.addWidget(self.raw_response)
        self.technical = QToolBox()
        self.technical.addItem(raw_page, "Технические подробности и исходный ответ")
        result_layout.addWidget(self.technical)
        splitter.addWidget(result_panel)
        splitter.setSizes([590, 430])
        layout.addWidget(splitter, 1)
        self._set_review_enabled(False)

    def profile_changed(self, *_):
        stanza = self.profile.currentData() == "stanza_explanation"
        self.result_eyebrow.setText(
            "РАЗМЕТКА STANZA ПО-РУССКИ" if stanza else "КАНДИДАТЫ QWEN"
        )
        self.run_button.setText(
            "Показать русское объяснение" if stanza else "Запустить локальную проверку"
        )
        self.status.setText(
            "Сначала выполните основной анализ Stanza."
            if stanza and not self.tokens
            else ("Объяснение строится по уже полученной разметке; Qwen не запускается."
                  if stanza else
                  "Модель запускается только по кнопке и работает без доступа к интернету.")
        )

    def start(self):
        if self.worker and self.worker.isRunning():
            return
        if self.profile.currentData() == "stanza_explanation":
            self.display_stanza()
            return
        missing = []
        if not self.runtime.is_file():
            missing.append("исполняемый файл llama.cpp")
        if not self.model.is_file():
            missing.append("файл модели Qwen")
        if missing:
            self.status.setText(
                "Не найден: " + ", ".join(missing)
                + ". Откройте технические подробности установки в README."
            )
            return
        self.current_run = None
        self.candidates = []
        self.stanza_items = []
        self.stanza_mode = False
        self.candidate_list.clear()
        self.detail.clear()
        self.raw_response.clear()
        self.text_view.highlight(())
        self.result_summary.setText("Проверка выполняется…")
        self.run_button.setEnabled(False)
        self.profile.setEnabled(False)
        self.progress_bar.show()
        self._set_review_enabled(False)
        self.worker = QwenPilotWorker(
            self.source_text, str(self.profile.currentData()),
            runtime=self.runtime, model=self.model,
        )
        self.worker.progress.connect(self.status.setText)
        self.worker.completed.connect(self.display_run)
        self.worker.failed.connect(self.display_error)
        self.worker.finished.connect(self._worker_finished)
        self.worker.start()

    def _worker_finished(self):
        self.run_button.setEnabled(True)
        self.profile.setEnabled(True)
        self.progress_bar.hide()

    def display_error(self, message: str):
        self.result_summary.setText("Проверка не выполнена")
        self.status.setText(
            "Локальная модель не запустилась. Подробности записаны в технический журнал."
        )
        self.detail.setPlainText(message)

    def display_run(self, run):
        self.current_run = run
        self.stanza_mode = False
        self.stanza_items = []
        self.result_eyebrow.setText("КАНДИДАТЫ QWEN")
        self.raw_response.setPlainText(run.raw_response)
        self.candidates = list(run.candidates)
        self.candidate_list.clear()
        if run.status.value == "SYSTEM_REJECTED":
            self.result_summary.setText("Ответ модели заблокирован")
            self.status.setText("Строгая проверка не пропустила ответ модели.")
            self.detail.setPlainText(
                "Причина блокировки:\n" + run.rejection_reason
                + "\n\nИсходный ответ сохранён в технической вкладке."
            )
            self._set_review_enabled(False)
            return
        if run.status.value == "MODEL_ABSTAINED":
            self.result_summary.setText("Кандидаты не найдены")
            self.status.setText("Qwen воздержался: надёжной цитаты по выбранному профилю нет.")
            self.detail.setPlainText(
                "Это не означает отсутствия языковой особенности; модель лишь не предложила кандидата."
            )
            self._set_review_enabled(False)
            return
        self.result_summary.setText(f"Найдено кандидатов: {len(self.candidates)}")
        self.status.setText(
            "Проверьте цитаты вручную. Даже подтверждение здесь действует только в пилотном окне."
        )
        self.populate_candidates()

    def display_stanza(self):
        self.current_run = None
        self.candidates = []
        self.stanza_items = list(explain_stanza_tokens(self.tokens))
        self.stanza_mode = True
        self.candidate_list.clear()
        self.text_view.highlight(())
        self.result_eyebrow.setText("РАЗМЕТКА STANZA ПО-РУССКИ")
        if not self.stanza_items:
            self.result_summary.setText("Разметка недоступна")
            self.status.setText("Сначала выполните основной анализ выбранного текста.")
            self.detail.setPlainText(
                "После анализа здесь появятся словоформы, русские названия частей речи, "
                "грамматические характеристики и нейтральное объяснение машинных связей."
            )
            self.raw_response.clear()
            self._set_review_enabled(False)
            return
        self.result_summary.setText(f"Размечено словоформ: {len(self.stanza_items)}")
        self.status.setText(
            "Это перевод технической разметки, а не исправление Stanza и не экспертный вывод."
        )
        self.raw_response.setPlainText(
            "Технические коды показываются для выбранной словоформы. "
            "В сопоставлении они отдельно не используются."
        )
        for index, item in enumerate(self.stanza_items):
            row = QListWidgetItem(f"{item.text} · {item.word_class}")
            row.setData(Qt.ItemDataRole.UserRole, index)
            self.candidate_list.addItem(row)
        if self.candidate_list.count():
            self.candidate_list.setCurrentRow(0)
        self._set_review_enabled(False)

    def candidate_key(self, candidate) -> tuple[str, str, int, int]:
        evidence = (candidate.evidence if hasattr(candidate, "feature_id")
                    else candidate.evidence[0])
        identity = candidate.feature_id if hasattr(candidate, "feature_id") else candidate.label
        return identity, evidence.quote, evidence.span.start, evidence.span.end

    def populate_candidates(self):
        selected = self.candidate_list.currentRow()
        self.candidate_list.blockSignals(True)
        self.candidate_list.clear()
        for index, candidate in enumerate(self.candidates):
            status = self.decisions.get(self.candidate_key(candidate), "new")
            if hasattr(candidate, "feature_id"):
                feature = self.registry.get(candidate.feature_id)
                title = f"{feature.name_ru} · {candidate.feature_id}"
                quote = candidate.evidence.quote
            else:
                title = "Тема · " + candidate.label
                quote = candidate.evidence[0].quote
            item = QListWidgetItem(
                f"{title} · {REVIEW_LABELS[status]}\n"
                f"«{quote.replace(chr(10), ' ')}»"
            )
            item.setData(Qt.ItemDataRole.UserRole, index)
            self.candidate_list.addItem(item)
        self.candidate_list.blockSignals(False)
        if self.candidate_list.count():
            self.candidate_list.setCurrentRow(
                selected if 0 <= selected < self.candidate_list.count() else 0
            )

    def select_candidate(self, item, previous=None):
        if not item:
            self._set_review_enabled(False)
            return
        if self.stanza_mode:
            self.select_stanza_item(item)
            return
        if not self.current_run:
            self._set_review_enabled(False)
            return
        candidate = self.candidates[item.data(Qt.ItemDataRole.UserRole)]
        status = self.decisions.get(self.candidate_key(candidate), "new")
        if hasattr(candidate, "feature_id"):
            feature = self.registry.get(candidate.feature_id)
            evidence = (candidate.evidence,)
            sources = "\n".join(
                f"• {item.title}, {item.locator}; роль: {item.role}"
                for item in feature.sources
            )
            detail = (
                f"{feature.name_ru}\n\nЧто искала модель: {feature.definition}\n\n"
                f"Дословная цитата: «{candidate.evidence.quote}»\n"
                f"Координаты: {candidate.evidence.span.start}–{candidate.evidence.span.end}\n"
                f"\nОснования записи в пилотном реестре:\n{sources}\n"
            )
        else:
            evidence = candidate.evidence
            quotes = "\n".join(
                f"• «{item.quote}» ({item.span.start}–{item.span.end})"
                for item in evidence
            )
            detail = (
                f"Тематический кандидат: {candidate.label}\n\n"
                f"Основания в тексте:\n{quotes}\n\n"
                "Тема является вспомогательной описательной подсказкой, а не "
                "идентификационным признаком.\n"
            )
        self.detail.setPlainText(
            detail + f"\nРешение: {REVIEW_LABELS[status]}\n\n"
            "Источник результата: локальный Qwen. Python подтвердил дословность и "
            "координаты цитат, но смысловую оценку выполняет эксперт."
        )
        spans = tuple(item.span for item in evidence)
        self.text_view.highlight(spans)
        self.context.setText("Контекст · " + self.evidence_context(evidence))
        self._set_review_enabled(True)

    def evidence_context(self, evidence) -> str:
        """Окрестность каждой цитаты отдельно, а не промежуток между ними.

        У тематического кандидата цитаты стоят далеко друг от друга, и окно от
        первой до последней вырастало до тысячи с лишним знаков, занимая
        пол-окна. Теперь каждая цитата показывается со своей окрестностью.
        """
        pieces = []
        for span in sorted((item.span for item in evidence), key=lambda x: x.start):
            start = max(0, span.start - CONTEXT_MARGIN)
            end = min(len(self.source_text), span.end + CONTEXT_MARGIN)
            pieces.append(self.source_text[start:end].replace("\r", " ").replace("\n", " ").strip())
        context = " … ".join(pieces)
        if len(context) > CONTEXT_LIMIT:
            context = context[:CONTEXT_LIMIT].rstrip() + "…"
        return context

    def select_stanza_item(self, item):
        value = self.stanza_items[item.data(Qt.ItemDataRole.UserRole)]
        morphology = ("; ".join(value.morphology)
                      if value.morphology else "Stanza не указала характеристик")
        self.detail.setPlainText(
            f"Словоформа: «{value.text}»\n"
            f"Словарная форма по Stanza: «{value.lemma}»\n"
            f"Часть речи в русском представлении: {value.word_class}\n"
            f"Грамматические характеристики: {morphology}\n\n"
            f"Машинная связь простыми словами: {value.relation}\n\n"
            "Разметка получена автоматически и может ошибаться; это описание результата "
            "Stanza, а не новое понятие русской грамматики."
        )
        self.raw_response.setPlainText(value.technical)
        self.text_view.highlight((value.span,) if value.span else ())
        self.context.setText("Выбрана словоформа · " + value.text)
        self._set_review_enabled(False)

    def review(self, status: str):
        item = self.candidate_list.currentItem()
        if not item:
            return
        candidate = self.candidates[item.data(Qt.ItemDataRole.UserRole)]
        self.decisions[self.candidate_key(candidate)] = status
        self.populate_candidates()

    def _set_review_enabled(self, enabled: bool):
        self.accept_button.setEnabled(enabled)
        self.reject_button.setEnabled(enabled)
        self.reset_button.setEnabled(enabled)

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.status.setText("Дождитесь завершения локальной проверки перед закрытием окна.")
            event.ignore()
        else:
            event.accept()
