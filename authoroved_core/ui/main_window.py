from pathlib import Path

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox, QDialog, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QProgressBar, QLayout,
    QPushButton, QScrollArea, QSplitter, QStackedWidget, QTextEdit, QToolBox,
    QVBoxLayout, QWidget,
)

from authoroved_core.core.analysis import AnalysisService
from authoroved_core.core.comparison import compare_results
from authoroved_core.core.document import EncodingChoiceRequired, load_document
from authoroved_core.core.models import ReviewStatus, STATUS_LABELS
from authoroved_core.metrics.basic import GLOBAL_NOTE, WORD_PATTERN
from authoroved_core.nlp.settings import LocalSettings
from authoroved_core.ui.text_view import SourceTextView
from authoroved_core.ui.appearance import STYLE, METRIC_HIGHLIGHT



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

    def __init__(self, settings=None, service=None):
        super().__init__()
        self.setWindowTitle("Авторовед Core — новый анализ")
        self.resize(1280, 900)
        self.setMinimumSize(1060, 760)
        self.setStyleSheet(STYLE)
        self.settings = settings or LocalSettings.load()
        self.service = service or AnalysisService(self.settings)
        self.materials = [None, None]
        self.results = [None, None]
        self.current_slot = 0
        self.worker = None
        self.worker_slot = None
        self.current_candidate = None
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
        self.open_button = button("Новый анализ", self.open_file, True)
        header.addWidget(self.settings_button)
        header.addWidget(self.open_button)
        layout.addLayout(header)
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
        layout.addWidget(label("Предварительная версия · до двух документов · решения сохраняются только до закрытия окна", "notice"))
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
        metrics_layout.addWidget(button("Перейти к проверке кандидатов →", lambda: self.show_stage(2), True))
        self.pages.addWidget(self.metrics_page)

        self.review_page = QWidget()
        self.review_page.setObjectName("reviewPage")
        review_layout = QVBoxLayout(self.review_page)
        review_layout.setSizeConstraints(QLayout.SizeConstraint.SetNoConstraint,
                                         QLayout.SizeConstraint.SetMinimumSize)
        review_layout.setContentsMargins(0, 4, 0, 0)
        self.filter = QComboBox()
        self.filter.addItems(["Все кандидаты", "Не рассмотрены", "Приняты", "Отклонены"])
        self.filter.currentIndexChanged.connect(self.populate_candidates)
        review_layout.addWidget(self.filter)
        self.candidate_list = QListWidget()
        self.candidate_list.setWordWrap(True)
        self.candidate_list.setFixedHeight(124)
        self.candidate_list.currentItemChanged.connect(self.select_candidate)
        review_layout.addWidget(self.candidate_list, 1)
        review_card = QFrame()
        review_card.setObjectName("reviewCard")
        review_card.setMinimumHeight(145)
        detail_layout = QVBoxLayout(review_card)
        detail_layout.setContentsMargins(12, 8, 12, 8)
        detail_layout.setSpacing(5)
        self.candidate_detail = label("Выберите кандидата в списке.", "candidateDetail")
        detail_layout.addWidget(self.candidate_detail)
        self.explanation = QTextEdit()
        self.explanation.setObjectName("explanation")
        self.explanation.setReadOnly(True)
        self.explanation.setFixedHeight(82)
        detail_layout.addWidget(self.explanation)
        review_layout.addWidget(review_card)
        self.comment = QTextEdit()
        self.comment.setObjectName("comment")
        self.comment.setPlaceholderText("Комментарий эксперта (необязательно)")
        self.comment.setFixedHeight(62)
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
        layout.addWidget(self.workspace, 1)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.hide()
        layout.addWidget(self.progress_bar)
        self.status = label("Готово к работе · анализ выполняется на вашем компьютере", "muted")
        layout.addWidget(self.status)
        self.show_stage(0)
        self.set_candidate_enabled(False)

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
        accepted_layout.addWidget(self.comparison_help)
        lower.addWidget(accepted_panel)
        lower.setSizes([660, 540])
        page_layout.addWidget(lower, 2)
        return page

    def confirm_discard(self):
        if not any(self.results):
            return True
        dialog = QMessageBox(self)
        dialog.setWindowTitle("Начать заново?")
        dialog.setText("Результаты, комментарии и решения текущего сеанса будут потеряны. Сохранение на диск появится на этапе D.")
        continue_button = dialog.addButton("Начать заново", QMessageBox.ButtonRole.AcceptRole)
        dialog.addButton("Остаться", QMessageBox.ButtonRole.RejectRole)
        dialog.exec()
        return dialog.clickedButton() is continue_button

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
            self.materials = [None, None]
            self.results = [None, None]
            self.current_slot = 0
            self.load_path(path, slot=0)

    def open_second_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Выберите второй текст", "", "Текстовые документы (*.txt *.docx)")
        if not path:
            return
        if self.results[1]:
            dialog = QMessageBox(self)
            dialog.setWindowTitle("Заменить второй текст?")
            dialog.setText("Результаты и решения по тексту 2 будут потеряны.")
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
        self.materials[target_slot] = material
        self.results[target_slot] = None
        self.current_slot = target_slot
        self.current_candidate = None
        self.update_material_selector()
        self.material_selector.setCurrentIndex(target_slot)
        self.render_current_material()
        self.error_label.hide()
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
        self.update_workflow_button()

    def switch_material(self, index):
        if index == self.current_slot:
            return
        self.current_slot = index
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
            return
        self.filename.setText(material.name)
        self.text_view.set_source(material.text)
        preliminary_words = len(WORD_PATTERN.findall(material.text))
        self.summary.setText(f"{len(material.text):,} символов · около {preliminary_words} слов · предложения определятся после анализа".replace(",", " "))
        self.import_note.setText(material.import_note)
        self.hash_note.setText("SHA-256 исходного файла\n" + material.file_sha256[:32] + "\n" + material.file_sha256[32:])
        self.hash_note.setToolTip(material.file_sha256)
        self.analyze_button.setEnabled(not (self.worker and self.worker.isRunning()))
        if result:
            values = {metric.name: metric.value for metric in result.metrics}
            self.summary.setText(" · ".join(
                f"{values[name]} {unit}" for name, unit in
                [("Слова", "слов"), ("Предложения", "предложений"), ("Абзацы", "абзацев")]
                if name in values
            ))
            self.populate_metrics()
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

    def set_busy(self, busy):
        self.progress_bar.setVisible(busy)
        self.open_button.setEnabled(not busy)
        self.settings_button.setEnabled(not busy)
        self.material_selector.setEnabled(not busy)
        self.analyze_button.setEnabled(not busy and self.material is not None)
        for i in range(3):
            self.stage_buttons[i].setEnabled(not busy)
        self.stage_buttons[3].setEnabled(not busy and all(self.results))

    def analysis_failed(self):
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
        self.populate_candidates()
        self.stage_buttons[3].setEnabled(all(self.results))
        self.update_workflow_button()
        self.show_stage(1)
        self.status.setText(("Анализ выполнен частично" if result.errors else f"Анализ текста {slot + 1} завершён") + " · результаты требуют вашей проверки")

    def show_stage(self, index):
        if index > 3:
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
                f"{group.category}\n{group.relation} · текст 1: {group.count_first} · текст 2: {group.count_second}"
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
            "Группировка наблюдений выполнена по категории. Она не означает совпадение одного языкового признака."
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
                f"{metric.name}\nТекст 1: {metric.value_first} · Текст 2: {metric.value_second} · разница: {metric.difference}"
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
        self.comparison_help.setText(metric.explanation + "\n\n" + fragment_note)

    def select_comparison_candidate_group(self, item, previous=None):
        if item is None or item.data(Qt.ItemDataRole.UserRole) is None:
            return
        group = item.data(Qt.ItemDataRole.UserRole)
        self.comparison_texts[0].highlight(group.spans_first)
        self.comparison_texts[1].highlight(group.spans_second)
        self.comparison_help.setText(
            f"{group.relation}. Принято наблюдений: {group.count_first} в тексте 1 и "
            f"{group.count_second} в тексте 2. Категория сама по себе не является выводом об авторстве."
        )

    def populate_metrics(self):
        while self.toolbox.count():
            page = self.toolbox.widget(0)
            self.toolbox.removeItem(0)
            page.deleteLater()
        for group in ["Количественные показатели", "Лексика", "Морфология", "Предложения", "Структура", "Технические связи Stanza (UD)"]:
            page = QListWidget()
            page.setWordWrap(True)
            for metric in self.result.metrics:
                if metric.group == group:
                    item = QListWidgetItem(f"{metric.name}\n{metric.value}")
                    item.setData(Qt.ItemDataRole.UserRole, metric)
                    page.addItem(item)
            page.currentItemChanged.connect(self.select_metric)
            self.toolbox.addItem(page, group)

    def select_metric(self, item, previous=None):
        if item is None:
            return
        metric = item.data(Qt.ItemDataRole.UserRole)
        self.metric_help.setText(metric.explanation)
        self.text_view.highlight(metric.spans, METRIC_HIGHLIGHT)
        self.highlight_note.setText(f"Связанных фрагментов: {len(metric.spans)}" if metric.spans else GLOBAL_NOTE)

    def populate_candidates(self, *_):
        selected_id = self.current_candidate.id if self.current_candidate else None
        self.candidate_list.blockSignals(True)
        self.candidate_list.clear()
        wanted = [None, ReviewStatus.NEW, ReviewStatus.ACCEPTED, ReviewStatus.REJECTED][self.filter.currentIndex()]
        selected_item = None
        for candidate in self.result.candidates if self.result else []:
            if wanted is not None and candidate.status != wanted:
                continue
            fragment = candidate.fragment.replace("\n", " ").replace("\r", " ")
            if len(fragment) > 55:
                fragment = fragment[:52] + "…"
            item = QListWidgetItem(f"{candidate.category} · {STATUS_LABELS[candidate.status]}\n«{fragment}»" if fragment else f"{candidate.category} · {STATUS_LABELS[candidate.status]}\nМесто возможной вставки")
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
        self.current_candidate = next(c for c in self.result.candidates if c.id == item.data(Qt.ItemDataRole.UserRole))
        candidate = self.current_candidate
        self.set_candidate_enabled(True)
        self.candidate_detail.setText(f"{candidate.category} · {STATUS_LABELS[candidate.status]}\nИсточник: {candidate.source}")
        message = candidate.explanation
        if candidate.replacements:
            heading = ("Варианты из словаря LanguageTool: "
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

    def comment_changed(self):
        if self.current_candidate:
            self.current_candidate.comment = self.comment.toPlainText()

    def decide(self, status):
        if self.current_candidate:
            self.current_candidate.review(status, self.comment.toPlainText())
            self.populate_candidates()

    def next_candidate(self):
        if not self.result:
            return
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
        elif any(self.results) and not self.confirm_discard():
            event.ignore()
        else:
            event.accept()
