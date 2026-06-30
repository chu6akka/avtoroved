"""Проверка LLM-оценщика: разбор ответа (детерминированно) и живой вызов (со скипом)."""

import pytest

from aved.core.registry import Registry
from aved.features.assessor import ManualAssessor, OllamaAssessor
from aved.features.assessor.local_llm import _parse_items
from aved.features.extractors import ExtractorContext
from aved.nlp import analyze


def test_parse_items_object_form():
    items = _parse_items('{"items":[{"id":"x","present":true,"confidence":0.9,"evidence":"цитата"}]}')
    assert items == [{"id": "x", "present": True, "confidence": 0.9, "evidence": "цитата"}]


def test_parse_items_list_form():
    items = _parse_items('[{"id":"y","present":false}]')
    assert items and items[0]["id"] == "y"


def test_parse_items_garbage_returns_empty():
    assert _parse_items("не json вовсе") == []
    assert _parse_items("") == []


def test_manual_assessor_returns_none():
    ctx = ExtractorContext(analyze("Короткий текст."))
    reg = Registry.load()
    f = reg.get("ns.psy.moralizing")
    assert ManualAssessor().assess(f, ctx) is None
    assert ManualAssessor().assess_batch([f], ctx) == {}


def test_ollama_assessor_live_or_skip():
    reg = Registry.load()
    text = "Как же мне жаль этого несчастного человека! Надо жить по совести и не грешить."
    ctx = ExtractorContext(analyze(text))
    feats = [reg.get("ns.psy.pity_empathy"), reg.get("ns.psy.moralizing")]
    res = OllamaAssessor(batch_size=8).assess_batch(feats, ctx)
    if not res:
        pytest.skip("Ollama/модель недоступна — живой вызов пропущен")
    for fv in res.values():
        assert fv.source_kind == "llm"
        assert isinstance(fv.present, bool)
