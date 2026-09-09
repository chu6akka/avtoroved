import logging
from datetime import datetime, timezone
from time import perf_counter

from authoroved_core import __version__
from authoroved_core.core.document import Document
from authoroved_core.core.models import AnalysisResult
from authoroved_core.metrics.basic import calculate_metrics, structural_metrics
from authoroved_core.nlp.languagetool_adapter import LanguageToolAdapter
from authoroved_core.nlp.settings import LocalSettings
from authoroved_core.nlp.stanza_adapter import StanzaAdapter


class AnalysisService:
    def __init__(self, settings: LocalSettings):
        self.stanza = StanzaAdapter(settings.stanza_dir)
        self.lt = LanguageToolAdapter(settings)

    def analyze(self, document: Document, progress=lambda message: None) -> AnalysisResult:
        started = perf_counter()
        result = AnalysisResult(document.id, metadata={"program_version": __version__,
                                 "file_sha256": document.file_sha256, "text_sha256": document.text_sha256,
                                 "started_at": datetime.now(timezone.utc).isoformat()})
        result.metrics = structural_metrics(document.text)
        progress("Stanza: предложения, слова и грамматика…")
        try:
            result.tokens, result.metadata["stanza"] = self.stanza.analyze(document.text)
            result.metrics = calculate_metrics(document.text, result.tokens)
        except Exception:
            logging.exception("Stanza analysis failed")
            result.errors.append("Stanza: анализ не выполнен. Проверьте локальные модели в настройках. Подробности записаны в технический журнал.")
        progress("LanguageTool: проверка возможных ошибок…")
        try:
            result.candidates, result.metadata["languagetool"] = self.lt.analyze(document.id, document.text)
        except Exception:
            logging.exception("LanguageTool analysis failed")
            result.errors.append("LanguageTool: проверка не выполнена. Проверьте Java и папку LanguageTool в настройках. Подробности записаны в технический журнал.")
        result.metadata["seconds"] = round(perf_counter() - started, 3)
        return result
