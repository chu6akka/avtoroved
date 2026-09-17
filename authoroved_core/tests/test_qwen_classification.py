"""Подсказка по кандидату LanguageTool; настоящая модель не запускается."""
import json

import pytest

from authoroved_core.core.lt_grouping import UNKNOWN_WORD_CLASSIFICATIONS
from authoroved_core.core.models import Candidate, Span
from authoroved_core.core.qwen_classification import (
    ALLOWED_ANSWERS, CLASSIFICATION_EXAMPLES, CLASSIFICATION_KEYS,
    CLASSIFICATION_SCHEMA, HintStatus, HintValidator, QwenClassificationService,
    candidate_labels, classification_schema, context_window,
)
from authoroved_core.core.word_evidence import FrequencyDictionary, collect
from authoroved_core.core.qwen_shadow import ProviderCompletion


class FakeProvider:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def complete(self, **kwargs):
        self.calls.append(kwargs)
        return ProviderCompletion(next(self.responses), {"model": "frozen-test-model"})


def candidate(fragment="зачётненько", start=10):
    return Candidate(
        "c1", "d1", "Слово не распознано словарём", "Слово не распознано словарём",
        "Словарь не знает эту форму", fragment, Span(start, start + len(fragment)),
        "MORFOLOGIK_RULE_RU_RU", ("зачётно",),
    )


def answer(classification, reason="разговорная оценочная форма"):
    return json.dumps({"classification": classification, "reason": reason},
                      ensure_ascii=False)


def test_schema_closes_the_answer_set_to_the_expert_labels():
    allowed = CLASSIFICATION_SCHEMA["properties"]["classification"]["enum"]

    assert set(allowed) == ALLOWED_ANSWERS
    assert {key for key, _ in UNKNOWN_WORD_CLASSIFICATIONS} < set(allowed)
    assert CLASSIFICATION_SCHEMA["additionalProperties"] is False


def test_hint_carries_a_label_and_never_allows_expert_use():
    text = "Получилось зачётненько, всем понравилось."
    service = QwenClassificationService(FakeProvider([answer("colloquial")]))

    hint = service.hint(candidate(start=text.index("зачётненько")), text)

    assert hint.status is HintStatus.VALIDATED_HINT
    assert hint.classification == "colloquial"
    assert hint.label == "Разговорная или жаргонная форма"
    assert hint.expert_use_allowed is False


def test_model_may_abstain_instead_of_guessing():
    service = QwenClassificationService(
        FakeProvider([answer("unclear", "окружения не хватает")]),
    )

    hint = service.hint(candidate(), "Короткий текст с зачётненько внутри.")

    assert hint.status is HintStatus.MODEL_UNCLEAR
    assert hint.classification == ""
    assert hint.expert_use_allowed is False


@pytest.mark.parametrize("raw", [
    '{"classification":"выдуманная","reason":"причина"}',
    '{"classification":"colloquial","reason":"english only reason"}',
    '{"classification":"colloquial"}',
    '{"classification":"colloquial","reason":"","extra":1}',
    "не json",
])
def test_invalid_answer_is_rejected_and_raw_response_is_kept(raw):
    service = QwenClassificationService(FakeProvider([raw]))

    hint = service.hint(candidate(), "текст с зачётненько внутри")

    assert hint.status is HintStatus.SYSTEM_REJECTED
    assert hint.raw_response == raw
    assert hint.classification == "" and hint.expert_use_allowed is False


def test_model_receives_a_window_not_the_whole_document():
    """Свободный поиск по документу и был причиной 84 % нарушений."""
    text = "А" * 5000 + "зачётненько" + "Б" * 5000
    service = QwenClassificationService(FakeProvider([answer("colloquial")]))

    service.hint(candidate(start=5000), text)

    payload = json.loads(service.provider.calls[0]["user_prompt"])
    assert len(payload["context"]) < 400
    assert "зачётненько" in payload["context"]
    assert payload["word"] == "зачётненько"


