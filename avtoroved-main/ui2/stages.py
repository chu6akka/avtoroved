"""
Стадии нового интерфейса. Каждая — QWidget с методами on_enter/is_complete.
Стадия 1 (Материал) реализована; 2–4 будут наполнены поэтапно.
"""
from __future__ import annotations
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QFrame, QFileDialog, QMessageBox, QSizePolicy,
    QTableWidget, QTableWidgetItem, QHeaderView, QScrollArea
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor


# ── Утилиты ──────────────────────────────────────────────────────────────────

def _card(parent_layout) -> QVBoxLayout:
    frame = QFrame()
    frame.setProperty("class", "card")
    frame.setStyleSheet("QFrame { background:white; border:1px solid #e3e6ea; border-radius:10px; }")
    lay = QVBoxLayout(frame)
    lay.setContentsMargins(16, 14, 16, 14)
    parent_layout.addWidget(frame)
    return lay


def _suitability(words: int) -> tuple[str, str]:
    """Вердикт пригодности по объёму (ЭКЦ МВД, с. 31)."""
    if words < 100:
        return ("⛔ Недостаточно для экспертизы (минимум 100 слов)", "#c0392b")
    if words < 500:
        return (f"⚠ {words} слов — пригоден только для диагностики "
                f"(идентификация требует ≥500)", "#b9770e")
    return (f"✓ {words} слов — пригоден для идентификационного исследования", "#1e8449")


class Stage(QWidget):
    """База стадии."""
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.state = win.state
        self.root = QVBoxLayout(self)
        self.root.setContentsMargins(0, 0, 0, 0)
        self.root.setSpacing(14)
        self._build()

    def _header(self, title: str, hint: str):
        t = QLabel(title); t.setObjectName("stageTitle")
        self.root.addWidget(t)
        h = QLabel(hint); h.setObjectName("stageHint"); h.setWordWrap(True)
        self.root.addWidget(h)

    # переопределяемые
    def _build(self): ...
    def on_enter(self): ...
    def is_complete(self) -> bool: return False
    def on_mode_changed(self): ...


# ── Стадия 1: Материал ───────────────────────────────────────────────────────

class _TextPanel(QFrame):
    """Колонка одного текста: загрузка, ввод, вердикт пригодности."""
    def __init__(self, slot, on_change):
        super().__init__()
        self.slot = slot
        self.on_change = on_change
        self.setStyleSheet("QFrame { background:white; border:1px solid #e3e6ea; border-radius:10px; }")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(8)

        top = QHBoxLayout()
        self.title = QLabel(slot.name)
        self.title.setStyleSheet("font-weight:600; font-size:14px; border:none;")
        top.addWidget(self.title)
        top.addStretch()
        btn = QPushButton("📂 Загрузить")
        btn.setObjectName("ghost")
        btn.clicked.connect(self._load)
        top.addWidget(btn)
        lay.addLayout(top)

        self.edit = QTextEdit()
        self.edit.setPlaceholderText("Вставьте или загрузите текст…")
        self.edit.setPlainText(slot.text)
        self.edit.textChanged.connect(self._changed)
        lay.addWidget(self.edit)

        self.badge = QLabel("")
        self.badge.setWordWrap(True)
        self.badge.setStyleSheet("font-size:12px; border:none;")
        lay.addWidget(self.badge)
        self._refresh_badge()

    def _changed(self):
        self.slot.text = self.edit.toPlainText()
        self.slot.analyzed = False
        self._refresh_badge()
        self.on_change()

    def _load(self):
        fp, _ = QFileDialog.getOpenFileName(
            self, "Открыть текст", "", "Тексты (*.txt *.docx);;Все файлы (*)")
        if not fp:
            return
        try:
            from analyzer.export import load_text_from_file
            self.edit.setPlainText(load_text_from_file(fp))
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", str(e))

    def _refresh_badge(self):
        n = self.slot.word_count()
        if n == 0:
            self.badge.setText("")
            return
        msg, color = _suitability(n)
        self.badge.setText(msg)
        self.badge.setStyleSheet(f"font-size:12px; color:{color}; border:none;")


