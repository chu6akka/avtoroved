"""
Вкладка 11: Модель / Корпус — управление самообучением.
"""
from __future__ import annotations
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QLabel, QPushButton, QProgressBar, QTableWidget,
    QTableWidgetItem, QHeaderView, QMessageBox, QSplitter,
    QComboBox, QScrollArea, QFrame,
)
from PyQt6.QtCore import Qt, pyqtSignal, QThread
from PyQt6.QtGui import QColor

from analyzer import corpus_manager, learning_backend as lb_module
from analyzer import rusvec_engine as rusvec_module
from analyzer import strat_annotator


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


class TrainAnnotatorThread(QThread):
    """Фоновый поток обучения ML-фильтра стратификации."""
    status   = pyqtSignal(str)
    finished = pyqtSignal(bool, str)   # success, message

    def run(self):
        annotations = corpus_manager.get_all_strat_annotations()
        ok, msg = strat_annotator.retrain(annotations)
        self.finished.emit(ok, msg)


class LearningTab(QWidget):
    """Вкладка управления корпусом и моделью самообучения."""

    train_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._lb        = lb_module.get()
        self._rusvec    = rusvec_module.get()
        self._train_thread        = None
        self._expand_thread       = None
        self._download_thread     = None
        self._annotator_thread    = None
        self._ann_ids: list       = []
        self._ud_ids: list        = []
        self._setup_ui()
        self.refresh()

    def _make_stat_card(self, val_text: str, label_text: str) -> tuple:
        """Создать вертикальную карточку статистики. Возвращает (widget, val_lbl)."""
        card = QFrame()
        card.setFrameShape(QFrame.Shape.StyledPanel)
        card.setStyleSheet(
            "QFrame { background: transparent; border: none; }"
        )
        cl = QVBoxLayout(card)
        cl.setContentsMargins(8, 4, 8, 4)
        cl.setSpacing(1)
        val_lbl = QLabel(val_text)
        val_lbl.setObjectName("stat_val")
        val_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl = QLabel(label_text)
        lbl.setObjectName("stat_label")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl.addWidget(val_lbl)
        cl.addWidget(lbl)
        return card, val_lbl

    def _setup_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── Прокручиваемая область ────────────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        outer.addWidget(scroll)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)
        scroll.setWidget(content)

        # ── Заголовок-баннер ──────────────────────────────────────────────
        banner = QLabel(
            "Корпус · Модели · Словарь — управление самообучением анализатора"
        )
        banner.setObjectName("title")
        banner.setWordWrap(True)
        layout.addWidget(banner)

        desc = QLabel(
            "Программа накапливает корпус из анализируемых текстов, дообучает FastText "
            "для семантического сравнения и расширяет тематические словари через "
            "векторные модели Navec / RusVectores."
        )
        desc.setWordWrap(True)
        desc.setObjectName("subtitle")
        layout.addWidget(desc)

        # ── Памятка по обучению (сворачивается) ──────────────────────────
        memo_group = QGroupBox("  Памятка по обучению")
        memo_group.setObjectName("corpus_box")
        memo_layout = QVBoxLayout(memo_group)
        memo_layout.setSpacing(4)

        self._btn_memo_toggle = QPushButton("▼  Показать памятку")
        self._btn_memo_toggle.setObjectName("secondary")
        self._btn_memo_toggle.setCheckable(True)
        self._btn_memo_toggle.setChecked(False)
        self._btn_memo_toggle.clicked.connect(self._toggle_memo)
        memo_layout.addWidget(self._btn_memo_toggle)

        self._memo_widget = QFrame()
        self._memo_widget.setVisible(False)
        memo_inner = QVBoxLayout(self._memo_widget)
        memo_inner.setContentsMargins(4, 4, 4, 4)
        memo_inner.setSpacing(6)

        _MEMO_STEPS = [
            ("1 · Наполнение корпуса",
             "#e8a030",
             "Корпус пополняется автоматически при каждом анализе — ничего делать не нужно.\n"
             "Рекомендуется 20–50 текстов одной тематики перед первым обучением.\n"
             "Прогресс-бар показывает накопление до минимального порога (500 слов / 3 текста)."),

            ("2 · Обучить FastText",
             "#5aa0e8",
             "Нажмите один раз после набора достаточного корпуса.\n"
             "Используется только для вкладки «Сравнение» — не влияет на стратификацию и тематику.\n"
             "Повторные нажатия дообучают модель — не делайте это после каждого текста.\n"
             "Для переобучения с нуля: удалите models/fasttext.model вручную."),

            ("3 · Расширить тематические словари",
             "#4db8b8",
             "Сначала обучите FastText (шаг 2) и загрузите векторную модель (Navec или RusVectores).\n"
             "RusVectores (~462 МБ) точнее для научной/юридической/медицинской лексики.\n"
             "Navec (~50 МБ) быстрее, но обучен на художественной литературе.\n"
             "Нажимайте «Расширить словари» один раз — повторные нажатия раздувают словари мусором.\n"
             "После расширения проанализируйте тот же текст заново и сравните тематику."),

            ("4 · ML-фильтр стратификации",
             "#b888e8",
             "Открыть вкладку «Стратификация» → найти слово в не том пласте → ПКМ → «✗ Ложное срабатывание».\n"
             "Также помечайте правильные слова: ПКМ → «✓ Подтвердить».\n"
             "После 10+ аннотаций кнопка «Обучить ML-фильтр» разблокируется.\n"
             "Пометки не удаляют слово из словаря — только уточняют, что в данном контексте оно нейтральное.\n"
             "В другом тексте с жаргонным употреблением того же слова — оно всё равно будет показано."),

            ("5 · Пользовательский словарь (фильтр LT)",
             "#6abf69",
             "Незнакомые слова, которые LT помечает как ошибку — добавляйте через ПКМ во вкладке «Ошибки».\n"
             "Выбирайте пласт/тему точно: медицинский термин → «Медицинская», жаргон → нужный пласт.\n"
             "Слово сразу исчезает из ошибок LT и учитывается в тематическом / стилистическом анализе."),

            ("⚠  Чего не делать",
             "#e06c6c",
             "— Не нажимать «Обучить FastText» после каждого текста.\n"
             "— Не нажимать «Расширить словари» многократно на одном корпусе.\n"
             "— Не смешивать в корпусе тексты разных жанров, если нужна точная тематика.\n"
             "— «Очистить корпус» не удаляет обученные модели и пометки — только сырые тексты."),
        ]

        for title, color, body in _MEMO_STEPS:
            step_frame = QFrame()
            step_frame.setStyleSheet(
                f"QFrame {{ border-left: 3px solid {color}; "
                f"background-color: transparent; padding-left: 6px; }}"
            )
            sf_layout = QVBoxLayout(step_frame)
            sf_layout.setContentsMargins(8, 4, 4, 4)
            sf_layout.setSpacing(2)

            title_lbl = QLabel(title)
            title_lbl.setStyleSheet(
                f"font-weight: 700; font-size: 12px; color: {color}; "
                f"background: transparent; border: none;"
            )
            body_lbl = QLabel(body)
            body_lbl.setObjectName("caption")
            body_lbl.setWordWrap(True)
            body_lbl.setStyleSheet("background: transparent; border: none;")

            sf_layout.addWidget(title_lbl)
            sf_layout.addWidget(body_lbl)
            memo_inner.addWidget(step_frame)

        memo_layout.addWidget(self._memo_widget)
        layout.addWidget(memo_group)

        # ── Верхний сплиттер: корпус+FastText | векторные модели ─────────
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        # ── Левая панель ──────────────────────────────────────────────────
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 4, 0)
        left_layout.setSpacing(8)

        # Корпус — с карточками статистики
        corpus_group = QGroupBox("  Корпус текстов")
        corpus_group.setObjectName("corpus_box")
        corpus_form = QVBoxLayout(corpus_group)
        corpus_form.setSpacing(8)

        # Три карточки: текстов / слов / дата
        cards_row = QHBoxLayout()
        cards_row.setSpacing(0)
        c1, self.lbl_texts = self._make_stat_card("—", "ТЕКСТОВ")
        c2, self.lbl_words = self._make_stat_card("—", "СЛОВ")
        c3, self.lbl_last  = self._make_stat_card("—", "ОБНОВЛЕНО")
        for c in (c1, c2, c3):
            cards_row.addWidget(c, 1)
        corpus_form.addLayout(cards_row)

        # Прогресс-бар
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, corpus_manager.MIN_WORDS_FOR_TRAINING)
        self.progress_bar.setFormat("%v / %m слов")
        self.progress_bar.setTextVisible(True)
        corpus_form.addWidget(self.progress_bar)

        self.lbl_status = QLabel("Статус: —")
        self.lbl_status.setObjectName("section_status")
        self.lbl_status.setWordWrap(True)
        corpus_form.addWidget(self.lbl_status)

        btn_row = QHBoxLayout()
        self.btn_refresh = QPushButton("↺  Обновить")
        self.btn_refresh.setObjectName("secondary")
        self.btn_refresh.clicked.connect(self.refresh)
        self.btn_clear_corpus = QPushButton("Очистить корпус")
        self.btn_clear_corpus.setObjectName("danger")
        self.btn_clear_corpus.clicked.connect(self._clear_corpus)
        btn_row.addWidget(self.btn_refresh)
        btn_row.addWidget(self.btn_clear_corpus)
        corpus_form.addLayout(btn_row)
        left_layout.addWidget(corpus_group)

        # FastText
        ft_group = QGroupBox("  FastText — сравнение текстов")
        ft_group.setObjectName("model_box")
        ft_form  = QVBoxLayout(ft_group)
        ft_form.setSpacing(6)

        self.lbl_ft_status = QLabel("FastText: не обучена")
        self.lbl_ft_status.setObjectName("section_status")
        self.lbl_vocab = QLabel("Словарь: —")
        self.lbl_vocab.setObjectName("subtitle")

        note = QLabel(
            "Семантическое сходство во вкладке «Сравнение».\n"
            "Тематические словари не изменяет."
        )
        note.setObjectName("caption")
        note.setWordWrap(True)

        self.train_status = QLabel("")
        self.train_status.setWordWrap(True)
        self.train_status.setObjectName("subtitle")

        for w in (self.lbl_ft_status, self.lbl_vocab, note, self.train_status):
            ft_form.addWidget(w)

        self.btn_train = QPushButton("▶  Обучить FastText")
        self.btn_train.setObjectName("primary")
        self.btn_train.clicked.connect(self._run_training)
        ft_form.addWidget(self.btn_train)
        left_layout.addWidget(ft_group)

        left_layout.addStretch()
        splitter.addWidget(left)

        # ── Правая панель ─────────────────────────────────────────────────
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(4, 0, 0, 0)
        right_layout.setSpacing(8)

        vec_group = QGroupBox("  Векторные модели — расширение словарей")
        vec_group.setObjectName("vec_box")
        vec_form  = QVBoxLayout(vec_group)
        vec_form.setSpacing(6)

        self.lbl_navec_status  = QLabel()
        self.lbl_rusvec_status = QLabel()
        self._update_vec_status_labels()
        for lbl in (self.lbl_navec_status, self.lbl_rusvec_status):
            lbl.setWordWrap(True)
            vec_form.addWidget(lbl)

        vec_desc = QLabel(
            "Navec (Natasha/Яндекс): ~50 МБ · без POS · худ. литература\n"
            "RusVectores (НКРЯ ИРЯ РАН): ~462 МБ · UPOS-теги · академический корпус"
        )
        vec_desc.setObjectName("caption")
        vec_desc.setWordWrap(True)
        vec_form.addWidget(vec_desc)

        dl_row = QHBoxLayout()
        self.btn_download_navec  = QPushButton("⬇  Navec (~50 МБ)")
        self.btn_download_navec.setObjectName("secondary")
        self.btn_download_navec.clicked.connect(self._navec_btn_action)
        self.btn_download_rusvec = QPushButton("⬇  RusVectores (~462 МБ)")
        self.btn_download_rusvec.setObjectName("secondary")
        self.btn_download_rusvec.clicked.connect(self._rusvec_btn_action)
        dl_row.addWidget(self.btn_download_navec)
        dl_row.addWidget(self.btn_download_rusvec)
        vec_form.addLayout(dl_row)

        expand_row = QHBoxLayout()
        expand_lbl = QLabel("Источник:")
        expand_lbl.setObjectName("caption")
        self.combo_backend = QComboBox()
        self.combo_backend.addItems(["Оба", "Navec", "RusVectores"])
        self.combo_backend.setFixedWidth(120)
        self.btn_expand = QPushButton("✦  Расширить словари")
        self.btn_expand.clicked.connect(self._run_expand)
        self.btn_expand.setToolTip(
            "Найти семантически близкие слова и добавить\nв тематические JSON-файлы."
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

        result_group = QGroupBox("  Результат расширения")
        result_group.setObjectName("result_box")
        result_layout = QVBoxLayout(result_group)
        self.dict_table = QTableWidget(0, 2)
        self.dict_table.setHorizontalHeaderLabels(["Домен", "Добавлено слов"])
        self.dict_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.dict_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.dict_table.setAlternatingRowColors(True)
        self.dict_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.dict_table.verticalHeader().setVisible(False)
        self.dict_table.setMinimumHeight(100)
        result_layout.addWidget(self.dict_table)
        self.lbl_dict_status = QLabel("Нажмите «Расширить словари» для запуска.")
        self.lbl_dict_status.setObjectName("subtitle")
        self.lbl_dict_status.setWordWrap(True)
        result_layout.addWidget(self.lbl_dict_status)
        right_layout.addWidget(result_group)

        right_layout.addStretch()
        splitter.addWidget(right)
        splitter.setSizes([400, 420])
        layout.addWidget(splitter)

        # ── Аннотации стратификации ───────────────────────────────────────
        ann_group = QGroupBox("  Аннотации стратификации — экспертные правки")
        ann_group.setObjectName("ann_box")
        ann_layout = QVBoxLayout(ann_group)
        ann_layout.setSpacing(6)

        ann_ctrl = QHBoxLayout()
        self._lbl_ann_stats = QLabel("Аннотаций: 0")
        self._lbl_ann_stats.setObjectName("subtitle")
        ann_ctrl.addWidget(self._lbl_ann_stats, 1)

        self._btn_train_clf = QPushButton("  Обучить ML-фильтр")
        self._btn_train_clf.setObjectName("primary")
        self._btn_train_clf.setFixedHeight(30)
        self._btn_train_clf.setToolTip(
            f"Обучить контекстный ML-классификатор на накопленных аннотациях.\n"
            f"Требуется минимум {strat_annotator.MIN_SAMPLES} примеров."
        )
        self._btn_train_clf.clicked.connect(self._train_annotator)
        ann_ctrl.addWidget(self._btn_train_clf)

        self._btn_del_ann = QPushButton("Удалить")
        self._btn_del_ann.setObjectName("danger")
        self._btn_del_ann.setFixedHeight(30)
        self._btn_del_ann.setEnabled(False)
        self._btn_del_ann.clicked.connect(self._delete_selected_annotation)
        ann_ctrl.addWidget(self._btn_del_ann)

        self._btn_clear_ann = QPushButton("Очистить всё")
        self._btn_clear_ann.setObjectName("danger")
        self._btn_clear_ann.setFixedHeight(30)
        self._btn_clear_ann.clicked.connect(self._clear_annotations)
        ann_ctrl.addWidget(self._btn_clear_ann)
        ann_layout.addLayout(ann_ctrl)

        self._lbl_clf_status = QLabel("")
        self._lbl_clf_status.setObjectName("subtitle")
        self._lbl_clf_status.setWordWrap(True)
        ann_layout.addWidget(self._lbl_clf_status)

        self._ann_table = QTableWidget(0, 6)
        self._ann_table.setHorizontalHeaderLabels(
            ["Лемма", "Форма", "Пласт", "Вердикт", "Контекст", "Дата"])
        hdr = self._ann_table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self._ann_table.setAlternatingRowColors(True)
        self._ann_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._ann_table.verticalHeader().setVisible(False)
        self._ann_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._ann_table.itemSelectionChanged.connect(self._on_ann_selection_changed)
        self._ann_table.setMinimumHeight(160)
        ann_layout.addWidget(self._ann_table)
        layout.addWidget(ann_group)

        # ── Пользовательский словарь ──────────────────────────────────────
        ud_group = QGroupBox("  Пользовательский словарь — фильтр ошибок LT")
        ud_group.setObjectName("ud_box")
        ud_layout = QVBoxLayout(ud_group)
        ud_layout.setSpacing(6)

        ud_note = QLabel(
            "Слова из этого словаря исключаются из ошибок LanguageTool и "
            "учитываются в стратификации / тематическом анализе. "
            "Добавляйте через ПКМ на ошибке во вкладке «Ошибки»."
        )
        ud_note.setWordWrap(True)
        ud_note.setObjectName("caption")
        ud_layout.addWidget(ud_note)

        ud_ctrl = QHBoxLayout()
        self._lbl_ud_count = QLabel("Слов в словаре: 0")
        self._lbl_ud_count.setObjectName("subtitle")
        ud_ctrl.addWidget(self._lbl_ud_count, 1)

        self._btn_del_word = QPushButton("Удалить")
        self._btn_del_word.setObjectName("danger")
        self._btn_del_word.setFixedHeight(30)
        self._btn_del_word.setEnabled(False)
        self._btn_del_word.clicked.connect(self._delete_selected_word)
        ud_ctrl.addWidget(self._btn_del_word)

        self._btn_clear_dict = QPushButton("Очистить всё")
        self._btn_clear_dict.setObjectName("danger")
        self._btn_clear_dict.setFixedHeight(30)
        self._btn_clear_dict.clicked.connect(self._clear_user_dict)
        ud_ctrl.addWidget(self._btn_clear_dict)
        ud_layout.addLayout(ud_ctrl)

        self._ud_table = QTableWidget(0, 4)
        self._ud_table.setHorizontalHeaderLabels(["Слово", "Пласт / тема", "Заметка", "Добавлено"])
        ud_hdr = self._ud_table.horizontalHeader()
        ud_hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        ud_hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        ud_hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        ud_hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self._ud_table.setAlternatingRowColors(True)
        self._ud_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._ud_table.verticalHeader().setVisible(False)
        self._ud_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._ud_table.itemSelectionChanged.connect(self._on_ud_selection_changed)
        self._ud_table.setMinimumHeight(140)
        ud_layout.addWidget(self._ud_table)
        layout.addWidget(ud_group)

        layout.addStretch()

    def _toggle_memo(self, checked: bool):
        self._memo_widget.setVisible(checked)
        self._btn_memo_toggle.setText(
            "▲  Скрыть памятку" if checked else "▼  Показать памятку"
        )

    # ── Обновление ────────────────────────────────────────────────────────

    def _update_vec_status_labels(self):
        if self._rusvec.navec_ready:
            self.lbl_navec_status.setText("Navec: загружен ✓")
            self.lbl_navec_status.setStyleSheet("color: #6abf69;")
        elif self._rusvec.navec_downloaded:
            self.lbl_navec_status.setText("Navec: скачан, не загружен в память")
            self.lbl_navec_status.setStyleSheet("color: #d4883a;")
        else:
            self.lbl_navec_status.setText("Navec: не скачан")
            self.lbl_navec_status.setStyleSheet("color: #e06c6c;")

        if self._rusvec.rusvec_ready:
            self.lbl_rusvec_status.setText("RusVectores (НКРЯ): загружен ✓")
            self.lbl_rusvec_status.setStyleSheet("color: #6abf69;")
        elif self._rusvec.rusvec_downloaded:
            self.lbl_rusvec_status.setText("RusVectores (НКРЯ): скачан, не загружен в память")
            self.lbl_rusvec_status.setStyleSheet("color: #d4883a;")
        else:
            self.lbl_rusvec_status.setText("RusVectores (НКРЯ): не скачан")
            self.lbl_rusvec_status.setStyleSheet("color: #e06c6c;")

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
        self.lbl_texts.setText(str(s['total_texts']))
        self.lbl_words.setText(f"{s['total_words']:,}".replace(",", "\u202f"))
        last = s['last_added']
        # Показываем только дату (без времени) если есть пробел
        self.lbl_last.setText(last.split(" ")[0] if " " in last else last)

        if s["ready_for_training"]:
            self.lbl_status.setText("Корпус готов к обучению ✓")
            self.lbl_status.setStyleSheet("color: #6abf69;")
            self.progress_bar.setValue(corpus_manager.MIN_WORDS_FOR_TRAINING)
            self.progress_bar.setObjectName("ready")
            self.progress_bar.setStyleSheet(
                "QProgressBar::chunk { background-color: #6abf69; border-radius: 4px; }")
        else:
            need = s["words_needed"]
            self.lbl_status.setText(
                f"Накопление — ещё ~{need:,} слов".replace(",", "\u202f"))
            self.lbl_status.setStyleSheet("color: #d4883a;")
            self.progress_bar.setValue(s["total_words"])
            self.progress_bar.setStyleSheet("")

        if self._lb.ft_ready:
            self.lbl_ft_status.setText("FastText: обучена ✓")
            self.lbl_ft_status.setStyleSheet("color: #6abf69;")
            self.lbl_vocab.setText(f"Словарь: {self._lb.vocab_size:,} слов".replace(",", "\u202f"))
        else:
            self.lbl_ft_status.setText("FastText: не обучена")
            self.lbl_ft_status.setStyleSheet("color: #e06c6c;")
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
        self._refresh_annotations()
        self._refresh_user_dict()

    def update_dict_table(self, expanded: dict):
        self.dict_table.setRowCount(0)
        if not expanded:
            self.lbl_dict_status.setText("Новых слов не найдено.")
            return
        self.dict_table.setRowCount(len(expanded))
        for row, (domain, count) in enumerate(sorted(expanded.items())):
            self.dict_table.setItem(row, 0, QTableWidgetItem(domain))
            cnt = QTableWidgetItem(f"+{count}")
            cnt.setForeground(QColor("#6abf69"))
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

    # ── Аннотации стратификации ───────────────────────────────────────────

    def _refresh_annotations(self) -> None:
        """Обновить таблицу аннотаций и статистику."""
        anns = corpus_manager.get_all_strat_annotations()
        stats = corpus_manager.get_strat_annotation_stats()

        # Статистика
        clf_ready = strat_annotator.get().is_ready
        clf_txt = "  ·  фильтр обучен ✓" if clf_ready else ""
        self._lbl_ann_stats.setText(
            f"Аннотаций: {stats['total']}  "
            f"(исключений: {stats['exclude_count']}, "
            f"подтверждений: {stats['confirm_count']}){clf_txt}"
        )

        # Активность кнопки обучения
        can_train = stats["total"] >= strat_annotator.MIN_SAMPLES
        self._btn_train_clf.setEnabled(
            can_train and self._annotator_thread is None)
        if not can_train:
            self._btn_train_clf.setToolTip(
                f"Нужно минимум {strat_annotator.MIN_SAMPLES} аннотаций "
                f"(сейчас: {stats['total']})"
            )

        # Заполнить таблицу
        self._ann_table.setRowCount(0)
        self._ann_table.setRowCount(len(anns))
        self._ann_ids = [a["id"] for a in anns]  # для удаления

        _VERDICT_COLORS = {"exclude": "#e06c6c", "confirm": "#6abf69"}

        for row, ann in enumerate(anns):
            ctx = ann.get("context", "")
            if len(ctx) > 60:
                ctx = ctx[:58] + "…"
            vals = [
                ann["lemma"],
                ann.get("surface", ""),
                ann["layer"],
                "✗ исключить" if ann["verdict"] == "exclude" else "✓ подтвердить",
                ctx,
                ann["created_at"],
            ]
            verdict_color = _VERDICT_COLORS.get(ann["verdict"], "#a09080")
            for col, val in enumerate(vals):
                item = QTableWidgetItem(val)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if col == 3:
                    item.setForeground(QColor(verdict_color))
                self._ann_table.setItem(row, col, item)

    def _on_ann_selection_changed(self) -> None:
        self._btn_del_ann.setEnabled(
            bool(self._ann_table.selectedItems()))

    def _delete_selected_annotation(self) -> None:
        rows = sorted({idx.row() for idx in self._ann_table.selectedIndexes()},
                      reverse=True)
        for row in rows:
            if row < len(self._ann_ids):
                corpus_manager.delete_strat_annotation_by_id(self._ann_ids[row])
        self._refresh_annotations()

    def _clear_annotations(self) -> None:
        reply = QMessageBox.question(
            self, "Очистить аннотации",
            "Удалить все экспертные аннотации стратификации?\n"
            "ML-модель фильтра будет также сброшена.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            corpus_manager.clear_strat_annotations()
            # Сбросить singleton модели
            import os
            from analyzer.strat_annotator import _MODEL_PATH
            if os.path.exists(_MODEL_PATH):
                try:
                    os.remove(_MODEL_PATH)
                except Exception:
                    pass
            strat_annotator._instance = None
            self._lbl_clf_status.setText("Аннотации и модель очищены.")
            self._refresh_annotations()

    def _train_annotator(self) -> None:
        if self._annotator_thread is not None:
            return
        self._btn_train_clf.setEnabled(False)
        self._lbl_clf_status.setText("Обучение ML-фильтра…")
        self._annotator_thread = TrainAnnotatorThread(parent=self)
        self._annotator_thread.finished.connect(self._on_annotator_trained)
        self._annotator_thread.start()

    def _on_annotator_trained(self, success: bool, message: str) -> None:
        self._annotator_thread = None
        color = "#6abf69" if success else "#e06c6c"
        self._lbl_clf_status.setStyleSheet(f"color: {color};")
        self._lbl_clf_status.setText(message)
        self._refresh_annotations()

    # ── Пользовательский словарь ─────────────────────────────────────────

    def _refresh_user_dict(self) -> None:
        entries = corpus_manager.get_user_dict_all()
        self._ud_ids = [e["id"] for e in entries]
        self._lbl_ud_count.setText(f"Слов в словаре: {len(entries)}")
        self._ud_table.setRowCount(0)
        self._ud_table.setRowCount(len(entries))
        _STRAT_COLOR  = "#b888e8"   # стилистический пласт
        _DOMAIN_COLOR = "#5aa0e8"   # тематический домен
        _ALL_LABELS   = {**corpus_manager.STRAT_LAYER_LABELS,
                         **corpus_manager.THEMATIC_DOMAIN_LABELS}
        for row, entry in enumerate(entries):
            cat_key   = entry["category"]
            cat_label = _ALL_LABELS.get(cat_key, cat_key)
            vals = [entry["word"], cat_label,
                    entry.get("note", ""), entry["created_at"]]
            cat_color = _DOMAIN_COLOR if cat_key.startswith("domain:") else _STRAT_COLOR
            for col, val in enumerate(vals):
                item = QTableWidgetItem(val)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if col == 1:
                    item.setForeground(QColor(cat_color))
                self._ud_table.setItem(row, col, item)

    def _on_ud_selection_changed(self) -> None:
        self._btn_del_word.setEnabled(bool(self._ud_table.selectedItems()))

    def _delete_selected_word(self) -> None:
        rows = sorted({idx.row() for idx in self._ud_table.selectedIndexes()},
                      reverse=True)
        for row in rows:
            if row < len(self._ud_ids):
                corpus_manager.remove_from_user_dict(self._ud_ids[row])
        self._refresh_user_dict()

    def _clear_user_dict(self) -> None:
        reply = QMessageBox.question(
            self, "Очистить словарь",
            "Удалить все слова из пользовательского словаря?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            corpus_manager.clear_user_dict()
            self._refresh_user_dict()
