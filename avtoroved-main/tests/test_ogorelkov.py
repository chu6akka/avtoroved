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


# ── compare_ogorelkov: сопоставление пары ────────────────────────────────────
def _mini_result(counts: dict, total_words: int, freq: dict | None = None):
    """Синтетический результат движка из {лемма: (категория, вхождения)}."""
    tokens = []
    pos_by_cat = {"частицы": "PART", "личные_местоимения": "PRON",
                  "простые_предлоги": "ADP", "сочинительные_союзы": "CCONJ"}
    for lemma, (cat, n) in counts.items():
        tokens += [_tok(lemma, lemma, pos_by_cat[cat]) for _ in range(n)]
    used = sum(n for _c, n in counts.values())
    tokens += [_tok("дом", "дом", "NOUN") for _ in range(total_words - used)]
    lookup = (lambda l: freq.get(l)) if freq is not None else None
    return og.analyze(tokens, freq_lookup=lookup)


def test_compare_ogorelkov_diffs_and_missing():
    from protocol import comparison as cmp
    freq = {"не": (5, 10000.0, "part"), "я": (10, 20000.0, "spro")}
    a = _mini_result({"не": ("частицы", 10), "я": ("личные_местоимения", 5)},
                     1000, freq)
    b = _mini_result({"не": ("частицы", 4)}, 1000, freq)
    res = cmp.compare_ogorelkov(a, b)

    # Категории: разность ipm A−B считается по обоим текстам.
    cats = {r["category"]: r for r in res["categories"]}
    assert cats["частицы"]["ipm_a"] == pytest.approx(10000.0)
    assert cats["частицы"]["ipm_b"] == pytest.approx(4000.0)
    assert cats["частицы"]["diff_ipm"] == pytest.approx(6000.0)
    # Норма НКРЯ по классу одинакова для обоих текстов.
    assert cats["частицы"]["ipm_rnc"] == cats["частицы"]["ipm_rnc"]

    # Леммы: «я» есть только в A → в B ноль вхождений и прочерк ipm.
    lemmas = {r["lemma"]: r for r in res["lemmas"]}
    assert lemmas["я"]["count_a"] == 5
    assert lemmas["я"]["count_b"] == 0
    assert lemmas["я"]["ipm_b"] is None          # прочерк, не ноль
    assert lemmas["я"]["ratio_b"] is None
    # Сортировка по модулю разности ipm, по убыванию.
    diffs = [abs(r["diff_ipm"]) for r in res["lemmas"]]
    assert diffs == sorted(diffs, reverse=True)
    # Агрегированной меры сходства нет — только наблюдаемые таблицы.
    assert set(res) == {"categories", "lemmas"}


def test_compare_ogorelkov_na_without_freq_dict():
    from protocol import comparison as cmp
    a = _mini_result({"не": ("частицы", 3)}, 100)      # без частотного словаря
    b = _mini_result({"не": ("частицы", 1)}, 100)
    res = cmp.compare_ogorelkov(a, b)
    lem = next(r for r in res["lemmas"] if r["lemma"] == "не")
    assert lem["ipm_rnc"] is None and lem["ratio_a"] is None   # «н/д», не ноль


def test_compare_ogorelkov_none_inputs():
    from protocol import comparison as cmp
    assert cmp.compare_ogorelkov(None, {"categories": {}}) is None


# ── кандидаты признаков ──────────────────────────────────────────────────────
def test_ogorelkov_candidates_categories_and_source():
    from protocol import profile as pf
    freq = {"не": (5, 10000.0, "part")}
    res = _mini_result({"не": ("частицы", 3)}, 1000, freq)
    cands = pf.ogorelkov_candidates(res)
    cat_cands = [c for c in cands if c["source"].count(":") == 1]
    # Кандидат по каждой из 11 категорий.
    assert len(cat_cands) == 11
    part = next(c for c in cat_cands if c["source"] == "ogorelkov:частицы")
    assert part["kind"] == pf.KIND_CANDIDATE
    assert part["subgroup"] == pf.SUB_FUNCTION_WORDS
    assert "вхождений" in part["value"] and "ipm" in part["value"]
    assert "норма НКРЯ по категории" in part["value"]