class MaterialStage(Stage):
    def _build(self):
        self._header("Материал исследования",
                     "Стадия 1 из 4. Введите текст(ы) и проверьте пригодность по объёму "
                     "(методика ЭКЦ МВД: ≥100 слов — диагностика, ≥500 — идентификация).")

        self.cols = QHBoxLayout()
        self.cols.setSpacing(14)
        self.panel1 = _TextPanel(self.state.slot1, self._on_change)
        self.panel2 = _TextPanel(self.state.slot2, self._on_change)
        self.cols.addWidget(self.panel1)
        self.cols.addWidget(self.panel2)
        self.root.addLayout(self.cols, stretch=1)

        footer = QHBoxLayout()
        footer.addStretch()
        self.next_btn = QPushButton("Далее → Раздельный анализ")
        self.next_btn.setObjectName("primary")
        self.next_btn.clicked.connect(lambda: self.win.go_to(1))
        footer.addWidget(self.next_btn)
        self.root.addLayout(footer)
        self.on_mode_changed()

    def _on_change(self):
        self.next_btn.setEnabled(self.is_complete())
        self.win.refresh_steps_enabled()

    def on_mode_changed(self):
        self.panel2.setVisible(self.state.mode == "identification")
        self._on_change()

    def on_enter(self):
        self.win.set_status("Стадия 1 — материал и пригодность")
        self._on_change()

    def is_complete(self) -> bool:
        return all(s.word_count() >= 1 for s in self.state.active_slots())


def _author_card(slot, mode: str) -> QFrame:
    """Сводная карточка автора по результатам раздельного анализа."""
    from analyzer import comparison_engine as ce

    frame = QFrame()
    frame.setStyleSheet("QFrame { background:white; border:1px solid #e3e6ea; border-radius:10px; }")
    lay = QVBoxLayout(frame)
    lay.setContentsMargins(16, 14, 16, 14)
    lay.setSpacing(6)

    def line(html):
        l = QLabel(html); l.setWordWrap(True)
        l.setStyleSheet("border:none; font-size:12px;")
        l.setTextFormat(Qt.TextFormat.RichText)
        lay.addWidget(l)
        return l

    title = QLabel(slot.name)
    title.setStyleSheet("border:none; font-weight:700; font-size:15px;")
    lay.addWidget(title)

    er = slot.error_result
    add = slot.metrics.get("дополнительно", {})

    line(f"<b>Объём:</b> {slot.word_count()} слов")

    if er and er.general_skill_level:
        col = {"высокая": "#1e8449", "средняя": "#b9770e", "низкая": "#c0392b"}.get(
            er.general_skill_level, "#333")
        line(f"<b>Владение литературным языком:</b> "
             f"<span style='color:{col}'>{er.general_skill_level}</span>")
        if er.skill_levels:
            sk = " · ".join(f"{s.skill_name.replace(' навык','')}: {s.level}"
                            for s in er.skill_levels)
            line(f"<span style='color:#6b7280'>{sk}</span>")

    style = ce._leading_style(slot.metrics, slot.strat_result)
    line(f"<b>Ведущий стиль:</b> {style}")

    ttr = add.get("Лексическое разнообразие (TTR)")
    sent = add.get("Средняя длина предложения (слов)")
    if ttr is not None:
        line(f"<b>TTR:</b> {ttr}  ·  <b>ср. предложение:</b> {sent} сл.")

    tr = slot.thematic_result
    if tr and getattr(tr, "top_domains", None):
        doms = ", ".join(f"{d.label.split(' / ')[0]} ({d.cosine:.0%})"
                         for d in tr.top_domains)
        line(f"<b>Тематика:</b> {doms}")

    sr = slot.strat_result
    if sr and getattr(sr, "layer_counts", None):
        nonlit = {k: v for k, v in sr.layer_counts.items()
                  if k != "literary_standard" and v > 0}
        if nonlit:
            from analyzer.comparison_engine import _LAYER_LABEL
            txt = ", ".join(f"{_LAYER_LABEL.get(k, k)}: {v}"
                            for k, v in sorted(nonlit.items(), key=lambda x: -x[1]))
            line(f"<b>Нелитературные пласты:</b> {txt}")

    if mode == "diagnostic" and slot.diagnostic_result:
        d = slot.diagnostic_result
        lay.addWidget(_hsep())
        prof = QLabel("Диагностический профиль")
        prof.setStyleSheet("border:none; font-weight:700; font-size:13px;")
        lay.addWidget(prof)
        for label, f in [("Пол", d.gender), ("Возраст", d.age),
                         ("Образование", d.education), ("Культура речи", d.speech_culture)]:
            if f:
                line(f"<b>{label}:</b> {f.label} "
                     f"<span style='color:#9aa3af'>({f.confidence})</span>")

    lay.addStretch()

    # Кнопка детальной статистики (разбор по словам, частоты, индексы, SAE)
    det = QPushButton("Подробно: разбор по словам · частоты · 20 индексов · SAE")
    det.setObjectName("ghost")

    def _open():
        from ui2.details_dialog import DetailsDialog
        DetailsDialog(slot, parent=det.window()).exec()
    det.clicked.connect(_open)
    lay.addWidget(det)
    return frame


