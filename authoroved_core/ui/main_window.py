import logging
import json
from pathlib import Path

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QComboBox, QDialog, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QProgressBar, QLayout,
    QPushButton, QScrollArea, QSplitter, QStackedWidget, QTextEdit, QToolBox,
    QVBoxLayout, QWidget,
)

from authoroved_core.core.analysis import AnalysisService
from authoroved_core.core.case_repository import (
    CaseError, CaseIntegrityError, CasePasswordError, CaseRepository,
)
from authoroved_core.core.comparison import compare_results
from authoroved_core.core.document import EncodingChoiceRequired, load_document
from authoroved_core.core.feature_models import (
    Applicability, ExpertFeatureStatus, FeatureObservation,
)
from authoroved_core.core.lt_grouping import (
    UNKNOWN_WORD_CLASSIFICATIONS,
    UNKNOWN_WORD_CLASSIFICATION_LABELS,
    candidate_group_key,
    group_candidates,
)
from authoroved_core.core.models import ReviewStatus, STATUS_LABELS
from authoroved_core.core.report_service import ReportError, ReportService
from authoroved_core.metrics.basic import GLOBAL_NOTE, WORD_PATTERN
from authoroved_core.nlp.settings import LocalSettings
from authoroved_core.ui.text_view import SourceTextView
from authoroved_core.ui.appearance import STYLE, METRIC_HIGHLIGHT
from authoroved_core.core.word_evidence import (
    FrequencyDictionary, collect as collect_word_evidence, summary_lines,
)
from authoroved_core.core.qwen_classification import (
    PROFILE_VERSION as QWEN_HINT_PROFILE_VERSION,
)
from authoroved_core.ui.qwen_pilot import (
    DEFAULT_QWEN_MODEL, DEFAULT_QWEN_RUNTIME, LtHintWorker, QwenPilotDialog,
)



def label(text="", name=None):
    widget = QLabel(text)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    widget.setWordWrap(True)
    if name:
        widget.setObjectName(name)
    return widget


def button(text, callback, primary=False):
    widget = QPushButton(text)
    widget.setCursor(Qt.CursorShape.PointingHandCursor)
    if primary:
        widget.setObjectName("primary")
    widget.clicked.connect(callback)
    return widget


FEATURE_KEY_RU = {
    "word_count": "слов в материале", "counts": "количества",
    "forms": "словоформы", "features": "характеристики",
    "per_1000_words": "на 1000 слов", "percent_of_words": "доли слов, %",
    "case_marked_nominals": "именных форм с падежом", "verb_forms": "глагольных форм",
    "sentence_count": "предложений", "lengths": "длины предложений",
    "mattr": "MATTR", "window": "окно", "window_count": "окон",
    "denominators": "форм с указанной характеристикой",
    "percent_of_case_marked_nominals": "доли форм с указанным падежом, %",
    "percent_within_each_marked_feature": "доли внутри размеченной характеристики, %",
    "mean": "среднее", "median": "медиана",
    "population_standard_deviation": "разброс",
    "sequences": "сочетания и повторы",
    "словоформы_на_1000_слов": "словоформы на 1000 слов",
    "характеристики_на_1000_слов": "характеристики на 1000 слов",
}


def feature_value_preview(value, limit=3):
    if value is None:
        return "не рассчитано"
    if isinstance(value, dict):
        parts = []
        for key, item in list(value.items())[:limit]:
            title = FEATURE_KEY_RU.get(str(key), str(key))
            parts.append(f"{title}: {feature_value_preview(item, 3)}")
        if len(value) > limit:
            parts.append(f"ещё {len(value) - limit}")
        return "; ".join(parts) if parts else "нет реализаций"
    if isinstance(value, list):
        shown = ", ".join(str(item) for item in value[:limit])
        return shown + (f" … ещё {len(value) - limit}" if len(value) > limit else "")
    if isinstance(value, float):
        return f"{value:.3f}".rstrip("0").rstrip(".").replace(".", ",")
    return str(value)


class AnalysisWorker(QThread):
    progress = pyqtSignal(str)
    completed = pyqtSignal(object)
    failed = pyqtSignal()

    def __init__(self, service, document):
        super().__init__()
        self.service, self.source_document = service, document

    def run(self):
        try:
            self.completed.emit(self.service.analyze(self.source_document, self.progress.emit))
        except Exception:
            import logging
            logging.exception("Analysis worker failed")
            self.failed.emit()


class ResourceDialog(QDialog):
    def __init__(self, settings, parent):
        super().__init__(parent)
        self.setWindowTitle("Локальные анализаторы")
        self.setMinimumWidth(650)
        layout = QVBoxLayout(self)
        layout.addWidget(label("Тексты остаются на этом компьютере", "sectionTitle"))
        layout.addWidget(label("Укажите уже установленные ресурсы. Программа ничего не скачивает и не использует внешние сервисы.", "muted"))
        self.fields = []
        for title, value, is_file in [
            ("Папка моделей Stanza (с resources.json)", settings.stanza_dir, False),
            ("Папка LanguageTool (с languagetool-commandline.jar)", settings.languagetool_dir, False),
            ("Java — файл java.exe", settings.java_executable, True),
        ]:
            layout.addWidget(label(title))
            row = QHBoxLayout()
            field = QLineEdit(value)
            row.addWidget(field, 1)
            row.addWidget(button("Выбрать…", lambda _=False, f=field, file=is_file: self.browse(f, file)))
            layout.addLayout(row)
            self.fields.append(field)
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(button("Отмена", self.reject))
        row.addWidget(button("Сохранить настройки", self.accept, True))
        layout.addLayout(row)

    def browse(self, field, is_file):
        selected = (QFileDialog.getOpenFileName(self, "Выберите Java", field.text(), "Java (java.exe)")[0]
                    if is_file else QFileDialog.getExistingDirectory(self, "Выберите папку", field.text()))
        if selected:
            field.setText(selected)

    def settings(self):
        return LocalSettings(*(field.text().strip() for field in self.fields))


class PasswordDialog(QDialog):
    def __init__(self, parent, *, confirmation):
        super().__init__(parent)
        self.confirmation = confirmation
        self.setWindowTitle("Пароль файла дела")
        self.setMinimumWidth(430)
        layout = QVBoxLayout(self)
        layout.addWidget(label(
            "Файл дела зашифрован. Пароль не сохраняется и не может быть восстановлен.",
            "metricHelp",
        ))
        layout.addWidget(label("Пароль"))
        self.password_field = QLineEdit()
        self.password_field.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(self.password_field)
        self.confirm_field = None
        if confirmation:
            layout.addWidget(label("Повторите пароль"))
            self.confirm_field = QLineEdit()
            self.confirm_field.setEchoMode(QLineEdit.EchoMode.Password)
            layout.addWidget(self.confirm_field)
        self.error = label("", "error")
        self.error.hide()
        layout.addWidget(self.error)
        actions = QHBoxLayout()
        actions.addStretch()
        actions.addWidget(button("Отмена", self.reject))
        actions.addWidget(button("Продолжить", self.accept, True))
        layout.addLayout(actions)

    def accept(self):
        password = self.password_field.text()
        if not password:
            self.error.setText("Введите пароль.")
            self.error.show()
            return
        if self.confirmation and len(password) < 8:
            self.error.setText("Используйте не менее 8 символов.")
            self.error.show()
            return
        if self.confirmation and password != self.confirm_field.text():
            self.error.setText("Пароли не совпадают.")
            self.error.show()
            return
        super().accept()

    def password(self):
        return self.password_field.text()


