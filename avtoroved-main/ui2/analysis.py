"""
Сервис раздельного анализа для нового интерфейса.
Переиспользует существующие движки analyzer/* — ничего не дублирует.
"""
from __future__ import annotations
from PyQt6.QtCore import QThread, pyqtSignal


class Engines:
    """Ленивый держатель движков анализа (один экземпляр на окно)."""
    def __init__(self):
        self._stanza = None
        self._errors = None
        self._strat = None
        self._thematic = None
        self._diag = None

    @property
    def stanza(self):
        if self._stanza is None:
            from analyzer.stanza_backend import StanzaBackend
            self._stanza = StanzaBackend()
        return self._stanza

    @property
    def errors(self):
        if self._errors is None:
            from analyzer.errors import ErrorAnalyzer
            self._errors = ErrorAnalyzer()
        return self._errors

    @property
    def strat(self):
        if self._strat is None:
            from analyzer import stratification_engine as m
            self._strat = m.get()
        return self._strat

    @property
    def thematic(self):
        if self._thematic is None:
            from analyzer import thematic_engine as m
            self._thematic = m.get()
        return self._thematic

    @property
    def diagnostic(self):
        if self._diag is None:
            from analyzer import diagnostic_engine as m
            self._diag = m.get()
        return self._diag


def analyze_slot(slot, engines: Engines, want_diagnostic: bool, status_cb=None):
    """Полный раздельный анализ одного текста; заполняет поля slot."""
    from analyzer.stanza_backend import WORD_RE
    from analyzer.metrics import calculate_metrics
    from analyzer.errors import calculate_general_skill

    text = slot.text
    if status_cb:
        status_cb(f"{slot.name}: морфологический анализ…")
    engines.stanza.ensure_loaded(status_cb or (lambda m: None))
    tokens = engines.stanza.analyze(text)
    slot.tokens = tokens

    if status_cb:
        status_cb(f"{slot.name}: метрики…")
    metrics = calculate_metrics(tokens, text)
    slot.metrics = metrics

    if status_cb:
        status_cb(f"{slot.name}: ошибки и навыки…")
    er = engines.errors.analyze(text, tokens)
    if er is not None and not er.general_skill_level:
        (er.general_skill_level, er.general_skill_desc,
         er.total_unique_errors) = calculate_general_skill(er.errors, er.total_words)
    slot.error_result = er

    if status_cb:
        status_cb(f"{slot.name}: стратификация…")
    try:
        slot.strat_result = engines.strat.analyze(text)
    except Exception:
        slot.strat_result = None

    if status_cb:
        status_cb(f"{slot.name}: тематика…")
    try:
        lemmas = [t.lemma.lower() for t in tokens
                  if WORD_RE.search(t.text) and t.pos not in ("PUNCT", "NUM")]
        slot.thematic_result = engines.thematic.analyze(lemmas)
    except Exception:
        slot.thematic_result = None

    if want_diagnostic:
        if status_cb:
            status_cb(f"{slot.name}: диагностический профиль…")
        try:
            slot.diagnostic_result = engines.diagnostic.analyze(
                tokens, metrics, er, slot.thematic_result)
        except Exception:
            slot.diagnostic_result = None

    slot.analyzed = True


class AnalyzeThread(QThread):
    """Фоновый прогон анализа по списку текстов."""
    status = pyqtSignal(str)
    finished = pyqtSignal(bool, str)   # ok, error_message

    def __init__(self, slots, engines: Engines, want_diagnostic: bool):
        super().__init__()
        self.slots = slots
        self.engines = engines
        self.want_diagnostic = want_diagnostic

    def run(self):
        try:
            for slot in self.slots:
                analyze_slot(slot, self.engines, self.want_diagnostic,
                             self.status.emit)
            self.finished.emit(True, "")
        except Exception as e:
            self.finished.emit(False, str(e))