def _hsep() -> QFrame:
    s = QFrame(); s.setFrameShape(QFrame.Shape.HLine)
    s.setStyleSheet("color:#e3e6ea; border:none;")
    return s


class AnalysisStage(Stage):
    TITLE = "Раздельный анализ"

    def _build(self):
        self._header("Раздельное исследование",
                     "Стадия 2 из 4. Анализ каждого текста по отдельности — "
                     "навыки, стиль, лексика, тематика. Запустите анализ.")
        bar = QHBoxLayout()
        self.run_btn = QPushButton("▶ Анализировать")
        self.run_btn.setObjectName("primary")
        self.run_btn.clicked.connect(self._run)
        bar.addWidget(self.run_btn)
        self.status = QLabel("")
        self.status.setStyleSheet("color:#6b7280; font-size:12px;")
        bar.addWidget(self.status)
        bar.addStretch()
        self.root.addLayout(bar)

        self.cards = QHBoxLayout()
        self.cards.setSpacing(14)
        self.root.addLayout(self.cards, stretch=1)

        footer = QHBoxLayout()
        footer.addStretch()
        self.next_btn = QPushButton("Далее →")
        self.next_btn.setObjectName("primary")
        self.next_btn.setEnabled(False)
        self.next_btn.clicked.connect(lambda: self.win.go_to(2))
        footer.addWidget(self.next_btn)
        self.root.addLayout(footer)
        self._thread = None

    def on_enter(self):
        third = "Сравнение" if self.state.mode == "identification" else "Профиль автора"
        self.next_btn.setText(f"Далее → {third}")
        self.win.set_status(self.TITLE)
        if all(s.analyzed for s in self.state.active_slots()):
            self._render_cards()
            self.next_btn.setEnabled(True)

    def _run(self):
        from ui2.analysis import AnalyzeThread
        slots = self.state.active_slots()
        if any(not s.text.strip() for s in slots):
            QMessageBox.warning(self, "Нет текста", "Сначала введите материал (Стадия 1).")
            return
        self.run_btn.setEnabled(False)
        self.next_btn.setEnabled(False)
        self._thread = AnalyzeThread(
            slots, self.win.engines, self.state.mode == "diagnostic")
        self._thread.status.connect(lambda m: self.status.setText(m))
        self._thread.finished.connect(self._done)
        self._thread.start()

    def _done(self, ok: bool, err: str):
        self.run_btn.setEnabled(True)
        if not ok:
            self.status.setText("")
            QMessageBox.critical(self, "Ошибка анализа", err)
            return
        self.status.setText("Анализ завершён.")
        self._render_cards()
        self.next_btn.setEnabled(True)
        self.win.refresh_steps_enabled()

    def _render_cards(self):
        while self.cards.count():
            it = self.cards.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        for s in self.state.active_slots():
            if s.analyzed:
                self.cards.addWidget(_author_card(s, self.state.mode))

    def is_complete(self) -> bool:
        return all(s.analyzed for s in self.state.active_slots())


_MATCH_BG = QColor("#eaf6ec")
_DIFF_BG = QColor("#fdecea")


