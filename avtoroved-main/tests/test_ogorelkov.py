"""Тесты модуля «Служебная лексика (Огорелков)» (analyzer/ogorelkov_engine.py)."""
import pytest

from analyzer import ogorelkov_engine as og
from analyzer.stanza_backend import TokenInfo


def _tok(text, lemma, pos, sent_id=0):
    return TokenInfo(text=text, lemma=lemma, pos=pos, pos_label=pos, feats="—",
                     sent_id=sent_id)


# ── 1. Словарь: 11 категорий, точные составы ─────────────────────────────────
def test_dictionary_categories_and_counts():
    markers, sha = og.load_marker_dict()
    assert len(sha) == 64
    expected = {
        "личные_местоимения": 8,
        "притяжательные_местоимения": 5,
        "указательные_местоимения": 3,
        "неопределённые_местоимения": 9,
        "отрицательные_местоимения": 11,
        "сочинительные_союзы": 11,
        "подчинительные_союзы": 15,
        "простые_предлоги": 22,
        "производные_предлоги": 15,
        "частицы": 24,
        "вводные_слова": 17,
    }
    assert {k: len(v) for k, v in markers.items()} == expected


# ── 2. Формула ipm ───────────────────────────────────────────────────────────
def test_ipm_formula_on_synthetic_text():
    """1000 словоупотреблений, «не» (PART) ровно 7 раз → ipm = 7000."""
    tokens = [_tok("не", "не", "PART") for _ in range(7)]
    tokens += [_tok("слово", "слово", "NOUN") for _ in range(993)]
    res = og.analyze(tokens)
    assert res["total_words"] == 1000
    ne = res["categories"]["частицы"]["lemmas"]["не"]
    assert ne["count"] == 7
    assert ne["ipm_text"] == pytest.approx(7000.0)
    # Агрегат категории: «использовано 1 из 24 лемм».
    cat = res["categories"]["частицы"]
    assert cat["used"] == 1 and cat["total_lemmas"] == 24
    assert cat["share_pct"] == pytest.approx(0.7)


# ── 3. Снятие омонимии по POS ────────────────────────────────────────────────
def test_pos_disambiguation_chto():
    """«Что ты сказал, что уходишь?»: что-PRON не союз, что-SCONJ — союз."""
    tokens = [
        _tok("Что", "что", "PRON"), _tok("ты", "ты", "PRON"),
        _tok("сказал", "сказать", "VERB"),
        _tok("что", "что", "SCONJ"), _tok("уходишь", "уходить", "VERB"),
    ]
    res = og.analyze(tokens)
    sconj = res["categories"]["подчинительные_союзы"]["lemmas"]
    assert sconj.get("что", {}).get("count") == 1     # только SCONJ-вхождение


def test_pos_disambiguation_da_and_tak():
    tokens = [
        _tok("да", "да", "CCONJ"),      # союз «да» = «и»
        _tok("да", "да", "PART"),       # частица «да»... в словаре частиц «да» нет
        _tok("так", "так", "PART"),     # частица
        _tok("так", "так", "ADV"),      # наречие — не частица
    ]
    res = og.analyze(tokens)
    assert res["categories"]["сочинительные_союзы"]["lemmas"]["да"]["count"] == 1
    assert res["categories"]["частицы"]["lemmas"]["так"]["count"] == 1


# ── 4. Биграмма «несмотря на» ────────────────────────────────────────────────
def test_bigram_nesmotrya_na():
    tokens = [
        _tok("Несмотря", "несмотря", "SCONJ"), _tok("на", "на", "ADP"),
        _tok("дождь", "дождь", "NOUN"),
        _tok("на", "на", "ADP"), _tok("стол", "стол", "NOUN"),
    ]
    res = og.analyze(tokens)
    deriv = res["categories"]["производные_предлоги"]["lemmas"]
    assert deriv["несмотря на"]["count"] == 1
    # Обычное «на» при этом считается простым предлогом (2 вхождения).
    assert res["categories"]["простые_предлоги"]["lemmas"]["на"]["count"] == 2


def test_bigram_not_across_sentences():
    tokens = [_tok("несмотря", "несмотря", "SCONJ", sent_id=0),
              _tok("на", "на", "ADP", sent_id=1)]
    res = og.analyze(tokens)
    assert "несмотря на" not in res["categories"]["производные_предлоги"]["lemmas"]


# ── 5. Воспроизводимость: два прогона идентичны, хеш словаря в аудите ────────
def test_reproducibility_and_audit(tmp_path):
    import hashlib
    import json as _json
    from protocol import db as protocol_db
    pdb = protocol_db.ProtocolDB(str(tmp_path / "og.db"))

    tokens = [_tok("я", "я", "PRON"), _tok("не", "не", "PART"),
              _tok("спал", "спать", "VERB")]
    r1 = og.analyze(tokens)
    r2 = og.analyze(tokens)
    assert r1 == r2                                   # идентичные результаты
    assert r1["dict_sha256"] == r2["dict_sha256"]     # один хеш словаря

    text_sha = hashlib.sha256("я не спал".encode()).hexdigest()
    pdb.save_ogorelkov_result(text_sha, r1["dict_sha256"], r1["total_words"],
                              r1, label="тест", program_version="5.0")
    rows = pdb.fetch_ogorelkov_results(text_sha)
    assert len(rows) == 1
    assert rows[0]["dict_sha256"] == r1["dict_sha256"]
    saved = _json.loads(rows[0]["results"])
    assert saved["total_words"] == 3
    # Append-only аудит: хеш словаря зафиксирован в журнале.
    log = pdb.fetch_audit_log(None)
    entry = next(r for r in log
                 if r["action"] == "служебная лексика (Огорелков): расчёт")
    details = _json.loads(entry["details"])
    assert details["словарь_sha256"] == r1["dict_sha256"]


# ── ipm НКРЯ и «н/д» ─────────────────────────────────────────────────────────
def test_rnc_ipm_and_na():
    tokens = [_tok("я", "я", "PRON"), _tok("слово", "слово", "NOUN")]
    def lookup(lemma):
        return {"я": (10, 20000.0, "spro")}.get(lemma)
    res = og.analyze(tokens, freq_lookup=lookup)
    ya = res["categories"]["личные_местоимения"]["lemmas"]["я"]
    assert ya["ipm_rnc"] == 20000.0
    assert ya["ratio"] == pytest.approx(round(ya["ipm_text"] / 20000.0, 2))
    # Леммы нет в словаре → н/д (None), не ноль.
    res2 = og.analyze(tokens, freq_lookup=lambda l: None)
    assert res2["categories"]["личные_местоимения"]["lemmas"]["я"]["ipm_rnc"] is None
    assert res2["categories"]["личные_местоимения"]["lemmas"]["я"]["ratio"] is None
