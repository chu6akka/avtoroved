"""Тесты стадии «раздельное исследование» (protocol/profile.py)."""
import pytest

from protocol import db as protocol_db
from protocol import profile as pf


# ── чистые сборщики ──────────────────────────────────────────────────────────
class _FakeDomain:
    def __init__(self):
        self.label = "Право"
        self.cosine = 0.42
        self.match_count = 7
        self.examples = ["закон", "договор"]


class _FakeThematic:
    top_domains = [_FakeDomain()]


def test_semantic_candidates_low_id_value():
    out = pf.semantic_candidates(_FakeThematic())
    assert len(out) == 1
    c = out[0]
    assert c["group_name"] == pf.GROUP_SEMANTIC
    assert c["id_value"] == "низкая"          # тема ≠ автор
    assert "Право" in c["label"]
    assert c["source"] == "thematic_engine"


def test_textological_counters():
    metrics = {"дополнительно": {
        "Всего слов": 120, "Всего предложений": 9,
        "Средняя длина предложения (слов)": 13.3,
        "Дисперсия длины предложений": 4.2}}
    text = "Первый абзац из нескольких слов.\n\nВторой абзац тоже есть."
    out = pf.textological_candidates(metrics, text)
    labels = {c["label"]: c for c in out}
    assert labels["Число абзацев"]["value"] == "2"
    assert all(c["kind"] == pf.KIND_COUNTER for c in out)
    assert all(c["group_name"] == pf.GROUP_TEXTOLOGICAL for c in out)


class _FakeStratToken:
    def __init__(self, surface, lemma, layer, context=""):
        self.surface, self.lemma, self.layer, self.context = surface, lemma, layer, context


class _FakeStrat:
    layer_counts = {"разговорная": 3, "жаргон": 1}
    layer_words = {"разговорная": ["чуток", "малость"], "жаргон": ["движуха"]}
    marked_ratio = 0.05
    tokens = [_FakeStratToken("движуха", "движуха", "жаргон", "вся эта движуха вокруг")]


def test_lexical_candidates_with_strat():
    metrics = {"дополнительно": {"Лексическое разнообразие (TTR)": 0.61,
                                 "Доля hapax-лемм": 0.44}}
    out = pf.lexical_candidates(metrics, _FakeStrat())
    labels = [c["label"] for c in out]
    assert "Лексическое разнообразие (TTR)" in labels
    assert any("разговорная" in l for l in labels)
    assert any("Доля нелитературной лексики" in l for l in labels)
    assert all(c["subgroup"] == pf.SUB_LEXICAL for c in out)


def test_syntactic_sentence_types():
    metrics = {"частоты": {"Существительное": {"количество": 10, "коэффициент": 0.3}}}
    text = "Это утверждение. А это вопрос? И восклицание! И недосказанность…"
    out = pf.syntactic_candidates(metrics, text)
    labels = {c["label"]: c["value"] for c in out}
    assert labels["Вопросительные предложения"] == "1"
    assert labels["Восклицательные предложения"] == "1"
    assert labels["Предложения с многоточием"] == "1"
    assert any(l.startswith("Доля POS") for l in labels)


# ── кандидаты ошибок: требование проверки и ненадёжность ─────────────────────
class _FakeError:
    def __init__(self, error_type="Пунктуационная", subtype="запятая",
                 significance="высокая"):
        self.error_type = error_type
        self.subtype = subtype
        self.fragment = "текст , с ошибкой"
        self.description = "лишний пробел перед запятой"
        self.position = (5, 6)
        self.source = "PUNCT"
        self.context = "…текст , с ошибкой…"
        self.significance = significance
        self.rule_ref = "PUNCT:TEST"


def test_error_candidates_default_needs_review():
    out = pf.error_candidates([_FakeError()], autocorrect_unreliable=False)
    assert len(out) == 1
    c = out[0]
    assert c["kind"] == pf.KIND_CANDIDATE
    assert pf.NOTE_NEEDS_REVIEW in c["value"]
    assert pf.NOTE_UNRELIABLE_AUTOCORRECT not in c["value"]
    assert c["subgroup"] == pf.SUB_PUNCTUATION
    assert c["id_value"] == "высокая"
    assert c["fragment"]


