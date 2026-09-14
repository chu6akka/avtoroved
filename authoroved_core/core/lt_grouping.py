"""Понятная группировка кандидатов LanguageTool без переоценки их значения."""
from dataclasses import dataclass

from authoroved_core.core.models import Candidate, ReviewStatus


@dataclass(frozen=True)
class GroupDefinition:
    key: str
    title: str
    description: str


@dataclass(frozen=True)
class CandidateGroup:
    definition: GroupDefinition
    candidates: tuple[Candidate, ...]
    new: int
    accepted: int
    rejected: int


GROUPS = (
    GroupDefinition(
        "unknown_words", "Слова вне словаря LanguageTool",
        "LanguageTool не распознал словоформу. Это не доказательство ошибки: "
        "проверьте профессиональную, разговорную, диалектную, новую или авторскую лексику. "
        "Автоматические варианты LT могут ошибочно разрывать новое слово; перед сохранением "
        "укажите экспертную классификацию словоформы.",
    ),
    GroupDefinition(
        "spelling", "Правописание и регистр",
        "Автоматические предположения о написании или регистре букв. "
        "Подтверждайте только после проверки контекста.",
    ),
    GroupDefinition(
        "grammar", "Грамматические рекомендации",
        "Предположения LanguageTool о согласовании и форме конструкции. "
        "Автоматический разбор может не учитывать намеренную разговорную речь.",
    ),
    GroupDefinition(
        "punctuation", "Пунктуация и оформление",
        "Предположения о знаках препинания и техническом оформлении текста.",
    ),
    GroupDefinition(
        "wording", "Словоупотребление и редактура",
        "Стилистические, семантические и редакторские рекомендации. "
        "Они не равнозначны нарушениям языковой нормы.",
    ),
    GroupDefinition(
        "other", "Другие рекомендации LanguageTool",
        "Рекомендации, которым не назначена более точная группа. "
        "Перед принятием требуется отдельная экспертная оценка.",
    ),
)

GROUP_BY_KEY = {group.key: group for group in GROUPS}

UNKNOWN_WORD_CLASSIFICATIONS = (
    ("authorial", "Авторское образование или окказионализм"),
    ("neologism", "Неологизм или новая лексика"),
    ("professional", "Профессиональная или специальная лексика"),
    ("colloquial", "Разговорная или жаргонная форма"),
    ("dialect", "Диалектная форма"),
    ("name", "Имя, название или заимствование"),
    ("dictionary_gap", "Нормативная словоформа, которой нет в словаре LT"),
    ("spelling_error", "Орфографическая ошибка"),
)
UNKNOWN_WORD_CLASSIFICATION_LABELS = dict(UNKNOWN_WORD_CLASSIFICATIONS)


def candidate_group_key(candidate: Candidate) -> str:
    if candidate.rule_id == "MORFOLOGIK_RULE_RU_RU" or candidate.category == "Слово не распознано словарём":
        return "unknown_words"
    if candidate.category in {"Орфография", "Регистр букв"}:
        return "spelling"
    if candidate.category == "Грамматика":
        return "grammar"
    if candidate.category in {"Пунктуация", "Типографика"}:
        return "punctuation"
    if candidate.category in {
        "Стилистическая рекомендация", "Избыточность", "Словоупотребление",
        "Смешение слов", "Рекомендация по словоупотреблению",
    }:
        return "wording"
    return "other"


def group_candidates(candidates: list[Candidate]) -> tuple[CandidateGroup, ...]:
    grouped = []
    for definition in GROUPS:
        items = tuple(candidate for candidate in candidates
                      if candidate_group_key(candidate) == definition.key)
        if not items:
            continue
        grouped.append(CandidateGroup(
            definition=definition,
            candidates=items,
            new=sum(item.status == ReviewStatus.NEW for item in items),
            accepted=sum(item.status == ReviewStatus.ACCEPTED for item in items),
            rejected=sum(item.status == ReviewStatus.REJECTED for item in items),
        ))
    return tuple(grouped)
