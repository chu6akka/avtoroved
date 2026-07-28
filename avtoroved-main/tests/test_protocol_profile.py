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
    tokens = [
        _FakeStratToken("движуха", "движуха", "common_jargon", "вся эта движуха вокруг"),
        _FakeStratToken("хрень", "хрень", "obscene", "какая-то хрень"),
    ]


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


class _FakeSkill:
    def __init__(self, name, level="средняя", rate=5.0):
        self.skill_name = name
        self.level = level
        self.error_rate = rate


def test_general_skill_candidates():
    skills = [_FakeSkill("Орфографический навык", rate=2.0),
              _FakeSkill("Грамматический навык", rate=7.5),
              _FakeSkill("Стилистический навык")]     # не входит в общие признаки
    out = pf.general_skill_candidates(skills, "средняя", "описание уровня",
                                      autocorrect_unreliable=False)
    subs = {c["subgroup"]: c for c in out}
    assert set(subs) == {"орфографический", "грамматический", "общий_уровень"}
    assert "7.5 ошибок/200" in subs["грамматический"]["value"]
    # Решающие навыки Вула — высокая идентификационная ценность.
    assert subs["грамматический"]["id_value"] == "высокая"
    assert subs["орфографический"]["id_value"] == "средняя"
    assert all(c["kind"] == pf.KIND_GENERAL for c in out)


def test_general_skill_candidates_autocorrect_downgrade():
    skills = [_FakeSkill("Орфографический навык"),
              _FakeSkill("Грамматический навык")]
    out = pf.general_skill_candidates(skills, "", "", autocorrect_unreliable=True)
    subs = {c["subgroup"]: c for c in out}
    # Орфография ненадёжна при автокоррекции, грамматика — нет.
    assert subs["орфографический"]["reliability"] == "низкая"
    assert "ненадёжен" in subs["орфографический"]["value"]
    assert subs["грамматический"].get("reliability", "") != "низкая"


def test_psycho_candidates_minimal_no_interpretation():
    out = pf.psycho_candidates(_FakeStrat())
    # Только эмоционально-экспрессивные слои (obscene) — жаргон уходит
    # в лексические маркеры, без дублирования.
    assert len(out) == 1
    c = out[0]
    assert c["group_name"] == pf.GROUP_PSYCHO
    assert "хрень" in c["value"]
    assert "эксперту" in c["value"]     # интерпретация остаётся эксперту
    assert c["id_value"] == ""          # автоматической оценки нет


# ── фиксы «на злобу дня» ─────────────────────────────────────────────────────
def test_semantic_threshold_skips_noise():
    """Тематика с cosine ниже порога не создаёт мусорных кандидатов."""
    class _NoiseDomain(_FakeDomain):
        def __init__(self):
            super().__init__()
            self.cosine = 0.08          # уровень шума (реальный кейс)
    class _NoiseThematic:
        top_domains = [_NoiseDomain()]
    assert pf.semantic_candidates(_NoiseThematic()) == []


def test_semantic_weak_attribution_marked():
    class _WeakDomain(_FakeDomain):
        def __init__(self):
            super().__init__()
            self.cosine = 0.18
    class _WeakThematic:
        top_domains = [_WeakDomain()]
    out = pf.semantic_candidates(_WeakThematic())
    assert len(out) == 1
    assert "слабая атрибуция" in out[0]["value"]


def test_internet_candidates_concrete_with_fragments():
    text = ("Лол, ну ты кринж выдал!!! Это кринж какой-то, СРОЧНО удали. "
            "Держи лайк :) и ещё смайл :)")
    out = pf.internet_candidates(text)
    labels = {c["value"]: c for c in out}
    # Конкретные вхождения с числом употреблений и фрагментом.
    kr = next(c for c in out if "кринж" in c["value"])
    assert "×2" in kr["value"]
    assert kr["id_value"] == "высокая"          # устойчивое употребление
    assert kr["fragment"]                        # фрагмент присутствует
    assert kr["subgroup"] == pf.SUB_INTERNET
    assert any("СРОЧНО" in c["value"] for c in out)        # капс
    assert any("!!!" in c["value"] for c in out)           # повторная пунктуация
    assert any(":)" in c["value"] for c in out)            # эмотикон


def test_lexical_marker_candidates_values():
    class _Freq:
        def lookup(self, lemma):
            return {"движуха": (50000, 1.0, "s")}.get(lemma)   # редкое (rank>30000)
    out = pf.lexical_marker_candidates(_FakeStrat(), freq_engine=_Freq())
    by_val = {c["value"]: c for c in out}
    assert by_val["«хрень»"]["id_value"] == "высокая"      # обсценный слой
    assert by_val["«движуха»"]["id_value"] == "высокая"    # жаргон + редкое
    assert all(c["subgroup"] == pf.SUB_LEXICAL for c in out)


def test_suppressed_candidates_stored_and_marked():
    err = _FakeError()
    out = pf.suppressed_candidates([(err, "правило отключено конфигом (PUNCT:TEST)")])
    assert len(out) == 1
    c = out[0]
    assert c["reliability"] == pf.RELIABILITY_SUPPRESSED
    assert "подавлен фильтром" in c["value"]
    assert "PUNCT:TEST" in c["value"]


def test_autocorrect_one_step_and_only_ortho_punct():
    """Автокоррекция понижает на ступень и не трогает грамматику."""
    errs = [_FakeError("Орфографическая", "тся"),
            _FakeError("Грамматическая", "согласование")]
    out = pf.error_candidates(errs, autocorrect_unreliable=True,
                              reliabilities=["высокая", "высокая"])
    ortho = next(c for c in out if c["subgroup"] == pf.SUB_ORTHOGRAPHIC)
    gram = next(c for c in out if c["subgroup"] == pf.SUB_GRAMMAR)
    assert ortho["reliability"] == "средняя"     # высокая → средняя (одна ступень)
    assert pf.NOTE_UNRELIABLE_AUTOCORRECT in ortho["value"]
    assert gram["reliability"] == "высокая"      # грамматика не пострадала
    assert pf.NOTE_UNRELIABLE_AUTOCORRECT not in gram["value"]


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
    assert all(r["kind"] in (pf.KIND_COUNTER, pf.KIND_CANDIDATE, pf.KIND_GENERAL)
               for r in rows)
    assert all(r["source"] for r in rows)
    assert all(r["created_at"] for r in rows)
    # Общие признаки (степени навыков) присутствуют: 4 навыка + общий уровень.
    general = [r for r in rows if r["kind"] == pf.KIND_GENERAL]
    assert len(general) == 5
    assert {r["subgroup"] for r in general} == {
        "орфографический", "пунктуационный", "грамматический",
        "лексико-фразеологический", "общий_уровень"}
    assert all("ошибок/200" in (r["value"] or "") for r in general
               if r["subgroup"] != "общий_уровень")
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
