"""Тесты стадии «оценка пригодности» (protocol/suitability.py)."""
import json

import pytest

from protocol import db as protocol_db
from protocol import suitability as su


def make_doc(**kw) -> dict:
    """Документ-заглушка с разумными значениями «пригоден» по умолчанию."""
    base = {
        "id": 1, "filename": "doc.txt", "role": protocol_db.ROLE_SAMPLE,
        "provenance": "рукопись", "genre": "письмо",
        "word_count": 200, "sentence_count": 15, "token_count": 220,
        "text": ("Это первое связное предложение для проверки. "
                 "Второе предложение отличается по содержанию. "
                 "Третья мысль завершает короткий абзац."),
    }
    base.update(kw)
    return base


# ── вердикт «пригоден» как базовый случай ────────────────────────────────────
def test_clean_document_is_fit():
    verdict, flags, metrics, blocks = su.evaluate_document(make_doc())
    assert verdict == su.VERDICT_FIT
    assert flags == []
    assert blocks is False


# ── флаг: извлечение пусто → непригоден ──────────────────────────────────────
def test_empty_extraction_is_unfit():
    verdict, flags, _, blocks = su.evaluate_document(
        make_doc(word_count=0, sentence_count=0, token_count=0, text=""))
    assert verdict == su.VERDICT_UNFIT
    assert blocks is True
    assert any(f["code"] == "извлечение" and f["level"] == su.LEVEL_UNFIT for f in flags)


# ── флаг: малый объём → пригоден_с_ограничениями ─────────────────────────────
def test_small_volume_is_limited():
    verdict, flags, _, blocks = su.evaluate_document(
        make_doc(word_count=50, sentence_count=6, token_count=60))
    assert verdict == su.VERDICT_LIMITED
    assert blocks is True
    assert any(f["code"] == "малый_объём" for f in flags)


def test_volume_below_reliable_flag():
    _, flags, _, _ = su.evaluate_document(make_doc(word_count=120))
    assert any(f["code"] == "объём_ненадёжный" for f in flags)


def test_few_sentences_flag():
    _, flags, _, _ = su.evaluate_document(make_doc(sentence_count=5))
    assert any(f["code"] == "мало_предложений" for f in flags)


# ── флаг: цитаты ─────────────────────────────────────────────────────────────
def test_quotes_flag():
    quoted = "«" + ("чужой текст " * 30) + "»"
    _, flags, metrics, _ = su.evaluate_document(make_doc(text=quoted + " свой."))
    assert metrics["quote_share"] >= su.QUOTE_SHARE_FLAG
    assert any(f["code"] == "цитаты" for f in flags)


# ── флаг: повторы ────────────────────────────────────────────────────────────
def test_repeats_flag():
    repeated = "Одно и то же предложение повторяется. " * 5
    _, flags, metrics, _ = su.evaluate_document(make_doc(text=repeated))
    assert metrics["repeat_share"] >= su.REPEAT_SHARE_FLAG
    assert any(f["code"] == "повторы" for f in flags)


# ── флаг: автокоррекция по происхождению ─────────────────────────────────────
@pytest.mark.parametrize("prov", ["цифровой", "опубликованный"])
def test_autocorrect_flag(prov):
    _, flags, _, _ = su.evaluate_document(make_doc(provenance=prov))
    assert any(f["code"] == "автокоррекция" for f in flags)


# ── флаг: устная речь (по происхождению и по маркерам) ───────────────────────
def test_oral_speech_by_provenance():
    _, flags, _, _ = su.evaluate_document(
        make_doc(provenance="расшифровка_устной_речи"))
    assert any(f["code"] == "устная_речь" for f in flags)


def test_oral_speech_by_markers():
    _, flags, metrics, _ = su.evaluate_document(
        make_doc(text="Ну ээ вот это самое, я хотел сказать. " * 5))
    assert metrics["oral_markers"] > 0
    assert any(f["code"] == "устная_речь" for f in flags)


# ── пара: сопоставимость ─────────────────────────────────────────────────────
def test_pair_genre_mismatch():
    a = make_doc(id=1, role=protocol_db.ROLE_DISPUTED, genre="письмо")
    b = make_doc(id=2, role=protocol_db.ROLE_SAMPLE, genre="статья")
    verdict, flags, _, blocks = su.evaluate_pair(a, b)
    assert verdict == su.VERDICT_LIMITED and blocks is True
    assert any(f["code"] == "несопоставимость_жанр" for f in flags)


def test_pair_provenance_mismatch():
    a = make_doc(id=1, provenance="рукопись")
    b = make_doc(id=2, provenance="цифровой")
    _, flags, _, _ = su.evaluate_pair(a, b)
    assert any(f["code"] == "несопоставимость_форма" for f in flags)


def test_pair_style_mismatch():
    a = make_doc(id=1, word_count=200, sentence_count=20)   # awl 10
    b = make_doc(id=2, word_count=500, sentence_count=20)   # awl 25
    _, flags, _, _ = su.evaluate_pair(a, b)
    assert any(f["code"] == "несопоставимость_стиль" for f in flags)


def test_pair_comparable_is_fit():
    a = make_doc(id=1, genre="письмо", provenance="рукопись",
                 word_count=200, sentence_count=20)
    b = make_doc(id=2, genre="письмо", provenance="рукопись",
                 word_count=210, sentence_count=20)
    verdict, flags, _, blocks = su.evaluate_pair(a, b)
    assert verdict == su.VERDICT_FIT and flags == [] and blocks is False


