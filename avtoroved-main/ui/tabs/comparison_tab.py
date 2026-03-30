"""
Вкладка 6: Сравнение текстов.
"""
from __future__ import annotations
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QGroupBox, QTextEdit, QPushButton, QLabel,
    QFileDialog, QMessageBox, QTableWidget,
    QTableWidgetItem, QHeaderView
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor


class ComparisonTab(QWidget):
    """Идентификационная задача: сравнение двух текстов."""

    compare_requested = pyqtSignal(str, str)
    export_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._last_comparison = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Левая панель: ввод текстов
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)

        g1 = QGroupBox("Текст 1")
        g1_layout = QVBoxLayout(g1)
        btn1 = QPushButton("📂 Загрузить")
        btn1.setObjectName("secondary")
        btn1.clicked.connect(lambda: self._load_file(1))
        g1_layout.addWidget(btn1)
        self.text1 = QTextEdit()
        self.text1.setPlaceholderText("Введите или загрузите первый текст...")
        g1_layout.addWidget(self.text1)
        left_layout.addWidget(g1)

        g2 = QGroupBox("Текст 2")
        g2_layout = QVBoxLayout(g2)
        btn2 = QPushButton("📂 Загрузить")
        btn2.setObjectName("secondary")
        btn2.clicked.connect(lambda: self._load_file(2))
        g2_layout.addWidget(btn2)
        self.text2 = QTextEdit()
        self.text2.setPlaceholderText("Введите или загрузите второй текст...")
        g2_layout.addWidget(self.text2)
        left_layout.addWidget(g2)

        self.btn_compare = QPushButton("▶ Сравнить тексты")
        self.btn_compare.clicked.connect(self._request_compare)
        left_layout.addWidget(self.btn_compare)
        splitter.addWidget(left)

        # Правая панель: результаты
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)

        res_group = QGroupBox("Результат сравнения")
        res_layout = QVBoxLayout(res_group)

        self.metrics_table = QTableWidget()
        self.metrics_table.setColumnCount(2)
        self.metrics_table.setHorizontalHeaderLabels(["Компонент", "Значение"])
        self.metrics_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.metrics_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.metrics_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.metrics_table.verticalHeader().setVisible(False)
        self.metrics_table.setMaximumHeight(200)
        res_layout.addWidget(self.metrics_table)

        self.result_text = QTextEdit()
        self.result_text.setReadOnly(True)
        res_layout.addWidget(self.result_text)

        btn_export = QPushButton("📄 Экспорт в DOCX")
        btn_export.setObjectName("secondary")
        btn_export.clicked.connect(self.export_requested)
        res_layout.addWidget(btn_export)
        right_layout.addWidget(res_group)
        splitter.addWidget(right)

        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter)

    def _load_file(self, num: int):
        fp, _ = QFileDialog.getOpenFileName(
            self, "Открыть текст", "", "Тексты (*.txt *.docx);;Все файлы (*)")
        if not fp:
            return
        try:
            from analyzer.export import load_text_from_file
            text = load_text_from_file(fp)
            if num == 1:
                self.text1.setPlainText(text)
            else:
                self.text2.setPlainText(text)
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", str(e))

    def _request_compare(self):
        t1 = self.text1.toPlainText().strip()
        t2 = self.text2.toPlainText().strip()
        if not t1 or not t2:
            QMessageBox.warning(self, "Нет текстов", "Введите оба текста для сравнения.")
            return
        self.compare_requested.emit(t1, t2)

    def show_result(self, comp: dict):
        """Отобразить результат сравнения."""
        self._last_comparison = comp

        rows = [
            ("Общее сходство", f"{comp['overall']:.1%}"),
            ("Лексическое (Jaccard)", f"{comp['jaccard']:.1%}"),
            ("Морфологическое (POS)", f"{comp['pos_similarity']:.1%}"),
            ("Синтаксическое", f"{comp['syntactic_similarity']:.1%}"),
            ("TTR-сходство", f"{comp['ttr_similarity']:.1%}"),
            ("POS-биграммное", f"{comp.get('bigram_similarity', 0):.1%}"),
        ]
        if "fasttext_sim" in comp:
            rows.append(("FastText (семантическое) ⚡", f"{comp['fasttext_sim']:.1%}"))
        self.metrics_table.setRowCount(len(rows))
        for i, (k, v) in enumerate(rows):
            ki = QTableWidgetItem(k)
            ki.setFlags(ki.flags() & ~Qt.ItemFlag.ItemIsEditable)
            vi = QTableWidgetItem(v)
            vi.setFlags(vi.flags() & ~Qt.ItemFlag.ItemIsEditable)
            if i == 0:
                sim = comp["overall"]
                color = "#a6e3a1" if sim >= 0.7 else "#fab387" if sim >= 0.5 else "#f38ba8"
                vi.setForeground(QColor(color))
                font = vi.font()
                font.setBold(True)
                vi.setFont(font)
            self.metrics_table.setItem(i, 0, ki)
            self.metrics_table.setItem(i, 1, vi)

        sim = comp["overall"]
        if sim >= 0.7:
            conclusion = "Высокое сходство — возможно один автор."
        elif sim >= 0.5:
            conclusion = "Среднее сходство — необходим дополнительный материал."
        elif sim >= 0.3:
            conclusion = "Умеренные различия — разные авторы или ситуации."
        else:
            conclusion = "Существенные различия — вероятно, разные авторы."

        lemmas = comp.get("common_lemmas", [])
        chunks = []
        for i in range(0, len(lemmas), 6):
            chunks.append("  " + ", ".join(lemmas[i:i + 6]))

        ft_line = ""
        if "fasttext_sim" in comp:
            ft_line = f"FastText семантическое сходство: {comp['fasttext_sim']:.1%}\n"

        report = [
            f"Текст 1: {comp['words1']} слов, TTR={comp['ttr1']}, ср.предл.={comp['avg_sent1']}",
            f"Текст 2: {comp['words2']} слов, TTR={comp['ttr2']}, ср.предл.={comp['avg_sent2']}",
            "",
            f"Совпадающие леммы ({len(lemmas)}):",
        ] + chunks + ["", ft_line + f"ВЫВОД: {conclusion}"]

        self.result_text.setPlainText("\n".join(report))

    def get_last_comparison(self):
        return self._last_comparison

    def get_texts(self):
        return self.text1.toPlainText(), self.text2.toPlainText()

    def clear(self):
        self.metrics_table.setRowCount(0)
        self.result_text.clear()
        self._last_comparison = None
