"""Тесты офлайн-базы правил LanguageTool (analyzer/lt_offline_rules.py)."""
import json
import os

from analyzer import lt_offline_rules as ltx


def test_data_file_present_with_attribution():
    assert os.path.exists(ltx.DATA_PATH)
    data = json.load(open(ltx.DATA_PATH, encoding="utf-8"))
    meta = data["meta"]
    assert "LGPL" in meta["license"]
    assert "languagetool" in meta["attribution"]
    assert meta["rules"] > 150 and meta["replacements"] > 200


def test_rules_compile():
    n_rules, n_reps = ltx.rules_count()
    assert n_rules > 150
    assert n_reps > 200
    assert ltx.data_version() != "нет базы"


def test_known_grammar_rule_fires():
    errs = ltx.check("Встреча назначена на май 20001 года.")
    hit = [e for e in errs if e.rule_ref == "LTX:YEAR_20001"]
    assert hit and hit[0].error_type == "Лексическая"
    assert "20001" in hit[0].fragment
    assert hit[0].fragment in hit[0].context


def test_known_replacement_fires():
    errs = ltx.check("Он решил по идти домой.")
    hit = [e for e in errs if e.rule_ref == "LTX:REPLACE"]
    assert hit and hit[0].suggestion == "→ пойти"
    assert hit[0].error_type == "Орфографическая"


def test_no_unbounded_patterns_imported():
    """Правила с .* дают квадратичный бэктрекинг — их не должно быть в базе."""
    data = json.load(open(ltx.DATA_PATH, encoding="utf-8"))
    for r in data["rules"]:
        for t in r["tokens"]:
            if t["regexp"]:
                assert ".*" not in t["text"] and ".+" not in t["text"], r["id"]


def test_performance_on_large_text():
    import time
    text = "Обычный связный текст без особых ошибок для проверки скорости. " * 400
    t0 = time.time()
    ltx.check(text)
    assert time.time() - t0 < 3.0    # 25К символов — секунды, не минуты


def test_empty_text():
    assert ltx.check("") == []
