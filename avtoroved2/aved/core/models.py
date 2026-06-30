"""Модели данных ядра: признаки, их значения, модель навыка, сравнение, вывод.

Терминология — по методике Рубцовой и др. (ЭКЦ МВД, 2007):
уровни индивидуализации навыка НН / НС / НСВ, признаки письменной речи,
комплексы совпадающих и различающихся признаков, идентификационный вывод.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Level(str, Enum):
    """Уровень индивидуализации навыка (с. 11). Значимость растёт НН < НС < НСВ."""

    NN = "NN"      # набор норм
    NS = "NS"      # набор свойств норм
    NSV = "NSV"    # набор средств выражения свойств норм


class Category(str, Enum):
    """Категория признака по методике."""

    SMYSLOVYE = "smyslovye"               # смысловые
    TEXTOLOGICAL = "textological"         # текстологические
    LANGUAGE = "language"                 # языковые (только НН)
    LEXICAL = "lexical"                   # лексические
    STYLISTIC = "stylistic"               # стилистические
    SYNTACTIC = "syntactic"               # синтаксические
    PSYCHOLINGUISTIC = "psycholinguistic" # психолингвистические


class Significance(str, Enum):
    """Идентификационная значимость (информативность) признака."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Method(str, Enum):
    """Способ установления признака программой."""

    AUTO = "auto"       # вычисляется экстрактором
    HYBRID = "hybrid"   # экстрактор + LLM/словарь, эксперт подтверждает
    LLM = "llm"         # оценивает локальная LLM, эксперт подтверждает
    MANUAL = "manual"   # отмечает только эксперт


@dataclass(frozen=True, slots=True)
class Feature:
    """Описание признака из методики (запись реестра)."""

    id: str
    level: Level
    category: Category
    name: str
    significance: Significance
    method: Method
    source: str                       # ссылка на страницу методики, напр. "с. 87"
    extractor: str | None = None      # имя экстрактора для auto/hybrid
    lexicon: str | None = None        # путь к словарю-помощнику (если есть)
    subcategory: str | None = None    # подгруппа (для лексич./синтаксич./стилистич.)
    note: str | None = None

    @property
    def high_info(self) -> bool:
        return self.significance is Significance.HIGH


# --------------------------------------------------------------------------- #
#  Результаты анализа конкретного текста
# --------------------------------------------------------------------------- #

class Role(str, Enum):
    """Роль текста в исследовании."""

    DISPUTED = "disputed"   # спорный текст
    SAMPLE = "sample"       # образец


@dataclass(slots=True)
class Evidence:
    """Фрагмент-иллюстрация проявления признака в тексте."""

    quote: str
    start: int = -1
    stop: int = -1


@dataclass(slots=True)
class FeatureValue:
    """Установленное в тексте значение признака."""

    feature_id: str
    present: bool                                  # обнаружен ли признак
    value: float | str | None = None              # количественное значение (частота и т.п.)
    evidence: list[Evidence] = field(default_factory=list)
    confidence: float = 1.0                        # уверенность (актуально для LLM)
    source_kind: str = "auto"                      # auto | llm | manual — кто установил
    expert_confirmed: bool = False                 # подтверждено экспертом
    stable: bool | None = None                     # устойчивость (повторяемость по тексту)
    note: str = ""


@dataclass(slots=True)
class ObjectText:
    """Объект исследования: спорный текст или образец."""

    id: str
    role: Role
    title: str
    text: str
    style: str | None = None        # функциональный стиль
    date: str | None = None         # время составления (для проверки сопоставимости)
    # заполняется на стадии пригодности:
    word_count: int = 0
    suitable: bool | None = None
    suitability_notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class NavykModel:
    """Модель речемыслительного навыка, отразившегося в одном тексте (стадия 2)."""

    object_id: str
    values: dict[str, FeatureValue] = field(default_factory=dict)

    def present_ids(self) -> set[str]:
        return {fid for fid, v in self.values.items() if v.present}


# --------------------------------------------------------------------------- #
#  Сравнение и вывод
# --------------------------------------------------------------------------- #

@dataclass(slots=True)
class LevelComparison:
    """Итог сравнения по одному уровню индивидуализации."""

    level: Level
    matching: list[str] = field(default_factory=list)   # совпадающие признаки (id)
    differing: list[str] = field(default_factory=list)  # различающиеся признаки (id)
    matching_high: int = 0                              # из них высокоинформативных
    differing_high: int = 0

    @property
    def has_matches(self) -> bool:
        return bool(self.matching)

    @property
    def has_differences(self) -> bool:
        return bool(self.differing)


@dataclass(slots=True)
class Comparison:
    """Результат сравнительного исследования (стадия 3): комплексы по уровням."""

    disputed_id: str
    sample_id: str
    levels: dict[Level, LevelComparison] = field(default_factory=dict)
    # конфликт на уровне НН: различие наборов норм (разный преобладающий стиль/тип мышления)
    nn_norm_conflict: bool = False
    nn_conflict_reason: str = ""

    def total_matching_high(self) -> int:
        return sum(lc.matching_high for lc in self.levels.values())

    def total_differing_high(self) -> int:
        return sum(lc.differing_high for lc in self.levels.values())

    def levels_with_matches(self) -> list[Level]:
        return [lv for lv, lc in self.levels.items() if lc.has_matches]

    def levels_with_differences(self) -> list[Level]:
        return [lv for lv, lc in self.levels.items() if lc.has_differences]


class VerdictType(str, Enum):
    """Виды идентификационного вывода (с. 85–86)."""

    CATEGORICAL_POSITIVE = "categorical_positive"   # категорический положительный
    PROBABLE_POSITIVE = "probable_positive"         # вероятный положительный / «не исключается»
    PROBABLE_NEGATIVE = "probable_negative"         # вероятный отрицательный
    CATEGORICAL_NEGATIVE = "categorical_negative"   # категорический отрицательный
    INCONCLUSIVE = "inconclusive"                   # НПВ — решить не представляется возможным


@dataclass(slots=True)
class Verdict:
    """Сформулированный вывод по совокупности признаков (стадия 4)."""

    type: VerdictType
    rationale: list[str] = field(default_factory=list)
    matching_high_count: int = 0
    differing_high_count: int = 0
    levels_with_matches: list[Level] = field(default_factory=list)
    levels_with_differences: list[Level] = field(default_factory=list)

    # порог методики: комплекс должен включать не менее 20 высокоинформативных признаков
    MIN_HIGH_INFO: int = 20
