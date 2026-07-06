"""
ui/tabs/token_inspector_tab.py — вкладка «Инспектор токенов».

Каждый токен документа кликабелен: клик открывает карточку со всей локальной
информацией (морфология, частотность НКРЯ, регистровый слой, тональность,
hapax/употребления) и справочными ссылками на внешние словари. Режимы
подсветки: части речи / регистровые слои / частотность.

Анализ офлайн; внешние ссылки открываются в браузере только по клику эксперта
на конкретное слово — материалы дела никуда не отправляются.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QTextBrowser,
    QSplitter,
)

from protocol import db as protocol_db
from protocol import token_card

# ── Палитры подсветки (Catppuccin-совместимые) ───────────────────────────────
_POS_COLORS = {
    "NOUN": "#89b4fa", "PROPN": "#74c7ec", "VERB": "#a6e3a1", "AUX": "#94e2d5",
    "ADJ": "#f9e2af", "ADV": "#fab387", "PRON": "#cba6f7", "NUM": "#f5c2e7",
    "DET": "#cba6f7", "ADP": "#7f849c", "PART": "#7f849c",
    "CCONJ": "#7f849c", "SCONJ": "#7f849c", "INTJ": "#eba0ac",
}
_BAND_COLORS = {
    "core": "#7f849c", "high": "#89b4fa", "mid": "#a6e3a1",
    "low": "#f9e2af", "rare": "#fab387", "absent": "#f38ba8",
}
_LAYER_COLORS = {
    "obscene": "#f38ba8", "criminal_jargon": "#eba0ac", "drug_jargon": "#eba0ac",
    "youth_jargon": "#fab387", "common_jargon": "#fab387", "vernacular": "#f9e2af",
    "colloquial_low": "#f9e2af", "book_neutral": "#89b4fa", "archaism": "#cba6f7",
    "dialect": "#94e2d5", "euphemistic": "#f5c2e7",
}

_LEGENDS = {
    "pos": "Подсветка: существительные — синий, глаголы — зелёный, прилагательные — "
           "жёлтый, наречия — оранжевый, местоимения — фиолетовый, служебные — серый.",
    "band": "Подсветка частотности (НКРЯ): серый — ядро, синий — высокочастотная, "
            "зелёный — средняя, жёлтый — низкочастотная, оранжевый — раритетная, "
            "красный — отсутствует в НКРЯ.",
    "layer": "Подсветка регистров: красный — обсценная, оранжевый — жаргон, жёлтый — "
             "просторечие/разговорная, синий — книжная, фиолетовый — архаизмы, "
             "бирюзовый — диалектизмы, розовый — эвфемизмы; серый — нейтральная.",
    "none": "Подсветка выключена — все токены кликабельны.",
}


class TokenInspectorTab(QWidget):
    """Вкладка «Инспектор токенов»: кликабельные токены + карточка слова."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pdb = protocol_db.ProtocolDB()
        self._project_id: int | None = None
        self._document_id: int | None = None
        self._tokens: list = []
        self._lemma_counts: dict[str, int] = {}
        self._engines_ready = False
        self._freq = None
        self._strat_lookup = None
        self._senti = None
        self._build_ui()
        self._reload_projects()

    # ── ленивые словарные движки (локальные, без сети) ───────────────────────
    def _ensure_engines(self):
        if self._engines_ready:
            return
        try:
            from analyzer import freq_engine
            eng = freq_engine.get()
            eng.load()
            self._freq = eng
        except Exception:
            self._freq = None
        try:
            from analyzer import stratification_engine
            strat = stratification_engine.get()
            strat.load()
            self._strat_lookup = strat._lemma_to_layer.get
        except Exception:
            self._strat_lookup = None
        try:
            from analyzer import senti_engine
            s = senti_engine.get()
            s.load()
            self._senti = s
        except Exception:
            self._senti = None
        self._engines_ready = True

    # ── UI ───────────────────────────────────────────────────────────────────
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        title = QLabel("Инспектор токенов: клик по слову — полная карточка")
        title.setObjectName("subtitle")
        layout.addWidget(title)

        top = QHBoxLayout()
        top.addWidget(QLabel("Проект:"))
        self.project_combo = QComboBox()
        self.project_combo.setMinimumWidth(200)
        self.project_combo.currentIndexChanged.connect(self._on_project_changed)
        top.addWidget(self.project_combo)
        top.addWidget(QLabel("Документ:"))
        self.doc_combo = QComboBox()
        self.doc_combo.setMinimumWidth(220)
        self.doc_combo.currentIndexChanged.connect(self._on_document_changed)
        top.addWidget(self.doc_combo)
        top.addWidget(QLabel("Подсветка:"))
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("Части речи", "pos")
        self.mode_combo.addItem("Регистровые слои", "layer")
        self.mode_combo.addItem("Частотность НКРЯ", "band")
        self.mode_combo.addItem("Без подсветки", "none")
        self.mode_combo.currentIndexChanged.connect(lambda _i: self._render_text())
        top.addWidget(self.mode_combo)
        top.addStretch()
        layout.addLayout(top)

        self.legend_label = QLabel("")
        self.legend_label.setObjectName("caption")
        self.legend_label.setWordWrap(True)
        layout.addWidget(self.legend_label)

        # Слева — текст из кликабельных токенов, справа — карточка.
        self.text_view = QTextBrowser()
        self.text_view.setOpenLinks(False)
        self.text_view.anchorClicked.connect(self._on_token_clicked)
        self.text_view.setStyleSheet("QTextBrowser { font-size: 14px; }")

        self.card_view = QTextBrowser()
        self.card_view.setOpenLinks(False)
        self.card_view.anchorClicked.connect(self._on_card_link)
        self.card_view.setMinimumWidth(330)
        self.card_view.setPlaceholderText("Кликните по слову слева.")

        split = QSplitter(Qt.Orientation.Horizontal)
        split.setChildrenCollapsible(False)
        split.addWidget(self.text_view)
        split.addWidget(self.card_view)
        split.setSizes([650, 360])
        layout.addWidget(split, stretch=1)

        self.status_label = QLabel("")
        self.status_label.setObjectName("caption")
        layout.addWidget(self.status_label)

    # ── выбор проекта/документа ──────────────────────────────────────────────
    def _reload_projects(self):
        self.project_combo.blockSignals(True)
        self.project_combo.clear()
        projects = self._pdb.fetch_projects()
        for p in projects:
            self.project_combo.addItem(f"{p['name']} (#{p['id']})", p["id"])
        self.project_combo.blockSignals(False)
        if projects:
            self.project_combo.setCurrentIndex(0)
            self._project_id = projects[0]["id"]
            self._reload_documents()
        else:
            self._project_id = None
            self.doc_combo.clear()

    def _on_project_changed(self, index: int):
        self._project_id = self.project_combo.itemData(index) if index >= 0 else None
        self._reload_documents()

    def _reload_documents(self):
        self.doc_combo.blockSignals(True)
        self.doc_combo.clear()
        if self._project_id is not None:
            for d in self._pdb.fetch_documents(self._project_id):
                self.doc_combo.addItem(f"{d['filename']} ({d['role']})", d["id"])
        self.doc_combo.blockSignals(False)
        if self.doc_combo.count():
            self.doc_combo.setCurrentIndex(0)
            self._document_id = self.doc_combo.itemData(0)
        else:
            self._document_id = None
        self._load_tokens()

    def _on_document_changed(self, index: int):
        self._document_id = self.doc_combo.itemData(index) if index >= 0 else None
        self._load_tokens()

    def showEvent(self, event):
        super().showEvent(event)
        self._reload_projects()

    # ── данные и отрисовка ───────────────────────────────────────────────────
    def _load_tokens(self):
        self._tokens = []
        self._lemma_counts = {}
        self.card_view.clear()
        if self._document_id is not None:
            self._tokens = list(self._pdb.fetch_document_tokens(self._document_id))
            for t in self._tokens:
                if t["pos"] != "PUNCT":
                    lem = (t["lemma"] or t["text"]).lower()
                    self._lemma_counts[lem] = self._lemma_counts.get(lem, 0) + 1
        self._render_text()

    def _token_color(self, t, mode: str) -> str | None:
        if mode == "pos":
            return _POS_COLORS.get(t["pos"])
        if mode == "layer":
            self._ensure_engines()
            if self._strat_lookup is not None:
                layer = self._strat_lookup((t["lemma"] or t["text"]).lower())
                if layer:
                    return _LAYER_COLORS.get(layer, "#f9e2af")
            return "#7f849c"
        if mode == "band":
            self._ensure_engines()
            info = token_card.frequency_info(self._freq, (t["lemma"] or t["text"]).lower())
            return _BAND_COLORS.get(info["band"])
        return None

    def _render_text(self):
        mode = self.mode_combo.currentData() or "pos"
        self.legend_label.setText(_LEGENDS.get(mode, ""))
        if not self._tokens:
            self.text_view.setHtml(
                "<i>Нет токенов. Импортируйте документ во вкладке «Материалы» — "
                "разметка сохраняется в базе протокола.</i>")
            self.status_label.setText("")
            return
        if mode in ("layer", "band"):
            self._ensure_engines()

        parts: list[str] = []
        current_sent = None
        for i, t in enumerate(self._tokens):
            if t["sent_idx"] != current_sent:
                if current_sent is not None:
                    parts.append("<br>")
                current_sent = t["sent_idx"]
                parts.append(f"<span style='color:#585b70'>[{current_sent + 1}]</span> ")
            word = (t["text"] or "").replace("<", "&lt;").replace(">", "&gt;")
            if t["pos"] == "PUNCT":
                # Пунктуация прижимается к предыдущему слову.
                if parts and parts[-1].endswith(" "):
                    parts[-1] = parts[-1][:-1]
                parts.append(f"{word} ")
                continue
            color = self._token_color(t, mode)
            style = "text-decoration:none;"
            style += f"color:{color};" if color else "color:#cdd6f4;"
            parts.append(f"<a href='tok:{i}' style='{style}'>{word}</a> ")
        self.text_view.setHtml(
            "<div style='line-height:1.7'>" + "".join(parts) + "</div>")
        n_words = len(self._lemma_counts)
        self.status_label.setText(
            f"Токенов: {len(self._tokens)}, уникальных лемм: {n_words}. "
            "Клик по слову — карточка со словарями.")

    # ── карточка ─────────────────────────────────────────────────────────────
    def _on_token_clicked(self, url: QUrl):
        s = url.toString()
        if not s.startswith("tok:"):
            return
        idx = int(s[4:])
        if not (0 <= idx < len(self._tokens)):
            return
        self._ensure_engines()
        t = self._tokens[idx]
        card = token_card.build_card(
            {"text": t["text"], "lemma": t["lemma"], "pos": t["pos"],
             "feats": t["feats"], "sent_idx": t["sent_idx"]},
            self._lemma_counts,
            freq_engine=self._freq, strat_lookup=self._strat_lookup,
            senti_engine=self._senti)
        self.card_view.setHtml(self._card_html(card))

    def _card_html(self, c: dict) -> str:
        def chip(text, bg):
            return (f"<span style='background:{bg};color:#1e1e2e;border-radius:8px;"
                    f"padding:2px 8px;font-size:12px'>{text}</span>")

        badges = " ".join(chip(b, "#f9e2af" if "★" in b else "#89dceb")
                          for b in c["badges"]) or ""
        links = " · ".join(f"<a href='{u}' style='color:#89b4fa'>{n}</a>"
                           for n, u in c["links"])
        ipm_txt = f"{c['ipm']:.1f} ipm, ранг {c['rank']}" if c["rank"] else "—"
        senti_txt = (f"{c['sentiment']} ({c['senti_type']})"
                     if c["sentiment"] else "нейтральная / вне словаря")
        return f"""
        <div style='font-size:13px; line-height:1.55'>
          <div style='font-size:22px'><b>{c['word']}</b>
            <span style='color:#a6adc8'>→ {c['lemma']}</span></div>
          <div style='margin:6px 0'>{badges}</div>
          <table cellpadding='3' style='font-size:13px'>
            <tr><td style='color:#a6adc8'>Часть речи</td><td><b>{c['pos']}</b></td></tr>
            <tr><td style='color:#a6adc8'>Морфология</td><td>{c['feats']}</td></tr>
            <tr><td style='color:#a6adc8'>В документе</td>
                <td>{c['count_in_doc']} раз{' (hapax)' if c['is_hapax'] else ''},
                    предложение {c['sent_idx'] + 1 if c['sent_idx'] is not None else '—'}</td></tr>
            <tr><td style='color:#a6adc8'>Частотность НКРЯ</td>
                <td>{c['band_label']} ({ipm_txt})</td></tr>
            <tr><td style='color:#a6adc8'>Регистр</td><td>{c['layer_label']}</td></tr>
            <tr><td style='color:#a6adc8'>Тональность</td><td>{senti_txt}</td></tr>
          </table>
          <div style='margin-top:8px;color:#a6adc8'>Внешние словари
            (откроются в браузере):</div>
          <div>{links}</div>
        </div>"""

    def _on_card_link(self, url: QUrl):
        # Внешние ссылки — в системный браузер (по явному клику эксперта).
        if url.scheme() in ("http", "https"):
            QDesktopServices.openUrl(url)
