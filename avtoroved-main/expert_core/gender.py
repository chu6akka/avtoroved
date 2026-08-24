from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
import re

from .models import TextObject
from .suitability import SuitabilityService

_WORDS = re.compile(r"[А-Яа-яЁё]+")
_FUNCTION_WORDS = {
    "я", "мы", "ты", "вы", "он", "она", "они", "это", "тот", "который",
    "и", "а", "но", "или", "что", "чтобы", "если", "когда", "как",
    "в", "на", "с", "к", "у", "из", "за", "от", "для", "по", "о",
    "не", "ни", "же", "бы", "ли", "даже", "только", "уже",
}


@dataclass
class GenderApplicability:
    applicable: bool
    research_only: bool
    reasons: list[str] = field(default_factory=list)


@dataclass
class GenderDiagnosticResult:
    applicability: GenderApplicability
    frequencies_ipm: dict[str, float]
    conclusion: str
    limitations: list[str]
    exportable_as_evidence: bool = False
    method_version: str = "ogorealkov-political-2024:uncalibrated"


class GenderDiagnosticService:
    """Безопасная оболочка модели Огорелкова.

    Репозиторий пока не содержит верифицированной электронной таблицы порогов
    монографии, поэтому сервис не имитирует классификатор: он рассчитывает
    проверяемые частоты и оставляет результат исследовательским.
    """

    MIN_WORDS = 8000

    def check_applicability(self, obj: TextObject) -> GenderApplicability:
        reasons: list[str] = []
        wc = SuitabilityService.word_count(obj.text)
        if wc < self.MIN_WORDS:
            reasons.append(f"Объём {wc} слов меньше валидированного объёма {self.MIN_WORDS}")
        if obj.genre.strip().lower() not in {"политический дискурс", "политический", "political"}:
            reasons.append("Текст не отнесён экспертом к политическому дискурсу")
        if SuitabilityService._cyrillic_ratio(obj.text) < 0.5:
            reasons.append("Текст не является преимущественно русскоязычным")
        if obj.compilation_suspected is not False:
            reasons.append("Отсутствие компиляции не подтверждено")
        if obj.independent_authorship is not True:
            reasons.append("Самостоятельность составления не подтверждена")
        return GenderApplicability(not reasons, True, reasons)

    def analyze(self, obj: TextObject) -> GenderDiagnosticResult:
        applicability = self.check_applicability(obj)
        words = [w.lower() for w in _WORDS.findall(obj.text)]
        counts = Counter(words)
        total = len(words) or 1
        freqs = {w: round(counts[w] / total * 1_000_000, 3) for w in sorted(_FUNCTION_WORDS) if counts[w]}
        limitations = list(applicability.reasons)
        limitations.append("Калиброванные пороги 20 словоформ не импортированы и не валидированы в ПО")
        return GenderDiagnosticResult(
            applicability=applicability, frequencies_ipm=freqs,
            conclusion="НПВ: автоматический диагностический вывод отключён до корпусной валидации",
            limitations=limitations, exportable_as_evidence=False,
        )