def test_error_candidates_unreliable_with_autocorrect():
    out = pf.error_candidates(
        [_FakeError("Орфографическая", "тся/ться")], autocorrect_unreliable=True)
    c = out[0]
    assert pf.NOTE_UNRELIABLE_AUTOCORRECT in c["value"]
    assert c["subgroup"] == pf.SUB_ORTHOGRAPHIC
    assert c["reliability"] == "низкая"    # автокоррекция понижает надёжность


def test_error_candidates_reliability_passthrough():
    out = pf.error_candidates([_FakeError()], autocorrect_unreliable=False,
                              reliabilities=["низкая"])
    assert out[0]["reliability"] == "низкая"


def test_psycho_candidates_minimal_no_interpretation():
    out = pf.psycho_candidates(_FakeStrat())
    assert len(out) == 1
    c = out[0]
    assert c["group_name"] == pf.GROUP_PSYCHO
    assert c["kind"] == pf.KIND_CANDIDATE
    assert "эксперту" in c["value"]     # интерпретация остаётся эксперту
    assert c["id_value"] == ""          # автоматической оценки нет


# ── общие признаки: степени развития навыков (уровень НН) ───────────────────
def test_general_skill_candidates_five_rows():
    """4 навыка + общий уровень; формат value парсится стадией сравнения."""
    errors = [_FakeError("Орфографическая", f"тип{i}") for i in range(3)]
    out = pf.general_skill_candidates(errors, total_words=200)
    assert len(out) == 5
    assert all(c["kind"] == pf.KIND_GENERAL for c in out)
    assert all(c["group_name"] == pf.GROUP_LINGUISTIC for c in out)
    by_sub = {c["subgroup"]: c for c in out}
    assert set(by_sub) == set(pf.GENERAL_SKILLS) | {pf.GENERAL_OVERALL_SUBGROUP}
    # 3 уникальных орфографических ошибки на 200 словоформ → высокая (<4).
    orf = by_sub["орфографический"]
    assert orf["value"].startswith("высокая · 3.0 ош./200 сл.")
    # Навык без ошибок — высокая, 0 ошибок.
    assert by_sub["грамматический"]["value"].startswith("высокая · 0.0")
    # Общий уровень суммирует все категории.
    assert by_sub[pf.GENERAL_OVERALL_SUBGROUP]["value"].endswith("уникальных 3")


def test_general_skill_scale_boundaries():
    """Шкала Рубцовой с.13: средняя 4–6, низкая >6 (на 200 словоформ)."""
    errs = [_FakeError("Пунктуационная", f"т{i}") for i in range(5)]
    out = pf.general_skill_candidates(errs, total_words=200)
    punct = next(c for c in out if c["subgroup"] == "пунктуационный")
    assert punct["value"].startswith("средняя")
    errs = [_FakeError("Пунктуационная", f"т{i}") for i in range(7)]
    out = pf.general_skill_candidates(errs, total_words=200)
    punct = next(c for c in out if c["subgroup"] == "пунктуационный")
    assert punct["value"].startswith("низкая")


def test_general_skill_autocorrect_lowers_reliability():
    """При автокоррекции орф./пункт. ненадёжны; грамм./лекс.-фраз. — нет."""
    out = pf.general_skill_candidates([], total_words=200,
                                      autocorrect_unreliable=True)
    by_sub = {c["subgroup"]: c for c in out}
    assert by_sub["орфографический"].get("reliability") == "низкая"
    assert by_sub["пунктуационный"].get("reliability") == "низкая"
    assert by_sub["грамматический"].get("reliability", "") == ""
    assert by_sub["лексико-фразеологический"].get("reliability", "") == ""


def test_general_skill_empty_text():
    assert pf.general_skill_candidates([_FakeError()], total_words=0) == []


def test_general_skill_lt_unused_marks_detector_set():
    """Без LT каждый общий признак несёт пометку состава детекторов —
    сравнение по ней ловит асимметрию; надёжность не занижается (есть
    собственные офлайн-детекторы ru_checker)."""
    out = pf.general_skill_candidates([], total_words=200, lt_used=False)
    for c in out:
        assert pf.NOTE_LT_UNUSED in c["value"], c["subgroup"]
        assert c.get("reliability", "") == ""
    # Формат value остаётся парсируемым для стадии сравнения.
    from protocol import comparison as cmp
    assert cmp.parse_general_rate(out[0]["value"]) == 0.0
    # С LT пометки нет.
    out_lt = pf.general_skill_candidates([], total_words=200, lt_used=True)
    assert all(pf.NOTE_LT_UNUSED not in c["value"] for c in out_lt)


