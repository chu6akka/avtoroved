"""Тесты слоя фильтрации детектора (protocol/detector_filter.py)."""
import json

import pytest

from protocol import db as protocol_db
from protocol import detector_filter as df
from protocol import profile as pf


class _Err:
    """Мини-аналог TextError для фильтра."""
    def __init__(self, rule_ref="PUNCT:KOTORY", error_type="Пунктуационная",
                 fragment="пример , фрагмента", subtype="запятая",
                 significance="средняя", source="PUNCT"):
        self.rule_ref = rule_ref
        self.error_type = error_type
        self.fragment = fragment
        self.subtype = subtype
        self.significance = significance
        self.source = source
        self.description = "описание"
        self.context = ""
        self.position = (0, 1)


_CFG = {
    "disabled_rules": ["PUNCT:INTRO"],
    "low_confidence_rules": ["PUNCT:KOTORY"],
    "exception_dictionary": ["ноу-хау", "Universal"],
    "category_defaults": {"Пунктуационная": "низкая", "Орфографическая": "средняя"},
}


# ── отключение правила ───────────────────────────────────────────────────────
def test_disabled_rule_suppressed_and_counted():
    res = df.apply_filter([_Err(rule_ref="PUNCT:INTRO"), _Err()], _CFG)
    assert res.total_in == 2
    assert len(res.kept) == 1
    assert res.suppressed["PUNCT:INTRO"] == 1
    assert res.total_suppressed == 1


# ── словарь исключений ───────────────────────────────────────────────────────
def test_exception_dictionary_suppresses():
    err = _Err(rule_ref="PUNCT:PART_BEFORE",
               fragment="определение ноу-хау в законе")
    res = df.apply_filter([err], _CFG)
    assert len(res.kept) == 0
    assert res.total_suppressed == 1
    # Правило видно в счётчике с пометкой словаря.
    assert any("PUNCT:PART_BEFORE" in k for k in res.suppressed)


def test_exception_dictionary_case_insensitive():
    err = _Err(rule_ref="X", fragment="стандарт UNIVERSAL Dependencies")
    res = df.apply_filter([err], _CFG)
    assert len(res.kept) == 0


# ── пометка низкой надёжности ────────────────────────────────────────────────
def test_low_confidence_rule_marked_low():
    res = df.apply_filter([_Err(rule_ref="PUNCT:KOTORY")], _CFG)
    (err, rel), = res.kept
    assert rel == df.RELIABILITY_LOW


def test_category_default_applied():
    # Правило не в списках → надёжность из category_defaults.
    res = df.apply_filter(
        [_Err(rule_ref="PUNCT:NEW_RULE", error_type="Пунктуационная")], _CFG)
    (_, rel), = res.kept
    assert rel == "низкая"
    res2 = df.apply_filter(
        [_Err(rule_ref="ORFO:X", error_type="Орфографическая")], _CFG)
    (_, rel2), = res2.kept
    assert rel2 == "средняя"


def test_unknown_category_defaults_medium():
    res = df.apply_filter([_Err(rule_ref="R", error_type="Неизвестная")], _CFG)
    (_, rel), = res.kept
    assert rel == df.RELIABILITY_MEDIUM


# ── конфиг ───────────────────────────────────────────────────────────────────
def test_load_real_config_and_hash():
    cfg, h = df.load_config()
    assert "PUNCT:INTRO" in cfg["disabled_rules"]
    assert len(h) == 12
    # Хэш стабилен при повторной загрузке.
    _, h2 = df.load_config()
    assert h == h2


def test_load_missing_config():
    cfg, h = df.load_config("нет/такого/файла.json")
    assert cfg == {}
    assert h == "нет-конфига"
    # Пустой конфиг ничего не фильтрует.
    res = df.apply_filter([_Err()], cfg)
    assert len(res.kept) == 1


# ── интеграция: фильтр в run_for_document, журнал, надёжность в БД ───────────
@pytest.fixture()
def pdb(tmp_path):
    return protocol_db.ProtocolDB(str(tmp_path / "filt.db"))


def _fake_backend():
    from analyzer.stanza_backend import TokenInfo
    import re

    class FB:
        def analyze(self, text):
            return [TokenInfo(m.group(0), m.group(0).lower(), "NOUN",
                              "Существительное", "—",
                              char_start=m.start(), char_end=m.end(), sent_id=0)
                    for m in re.finditer(r"[A-Za-zА-Яа-яЁё]+", text)]
    return FB()