def test_prompt_forbids_authorship_and_personal_traits():
    service = QwenClassificationService(FakeProvider([answer("colloquial")]))

    service.hint(candidate(), "текст с зачётненько внутри")

    system = service.provider.calls[0]["system_prompt"]
    assert "Не делай вывод об авторстве" in system
    assert "пол, возраст, эмоции" in system


def test_context_window_stays_inside_the_text():
    text = "зачётненько в самом начале"

    window = context_window(text, candidate(start=0), width=1000)

    assert window == text


@pytest.mark.parametrize("classification", [key for key, _ in UNKNOWN_WORD_CLASSIFICATIONS])
def test_every_expert_label_round_trips(classification):
    assert HintValidator().validate(answer(classification)) == (
        classification, "разговорная оценочная форма",
    )


def test_every_label_carries_an_example_and_a_near_miss():
    """Приём из «Соучастника»: рядом с меткой показан близкий промах."""
    assert set(CLASSIFICATION_EXAMPLES) == set(CLASSIFICATION_KEYS)
    for key, (example, counterexample) in CLASSIFICATION_EXAMPLES.items():
        assert example.strip() and counterexample.strip()
        assert counterexample.startswith("а вот ")
        # Пример и контрпример — разные слова, иначе граница не показана.
        assert example.split(" —")[0] != counterexample.split(" не")[0]


def test_examples_reach_the_prompt():
    service = QwenClassificationService(FakeProvider([answer("colloquial")]))

    service.hint(candidate(), "текст с зачётненько внутри")

    payload = json.loads(service.provider.calls[0]["user_prompt"])
    entry = next(item for item in payload["classifications"] if item["key"] == "colloquial")
    assert entry["example"] and entry["counterexample"]


def test_repetition_narrows_the_label_set_before_the_model():
    """Выбор из нескольких кандидатов надёжнее выбора из всех."""
    text = "Был тимбилдинг, потом ещё тимбилдинг и снова тимбилдинг."
    start = text.index("тимбилдинг")
    item = Candidate(
        "c1", "d1", "Слово не распознано словарём", "Слово не распознано словарём",
        "пояснение", "тимбилдинг", Span(start, start + len("тимбилдинг")),
        "MORFOLOGIK_RULE_RU_RU",
    )
    evidence = collect(item, text, (), FrequencyDictionary({}))

    labels = candidate_labels(evidence)

    assert evidence.repeats_in_text == 3
    assert "spelling_error" not in labels
    assert set(labels) | {"spelling_error"} == set(CLASSIFICATION_KEYS)


def test_single_occurrence_keeps_every_label():
    text = "Ровно один раз слово зачётненько встречается."
    evidence = collect(candidate(start=text.index("зачётненько")), text, (), FrequencyDictionary({}))

    assert candidate_labels(evidence) == CLASSIFICATION_KEYS
    assert candidate_labels(None) == CLASSIFICATION_KEYS


def test_narrowed_schema_and_validator_agree():
    labels = candidate_labels(None)[:3]

    schema = classification_schema(labels)

    assert set(schema["properties"]["classification"]["enum"]) == set(labels) | {"unclear"}
    with pytest.raises(Exception):
        HintValidator().validate(answer("spelling_error"), labels)
    assert HintValidator().validate(answer(labels[0]))[0] == labels[0]


def test_narrowed_label_is_refused_by_the_service():
    """Модель не может вернуть метку, которую сняла справка."""
    text = "Был тимбилдинг, потом ещё тимбилдинг."
    start = text.index("тимбилдинг")
    item = Candidate(
        "c1", "d1", "Слово не распознано словарём", "Слово не распознано словарём",
        "пояснение", "тимбилдинг", Span(start, start + len("тимбилдинг")),
        "MORFOLOGIK_RULE_RU_RU",
    )
    evidence = collect(item, text, (), FrequencyDictionary({}))
    service = QwenClassificationService(FakeProvider([answer("spelling_error")]))

    hint = service.hint(item, text, evidence)

    assert hint.status is HintStatus.SYSTEM_REJECTED
    assert "закрытом списке" in hint.rejection_reason