def test_error_candidates_unknown_type_goes_to_other():
    """Неопознанный тип ошибки (категория LT вне маппинга) → подгруппа
    «прочие», а не «орфографические» — корзина орф+пункт не искажается."""
    err = _FakeError(error_type="LanguageTool", subtype="misc")
    out = pf.error_candidates([err], autocorrect_unreliable=False)
    assert out[0]["subgroup"] == pf.SUB_OTHER
    from protocol import comparison as cmp
    assert cmp.bucket_of("языковые", pf.SUB_OTHER) is None


def test_build_profile_includes_general_skills():
    profile = pf.build_profile("Первое предложение здесь. Второе тоже тут.",
                               metrics={}, errors=[_FakeError()])
    kinds = {c["kind"] for c in profile}
    assert pf.KIND_GENERAL in kinds
    generals = [c for c in profile if c["kind"] == pf.KIND_GENERAL]
    assert len(generals) == 5


# ── запись профиля в БД и журнал ─────────────────────────────────────────────
@pytest.fixture()
def pdb(tmp_path):
    return protocol_db.ProtocolDB(str(tmp_path / "prof.db"))


def _fake_backend():
    from analyzer.stanza_backend import TokenInfo

    class FB:
        def analyze(self, text):
            import re
            toks = []
            for sid, m in enumerate(re.finditer(r"[A-Za-zА-Яа-яЁё]+", text)):
                toks.append(TokenInfo(
                    text=m.group(0), lemma=m.group(0).lower(),
                    pos="NOUN", pos_label="Существительное", feats="—",
                    char_start=m.start(), char_end=m.end(), sent_id=0))
            return toks
    return FB()


def _make_doc(pdb, pid, provenance="рукопись"):
    did = pdb.add_document(pid, "doc.txt", protocol_db.ROLE_SAMPLE,
                           file_sha256="h", provenance=provenance,
                           genre="письмо", word_count=30)
    pdb.save_layers(did, {
        protocol_db.LAYER_CLEANED:
            "Первое предложение о разном.\n\nВторой абзац про закон и договор."})
    return did


def test_run_for_document_writes_profile_and_log(pdb):
    pid = pdb.create_project("Дело")
    did = _make_doc(pdb, pid)
    summary = pf.run_for_document(pdb, pid, did, _fake_backend(), use_lt=False,
                                  program_version="5.0")
    assert summary["count"] > 0
    rows = pdb.fetch_feature_candidates(did)
    assert len(rows) == summary["count"]
    groups = {r["group_name"] for r in rows}
    # Как минимум текстологические и языковые всегда строятся.
    assert pf.GROUP_TEXTOLOGICAL in groups
    assert pf.GROUP_LINGUISTIC in groups
    # Обязательные поля заполнены.
    assert all(r["kind"] in (pf.KIND_COUNTER, pf.KIND_CANDIDATE,
                             pf.KIND_GENERAL) for r in rows)
    assert all(r["source"] for r in rows)
    assert all(r["created_at"] for r in rows)
    # Журнал.
    actions = [r["action"] for r in pdb.fetch_audit_log(pid)]
    assert "построен профиль (раздельное исследование)" in actions


def test_run_for_document_idempotent(pdb):
    pid = pdb.create_project("Дело")
    did = _make_doc(pdb, pid)
    pf.run_for_document(pdb, pid, did, _fake_backend(), use_lt=False)
    n1 = len(pdb.fetch_feature_candidates(did))
    pf.run_for_document(pdb, pid, did, _fake_backend(), use_lt=False)
    n2 = len(pdb.fetch_feature_candidates(did))
    assert n1 == n2   # пересборка без дублей


def test_autocorrect_flag_from_suitability(pdb):
    """Флаг автокоррекции из 2А помечает кандидатов ошибок ненадёжными."""
    pid = pdb.create_project("Дело")
    did = _make_doc(pdb, pid, provenance="цифровой")
    # Стадия 2А поставила флаг автокоррекции.
    pdb.save_suitability(
        pid, verdict="пригоден_с_ограничениями", blocks_strong_conclusion=True,
        document_id=did,
        flags=[{"code": "автокоррекция", "level": "ограничение", "message": "…"}],
        metrics={})
    assert pf.has_autocorrect_flag(pdb, pid, did) is True
    summary = pf.run_for_document(pdb, pid, did, _fake_backend(), use_lt=False)
    assert summary["autocorrect_unreliable"] is True
