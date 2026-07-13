"""Тесты собственных офлайн-детекторов ошибок (analyzer/ru_checker.py)."""
import pytest

pytest.importorskip("pymorphy3")

from analyzer import ru_checker as rc
from analyzer.stanza_backend import TokenInfo


def _types(errs):
    return [(e.error_type, e.subtype) for e in errs]


# ── орфография: словарная проверка ───────────────────────────────────────────
def test_spelling_flags_unknown_word():
    errs = rc.spelling_errors("мой брат пошол домой вчера")
    assert any(e.fragment == "пошол" for e in errs)
    e = next(e for e in errs if e.fragment == "пошол")
    assert e.error_type == "Орфографическая"
    assert e.rule_ref == "RU:SPELL_DICT"
    assert e.fragment in e.context


def test_spelling_skips_capitalized_and_jargon():
    errs = rc.spelling_errors("Вася сказал что этот зашквар и движуха не проблема")
    frags = [e.fragment for e in errs]
    assert "Вася" not in frags          # заглавная буква — пропуск
    assert "зашквар" not in frags       # регистровый словарь
    assert "движуха" not in frags


def test_spelling_dedupes_repeated_form():
    errs = rc.spelling_errors("он пошол и снова пошол")
    assert len([e for e in errs if e.fragment == "пошол"]) == 1


# ── орфография: -тся/-ться ───────────────────────────────────────────────────
def test_tsya_after_infinitive_marker():
    errs = rc.tsya_errors("он будет старатся изо всех сил")
    assert _types(errs) == [("Орфографическая", "-тся вместо -ться")]
    assert "старатся" in errs[0].fragment


def test_tsya_after_pronoun():
    errs = rc.tsya_errors("он учиться в школе")
    assert _types(errs) == [("Орфографическая", "-ться вместо -тся")]


def test_tsya_correct_forms_not_flagged():
    assert rc.tsya_errors("он учится в школе") == []
    assert rc.tsya_errors("надо учиться каждый день") == []


# ── грамматика: согласование ─────────────────────────────────────────────────
def _tok(text, pos, sid, tid, cs, ce):
    return TokenInfo(text=text, lemma=text, pos=pos, pos_label="", feats="",
                     sent_id=sid, token_id=tid, char_start=cs, char_end=ce)


def test_agreement_mismatch_flagged():
    text = "Красивый девушка шла по улице."
    tokens = [_tok("Красивый", "ADJ", 0, 1, 0, 8),
              _tok("девушка", "NOUN", 0, 2, 9, 16)]
    errs = rc.agreement_errors(text, tokens)
    assert len(errs) == 1
    assert errs[0].error_type == "Грамматическая"
    assert "Красивый девушка" in errs[0].fragment


def test_agreement_correct_pair_not_flagged():
    text = "Красивая девушка шла по улице."
    tokens = [_tok("Красивая", "ADJ", 0, 1, 0, 8),
              _tok("девушка", "NOUN", 0, 2, 9, 16)]
    assert rc.agreement_errors(text, tokens) == []


def test_agreement_requires_adjacency_same_sentence():
    text = "Красивый закат. Девушка шла."
    tokens = [_tok("Красивый", "ADJ", 0, 2, 0, 8),
              _tok("Девушка", "NOUN", 1, 1, 16, 23)]
    assert rc.agreement_errors(text, tokens) == []


# ── лексика ──────────────────────────────────────────────────────────────────
def test_pleonasm():
    errs = rc.lexical_errors("у нас есть свободная вакансия для юриста")
    assert any("Плеоназм" in e.subtype for e in errs)


def test_tautology_same_lemma_in_window():
    errs = rc.lexical_errors("он выполнил работу и работа удалась сразу")
    taut = [e for e in errs if e.subtype == "Тавтология"]
    assert len(taut) == 1
    assert "работ" in taut[0].description


def test_tautology_not_for_different_lemmas():
    errs = rc.lexical_errors("работа работника оказалась рабочей")
    assert not any(e.subtype == "Тавтология" for e in errs)


# ── сборка check() ───────────────────────────────────────────────────────────
def test_check_filters_spelling_overlapped_by_tsya():
    """«старатся» — одно явление: контекстное правило вытесняет словарное."""
    errs = rc.check("он будет старатся изо всех сил")
    dict_hits = [e for e in errs if e.rule_ref == "RU:SPELL_DICT"]
    assert dict_hits == []
    assert any(e.rule_ref == "RU:TSYA_INF" for e in errs)


def test_check_without_tokens_skips_agreement():
    errs = rc.check("Красивый девушка шла.")
    assert not any(e.rule_ref == "RU:AGREE" for e in errs)