# ── знаменательные словоформы (методический минимум) ────────────────────────
def test_sample_below_significant_minimum_flagged():
    """Образец с 500 знаменательных словоформ — ниже минимума 600 → флаг."""
    verdict, flags, metrics, blocks = su.evaluate_document(
        make_doc(role=protocol_db.ROLE_SAMPLE, significant_count=500))
    assert any(f["code"] == "объём_знаменательных" for f in flags)
    assert verdict == su.VERDICT_LIMITED and blocks is True
    assert metrics["significant_count"] == 500


def test_sample_at_significant_minimum_ok():
    _, flags, _, _ = su.evaluate_document(
        make_doc(role=protocol_db.ROLE_SAMPLE,
                 significant_count=su.MIN_SIGNIFICANT_SAMPLE))
    assert not any(f["code"] == "объём_знаменательных" for f in flags)


def test_disputed_threshold_is_lower():
    """Для спорного текста минимум 100, а не 600."""
    _, flags_ok, _, _ = su.evaluate_document(
        make_doc(role=protocol_db.ROLE_DISPUTED, significant_count=150))
    assert not any(f["code"] == "объём_знаменательных" for f in flags_ok)
    _, flags_low, _, _ = su.evaluate_document(
        make_doc(role=protocol_db.ROLE_DISPUTED, significant_count=99))
    assert any(f["code"] == "объём_знаменательных" for f in flags_low)


def test_no_parse_flag_when_tokens_missing():
    """Есть текст, но нет NLP-разметки → флаг «нет_разметки», а не ложный недобор."""
    _, flags, _, _ = su.evaluate_document(
        make_doc(token_count=0, significant_count=0))
    assert any(f["code"] == "нет_разметки" for f in flags)
    assert not any(f["code"] == "объём_знаменательных" for f in flags)


def test_count_tokens_by_pos(tmp_path):
    pdb = protocol_db.ProtocolDB(str(tmp_path / "pos.db"))
    pid = pdb.create_project("Дело")
    did = pdb.add_document(pid, "a.txt", protocol_db.ROLE_SAMPLE, file_sha256="h")
    pdb.save_parsed(did, [{
        "idx": 0, "start_char": None, "end_char": None, "text": "Кот спит тихо.",
        "tokens": [
            {"idx": 0, "text": "Кот", "pos": "NOUN"},
            {"idx": 1, "text": "спит", "pos": "VERB"},
            {"idx": 2, "text": "тихо", "pos": "ADV"},
            {"idx": 3, "text": "и", "pos": "CCONJ"},
            {"idx": 4, "text": ".", "pos": "PUNCT"},
        ]}])
    assert pdb.count_tokens_by_pos(did, su.SIGNIFICANT_POS) == 3


# ── интеграция: run_for_project пишет в БД и журнал ──────────────────────────
@pytest.fixture()
def pdb(tmp_path):
    return protocol_db.ProtocolDB(str(tmp_path / "su.db"))


def _populate_doc(pdb, pid, role, provenance, word_count, n_sent, with_parse):
    did = pdb.add_document(pid, f"{role}.txt", role, file_sha256="h",
                           provenance=provenance, genre="письмо",
                           word_count=word_count)
    if with_parse:
        pdb.save_layers(did, {protocol_db.LAYER_CLEANED: "связный текст тут."})
        sents = [{"idx": i, "start_char": None, "end_char": None,
                  "text": "связный текст тут.",
                  "tokens": [{"idx": 0, "text": "связный"}, {"idx": 1, "text": "текст"}]}
                 for i in range(n_sent)]
        pdb.save_parsed(did, sents)
    return did


def test_run_for_project_writes_db_and_log(pdb):
    pid = pdb.create_project("Дело")
    # Нормальный образец (цифровой → автокоррекция = ограничение).
    _populate_doc(pdb, pid, protocol_db.ROLE_SAMPLE, "цифровой", 200, 15, with_parse=True)
    # Спорный без разметки → 0 токенов → непригоден.
    _populate_doc(pdb, pid, protocol_db.ROLE_DISPUTED, "рукопись", 0, 0, with_parse=False)

    result = su.run_for_project(pdb, pid, program_version="5.0")
    assert len(result["documents"]) == 2
    assert len(result["pairs"]) == 1  # 1 спорный × 1 образец

    rows = pdb.fetch_suitability(pid)
    verdicts = {r["verdict"] for r in rows}
    assert su.VERDICT_UNFIT in verdicts          # пустой спорный
    assert su.VERDICT_LIMITED in verdicts        # автокоррекция/пара
    assert all(r["created_at"] for r in rows)

    # blocks_strong_conclusion проставлен у непригодного.
    unfit = [r for r in rows if r["verdict"] == su.VERDICT_UNFIT]
    assert unfit and unfit[0]["blocks_strong_conclusion"] == 1

    # Журнал содержит записи об оценке пригодности.
    actions = [r["action"] for r in pdb.fetch_audit_log(pid)]
    assert "оценка пригодности" in actions
    assert "оценка пригодности (пара)" in actions


def test_run_for_project_is_idempotent(pdb):
    pid = pdb.create_project("Дело")
    _populate_doc(pdb, pid, protocol_db.ROLE_SAMPLE, "рукопись", 200, 15, with_parse=True)
    su.run_for_project(pdb, pid)
    su.run_for_project(pdb, pid)
    # Повторный пересчёт очищает прежние строки — без дублей.
    rows = pdb.fetch_suitability(pid)
    assert len(rows) == 1