class MainWindow(QMainWindow):
    @property
    def material(self):
        return self.materials[self.current_slot]

    @material.setter
    def material(self, value):
        self.materials[self.current_slot] = value

    @property
    def result(self):
        return self.results[self.current_slot]

    @result.setter
    def result(self, value):
        self.results[self.current_slot] = value

    def __init__(self, settings=None, service=None, case_repository=None):
        super().__init__()
        self.setWindowTitle("Авторовед Core — новый анализ")
        self.resize(1280, 900)
        self.setMinimumSize(1060, 760)
        self.setStyleSheet(STYLE)
        self.settings = settings or LocalSettings.load()
        self.service = service or AnalysisService(self.settings)
        self.case_repository = case_repository or CaseRepository()
        self.report_service = ReportService(self.case_repository)
        self.case = self.case_repository.create()
        self.materials = self.case.materials
        self.results = self.case.results
        self.current_slot = self.case.current_slot
        self.case_path = None
        self.dirty = False
        self.busy = False
        self.audited_comments = {}
        self.worker = None
        self.worker_slot = None
        self.current_candidate = None
        self.current_feature = None
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(28, 22, 28, 16)
        layout.setSpacing(12)

        header = QHBoxLayout()
        header.setSpacing(14)
        mark = label("А", "brandMark")
        mark.setFixedSize(52, 52)
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.addWidget(mark)
        branding = QVBoxLayout()
        branding.setSpacing(1)
        branding.addWidget(label("Авторовед", "brand"))
        subtitle = label("Пространство исследования текста", "muted")
        subtitle.setWordWrap(False)
        branding.addWidget(subtitle)
        header.addLayout(branding)
        header.addStretch()
        self.settings_button = button("Локальные анализаторы", self.configure)
        self.open_case_button = button("Открыть дело", self.open_case_dialog)
        self.save_button = button("Сохранить", self.save_case)
        self.save_button.setEnabled(False)
        self.audit_button = button("Журнал", self.show_audit)
        self.open_button = button("Новый анализ", self.open_file, True)
        self.open_button.setToolTip("Начать новое исследование (Ctrl+N)")
        self.open_case_button.setToolTip("Открыть сохранённое дело (Ctrl+O)")
        self.save_button.setToolTip("Сохранить зашифрованное дело (Ctrl+S)")
        header.addWidget(self.settings_button)
        header.addWidget(self.open_case_button)
        header.addWidget(self.save_button)
        header.addWidget(self.audit_button)
        header.addWidget(self.open_button)
        layout.addLayout(header)
        self.shortcuts = []
        for sequence, callback in (
            ("Ctrl+N", self.open_file),
            ("Ctrl+O", self.open_case_dialog),
            ("Ctrl+S", self.save_case),
        ):
            shortcut = QShortcut(QKeySequence(sequence), self)
            shortcut.activated.connect(callback)
            self.shortcuts.append(shortcut)
        self.stage_buttons = []
        navigation = QFrame()
        navigation.setObjectName("navigation")
        stages = QHBoxLayout(navigation)
        stages.setContentsMargins(6, 5, 6, 5)
        stages.setSpacing(4)
        for index, title in enumerate(["1  Материал", "2  Анализ", "3  Проверка", "4  Сравнение", "5  Итог"]):
            item = button(title, lambda _=False, i=index: self.show_stage(i))
            item.setObjectName("stage")
            item.setCheckable(True)
            if index > 2:
                item.setEnabled(False)
                item.setToolTip("Сначала проанализируйте два текста")
            self.stage_buttons.append(item)
            stages.addWidget(item)
        stages.addStretch()
        layout.addWidget(navigation)
        self.case_notice = label("Предварительная версия · до двух документов · файл дела защищается паролем", "notice")
        layout.addWidget(self.case_notice)
        self.error_label = label("", "error")
        self.error_label.hide()
        layout.addWidget(self.error_label)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setHandleWidth(18)
        left = QFrame()
        left.setObjectName("panel")
        left.setMinimumWidth(480)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(22, 18, 22, 12)
        left_layout.setSpacing(9)
        left_layout.addWidget(label("ИСХОДНЫЙ ДОКУМЕНТ", "eyebrow"))
        self.material_selector = QComboBox()
        self.material_selector.addItems(["Текст 1 · не загружен", "Текст 2 · не загружен"])
        self.material_selector.currentIndexChanged.connect(self.switch_material)
        left_layout.addWidget(self.material_selector)
        title_row = QHBoxLayout()
        self.filename = label("Материал исследования", "sectionTitle")
        title_row.addWidget(self.filename, 1)
        self.qwen_button = button("Qwen · пилот", self.open_qwen_pilot)
        self.qwen_button.setEnabled(False)
        self.qwen_button.setToolTip(
            "Открыть отдельную локальную теневую проверку выбранного текста"
        )
        title_row.addWidget(self.qwen_button)
        self.analyze_button = button("Анализировать", self.start_analysis, True)
        self.analyze_button.setEnabled(False)
        title_row.addWidget(self.analyze_button)
        left_layout.addLayout(title_row)
        self.summary = label("Откройте TXT или DOCX. Исходный файл не изменяется.", "muted")
        left_layout.addWidget(self.summary)
        self.text_view = SourceTextView()
        left_layout.addWidget(self.text_view, 1)
        self.highlight_note = label("Нажмите на результат справа, чтобы увидеть связанный фрагмент.", "muted")
        left_layout.addWidget(self.highlight_note)
        self.splitter.addWidget(left)

        right = QFrame()
        right.setObjectName("panel")
        right.setMinimumWidth(400)
        right.setMaximumWidth(510)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(18, 18, 18, 14)
        right_layout.setSpacing(9)
        right_layout.addWidget(label("РАБОЧАЯ ПАНЕЛЬ", "eyebrow"))
        self.right_title = label("Начните с текста", "sectionTitle")
        right_layout.addWidget(self.right_title)
        self.right_subtitle = label("Загрузите первый документ для исследования.", "muted")
        right_layout.addWidget(self.right_subtitle)
        self.pages = QStackedWidget()
        self.intro = QWidget()
        intro_layout = QVBoxLayout(self.intro)
        self.import_note = label("После анализа здесь появятся измерения и возможные ошибки. Вы решаете, какие наблюдения принять.")
        intro_layout.addWidget(self.import_note)
        self.hash_note = label("", "muted")
        self.hash_note.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        intro_layout.addWidget(self.hash_note)
        self.second_text_button = button("Добавить второй текст", self.open_second_file, True)
        self.second_text_button.hide()
        intro_layout.addWidget(self.second_text_button)
        intro_layout.addStretch()
        self.pages.addWidget(self.intro)

        self.metrics_page = QWidget()
        metrics_layout = QVBoxLayout(self.metrics_page)
        metrics_layout.setContentsMargins(0, 4, 0, 0)
        self.toolbox = QToolBox()
        metrics_layout.addWidget(self.toolbox, 1)
        self.metric_help = label("Выберите показатель: здесь появится объяснение расчёта.", "metricHelp")
        self.metric_help.setMinimumHeight(85)
        metrics_layout.addWidget(self.metric_help)
        self.feature_review_panel = QWidget()
        feature_review_layout = QVBoxLayout(self.feature_review_panel)
        feature_review_layout.setContentsMargins(0, 0, 0, 0)
        self.feature_comment = QLineEdit()
        self.feature_comment.setPlaceholderText("Комментарий к методическому показателю (необязательно)")
        feature_review_layout.addWidget(self.feature_comment)
        feature_buttons = QHBoxLayout()
        self.confirm_feature_button = button(
            "Подтвердить расчёт", lambda: self.review_feature(ExpertFeatureStatus.CONFIRMED), True,
        )
        self.reject_feature_button = button(
            "Не использовать", lambda: self.review_feature(ExpertFeatureStatus.REJECTED),
        )
        feature_buttons.addWidget(self.confirm_feature_button)
        feature_buttons.addWidget(self.reject_feature_button)
        feature_review_layout.addLayout(feature_buttons)
        self.feature_review_panel.hide()
        metrics_layout.addWidget(self.feature_review_panel)
        metrics_layout.addWidget(button("Перейти к проверке кандидатов →", lambda: self.show_stage(2), True))
        self.pages.addWidget(self.metrics_page)

        self.review_page = QWidget()
        self.review_page.setObjectName("reviewPage")
        review_layout = QVBoxLayout(self.review_page)
        review_layout.setSizeConstraints(QLayout.SizeConstraint.SetNoConstraint,
                                         QLayout.SizeConstraint.SetMinimumSize)
        review_layout.setContentsMargins(0, 4, 0, 0)
        self.candidate_group_filter = QComboBox()
        self.candidate_group_filter.addItem("Все группы", None)
        self.candidate_group_filter.currentIndexChanged.connect(self.candidate_group_changed)
        filters = QHBoxLayout()
        filters.addWidget(self.candidate_group_filter, 2)
        self.filter = QComboBox()
        self.filter.addItems(["Все кандидаты", "Не рассмотрены", "Приняты", "Отклонены"])
        self.filter.currentIndexChanged.connect(self.populate_candidates)
        filters.addWidget(self.filter, 1)
        review_layout.addLayout(filters)
        self.candidate_group_help = label(
            "Кандидаты разделены по типу автоматической рекомендации.", "muted",
        )
        self.candidate_group_help.setMinimumHeight(34)
        self.candidate_group_help.setMaximumHeight(42)
        review_layout.addWidget(self.candidate_group_help)
        self.candidate_list = QListWidget()
        self.candidate_list.setWordWrap(True)
        self.candidate_list.setFixedHeight(100)
        self.candidate_list.currentItemChanged.connect(self.select_candidate)
        review_layout.addWidget(self.candidate_list, 1)
        review_card = QFrame()
        review_card.setObjectName("reviewCard")
        review_card.setMinimumHeight(132)
        detail_layout = QVBoxLayout(review_card)
        detail_layout.setContentsMargins(12, 8, 12, 8)
        detail_layout.setSpacing(5)
        self.candidate_detail = label("Выберите кандидата в списке.", "candidateDetail")
        detail_layout.addWidget(self.candidate_detail)
        self.explanation = QTextEdit()
        self.explanation.setObjectName("explanation")
        self.explanation.setReadOnly(True)
        self.explanation.setFixedHeight(72)
        detail_layout.addWidget(self.explanation)
        review_layout.addWidget(review_card)
        self.unknown_classification = QComboBox()
        self.unknown_classification.addItem("Выберите, что это за словоформа", "")
        for key, title in UNKNOWN_WORD_CLASSIFICATIONS:
            self.unknown_classification.addItem(title, key)
        self.unknown_classification.currentIndexChanged.connect(self.classification_changed)
        self.unknown_classification.hide()
        review_layout.addWidget(self.unknown_classification)
        # Подсказка локальной модели. Она ничего не выбирает сама: перенос в
        # выпадающий список делает эксперт кнопкой, и только для текущего слова.
        # Справка считается на Python и не зависит от модели: если модель
        # выключить совсем, эксперт всё равно видит частоту, повторяемость и
        # расстояние до исправления LanguageTool.
        self.evidence_label = label("", "muted")
        self.evidence_label.hide()
        review_layout.addWidget(self.evidence_label)
        hint_row = QHBoxLayout()
        self.hint_label = label("", "muted")
        hint_row.addWidget(self.hint_label, 1)
        self.hint_apply_button = button("Перенести подсказку", self.apply_llm_hint)
        self.hint_apply_button.setToolTip(
            "Подставляет метку подсказки в выбор эксперта. Решение остаётся за вами."
        )
        hint_row.addWidget(self.hint_apply_button)
        self.hint_request_button = button("Подсказки Qwen", self.request_llm_hints)
        self.hint_request_button.setToolTip(
            "Локальная модель предложит метки для нераспознанных словоформ. "
            "Подсказка не является выводом и в заключение не попадает."
        )
        hint_row.addWidget(self.hint_request_button)
        self.hint_widgets = (self.hint_label, self.hint_apply_button, self.hint_request_button)
        for widget in self.hint_widgets:
            widget.hide()
        review_layout.addLayout(hint_row)
        self.comment = QTextEdit()
        self.comment.setObjectName("comment")
        self.comment.setPlaceholderText("Комментарий эксперта (необязательно)")
        self.comment.setFixedHeight(54)
        self.comment.textChanged.connect(self.comment_changed)
        review_layout.addWidget(self.comment)
        actions = QHBoxLayout()
        self.accept_button = button("Принять", lambda: self.decide(ReviewStatus.ACCEPTED), True)
        self.reject_button = button("Отклонить", lambda: self.decide(ReviewStatus.REJECTED))
        actions.addWidget(self.accept_button)
        actions.addWidget(self.reject_button)
        review_layout.addLayout(actions)
        self.reset_button = button("Вернуть на рассмотрение", lambda: self.decide(ReviewStatus.NEW))
        self.reset_button.setObjectName("quiet")
        review_layout.addWidget(self.reset_button)
        self.next_button = button("Следующий нерассмотренный →", self.next_candidate)
        review_layout.addWidget(self.next_button)
        self.review_continue_button = button("Добавить второй текст →", self.continue_workflow, True)
        review_layout.addWidget(self.review_continue_button)
        review_layout.addWidget(label("Принять — сохранить наблюдение в этом сеансе. Это не вывод об авторстве.", "muted"))
        self.review_scroll = QScrollArea()
        self.review_scroll.setWidgetResizable(True)
        self.review_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.review_scroll.setWidget(self.review_page)
        self.pages.addWidget(self.review_scroll)
        right_layout.addWidget(self.pages, 1)
        self.splitter.addWidget(right)
        self.splitter.setSizes([730, 460])
        self.splitter.setChildrenCollapsible(False)
        self.workspace = QStackedWidget()
        self.workspace.addWidget(self.splitter)
        self.comparison_page = self.build_comparison_page()
        self.workspace.addWidget(self.comparison_page)
        self.final_page = self.build_final_page()
        self.workspace.addWidget(self.final_page)
        layout.addWidget(self.workspace, 1)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.hide()
        layout.addWidget(self.progress_bar)
        self.status = label("Готово к работе · анализ выполняется на вашем компьютере", "muted")
        layout.addWidget(self.status)
        self.show_stage(0)
        self.set_candidate_enabled(False)
        self.update_case_controls()

    def build_comparison_page(self):
        page = QWidget()
        page.setObjectName("comparisonPage")
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(10)

        heading = QHBoxLayout()
        title_box = QVBoxLayout()
        title_box.addWidget(label("Сравнение двух текстов", "sectionTitle"))
        title_box.addWidget(label(
            "Сопоставляются измерения и принятые вами наблюдения. Программа не вычисляет авторство.",
            "muted",
        ))
        heading.addLayout(title_box, 1)
        heading.addWidget(button("Вернуться к проверке", lambda: self.show_stage(2)))
        page_layout.addLayout(heading)
        self.comparison_limitations = label("", "notice")
        self.comparison_limitations.setMinimumHeight(42)
        self.comparison_limitations.setMaximumHeight(88)
        page_layout.addWidget(self.comparison_limitations)

        texts = QSplitter(Qt.Orientation.Horizontal)
        texts.setHandleWidth(14)
        texts.setChildrenCollapsible(False)
        self.comparison_names = []
        self.comparison_summaries = []
        self.comparison_texts = []
        for number in (1, 2):
            panel = QFrame()
            panel.setObjectName("panel")
            panel_layout = QVBoxLayout(panel)
            panel_layout.setContentsMargins(18, 14, 18, 12)
            panel_layout.setSpacing(5)
            panel_layout.addWidget(label(f"ТЕКСТ {number}", "eyebrow"))
            name = label("Материал", "comparisonTitle")
            summary = label("", "muted")
            text_view = SourceTextView()
            panel_layout.addWidget(name)
            panel_layout.addWidget(summary)
            panel_layout.addWidget(text_view, 1)
            texts.addWidget(panel)
            self.comparison_names.append(name)
            self.comparison_summaries.append(summary)
            self.comparison_texts.append(text_view)
        texts.setSizes([600, 600])
        page_layout.addWidget(texts, 3)

        lower = QSplitter(Qt.Orientation.Horizontal)
        lower.setHandleWidth(14)
        lower.setChildrenCollapsible(False)
        metrics_panel = QFrame()
        metrics_panel.setObjectName("panel")
        metrics_layout = QVBoxLayout(metrics_panel)
        metrics_layout.setContentsMargins(18, 12, 18, 12)
        metrics_layout.addWidget(label("ИЗМЕРИМЫЕ ПОКАЗАТЕЛИ", "eyebrow"))
        self.comparison_group = QComboBox()
        self.comparison_group.currentIndexChanged.connect(self.populate_comparison_metrics)
        metrics_layout.addWidget(self.comparison_group)
        self.comparison_metric_list = QListWidget()
        self.comparison_metric_list.setWordWrap(True)
        self.comparison_metric_list.currentItemChanged.connect(self.select_comparison_metric)
        metrics_layout.addWidget(self.comparison_metric_list, 1)
        lower.addWidget(metrics_panel)

        accepted_panel = QFrame()
        accepted_panel.setObjectName("panel")
        accepted_layout = QVBoxLayout(accepted_panel)
        accepted_layout.setContentsMargins(18, 12, 18, 12)
        accepted_layout.addWidget(label("ПРИНЯТЫЕ НАБЛЮДЕНИЯ", "eyebrow"))
        self.comparison_review_note = label("", "muted")
        accepted_layout.addWidget(self.comparison_review_note)
        self.comparison_candidate_list = QListWidget()
        self.comparison_candidate_list.setWordWrap(True)
        self.comparison_candidate_list.currentItemChanged.connect(self.select_comparison_candidate_group)
        accepted_layout.addWidget(self.comparison_candidate_list, 1)
        self.comparison_help = label(
            "Выберите строку слева или справа, чтобы подсветить связанные места в обоих текстах.",
            "metricHelp",
        )
        self.comparison_help.setMinimumHeight(78)
        self.comparison_help.setMaximumHeight(96)
        accepted_layout.addWidget(self.comparison_help)
        lower.addWidget(accepted_panel)
        lower.setSizes([660, 540])
        page_layout.addWidget(lower, 2)
        page_layout.addWidget(button("Перейти к экспорту →", lambda: self.show_stage(4), True))
        return page

    def build_final_page(self):
        page = QWidget()
        page.setObjectName("finalPage")
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(12)

        heading = QHBoxLayout()
        title_box = QVBoxLayout()
        title_box.addWidget(label("Экспорт материалов", "sectionTitle"))
        title_box.addWidget(label(
            "Сохраните читаемый проект исследования и отдельный пакет для проверки расчётов.",
            "muted",
        ))
        heading.addLayout(title_box, 1)
        heading.addWidget(button("Вернуться к сравнению", lambda: self.show_stage(3)))
        page_layout.addLayout(heading)

        notice = label(
            "Экспорт не формулирует вывод об авторстве. В проект попадают измерения и только "
            "сохранённые экспертом наблюдения. Отклонённые и нерассмотренные кандидаты не "
            "переносятся как подтверждённые признаки.",
            "notice",
        )
        page_layout.addWidget(notice)

        cards = QHBoxLayout()
        cards.setSpacing(14)
        report_card = QFrame()
        report_card.setObjectName("panel")
        report_layout = QVBoxLayout(report_card)
        report_layout.setContentsMargins(24, 22, 24, 22)
        report_layout.addWidget(label("ПРОЕКТ ИССЛЕДОВАНИЯ", "eyebrow"))
        report_layout.addWidget(label("Документ Word", "sectionTitle"))
        report_layout.addWidget(label(
            "Объекты, контрольные суммы, версии анализаторов, результаты проверки, "
            "сопоставление показателей, ограничения и сведения о целостности.",
        ))
        report_layout.addStretch()
        self.export_docx_button = button("Сохранить проект DOCX", self.export_docx_dialog, True)
        report_layout.addWidget(self.export_docx_button)
        cards.addWidget(report_card)

        package_card = QFrame()
        package_card.setObjectName("panel")
        package_layout = QVBoxLayout(package_card)
        package_layout.setContentsMargins(24, 22, 24, 22)
        package_layout.addWidget(label("ПАКЕТ ПРОВЕРКИ", "eyebrow"))
        package_layout.addWidget(label("Архив ZIP", "sectionTitle"))
        package_layout.addWidget(label(
            "Манифест, контрольные суммы, журнал, версии компонентов и таблицы сравнения. "
            "Исходные тексты не добавляются без отдельного согласия.",
        ))
        package_layout.addStretch()
        self.export_package_button = button(
            "Создать проверочный пакет", self.export_verification_dialog, True,
        )
        package_layout.addWidget(self.export_package_button)
        cards.addWidget(package_card)
        page_layout.addLayout(cards, 1)

        self.export_summary = label("", "metricHelp")
        page_layout.addWidget(self.export_summary)
        return page

    def record_event(self, event, details):
        self.case.current_slot = self.current_slot
        self.case_repository.record(self.case, event, details)
        self.mark_dirty()

    def mark_dirty(self):
        self.dirty = True
        self.update_case_controls()

    def update_case_controls(self):
        has_material = any(self.materials)
        self.save_button.setEnabled(has_material and not self.busy)
        name = self.case_path.name if self.case_path else "новое дело"
        self.setWindowTitle(f"Авторовед Core — {name}{' *' if self.dirty else ''}")
        if self.case_path:
            self.case_notice.setText(
                f"Дело: {self.case_path.name} · {'есть несохранённые изменения' if self.dirty else 'сохранено'}"
            )
        else:
            self.case_notice.setText(
                "Новое дело · до двух документов · при сохранении файл будет защищён паролем"
            )

    def reset_case(self):
        self.case = self.case_repository.create()
        self.materials = self.case.materials
        self.results = self.case.results
        self.current_slot = 0
        self.case_path = None
        self.current_candidate = None
        self.audited_comments = {}
        self.dirty = False
        self.stage_buttons[3].setEnabled(False)
        self.stage_buttons[4].setEnabled(False)
        self.update_material_selector()
        self.update_case_controls()

    def password_from_user(self, confirmation):
        dialog = PasswordDialog(self, confirmation=confirmation)
        return dialog.password() if dialog.exec() else None

    def save_case(self):
        if not any(self.materials):
            return False
        self.record_comment_if_changed()
        path = self.case_path
        if path is None:
            selected, _ = QFileDialog.getSaveFileName(
                self, "Сохранить дело", "Новое дело.avedcase", "Дело Автороведа (*.avedcase)",
            )
            if not selected:
                return False
            path = Path(selected)
            if path.suffix.lower() != ".avedcase":
                path = path.with_suffix(".avedcase")
        password = self.password_from_user(confirmation=self.case_path is None)
        if password is None:
            return False
        return self.save_case_to(path, password)

    def save_case_to(self, path, password):
        path = Path(path)
        try:
            if self.case_path and path.resolve() == self.case_path.resolve() and path.exists():
                self.case_repository.open(path, password)
            self.case.current_slot = self.current_slot
            self.case.materials = self.materials
            self.case.results = self.results
            self.case_repository.save(path, self.case, password)
        except CasePasswordError:
            self.error_label.setText("Пароль не подходит к существующему файлу дела. Файл не изменён.")
            self.error_label.show()
            return False
        except (CaseError, OSError, TypeError, ValueError):
            logging.exception("Case save failed")
            self.error_label.setText("Не удалось сохранить дело. Файл не изменён; подробности находятся в техническом журнале.")
            self.error_label.show()
            return False
        self.case_path = path
        self.dirty = False
        self.error_label.hide()
        self.update_case_controls()
        self.status.setText("Дело сохранено и проверено · пароль и ключ не записаны")
        return True

    def open_case_dialog(self):
        if not self.confirm_discard():
            return
        selected, _ = QFileDialog.getOpenFileName(
            self, "Открыть дело", "", "Дело Автороведа (*.avedcase)",
        )
        if not selected:
            return
        password = self.password_from_user(confirmation=False)
        if password is not None:
            self.restore_case_from(selected, password)

    def restore_case_from(self, path, password):
        try:
            restored = self.case_repository.open(path, password)
        except CasePasswordError:
            self.error_label.setText("Неверный пароль либо файл дела повреждён.")
            self.error_label.show()
            return False
        except (CaseIntegrityError, CaseError, OSError):
            logging.exception("Case open failed")
            self.error_label.setText("Дело не открыто: нарушена целостность или формат файла.")
            self.error_label.show()
            return False
        self.case = restored
        self.materials = restored.materials
        self.results = restored.results
        self.current_slot = restored.current_slot
        if self.materials[self.current_slot] is None:
            self.current_slot = next((i for i, item in enumerate(self.materials) if item), 0)
        self.case_path = Path(path)
        self.current_candidate = None
        self.audited_comments = {
            (candidate.document_id, candidate.id): candidate.comment
            for result in self.results if result for candidate in result.candidates
        }
        self.case_repository.record(self.case, "case_opened", {"file_name": self.case_path.name})
        self.dirty = True
        self.update_material_selector()
        self.render_current_material()
        self.stage_buttons[3].setEnabled(all(self.results))
        self.stage_buttons[4].setEnabled(all(self.results))
        self.update_case_controls()
        self.error_label.hide()
        self.show_stage(1 if self.result else 0)
        self.status.setText("Дело открыто · целостность подтверждена · открытие добавлено в журнал")
        return True

    def show_audit(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Журнал дела")
        dialog.resize(720, 560)
        layout = QVBoxLayout(dialog)
        try:
            self.case.current_slot = self.current_slot
            self.case_repository.verify_integrity(self.case)
            layout.addWidget(label("Целостность журнала и материалов подтверждена.", "metricHelp"))
        except CaseIntegrityError as exc:
            warning = label("Нарушена целостность дела: " + str(exc), "error")
            layout.addWidget(warning)
        names = {
            "case_created": "Создано новое дело",
            "case_opened": "Открыт файл дела",
            "case_saved": "Сохранён файл дела",
            "document_imported": "Загружен исходный документ",
            "analysis_started": "Запущен анализ",
            "analysis_completed": "Анализ завершён",
            "analysis_failed": "Анализ завершился с ошибкой",
            "candidate_reviewed": "Изменено решение по кандидату",
            "candidate_classified": "Классифицирована словоформа вне словаря LT",
            "candidate_comment": "Изменён комментарий эксперта",
            "report_exported": "Сохранён проект исследования",
            "verification_package_exported": "Создан проверочный пакет",
        }
        journal = QTextEdit()
        journal.setReadOnly(True)
        journal.setPlainText("\n\n".join(
            f"{entry.sequence}. {entry.timestamp.replace('T', ' ')[:19]} UTC\n"
            f"{names.get(entry.event, entry.event)}{self.audit_details(entry)}\n"
            f"Контроль: {entry.entry_hash[:16]}…"
            for entry in self.case.audit
        ))
        layout.addWidget(journal, 1)
        layout.addWidget(button("Закрыть", dialog.accept, True))
        dialog.exec()

    @staticmethod
    def audit_details(entry):
        details = entry.details
        if entry.event in {"case_opened", "case_saved"}:
            return f" · {details.get('file_name', '')}"
        if entry.event == "document_imported":
            return f" · текст {details.get('slot')} · {details.get('name', '')}"
        if entry.event in {"analysis_started", "analysis_failed"}:
            return f" · текст {details.get('slot')}"
        if entry.event == "analysis_completed":
            return (f" · текст {details.get('slot')} · показателей: {details.get('metrics')} · "
                    f"кандидатов: {details.get('candidates')}")
        if entry.event == "candidate_reviewed":
            status = {"new": "на рассмотрении", "accepted": "принят", "rejected": "отклонён"}
            return f" · {details.get('category', '')} · {status.get(details.get('to'), '')}"
        if entry.event == "candidate_classified":
            before = UNKNOWN_WORD_CLASSIFICATION_LABELS.get(details.get("from"), "не указано")
            after = UNKNOWN_WORD_CLASSIFICATION_LABELS.get(details.get("to"), "не указано")
            return f" · {before} → {after}"
        if entry.event == "candidate_comment":
            return f" · длина комментария: {details.get('characters', 0)}"
        if entry.event == "report_exported":
            return f" · {details.get('file_name', '')}"
        if entry.event == "verification_package_exported":
            source_note = ("с исходными текстами" if details.get("source_documents_included")
                           else "без исходных текстов")
            return f" · {details.get('file_name', '')} · {source_note}"
        return ""

    def record_comment_if_changed(self):
        if not self.current_candidate:
            return
        key = (self.current_candidate.document_id, self.current_candidate.id)
        current = self.current_candidate.comment
        if self.audited_comments.get(key, "") != current:
            self.record_event("candidate_comment", {
                "document_id": self.current_candidate.document_id,
                "candidate_id": self.current_candidate.id,
                "characters": len(current),
            })
            self.audited_comments[key] = current

    def confirm_discard(self):
        if not self.dirty:
            return True
        dialog = QMessageBox(self)
        dialog.setWindowTitle("Есть несохранённые изменения")
        dialog.setText("Сохранить изменения файла дела перед продолжением?")
        save_button = dialog.addButton("Сохранить", QMessageBox.ButtonRole.AcceptRole)
        discard_button = dialog.addButton("Продолжить без сохранения", QMessageBox.ButtonRole.DestructiveRole)
        dialog.addButton("Остаться", QMessageBox.ButtonRole.RejectRole)
        dialog.exec()
        if dialog.clickedButton() is save_button:
            return self.save_case()
        return dialog.clickedButton() is discard_button

    def confirm_reanalysis(self):
        if not self.result:
            return True
        dialog = QMessageBox(self)
        dialog.setWindowTitle(f"Повторить анализ текста {self.current_slot + 1}?")
        dialog.setText("Результаты, комментарии и решения только по этому тексту будут потеряны.")
        continue_button = dialog.addButton("Повторить анализ", QMessageBox.ButtonRole.AcceptRole)
        dialog.addButton("Отмена", QMessageBox.ButtonRole.RejectRole)
        dialog.exec()
        return dialog.clickedButton() is continue_button

    def open_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Выберите материал", "", "Текстовые документы (*.txt *.docx)")
        if path and self.confirm_discard():
            self.reset_case()
            self.load_path(path, slot=0)

    def open_second_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Выберите второй текст", "", "Текстовые документы (*.txt *.docx)")
        if not path:
            return
        if self.materials[1]:
            dialog = QMessageBox(self)
            dialog.setWindowTitle("Заменить второй текст?")
            dialog.setText("Материал, результаты и решения по тексту 2 будут потеряны.")
            replace_button = dialog.addButton("Заменить", QMessageBox.ButtonRole.AcceptRole)
            dialog.addButton("Отмена", QMessageBox.ButtonRole.RejectRole)
            dialog.exec()
            if dialog.clickedButton() is not replace_button:
                return
        self.load_path(path, slot=1)

    def load_path(self, path, encoding=None, slot=None):
        target_slot = self.current_slot if slot is None else slot
        try:
            material = load_document(path, encoding)
        except EncodingChoiceRequired:
            dialog = QDialog(self)
            dialog.setWindowTitle("Кодировка текста")
            layout = QVBoxLayout(dialog)
            layout.addWidget(label("Файл не является UTF-8. Укажите кодировку и проверьте отображение текста."))
            choice = QComboBox()
            choice.addItems(["Windows-1251", "DOS-866"])
            layout.addWidget(choice)
            layout.addWidget(button("Открыть", dialog.accept, True))
            layout.addWidget(button("Отмена", dialog.reject))
            if dialog.exec():
                return self.load_path(path, ["cp1251", "cp866"][choice.currentIndex()], target_slot)
            return
        except Exception:
            self.error_label.setText("Не удалось открыть документ. Проверьте формат, доступ к файлу и наличие текста.")
            self.error_label.show()
            return
        replaced = self.materials[target_slot] is not None
        self.materials[target_slot] = material
        self.results[target_slot] = None
        self.current_slot = target_slot
        self.current_candidate = None
        self.update_material_selector()
        self.material_selector.setCurrentIndex(target_slot)
        self.render_current_material()
        self.error_label.hide()
        self.record_event("document_imported", {
            "slot": target_slot + 1, "name": material.name,
            "file_sha256": material.file_sha256, "text_sha256": material.text_sha256,
            "size_bytes": len(material.original_bytes), "replaced": replaced,
        })
        self.status.setText(f"Текст {target_slot + 1} загружен. Проверьте его и нажмите «Анализировать».")
        self.show_stage(0)

    def update_material_selector(self):
        self.material_selector.blockSignals(True)
        for index, material in enumerate(self.materials):
            state = material.name if material else "не загружен"
            self.material_selector.setItemText(index, f"Текст {index + 1} · {state}")
        self.material_selector.setCurrentIndex(self.current_slot)
        self.material_selector.blockSignals(False)
        self.second_text_button.setVisible(self.materials[0] is not None and self.materials[1] is None)
        if hasattr(self, "stage_buttons") and len(self.stage_buttons) > 3:
            self.stage_buttons[3].setEnabled(all(self.results) and not self.busy)
            self.stage_buttons[4].setEnabled(all(self.results) and not self.busy)
        self.update_workflow_button()

    def switch_material(self, index):
        if index == self.current_slot:
            return
        self.record_comment_if_changed()
        self.current_slot = index
        self.case.current_slot = index
        self.current_candidate = None
        self.render_current_material()
        self.show_stage(1 if self.result else 0)

    def render_current_material(self):
        material, result = self.material, self.result
        if material is None:
            self.filename.setText(f"Текст {self.current_slot + 1} не загружен")
            self.summary.setText("Выберите файл TXT или DOCX.")
            self.text_view.set_source("")
            self.import_note.setText("Добавьте документ, затем выполните его отдельный анализ.")
            self.hash_note.clear()
            self.analyze_button.setEnabled(False)
            self.qwen_button.setEnabled(False)
            return
        self.filename.setText(material.name)
        self.text_view.set_source(material.text)
        preliminary_words = len(WORD_PATTERN.findall(material.text))
        self.summary.setText(f"{len(material.text):,} символов · около {preliminary_words} слов · предложения определятся после анализа".replace(",", " "))
        self.import_note.setText(material.import_note)
        self.hash_note.setText("SHA-256 исходного файла\n" + material.file_sha256[:32] + "\n" + material.file_sha256[32:])
        self.hash_note.setToolTip(material.file_sha256)
        self.analyze_button.setEnabled(not (self.worker and self.worker.isRunning()))
        self.qwen_button.setEnabled(not (self.worker and self.worker.isRunning()))
        if result:
            values = {metric.name: metric.value for metric in result.metrics}
            self.summary.setText(" · ".join(
                f"{values[name]} {unit}" for name, unit in
                [("Слова", "слов"), ("Предложения", "предложений"), ("Абзацы", "абзацев")]
                if name in values
            ))
            self.populate_metrics()
            self.populate_candidate_groups()
            self.populate_candidates()

    def continue_workflow(self):
        if self.materials[1] is None:
            self.open_second_file()
        elif self.results[1] is None:
            self.material_selector.setCurrentIndex(1)
            self.show_stage(0)
            self.status.setText("Текст 2 загружен. Нажмите «Анализировать».")
        elif all(self.results):
            self.show_stage(3)

    def update_workflow_button(self):
        if not hasattr(self, "review_continue_button"):
            return
        if self.materials[1] is None:
            text = "Добавить второй текст →"
        elif self.results[1] is None:
            text = "Перейти к анализу текста 2 →"
        elif all(self.results):
            text = "Перейти к сравнению →"
        else:
            text = "Продолжить работу →"
        self.review_continue_button.setText(text)

    def start_analysis(self):
        if not self.material or (self.worker and self.worker.isRunning()):
            return
        if self.result and not self.confirm_reanalysis():
            return
        self.record_event("analysis_started", {
            "slot": self.current_slot + 1, "document_id": self.material.id,
            "file_sha256": self.material.file_sha256,
        })
        self.result = None
        self.current_candidate = None
        self.error_label.hide()
        self.show_stage(0)
        self.text_view.highlight(())
        self.set_busy(True)
        self.worker_slot = self.current_slot
        self.worker = AnalysisWorker(self.service, self.material)
        self.worker.progress.connect(self.status.setText)
        self.worker.completed.connect(self.display_result)
        self.worker.failed.connect(self.analysis_failed)
        self.worker.finished.connect(lambda: self.set_busy(False))
        self.worker.start()

    def open_qwen_pilot(self):
        if not self.material:
            self.status.setText("Сначала загрузите текст для проверки Qwen.")
            return
        tokens = self.result.tokens if self.result else []
        dialog = QwenPilotDialog(
            self.material.text, self.material.name, self, tokens=tokens,
        )
        dialog.exec()
        self.text_view.highlight(())
        self.status.setText(
            "Пилотное окно Qwen закрыто · его результаты не добавлены в дело"
        )

    def set_busy(self, busy):
        self.busy = busy
        self.progress_bar.setVisible(busy)
        self.open_button.setEnabled(not busy)
        self.settings_button.setEnabled(not busy)
        self.open_case_button.setEnabled(not busy)
        self.audit_button.setEnabled(not busy)
        self.material_selector.setEnabled(not busy)
        self.analyze_button.setEnabled(not busy and self.material is not None)
        self.qwen_button.setEnabled(not busy and self.material is not None)
        for i in range(3):
            self.stage_buttons[i].setEnabled(not busy)
        self.stage_buttons[3].setEnabled(not busy and all(self.results))
        self.stage_buttons[4].setEnabled(not busy and all(self.results))
        if hasattr(self, "export_docx_button"):
            self.export_docx_button.setEnabled(not busy and all(self.results))
            self.export_package_button.setEnabled(not busy and all(self.results))
        self.update_case_controls()

    def analysis_failed(self):
        if self.material:
            self.record_event("analysis_failed", {
                "slot": self.current_slot + 1, "document_id": self.material.id,
            })
        self.error_label.setText("Анализ прерван из-за ошибки. Подробности находятся в техническом журнале.")
        self.error_label.show()
        self.status.setText("Анализ не завершён")

    def display_result(self, result):
        slot = next((i for i, material in enumerate(self.materials)
                     if material and material.id == result.document_id), None)
        if slot is None:
            return
        self.results[slot] = result
        self.current_slot = slot
        self.update_material_selector()
        self.error_label.setText("\n".join(result.errors))
        self.error_label.setVisible(bool(result.errors))
        values = {metric.name: metric.value for metric in result.metrics}
        self.summary.setText(" · ".join(f"{values[name]} {unit}" for name, unit in [("Слова", "слов"), ("Предложения", "предложений"), ("Абзацы", "абзацев")] if name in values))
        self.populate_metrics()
        self.populate_candidate_groups()
        self.populate_candidates()
        self.stage_buttons[3].setEnabled(all(self.results))
        self.stage_buttons[4].setEnabled(all(self.results))
        self.update_workflow_button()
        self.record_event("analysis_completed", {
            "slot": slot + 1, "document_id": result.document_id,
            "errors": len(result.errors), "metrics": len(result.metrics),
            "candidates": len(result.candidates),
            "stanza_version": result.metadata.get("stanza", {}).get("version"),
            "languagetool_version": result.metadata.get("languagetool", {}).get("version"),
        })
        self.show_stage(1)
        self.status.setText(("Анализ выполнен частично" if result.errors else f"Анализ текста {slot + 1} завершён") + " · результаты требуют вашей проверки")

    def show_stage(self, index):
        if index != 2:
            self.record_comment_if_changed()
        if index > 4:
            return
        if index == 4:
            if not all(self.results):
                self.status.setText("Для экспорта сначала загрузите и проанализируйте оба текста.")
                return
            self.populate_final_summary()
            self.workspace.setCurrentIndex(2)
            for i, item in enumerate(self.stage_buttons):
                item.setChecked(i == 4)
            self.status.setText("Материалы готовы к экспорту · вывод об авторстве не формируется")
            return
        if index == 3:
            if not all(self.results):
                self.status.setText("Для сравнения сначала загрузите и проанализируйте оба текста.")
                return
            self.populate_comparison()
            self.workspace.setCurrentIndex(1)
            for i, item in enumerate(self.stage_buttons):
                item.setChecked(i == 3)
            self.status.setText("Сравнение построено · интерпретацию выполняет эксперт")
            return
        if index and not self.result:
            index = 0
        self.workspace.setCurrentIndex(0)
        for i, item in enumerate(self.stage_buttons):
            item.setChecked(i == index)
        self.pages.setCurrentIndex(index)
        self.right_title.setText(["Материал", "Измерения текста", "Проверка кандидатов"][index])
        if index == 2:
            self.update_review_summary()
            if self.candidate_list.currentItem():
                self.select_candidate(self.candidate_list.currentItem())
        else:
            self.right_subtitle.setText(["Исходный файл остаётся неизменным.", "Выберите показатель, чтобы понять расчёт."][index])
            self.text_view.highlight(())
            self.highlight_note.setText("Нажмите на результат справа, чтобы увидеть связанный фрагмент.")

    def populate_comparison(self):
        self.comparison = compare_results(self.results[0], self.results[1])
        limitations = " ".join(self.comparison.limitations)
        self.comparison_limitations.setText("Перед интерпретацией: " + limitations)
        self.comparison_limitations.setToolTip(limitations)
        for index, (material, result) in enumerate(zip(self.materials, self.results)):
            self.comparison_names[index].setText(material.name)
            self.comparison_texts[index].set_source(material.text)
            values = {metric.name: metric.value for metric in result.metrics}
            self.comparison_summaries[index].setText(
                " · ".join(f"{values[name]} {unit}" for name, unit in
                           [("Слова", "слов"), ("Предложения", "предложений")]
                           if name in values)
            )
        groups = ["Все разделы"] + list(dict.fromkeys(metric.group for metric in self.comparison.metrics))
        current = self.comparison_group.currentText()
        self.comparison_group.blockSignals(True)
        self.comparison_group.clear()
        self.comparison_group.addItems(groups)
        if current in groups:
            self.comparison_group.setCurrentText(current)
        self.comparison_group.blockSignals(False)
        self.populate_comparison_metrics()
        self.comparison_candidate_list.clear()
        for group in self.comparison.accepted_groups:
            item = QListWidgetItem(
                f"{group.label}\n{group.relation} · текст 1: {group.count_first} · текст 2: {group.count_second}"
            )
            item.setData(Qt.ItemDataRole.UserRole, group)
            self.comparison_candidate_list.addItem(item)
        if not self.comparison.accepted_groups:
            self.comparison_candidate_list.addItem("Нет принятых наблюдений для сопоставления")
        remaining = [sum(c.status == ReviewStatus.NEW for c in result.candidates) for result in self.results]
        self.comparison_review_note.setText(
            f"Не рассмотрено: текст 1 — {remaining[0]}, текст 2 — {remaining[1]}. "
            "Отклонённые кандидаты не сопоставляются."
        )
        self.comparison_help.setText(
            "Сопоставление идёт по виду рекомендации и точному фрагменту без учёта регистра. "
            "Это не вывод о совпадении авторского признака."
        )

    def populate_comparison_metrics(self, *_):
        if not hasattr(self, "comparison"):
            return
        selected_group = self.comparison_group.currentText()
        self.comparison_metric_list.clear()
        for metric in self.comparison.metrics:
            if selected_group != "Все разделы" and metric.group != selected_group:
                continue
            item = QListWidgetItem(
                f"{metric.name}\nТекст 1: {metric.value_first} · Текст 2: {metric.value_second}\n"
                f"Разница: {metric.difference} · {metric.direction}"
            )
            item.setData(Qt.ItemDataRole.UserRole, metric)
            self.comparison_metric_list.addItem(item)

    def select_comparison_metric(self, item, previous=None):
        if item is None:
            return
        metric = item.data(Qt.ItemDataRole.UserRole)
        self.comparison_texts[0].highlight(metric.spans_first, METRIC_HIGHLIGHT)
        self.comparison_texts[1].highlight(metric.spans_second, METRIC_HIGHLIGHT)
        fragment_note = (f"Связано фрагментов: {len(metric.spans_first)} в тексте 1 и "
                         f"{len(metric.spans_second)} в тексте 2.")
        if not metric.spans_first and not metric.spans_second:
            fragment_note = GLOBAL_NOTE
        self.comparison_help.setText(
            f"Основа сравнения: {metric.basis}. {metric.explanation}\n"
            f"Ограничение: {metric.caution}\n{fragment_note}"
        )

    def select_comparison_candidate_group(self, item, previous=None):
        if item is None or item.data(Qt.ItemDataRole.UserRole) is None:
            return
        group = item.data(Qt.ItemDataRole.UserRole)
        self.comparison_texts[0].highlight(group.spans_first)
        self.comparison_texts[1].highlight(group.spans_second)
        self.comparison_help.setText(
            f"{group.relation}. Принято наблюдений: {group.count_first} в тексте 1 и "
            f"{group.count_second} в тексте 2. Основа группировки: {group.basis}. "
            "Наблюдение само по себе не является выводом об авторстве."
        )

    def populate_final_summary(self):
        if not all(self.results):
            self.export_summary.setText("Для экспорта нужны результаты анализа двух текстов.")
            return
        rows = []
        for index, (material, result) in enumerate(zip(self.materials, self.results), 1):
            accepted = sum(item.status == ReviewStatus.ACCEPTED for item in result.candidates)
            remaining = sum(item.status == ReviewStatus.NEW for item in result.candidates)
            rows.append(
                f"Текст {index}: {material.name} · сохранено наблюдений: {accepted} · "
                f"не рассмотрено: {remaining}"
            )
        self.export_summary.setText("\n".join(rows))

    def export_docx_dialog(self):
        if not all(self.results):
            return False
        default = (self.case_path.with_suffix(".docx") if self.case_path
                   else Path("Проект исследования.docx"))
        selected, _ = QFileDialog.getSaveFileName(
            self, "Сохранить проект исследования", str(default), "Документ Word (*.docx)",
        )
        return self.export_docx_to(selected) if selected else False

    def export_docx_to(self, path):
        if not path:
            return False
        self.record_comment_if_changed()
        try:
            comparison = compare_results(self.results[0], self.results[1])
            exported = self.report_service.export_docx(path, self.case, comparison)
        except (ReportError, CaseError, OSError, TypeError, ValueError):
            logging.exception("Report export failed")
            self.error_label.setText(
                "Не удалось сохранить проект исследования. Дело не изменено; "
                "подробности находятся в техническом журнале."
            )
            self.error_label.show()
            return False
        self.record_event("report_exported", {"file_name": exported.name})
        self.error_label.hide()
        self.export_summary.setText(f"Проект исследования сохранён: {exported}")
        self.status.setText("Проект DOCX сохранён · вывод об авторстве не формировался")
        return True

    def export_verification_dialog(self):
        if not all(self.results):
            return False
        choice = QMessageBox(self)
        choice.setWindowTitle("Состав проверочного пакета")
        choice.setIcon(QMessageBox.Icon.Question)
        choice.setText("Добавить в архив исходные файлы и извлечённые тексты?")
        choice.setInformativeText(
            "Обычно достаточно пакета без исходных текстов. Добавляйте их только если "
            "получатель вправе работать с материалами дела."
        )
        without_sources = choice.addButton("Без исходных текстов", QMessageBox.ButtonRole.AcceptRole)
        with_sources = choice.addButton("Включить исходные тексты", QMessageBox.ButtonRole.ActionRole)
        choice.addButton("Отмена", QMessageBox.ButtonRole.RejectRole)
        choice.exec()
        clicked = choice.clickedButton()
        if clicked not in {without_sources, with_sources}:
            return False
        default = (self.case_path.with_name(self.case_path.stem + "_проверка.zip") if self.case_path
                   else Path("Проверочный пакет.zip"))
        selected, _ = QFileDialog.getSaveFileName(
            self, "Сохранить проверочный пакет", str(default), "Архив ZIP (*.zip)",
        )
        return self.export_verification_to(
            selected, include_sources=clicked is with_sources,
        ) if selected else False

    def export_verification_to(self, path, *, include_sources=False):
        if not path:
            return False
        self.record_comment_if_changed()
        try:
            comparison = compare_results(self.results[0], self.results[1])
            exported = self.report_service.export_verification_package(
                path, self.case, comparison, include_sources=include_sources,
            )
            self.report_service.verify_verification_package(exported)
        except (ReportError, CaseError, OSError, TypeError, ValueError):
            logging.exception("Verification package export failed")
            self.error_label.setText(
                "Не удалось создать проверочный пакет. Дело не изменено; "
                "подробности находятся в техническом журнале."
            )
            self.error_label.show()
            return False
        self.record_event("verification_package_exported", {
            "file_name": exported.name, "source_documents_included": include_sources,
        })
        self.error_label.hide()
        source_note = "с исходными текстами" if include_sources else "без исходных текстов"
        self.export_summary.setText(f"Проверочный пакет сохранён {source_note}: {exported}")
        self.status.setText(f"Проверочный пакет сохранён · {source_note}")
        return True

    def populate_metrics(self):
        while self.toolbox.count():
            page = self.toolbox.widget(0)
            self.toolbox.removeItem(0)
            page.deleteLater()
        for group in ["Количественные показатели", "Лексика", "Морфология", "Предложения", "Структура"]:
            page = QListWidget()
            page.setWordWrap(True)
            for metric in self.result.metrics:
                if metric.group == group:
                    item = QListWidgetItem(f"{metric.name}\n{metric.value}")
                    item.setData(Qt.ItemDataRole.UserRole, metric)
                    page.addItem(item)
            page.currentItemChanged.connect(self.select_metric)
            self.toolbox.addItem(page, group)
        if self.result.feature_observations:
            page = QListWidget()
            page.setWordWrap(True)
            labels = {
                ExpertFeatureStatus.UNREVIEWED: "Не проверен экспертом",
                ExpertFeatureStatus.CONFIRMED: "Подтверждён экспертом",
                ExpertFeatureStatus.REJECTED: "Не используется",
                ExpertFeatureStatus.CORRECTED: "Исправлен экспертом",
            }
            for observation in self.result.feature_observations:
                definition = self.service.features.registry.get(observation.feature_id)
                applicability = ("Рассчитан" if observation.applicability is Applicability.APPLICABLE
                                 else "Недостаточно данных")
                item = QListWidgetItem(
                    f"{definition.name_ru} · {applicability}\n"
                    f"{observation.feature_id} · {labels[observation.expert_status]}"
                )
                item.setData(Qt.ItemDataRole.UserRole, observation)
                page.addItem(item)
            page.currentItemChanged.connect(self.select_metric)
            self.toolbox.addItem(page, "Методические AUTO-показатели")

    def select_metric(self, item, previous=None):
        if item is None:
            return
        metric = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(metric, FeatureObservation):
            self.select_feature(metric)
            return
        self.current_feature = None
        self.feature_review_panel.hide()
        self.metric_help.setText(metric.explanation)
        self.text_view.highlight(metric.spans, METRIC_HIGHLIGHT)
        self.highlight_note.setText(f"Связанных фрагментов: {len(metric.spans)}" if metric.spans else GLOBAL_NOTE)

    def select_feature(self, observation):
        self.current_feature = observation
        definition = self.service.features.registry.get(observation.feature_id)
        applicability = ("применим" if observation.applicability is Applicability.APPLICABLE
                         else "недостаточно данных")
        raw = feature_value_preview(observation.raw_value, 3)
        normalized = feature_value_preview(observation.normalized_value, 3)
        main_source = definition.sources[0]
        self.metric_help.setText(
            f"{definition.name_ru}. Внутренняя операционализация, код: {definition.id}.\n"
            f"Что считаем: {definition.definition}\n"
            f"Сырое значение: {raw}\nНормированное значение: {normalized}\n"
            f"Статус расчёта: {applicability}. Основание: {main_source.title}, {main_source.locator}."
        )
        self.metric_help.setToolTip(
            "Полные данные:\n" + json.dumps({
                "raw": observation.raw_value,
                "normalized": observation.normalized_value,
            }, ensure_ascii=False, sort_keys=True, indent=2)
        )
        spans = tuple(item.span for item in observation.evidence)
        self.text_view.highlight(spans, METRIC_HIGHLIGHT)
        self.highlight_note.setText(
            f"Найдено реализаций: {len(spans)}. До подтверждения показатель не участвует в сопоставлении."
        )
        self.feature_comment.setText(observation.expert_comment)
        enabled = observation.applicability is Applicability.APPLICABLE
        self.confirm_feature_button.setEnabled(enabled)
        self.reject_feature_button.setEnabled(enabled)
        self.feature_review_panel.show()

    def review_feature(self, status):
        if self.current_feature is None:
            return
        previous = self.current_feature.expert_status
        self.current_feature.review(status, comment=self.feature_comment.text())
        self.record_event("feature_reviewed", {
            "slot": self.current_slot + 1,
            "document_id": self.result.document_id,
            "feature_id": self.current_feature.feature_id,
            "from": previous.value,
            "to": status.value,
        })
        self.populate_metrics()

    def populate_candidates(self, *_):
        self.record_comment_if_changed()
        selected_id = self.current_candidate.id if self.current_candidate else None
        self.candidate_list.blockSignals(True)
        self.candidate_list.clear()
        wanted = [None, ReviewStatus.NEW, ReviewStatus.ACCEPTED, ReviewStatus.REJECTED][self.filter.currentIndex()]
        wanted_group = self.candidate_group_filter.currentData()
        selected_item = None
        for candidate in self.result.candidates if self.result else []:
            if wanted is not None and candidate.status != wanted:
                continue
            if wanted_group is not None and candidate_group_key(candidate) != wanted_group:
                continue
            fragment = candidate.fragment.replace("\n", " ").replace("\r", " ")
            if len(fragment) > 55:
                fragment = fragment[:52] + "…"
            category = (
                UNKNOWN_WORD_CLASSIFICATION_LABELS.get(
                    candidate.expert_classification, candidate.category,
                ) if candidate_group_key(candidate) == "unknown_words" else candidate.category
            )
            item = QListWidgetItem(f"{category} · {STATUS_LABELS[candidate.status]}\n«{fragment}»" if fragment else f"{category} · {STATUS_LABELS[candidate.status]}\nМесто возможной вставки")
            item.setData(Qt.ItemDataRole.UserRole, candidate.id)
            self.candidate_list.addItem(item)
            if candidate.id == selected_id:
                selected_item = item
        self.candidate_list.blockSignals(False)
        self.current_candidate = None
        if selected_item or self.candidate_list.count():
            self.candidate_list.setCurrentItem(selected_item or self.candidate_list.item(0))
        else:
            self.set_candidate_enabled(False)
            self.candidate_detail.setText("В этом списке нет кандидатов.")
            self.explanation.clear()
            self.comment.clear()
            self.text_view.highlight(())
        self.update_review_summary()

    def populate_candidate_groups(self):
        current = self.candidate_group_filter.currentData()
        groups = group_candidates(self.result.candidates) if self.result else ()
        self.candidate_group_filter.blockSignals(True)
        self.candidate_group_filter.clear()
        self.candidate_group_filter.addItem("Все группы", None)
        for group in groups:
            self.candidate_group_filter.addItem(
                f"{group.definition.title} · {len(group.candidates)}",
                group.definition.key,
            )
        index = self.candidate_group_filter.findData(current)
        self.candidate_group_filter.setCurrentIndex(max(index, 0))
        self.candidate_group_filter.blockSignals(False)
        self.candidate_group_changed()

    def candidate_group_changed(self, *_):
        key = self.candidate_group_filter.currentData()
        if key is None:
            help_text = (
                "Кандидаты разделены по типу автоматической рекомендации. Выберите группу для пояснения."
            )
        else:
            group = next((item for item in group_candidates(self.result.candidates)
                          if item.definition.key == key), None) if self.result else None
            help_text = group.definition.description if group else ""
        self.candidate_group_help.setText(help_text)
        self.candidate_group_help.setToolTip(help_text)
        self.populate_candidates()

    def update_review_summary(self):
        if not self.result:
            return
        if "languagetool" not in self.result.metadata:
            self.right_subtitle.setText("LanguageTool: проверка не выполнена")
            return
        counts = {s: sum(c.status == s for c in self.result.candidates) for s in ReviewStatus}
        self.right_subtitle.setText(f"Всего: {len(self.result.candidates)} · принято: {counts[ReviewStatus.ACCEPTED]} · отклонено: {counts[ReviewStatus.REJECTED]} · осталось: {counts[ReviewStatus.NEW]}")

    def select_candidate(self, item, previous=None):
        if not item or not self.result:
            return
        self.record_comment_if_changed()
        self.current_candidate = next(c for c in self.result.candidates if c.id == item.data(Qt.ItemDataRole.UserRole))
        candidate = self.current_candidate
        self.set_candidate_enabled(True)
        if candidate_group_key(candidate) == "unknown_words":
            self.accept_button.setText("Сохранить особую словоформу")
            self.unknown_classification.blockSignals(True)
            index = self.unknown_classification.findData(candidate.expert_classification)
            self.unknown_classification.setCurrentIndex(max(0, index))
            self.unknown_classification.blockSignals(False)
            self.unknown_classification.show()
            self.accept_button.setEnabled(bool(candidate.expert_classification))
            self.show_word_evidence(candidate)
            self.show_llm_hint(candidate)
        else:
            self.accept_button.setText("Подтвердить наблюдение")
            self.unknown_classification.hide()
            self.evidence_label.hide()
            for widget in self.hint_widgets:
                widget.hide()
        self.reject_button.setText("Не учитывать")
        category = UNKNOWN_WORD_CLASSIFICATION_LABELS.get(
            candidate.expert_classification, candidate.category,
        )
        self.candidate_detail.setText(f"{category} · {STATUS_LABELS[candidate.status]}\nИсточник: {candidate.source}")
        message = candidate.explanation
        if candidate.replacements:
            heading = ("Автоматические догадки словаря LT — не варианты исправления: "
                       if candidate.rule_id == "MORFOLOGIK_RULE_RU_RU"
                       else "Предлагаемые варианты: ")
            message += "\n\n" + heading + ", ".join(candidate.replacements[:5])
        self.explanation.setPlainText(message)
        self.comment.blockSignals(True)
        self.comment.setPlainText(candidate.comment)
        self.comment.blockSignals(False)
        self.text_view.highlight((candidate.span,))
        context = self.material.text[max(0, candidate.span.start - 35):candidate.span.end + 35].replace("\n", " ").replace("\r", " ")
        self.highlight_note.setText(("Место вставки · " if candidate.span.start == candidate.span.end else "Контекст · ") + context)

    def set_candidate_enabled(self, enabled):
        for widget in [self.accept_button, self.reject_button, self.reset_button, self.comment]:
            widget.setEnabled(enabled)
        if not enabled:
            self.unknown_classification.hide()
            self.accept_button.setText("Подтвердить наблюдение")
            self.reject_button.setText("Не учитывать")

    def frequency_dictionary(self):
        """Снимок словаря читается один раз и работает офлайн."""
        if getattr(self, "_frequency", None) is None:
            try:
                self._frequency = FrequencyDictionary.load()
            except (OSError, ValueError):
                logging.getLogger(__name__).warning("Снимок частотного словаря недоступен")
                self._frequency = FrequencyDictionary.empty()
        return self._frequency

    def word_evidence(self, candidate):
        tokens = self.result.tokens if self.result else ()
        return collect_word_evidence(
            candidate, self.material.text, tokens, self.frequency_dictionary(),
        )

    def show_word_evidence(self, candidate):
        """Числа по словоформе. Метку из них не выводим.

        Автоматические вердикты были и сняты контрольным набором: из 37 верными
        оказались 4, потому что LanguageTool предлагает исправление любому
        незнакомому слову. Числа остаются доводом для эксперта.
        """
        lines = list(summary_lines(self.word_evidence(candidate)))
        self.evidence_label.setText("Справка · " + " · ".join(lines))
        self.evidence_label.show()

    def show_llm_hint(self, candidate):
        """Подсказка видна только для нераспознанных словоформ текущего кандидата."""
        for widget in self.hint_widgets:
            widget.show()
        if candidate.llm_hint:
            title = UNKNOWN_WORD_CLASSIFICATION_LABELS.get(
                candidate.llm_hint, candidate.llm_hint,
            )
            reason = f" · {candidate.llm_hint_reason}" if candidate.llm_hint_reason else ""
            self.hint_label.setText(f"Подсказка Qwen: {title}{reason}")
            self.hint_apply_button.setEnabled(
                candidate.llm_hint != candidate.expert_classification
            )
        else:
            self.hint_label.setText(
                "Подсказка Qwen не запрашивалась · она не является выводом "
                "и в заключение не попадает"
            )
            self.hint_apply_button.setEnabled(False)

    def apply_llm_hint(self):
        """Переносит метку подсказки в выбор эксперта по его прямому действию."""
        candidate = self.current_candidate
        if not candidate or not candidate.llm_hint:
            return
        index = self.unknown_classification.findData(candidate.llm_hint)
        if index < 0:
            return
        self.unknown_classification.setCurrentIndex(index)
        self.record_event("llm_hint_applied", {
            "document_id": candidate.document_id,
            "candidate_id": candidate.id,
            "classification": candidate.llm_hint,
        })
        self.status.setText(
            "Подсказка перенесена в выбор эксперта · решение и ответственность ваши"
        )
        self.show_llm_hint(candidate)

    def unknown_word_candidates(self):
        if not self.result:
            return []
        return [item for item in self.result.candidates
                if candidate_group_key(item) == "unknown_words"]

    def request_llm_hints(self):
        if self.busy or not self.material:
            return
        candidates = self.unknown_word_candidates()
        if not candidates:
            self.status.setText("Нераспознанных словоформ нет · подсказки не нужны")
            return
        missing = [name for path, name in (
            (DEFAULT_QWEN_RUNTIME, "исполняемый файл llama.cpp"),
            (DEFAULT_QWEN_MODEL, "файл модели Qwen"),
        ) if not Path(path).is_file()]
        if missing:
            self.status.setText("Не найден: " + ", ".join(missing))
            return
        self.set_busy(True)
        self.hint_request_button.setEnabled(False)
        self.hint_worker = LtHintWorker(
            candidates, self.material.text,
            runtime=DEFAULT_QWEN_RUNTIME, model=DEFAULT_QWEN_MODEL,
            tokens=self.result.tokens if self.result else (),
            dictionary=self.frequency_dictionary(),
        )
        self.hint_worker.progress.connect(self.status.setText)
        self.hint_worker.completed.connect(self.llm_hints_ready)
        self.hint_worker.failed.connect(self.llm_hints_failed)
        self.hint_worker.finished.connect(lambda: self.set_busy(False))
        self.hint_worker.finished.connect(lambda: self.hint_request_button.setEnabled(True))
        self.hint_worker.start()

    def llm_hints_ready(self, hints):
        """Записывает подсказки, никогда не трогая выбор эксперта."""
        by_id = {item.candidate_id: item for item in hints}
        applied = 0
        for candidate in self.unknown_word_candidates():
            hint = by_id.get(candidate.id)
            if hint is None or hint.status.value != "VALIDATED_HINT":
                continue
            candidate.llm_hint = hint.classification
            candidate.llm_hint_reason = hint.reason
            applied += 1
        if applied:
            self.mark_dirty()
            self.record_event("llm_hints_received", {
                "candidates": len(hints), "hints": applied,
                "profile_version": QWEN_HINT_PROFILE_VERSION,
            })
        self.status.setText(
            f"Подсказки Qwen: {applied} из {len(hints)} · это не вывод, "
            "решение по каждой словоформе принимает эксперт"
        )
        if self.current_candidate:
            self.show_llm_hint(self.current_candidate)

    def llm_hints_failed(self, message: str):
        self.status.setText("Локальная модель не запустилась · подсказки не получены")
        logging.getLogger(__name__).error("Подсказки Qwen: %s", message)

    def classification_changed(self):
        if not self.current_candidate or candidate_group_key(self.current_candidate) != "unknown_words":
            return
        previous = self.current_candidate.expert_classification
        current = str(self.unknown_classification.currentData() or "")
        self.current_candidate.expert_classification = current
        self.accept_button.setEnabled(bool(current))
        title = UNKNOWN_WORD_CLASSIFICATION_LABELS.get(
            current, self.current_candidate.category,
        )
        self.candidate_detail.setText(
            f"{title} · {STATUS_LABELS[self.current_candidate.status]}\n"
            f"Источник: {self.current_candidate.source}"
        )
        if previous != current:
            self.mark_dirty()
            self.record_event("candidate_classified", {
                "document_id": self.current_candidate.document_id,
                "candidate_id": self.current_candidate.id,
                "from": previous, "to": current,
            })

    def comment_changed(self):
        if self.current_candidate:
            self.current_candidate.comment = self.comment.toPlainText()
            self.mark_dirty()

    def decide(self, status):
        if self.current_candidate:
            if (status is ReviewStatus.ACCEPTED
                    and candidate_group_key(self.current_candidate) == "unknown_words"
                    and not self.current_candidate.expert_classification):
                self.status.setText("Сначала укажите, что это за словоформа.")
                return
            self.record_comment_if_changed()
            previous = self.current_candidate.status
            self.current_candidate.review(status, self.comment.toPlainText())
            self.record_event("candidate_reviewed", {
                "document_id": self.current_candidate.document_id,
                "candidate_id": self.current_candidate.id,
                "category": self.current_candidate.category,
                "expert_classification": self.current_candidate.expert_classification,
                "from": previous.value, "to": status.value,
            })
            self.populate_candidates()

    def next_candidate(self):
        if not self.result:
            return
        self.record_comment_if_changed()
        candidates = self.result.candidates
        current = next((i for i, c in enumerate(candidates) if c is self.current_candidate), -1)
        ordered = candidates[current + 1:] + candidates[:current + 1]
        target = next((c for c in ordered if c.status == ReviewStatus.NEW), None)
        if target is None:
            self.status.setText("Все кандидаты рассмотрены. Вы можете изменить любое решение.")
            return
        self.current_candidate = target
        self.filter.blockSignals(True)
        self.filter.setCurrentIndex(0)
        self.filter.blockSignals(False)
        self.populate_candidates()

    def configure(self):
        dialog = ResourceDialog(self.settings, self)
        if dialog.exec():
            try:
                settings = dialog.settings()
                settings.save()
                self.settings = settings
                self.service = AnalysisService(settings)
                self.status.setText("Настройки сохранены. Они будут использованы при следующем анализе.")
            except OSError:
                self.error_label.setText("Не удалось сохранить настройки. Проверьте доступ к папке программы.")
                self.error_label.show()

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.status.setText("Дождитесь завершения анализа перед закрытием окна.")
            event.ignore()
        elif self.dirty and not self.confirm_discard():
            event.ignore()
        else:
            event.accept()