@pytest.mark.parametrize("count,ipm_rnc,expect_candidate", [
    (5, 2500.0, False),   # коэффициент 5000/2500 = 2.0 — в пределах [0.5; 2.0]
    (5, 1000.0, True),    # коэффициент 5.0 — за пределами, вхождений 5 ≥ 3
    (2, 1000.0, False),   # коэффициент высок, но вхождений 2 < 3 (шум)
])
def test_ogorelkov_lemma_candidate_thresholds(count, ipm_rnc, expect_candidate):
    from protocol import profile as pf
    res = _mini_result({"не": ("частицы", count)}, 1000,
                       {"не": (5, ipm_rnc, "part")})
    cands = pf.ogorelkov_candidates(res)
    lemma_cands = [c for c in cands if c["source"] == "ogorelkov:частицы:не"]
    assert bool(lemma_cands) is expect_candidate
    if expect_candidate:
        c = lemma_cands[0]
        assert "«не»" in c["label"]
        assert c["id_value"] == "высокая"
        assert "коэффициент отклонения" in c["value"]


def test_ogorelkov_candidates_empty_result():
    from protocol import profile as pf
    assert pf.ogorelkov_candidates(None) == []


# ── интеграция с протоколом: профиль документа ───────────────────────────────
def test_profile_saves_ogorelkov_with_document_sha(tmp_path):
    """run_for_document кладёт результат в БД с sha256 материала из ingest."""
    import json as _json
    from protocol import db as protocol_db
    from protocol import profile as pf

    pdb = protocol_db.ProtocolDB(str(tmp_path / "int.db"))
    pid = pdb.create_project("Дело")
    sha = "a" * 64
    did = pdb.add_document(pid, "sporny.txt", protocol_db.ROLE_DISPUTED,
                           file_sha256=sha, word_count=10)
    pdb.save_layers(did, {protocol_db.LAYER_CLEANED:
                          "Я не помню, что и как. Но я не сдался."})

    class _FB:
        def analyze(self, text):
            import re
            pos = {"я": "PRON", "не": "PART", "и": "CCONJ", "но": "CCONJ"}
            return [_tok(m.group(0), m.group(0).lower(),
                         pos.get(m.group(0).lower(), "NOUN"))
                    for m in re.finditer(r"[A-Za-zА-Яа-яЁё]+", text)]

    summary = pf.run_for_document(pdb, pid, did, _FB(), use_lt=False,
                                  program_version="5.0")
    # Результат в слоте сводки и в таблице ogorelkov_results — по sha документа.
    assert summary["ogorelkov"] is not None
    rows = pdb.fetch_ogorelkov_results(sha)
    assert len(rows) == 1
    assert rows[0]["dict_sha256"] == summary["ogorelkov"]["dict_sha256"]
    assert "sporny.txt" in rows[0]["label"]
    saved = _json.loads(rows[0]["results"])
    assert saved["categories"]["личные_местоимения"]["total_count"] == 2

    # Кандидаты служебной лексики попали в карту признаков документа.
    cands = [c for c in pdb.fetch_feature_candidates(did)
             if (c["source"] or "").startswith("ogorelkov:")]
    assert len(cands) >= 11
    assert all(c["kind"] == pf.KIND_CANDIDATE for c in cands)
    # Хеш словаря маркеров зафиксирован в журнале построения профиля.
    entry = next(r for r in pdb.fetch_audit_log(pid)
                 if r["action"] == "построен профиль (раздельное исследование)")
    assert _json.loads(entry["details"])["словарь_Огорелкова_sha256"]


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