def test_run_for_document_filters_and_logs(pdb, monkeypatch):
    from analyzer import punct_checker

    fake_errors = [
        _Err(rule_ref="PUNCT:INTRO"),      # отключено конфигом → подавлено
        _Err(rule_ref="PUNCT:KOTORY"),     # низкая надёжность
        _Err(rule_ref="PUNCT:OTHER",       # дефолт категории: пунктуация → низкая
             error_type="Пунктуационная"),
    ]
    monkeypatch.setattr(punct_checker, "check_with_tokens",
                        lambda text, tokens: list(fake_errors))

    pid = pdb.create_project("Дело")
    did = pdb.add_document(pid, "d.txt", protocol_db.ROLE_SAMPLE,
                           file_sha256="h", provenance="рукопись", word_count=50)
    pdb.save_layers(did, {protocol_db.LAYER_CLEANED:
                          "Первое предложение. Второе предложение снова."})

    summary = pf.run_for_document(pdb, pid, did, _fake_backend(), use_lt=False)

    # Подавленное правило учтено, из 3 срабатываний осталось 2.
    assert summary["detector_total"] == 3
    assert summary["suppressed"].get("PUNCT:INTRO") == 1
    assert summary["filter_hash"]

    # Кандидаты в БД: 2 оставленных («низкая») + 1 подавленный (сохранён
    # для воспроизводимости с пометкой «подавлен»).
    # Только кандидаты детектора ошибок (прочие языковые кандидаты — служебная
    # лексика, интернет-маркеры и т.п. — к этому тесту отношения не имеют).
    rows = [r for r in pdb.fetch_feature_candidates(did)
            if r["kind"] == pf.KIND_CANDIDATE
            and r["subgroup"] in (pf.SUB_ORTHOGRAPHIC, pf.SUB_PUNCTUATION)]
    kept = [r for r in rows if r["reliability"] != "подавлен"]
    supp = [r for r in rows if r["reliability"] == "подавлен"]
    assert len(kept) == 2
    assert all(r["reliability"] == "низкая" for r in kept)
    assert len(supp) == 1
    assert "подавлен фильтром" in supp[0]["value"]
    # Подавленные не попадают в карту признаков.
    from protocol import feature_map as fmod
    pairs = fmod.candidates_with_state(pdb, did)
    assert all((c["reliability"] or "") != "подавлен" for c, _f in pairs)

    # Журнал: версии и счётчики подавленных.
    log = pdb.fetch_audit_log(pid)
    entry = next(r for r in log
                 if r["action"] == "построен профиль (раздельное исследование)")
    details = json.loads(entry["details"])
    assert details["подавлено_всего"] == 1
    assert details["подавлено_по_правилам"]["PUNCT:INTRO"] == 1
    assert details["фильтр_конфиг_hash"] == summary["filter_hash"]
    assert details["версия_правил_пунктуации"]           # версия правил пишется
    assert "languagetool" in details                      # режим LT фиксируется


def test_autocorrect_still_downgrades(pdb, monkeypatch):
    """Флаг автокоррекции из suitability понижает надёжность даже средних."""
    from analyzer import punct_checker
    monkeypatch.setattr(
        punct_checker, "check_with_tokens",
        lambda text, tokens: [_Err(rule_ref="ORFO:X", error_type="Орфографическая")])

    pid = pdb.create_project("Дело")
    did = pdb.add_document(pid, "d.txt", protocol_db.ROLE_SAMPLE,
                           file_sha256="h", provenance="цифровой", word_count=50)
    pdb.save_layers(did, {protocol_db.LAYER_CLEANED: "Текст тут есть."})
    pdb.save_suitability(
        pid, verdict="пригоден_с_ограничениями", blocks_strong_conclusion=True,
        document_id=did,
        flags=[{"code": "автокоррекция", "level": "ограничение", "message": "…"}],
        metrics={})

    pf.run_for_document(pdb, pid, did, _fake_backend(), use_lt=False)
    rows = [r for r in pdb.fetch_feature_candidates(did)
            if r["kind"] == pf.KIND_CANDIDATE and r["subgroup"] == pf.SUB_ORTHOGRAPHIC]
    assert rows and all(r["reliability"] == "низкая" for r in rows)