class CompareStage(Stage):
    """Стадия 3: идентификация (НН/НС/НСВ) или диагностический профиль."""
    TITLE = "Сравнительное исследование"
    def _build(self):
        self._header("Сравнительное исследование",
                     "Стадия 3 из 4.")
        self.body = QVBoxLayout()
        self.root.addLayout(self.body, stretch=1)

        footer = QHBoxLayout()
        footer.addStretch()
        self.next_btn = QPushButton("Далее → Заключение")
        self.next_btn.setObjectName("primary")
        self.next_btn.clicked.connect(lambda: self.win.go_to(3))
        footer.addWidget(self.next_btn)
        self.root.addLayout(footer)

        self._features = []
        self._populating = False
        self._built_for = None   # режим, под который построено тело

    def _clear_body(self):
        while self.body.count():
            it = self.body.takeAt(0)
            if it.widget():
                it.widget().deleteLater()

    def on_enter(self):
        self.win.set_status(self.TITLE)
        if self.state.mode == "identification":
            self._enter_identification()
        else:
            self._enter_diagnostic()

    # ── Идентификация ──────────────────────────────────────────────────────
    def _enter_identification(self):
        from analyzer.metrics import compare_texts
        from analyzer import comparison_engine as ce
        s1, s2 = self.state.slot1, self.state.slot2
        if not (s1.analyzed and s2.analyzed):
            self._clear_body()
            self.body.addWidget(self._note("Сначала выполните раздельный анализ (Стадия 2)."))
            return

        aux = compare_texts(s1.tokens, s2.tokens, s1.text, s2.text)
        b1 = ce.build_bundle(s1.name, s1.text, s1.tokens, s1.metrics, s1.error_result, s1.strat_result)
        b2 = ce.build_bundle(s2.name, s2.text, s2.tokens, s2.metrics, s2.error_result, s2.strat_result)
        res = ce.compare(b1, b2, aux)
        self.state.comparison = res
        self.state.comparison_aux = aux

        self._clear_body()
        self.summary = QLabel(""); self.summary.setWordWrap(True)
        self.summary.setStyleSheet("font-size:12px;")
        self.body.addWidget(self.summary)

        order = {"НН": 0, "НС": 1, "НСВ": 2}
        self._features = (sorted(res.matches, key=lambda f: order.get(f.level, 9))
                          + sorted(res.diffs, key=lambda f: order.get(f.level, 9)))
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(
            ["Комплекс", "Ур.", "Признак", "Текст 1", "Текст 2", "Высокоинф."])
        hh = self.table.horizontalHeader()
        for c in (0, 1, 3, 4, 5):
            hh.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.itemChanged.connect(self._on_check)
        self.body.addWidget(self.table, stretch=1)

        hint_lbl = QLabel("Отметьте «высокоинф.» для высокоинформативных признаков "
                          "(методика, с. 35/85) — подсказка пересчитается.")
        hint_lbl.setStyleSheet("color:#9aa3af; font-size:10px;")
        hint_lbl.setWordWrap(True)
        self.body.addWidget(hint_lbl)

        self._populate(res)
        self._refresh_summary()

    def _populate(self, res):
        self._populating = True
        self.table.setRowCount(len(self._features))
        for r, f in enumerate(self._features):
            is_m = (f.kind == "match")
            cells = [QTableWidgetItem("совпад." if is_m else "различ."),
                     QTableWidgetItem(f.level),
                     QTableWidgetItem(f.name + (" ⟲" if f.stable else "")),
                     QTableWidgetItem(str(f.value1)),
                     QTableWidgetItem(str(f.value2))]
            if f.note:
                cells[2].setToolTip(f.note)
            chk = QTableWidgetItem()
            chk.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            chk.setCheckState(Qt.CheckState.Checked if f.high_informative
                              else Qt.CheckState.Unchecked)
            for c in cells:
                c.setFlags(c.flags() & ~Qt.ItemFlag.ItemIsEditable)
                c.setBackground(_MATCH_BG if is_m else _DIFF_BG)
            chk.setBackground(_MATCH_BG if is_m else _DIFF_BG)
            for i, c in enumerate(cells):
                self.table.setItem(r, i, c)
            self.table.setItem(r, 5, chk)
        self._populating = False

    def _on_check(self, item):
        from analyzer import comparison_engine as ce
        if self._populating or item.column() != 5:
            return
        r = item.row()
        if 0 <= r < len(self._features):
            self._features[r].high_informative = (item.checkState() == Qt.CheckState.Checked)
            res = self.state.comparison
            res.high_informative_matches = sum(1 for f in res.matches if f.high_informative)
            res.high_informative_diffs = sum(1 for f in res.diffs if f.high_informative)
            ce.recompute_hint(res)
            self._refresh_summary()

    def _refresh_summary(self):
        res = self.state.comparison
        ls = res.level_summary
        lvl = "  ".join(f"{lv}: +{ls.get(lv,{}).get('match',0)}/−{ls.get(lv,{}).get('diff',0)}"
                        for lv in ("НН", "НС", "НСВ"))
        ok = res.high_informative_matches >= res.threshold
        col = "#1e8449" if ok else "#b9770e"
        self.summary.setText(
            f"<b>Признаков:</b> {res.total_features} "
            f"(совпадений {len(res.matches)}, различий {len(res.diffs)})  ·  {lvl}<br>"
            f"<b>Высокоинф. совпадений:</b> {res.high_informative_matches}/{res.threshold} "
            f"<span style='color:{col}'>({'порог достигнут' if ok else 'ниже порога'})</span><br>"
            f"<b>Подсказка (не вывод):</b> {res.hint}<br>"
            f"<span style='color:#9aa3af; font-size:10px'>"
            f"Окончательный вывод формулирует эксперт.</span>")

    # ── Диагностика ────────────────────────────────────────────────────────
    def _enter_diagnostic(self):
        self._clear_body()
        s = self.state.slot1
        d = s.diagnostic_result if s.analyzed else None
        if d is None:
            self.body.addWidget(self._note("Сначала выполните раздельный анализ (Стадия 2)."))
            return
        if not getattr(d, "sufficient_volume", True):
            self.body.addWidget(self._note(
                f"Объём текста ({d.word_count} слов) недостаточен для диагностики (мин. 100)."))
            return
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setStyleSheet("border:none;")
        host = QWidget(); hl = QVBoxLayout(host); hl.setSpacing(10)
        for label, f in [("Пол автора", d.gender), ("Возрастная группа", d.age),
                         ("Образование", d.education), ("Культура речи", d.speech_culture),
                         ("Маскировка речи", d.masquerade)]:
            if not f:
                continue
            card = QFrame()
            card.setStyleSheet("QFrame{background:white;border:1px solid #e3e6ea;border-radius:10px;}")
            cl = QVBoxLayout(card); cl.setContentsMargins(14, 10, 14, 10)
            t = QLabel(f"{label}: <b>{f.label}</b> "
                       f"<span style='color:#9aa3af'>({f.confidence})</span>")
            t.setTextFormat(Qt.TextFormat.RichText)
            t.setStyleSheet("border:none; font-size:13px;")
            cl.addWidget(t)
            for e in f.evidence_for[:5]:
                el = QLabel("✓ " + e); el.setWordWrap(True)
                el.setStyleSheet("border:none; color:#5b6675; font-size:11px;")
                cl.addWidget(el)
            hl.addWidget(card)
        hl.addStretch()
        scroll.setWidget(host)
        self.body.addWidget(scroll, stretch=1)

    def _note(self, text):
        n = QLabel(text); n.setAlignment(Qt.AlignmentFlag.AlignCenter)
        n.setStyleSheet("color:#9aa3af; font-size:13px; padding:30px;")
        return n

    def is_complete(self) -> bool:
        if self.state.mode == "identification":
            return self.state.comparison is not None
        return bool(self.state.slot1.diagnostic_result)


class ConclusionStage(Stage):
    """Стадия 4: единое заключение + экспорт DOCX."""
    TITLE = "Заключение"
    def _build(self):
        self._header("Заключение", "Стадия 4 из 4. Сводка, вывод эксперта и экспорт.")
        self.summary_view = QTextEdit(); self.summary_view.setReadOnly(True)
        self.summary_view.setStyleSheet(
            "background:white; border:1px solid #e3e6ea; border-radius:8px; padding:10px;")
        self.root.addWidget(self.summary_view, stretch=1)

        vlbl = QLabel("Вывод эксперта (формулируется экспертом):")
        vlbl.setStyleSheet("font-weight:600;")
        self.root.addWidget(vlbl)
        self.verdict = QTextEdit()
        self.verdict.setPlaceholderText("Окончательный вывод по совокупности признаков…")
        self.verdict.setMaximumHeight(100)
        self.root.addWidget(self.verdict)

        bar = QHBoxLayout(); bar.addStretch()
        self.export_btn = QPushButton("📄 Экспорт в DOCX")
        self.export_btn.setObjectName("primary")
        self.export_btn.clicked.connect(self._export)
        bar.addWidget(self.export_btn)
        self.root.addLayout(bar)

    def on_enter(self):
        self.win.set_status(self.TITLE)
        self.summary_view.setHtml(self._build_summary())

    def _build_summary(self) -> str:
        st = self.state
        if st.mode == "identification" and st.comparison is not None:
            res = st.comparison
            ls = res.level_summary
            rows = "".join(
                f"<tr><td>{lv}</td><td>+{ls.get(lv,{}).get('match',0)}</td>"
                f"<td>−{ls.get(lv,{}).get('diff',0)}</td></tr>"
                for lv in ("НН", "НС", "НСВ"))
            return (
                f"<h3>Сравнительное исследование</h3>"
                f"<p>Текст 1: {st.slot1.word_count()} слов · Текст 2: {st.slot2.word_count()} слов</p>"
                f"<table border=1 cellpadding=4 style='border-collapse:collapse'>"
                f"<tr><th>Уровень</th><th>Совпадения</th><th>Различия</th></tr>{rows}</table>"
                f"<p><b>Высокоинформативных совпадений:</b> "
                f"{res.high_informative_matches} из не менее {res.threshold} (с. 85)</p>"
                f"<p><b>Подсказка (не вывод):</b> {res.hint}</p>"
                f"<p style='color:#888'>Окончательный вывод формулирует эксперт.</p>")
        elif st.mode == "diagnostic" and st.slot1.diagnostic_result:
            d = st.slot1.diagnostic_result
            items = "".join(
                f"<li>{lbl}: <b>{f.label}</b> ({f.confidence})</li>"
                for lbl, f in [("Пол", d.gender), ("Возраст", d.age),
                               ("Образование", d.education), ("Культура речи", d.speech_culture)]
                if f)
            return (f"<h3>Диагностический профиль</h3>"
                    f"<p>Объём: {d.word_count} слов</p><ul>{items}</ul>"
                    f"<p style='color:#888'>Выводы вероятностные; формулирует эксперт.</p>")
        return "<p style='color:#999'>Нет данных. Выполните предыдущие стадии.</p>"

    def _export(self):
        st = self.state
        st.expert_verdict = self.verdict.toPlainText().strip()
        if st.mode == "identification" and st.comparison is not None:
            fp, _ = QFileDialog.getSaveFileName(
                self, "Сохранить заключение", "сравнение_текстов.docx", "Word (*.docx)")
            if not fp:
                return
            try:
                from analyzer.export import export_comparison_docx
                export_comparison_docx(fp, st.comparison, st.comparison_aux,
                                       st.slot1.text, st.slot2.text,
                                       expert_verdict=st.expert_verdict)
                QMessageBox.information(self, "Готово", f"Сохранено:\n{fp}")
            except Exception as e:
                QMessageBox.critical(self, "Ошибка", str(e))
        elif st.mode == "diagnostic" and st.slot1.analyzed:
            fp, _ = QFileDialog.getSaveFileName(
                self, "Сохранить отчёт", "профиль_автора.docx", "Word (*.docx)")
            if not fp:
                return
            try:
                from analyzer.export import export_report_docx
                s = st.slot1
                export_report_docx(fp, s.text, s.metrics, s.error_result, s.tokens,
                                   strat_result=s.strat_result,
                                   thematic_result=s.thematic_result)
                QMessageBox.information(self, "Готово", f"Сохранено:\n{fp}")
            except Exception as e:
                QMessageBox.critical(self, "Ошибка", str(e))
        else:
            QMessageBox.information(self, "Нет данных", "Сначала выполните анализ.")

    def is_complete(self) -> bool:
        return False
