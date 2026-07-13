"""
protocol/profile.py — стадия «раздельное исследование» (Задача 2Б).

Строит профиль КАЖДОГО текста по отдельности (до всякого сравнения — требование
стадийности по Огорелкову/Моисеевой) и складывает его в таблицу feature_candidates.
Сравнения здесь НЕТ. UI «принять/отклонить признак» здесь НЕТ — но данные
записываются так, чтобы следующий этап пристыковался без переделок
(kind/source/fragment/id_value заполняются уже сейчас).

Переиспользуются существующие модули анализа (analyzer.*), NLP не дублируется:
токены даёт уже инициализированный в приложении бэкенд (StanzaBackend).
Тяжёлых новых зависимостей нет.
"""
from __future__ import annotations

import json
import re
from typing import Any, Optional

from protocol import db as protocol_db
from protocol import detector_filter

# ── Группы (по методике: 4 группы признаков) ─────────────────────────────────
GROUP_SEMANTIC = "смысловые"
GROUP_TEXTOLOGICAL = "текстологические"
GROUP_LINGUISTIC = "языковые"
GROUP_PSYCHO = "психолингвистические"

# ── Подгруппы языковой группы ────────────────────────────────────────────────
SUB_LEXICAL = "лексические"
SUB_STYLISTIC = "стилистические"
SUB_SYNTACTIC = "синтаксические"
SUB_ORTHOGRAPHIC = "орфографические"
SUB_PUNCTUATION = "пунктуационные"
SUB_GRAMMAR = "грамматические"

# ── Виды элементов ───────────────────────────────────────────────────────────
KIND_COUNTER = "счётчик"
KIND_CANDIDATE = "кандидат_признак"
KIND_GENERAL = "общий_признак"   # степень развития навыка (уровень НН)

# ── Общие признаки: степени развития навыков ─────────────────────────────────
# Наименование степени — по единой шкале Рубцовой 2007, с. 13 (высокая <4,
# средняя 4–6, низкая >6 ошибок на 200 словоформ); дифференцированная таблица
# Вула по категориям в кодовой базе отсутствует [нужны пороги — сверить с
# Вул 2007]. Решающее правило Вула (стадия 4) работает по числам на 200
# словоформ и допускам, от наименования степени не зависит.
GENERAL_SKILLS = ("орфографический", "пунктуационный",
                  "грамматический", "лексико-фразеологический")
_SKILL_BY_ERROR_TYPE = {
    "Орфографическая": "орфографический",
    "Пунктуационная": "пунктуационный",
    "Грамматическая": "грамматический",
    "Лексическая": "лексико-фразеологический",
}
GENERAL_LABEL_PREFIX = "Общий признак: "
GENERAL_OVERALL_SUBGROUP = "общий уровень"
# Формат value парсится стадией сравнения (comparison.parse_general_rate).
GENERAL_VALUE_FMT = "{level} · {rate:.1f} ош./200 сл. · уникальных {count}"
# Навыки, ненадёжные при автокоррекции (цифровое/опубликованное происхождение).
_AUTOCORRECT_SENSITIVE_SKILLS = ("орфографический", "пунктуационный")

# Пометки надёжности для кандидатов ошибок.
NOTE_NEEDS_REVIEW = "требует проверки"
NOTE_UNRELIABLE_AUTOCORRECT = "ненадёжен (автокоррекция)"

# Маппинг типа ошибки (TextError.error_type) → подгруппа.
_ERROR_SUBGROUP = {
    "Орфографическая": SUB_ORTHOGRAPHIC,
    "Пунктуационная": SUB_PUNCTUATION,
    "Грамматическая": SUB_GRAMMAR,
    "Лексическая": SUB_LEXICAL,
    "Стилистическая": SUB_STYLISTIC,
}

_WORD_RE = re.compile(r"[A-Za-zА-Яа-яЁё]+")

# Максимум единичных психолингвистических кандидатов (только подсветка).
MAX_PSYCHO_CANDIDATES = 10


def _c(group: str, kind: str, label: str, value: Any = None,
       subgroup: Optional[str] = None, fragment: Optional[str] = None,
       source: Optional[str] = None, id_value: str = "") -> dict:
    """Собрать один элемент профиля в формате feature_candidates."""
    return {
        "group_name": group, "subgroup": subgroup, "kind": kind,
        "label": label, "value": None if value is None else str(value),
        "fragment": fragment, "source": source, "id_value": id_value,
    }


# ── 1. Смысловые (тематические): тема ≠ автор → id_value «низкая» ─────────────
def semantic_candidates(thematic_result: Any) -> list[dict]:
    out: list[dict] = []
    if thematic_result is None:
        return out
    for d in getattr(thematic_result, "top_domains", []) or []:
        examples = ", ".join(getattr(d, "examples", [])[:5])
        out.append(_c(
            GROUP_SEMANTIC, KIND_COUNTER, f"Доминирующая тема: {d.label}",
            value=f"cosine {d.cosine:.2f}, совпадений лемм {d.match_count}",
            subgroup="тематические", fragment=examples or None,
            source="thematic_engine", id_value="низкая"))
    return out


# ── 2. Текстологические: архитектоника (счётчики) ────────────────────────────
def textological_candidates(metrics: dict, text: str) -> list[dict]:
    out: list[dict] = []
    add = (metrics or {}).get("дополнительно", {})

    paragraphs = [p for p in re.split(r"\n\s*\n", text or "") if p.strip()]
    n_par = len(paragraphs)
    par_lens = [len(_WORD_RE.findall(p)) for p in paragraphs]
    avg_par = round(sum(par_lens) / n_par, 1) if n_par else 0

    out.append(_c(GROUP_TEXTOLOGICAL, KIND_COUNTER, "Число абзацев",
                  n_par, subgroup="архитектоника", source="profile"))
    out.append(_c(GROUP_TEXTOLOGICAL, KIND_COUNTER, "Средняя длина абзаца (слов)",
                  avg_par, subgroup="архитектоника", source="profile"))
    for key in ("Всего слов", "Всего предложений",
                "Средняя длина предложения (слов)", "Дисперсия длины предложений"):
        if key in add:
            out.append(_c(GROUP_TEXTOLOGICAL, KIND_COUNTER, key, add[key],
                          subgroup="архитектоника", source="metrics"))
    return out


# ── 3а. Языковые / лексические: TTR, hapax, стратификация ────────────────────
def lexical_candidates(metrics: dict, strat_result: Any) -> list[dict]:
    out: list[dict] = []
    add = (metrics or {}).get("дополнительно", {})
    for key in ("Лексическое разнообразие (TTR)", "Лемматическое разнообразие",
                "Доля hapax-лемм", "Средняя длина слова (букв)"):
        if key in add:
            out.append(_c(GROUP_LINGUISTIC, KIND_COUNTER, key, add[key],
                          subgroup=SUB_LEXICAL, source="metrics"))
    if strat_result is not None:
        for layer, cnt in sorted((strat_result.layer_counts or {}).items(),
                                 key=lambda x: -x[1]):
            words = ", ".join((strat_result.layer_words or {}).get(layer, [])[:5])
            out.append(_c(GROUP_LINGUISTIC, KIND_COUNTER,
                          f"Регистровый слой: {layer}", cnt,
                          subgroup=SUB_LEXICAL, fragment=words or None,
                          source="stratification_engine"))
        out.append(_c(GROUP_LINGUISTIC, KIND_COUNTER,
                      "Доля нелитературной лексики",
                      f"{strat_result.marked_ratio:.1%}",
                      subgroup=SUB_LEXICAL, source="stratification_engine"))
    return out


# ── 3б. Языковые / стилистические: маркеры, интернет-профиль ─────────────────
def stylistic_candidates(metrics: dict, internet_profile: Any) -> list[dict]:
    out: list[dict] = []
    style = (metrics or {}).get("профиль_служебных_слов", {})
    for group_name, markers in style.items():
        found = {m: c for m, c in markers.items() if c > 0}
        if not found:
            continue
        total = sum(found.values())
        frag = ", ".join(f"{m}×{c}" for m, c in sorted(found.items(), key=lambda x: -x[1])[:6])
        out.append(_c(GROUP_LINGUISTIC, KIND_COUNTER,
                      f"Стилевые маркеры: {group_name}", total,
                      subgroup=SUB_STYLISTIC, fragment=frag, source="metrics"))
    if internet_profile is not None:
        pairs = [
            ("Эмодзи", internet_profile.emoji_count),
            ("Эмотиконы", internet_profile.emoticon_count),
            ("Хэштеги", internet_profile.hashtag_count),
            ("Слова КАПСОМ", internet_profile.caps_words),
            ("Интернет-сленг", internet_profile.slang_count),
            ("Аббревиатуры", internet_profile.abbreviation_count),
            ("Повторная пунктуация (!!, ??)", internet_profile.repeated_punct_count),
        ]
        for label, cnt in pairs:
            if cnt:
                out.append(_c(GROUP_LINGUISTIC, KIND_COUNTER,
                              f"Интернет-коммуникация: {label}", cnt,
                              subgroup=SUB_STYLISTIC, source="errors.internet"))
    return out


# ── 3в. Языковые / синтаксические: POS-распределение, типы предложений ───────
def syntactic_candidates(metrics: dict, text: str) -> list[dict]:
    out: list[dict] = []
    freq = (metrics or {}).get("частоты", {})
    for pos_label, data in list(freq.items())[:8]:
        out.append(_c(GROUP_LINGUISTIC, KIND_COUNTER,
                      f"Доля POS: {pos_label}",
                      f"{data['коэффициент']:.3f} ({data['количество']})",
                      subgroup=SUB_SYNTACTIC, source="metrics"))
    # Типы предложений по финальному знаку.
    sents = [s.strip() for s in re.split(r"(?<=[.!?…])\s+", text or "") if s.strip()]
    if sents:
        q = sum(1 for s in sents if s.endswith("?"))
        e = sum(1 for s in sents if s.endswith("!"))
        ell = sum(1 for s in sents if s.endswith("…") or s.endswith("..."))
        out.append(_c(GROUP_LINGUISTIC, KIND_COUNTER, "Вопросительные предложения",
                      q, subgroup=SUB_SYNTACTIC, source="profile"))
        out.append(_c(GROUP_LINGUISTIC, KIND_COUNTER, "Восклицательные предложения",
                      e, subgroup=SUB_SYNTACTIC, source="profile"))
        out.append(_c(GROUP_LINGUISTIC, KIND_COUNTER, "Предложения с многоточием",
                      ell, subgroup=SUB_SYNTACTIC, source="profile"))
    return out


# ── 3г. Языковые / орфография+пунктуация: кандидаты из модуля ошибок ─────────
def error_candidates(errors: list, autocorrect_unreliable: bool,
                     reliabilities: Optional[list[str]] = None) -> list[dict]:
    """
    Кандидаты признаков из ошибок (TextError). По умолчанию каждый помечен
    «требует проверки»; при флаге автокоррекции из suitability — «ненадёжен
    (автокоррекция)» (орфографические и пунктуационные признаки искажены).

    reliabilities — надёжность каждого срабатывания из слоя фильтрации
    (protocol/detector_filter.py), позиционно к errors. Флаг автокоррекции
    дополнительно понижает надёжность до «низкая».
    """
    out: list[dict] = []
    note = NOTE_UNRELIABLE_AUTOCORRECT if autocorrect_unreliable else NOTE_NEEDS_REVIEW
    for i, err in enumerate(errors or []):
        subgroup = _ERROR_SUBGROUP.get(err.error_type, SUB_ORTHOGRAPHIC)
        desc = err.description or err.subtype or err.error_type
        rel = reliabilities[i] if reliabilities and i < len(reliabilities) else ""
        if autocorrect_unreliable:
            rel = "низкая"
        c = _c(
            GROUP_LINGUISTIC, KIND_CANDIDATE,
            f"{err.error_type}: {err.subtype or 'без подтипа'}",
            value=f"{desc} · {note}",
            subgroup=subgroup,
            fragment=err.fragment or err.context or None,
            # rule_ref (напр. LT:MORFOLOGIK_RULE_RU_RU) — чтобы правило можно
            # было найти и занести в detector_filter.json прямо из UI.
            source=getattr(err, "rule_ref", "") or err.source or "errors",
            id_value=err.significance or "средняя")
        c["reliability"] = rel
        out.append(c)
    return out


# ── 3д. Общие признаки: степени развития навыков (уровень НН) ────────────────
def general_skill_candidates(errors: list, total_words: int,
                             autocorrect_unreliable: bool = False) -> list[dict]:
    """
    Степени развития 4 навыков (орфографический, пунктуационный,
    грамматический, лексико-фразеологический) + общий уровень грамотности
    (Рубцова 2007, с. 13). Считаются от того же потока ошибок, что и кандидаты
    (после слоя фильтрации); дедупликация — по с. 14. Это общие признаки
    уровня НН — они минуют карту признаков и сопоставляются напрямую
    (comparison.general_skill_verdicts) с допусками Минюста.
    """
    if total_words <= 0:
        return []
    from analyzer.errors import (deduplicate_errors, get_skill_level,
                                 calculate_general_skill)
    out: list[dict] = []
    groups: dict[str, list] = {s: [] for s in GENERAL_SKILLS}
    for e in errors or []:
        skill = _SKILL_BY_ERROR_TYPE.get(e.error_type)
        if skill:
            groups[skill].append(e)
    norm = 200 / total_words
    for skill in GENERAL_SKILLS:
        unique = deduplicate_errors(groups[skill])
        count = len(unique)
        level, _desc = get_skill_level(count, total_words)
        c = _c(GROUP_LINGUISTIC, KIND_GENERAL,
               f"{GENERAL_LABEL_PREFIX}{skill} навык",
               value=GENERAL_VALUE_FMT.format(
                   level=level, rate=round(count * norm, 1), count=count),
               subgroup=skill, source="errors.scale", id_value="")
        if autocorrect_unreliable and skill in _AUTOCORRECT_SENSITIVE_SKILLS:
            c["reliability"] = "низкая"
        out.append(c)
    g_level, _g_desc, g_total = calculate_general_skill(errors or [], total_words)
    out.append(_c(GROUP_LINGUISTIC, KIND_GENERAL,
                  f"{GENERAL_LABEL_PREFIX}общий уровень грамотности",
                  value=GENERAL_VALUE_FMT.format(
                      level=g_level, rate=round(g_total * norm, 1), count=g_total),
                  subgroup=GENERAL_OVERALL_SUBGROUP, source="errors.scale"))
    return out


# ── 4. Психолингвистические: только подсветка, интерпретация — эксперту ──────
def psycho_candidates(strat_result: Any) -> list[dict]:
    """
    Минимум автоматики: подсвечиваем единичные яркие словоупотребления
    (редкие регистровые маркеры) как кандидатов. Автоматической интерпретации
    нет — оценка остаётся эксперту.
    """
    out: list[dict] = []
    if strat_result is None:
        return out
    seen: set[tuple[str, str]] = set()
    for tok in getattr(strat_result, "tokens", []) or []:
        key = (tok.lemma, tok.layer)
        if key in seen:
            continue
        seen.add(key)
        out.append(_c(
            GROUP_PSYCHO, KIND_CANDIDATE,
            f"Единичный маркер ({tok.layer})",
            value=f"«{tok.surface}» · интерпретация — эксперту",
            fragment=tok.context or None,
            source="stratification_engine", id_value=""))
        if len(out) >= MAX_PSYCHO_CANDIDATES:
            break
    return out


# ── сборка профиля из готовых результатов модулей ─────────────────────────────
def build_profile(text: str, metrics: dict,
                  thematic_result: Any = None, strat_result: Any = None,
                  errors: Optional[list] = None, internet_profile: Any = None,
                  autocorrect_unreliable: bool = False,
                  error_reliabilities: Optional[list[str]] = None) -> list[dict]:
    """Собрать полный профиль (4 группы) из результатов существующих модулей."""
    profile: list[dict] = []
    profile += semantic_candidates(thematic_result)
    profile += textological_candidates(metrics, text)
    profile += lexical_candidates(metrics, strat_result)
    profile += stylistic_candidates(metrics, internet_profile)
    profile += syntactic_candidates(metrics, text)
    profile += error_candidates(errors or [], autocorrect_unreliable,
                                reliabilities=error_reliabilities)
    total_words = len(_WORD_RE.findall(text or ""))
    profile += general_skill_candidates(errors or [], total_words,
                                        autocorrect_unreliable)
    profile += psycho_candidates(strat_result)
    return profile


# ── оркестрация: документ из БД → профиль → feature_candidates + журнал ───────
def has_autocorrect_flag(pdb: "protocol_db.ProtocolDB",
                         project_id: int, document_id: int) -> bool:
    """Стоит ли на документе флаг «автокоррекция» из стадии пригодности (2А)."""
    for row in pdb.fetch_suitability(project_id):
        if row["document_id"] != document_id or not row["flags"]:
            continue
        try:
            flags = json.loads(row["flags"])
        except Exception:
            continue
        if any(f.get("code") == "автокоррекция" for f in flags):
            return True
    return False


def run_for_document(
    pdb: "protocol_db.ProtocolDB",
    project_id: int,
    document_id: int,
    backend: Any,
    program_version: Optional[str] = None,
    status_cb=None,
    use_lt: bool = True,
) -> dict:
    """
    Построить и сохранить профиль одного документа (идемпотентно: старый
    профиль удаляется). NLP — через переданный уже инициализированный бэкенд;
    остальные модули — синглтоны analyzer.* (не дублируются).
    """
    def _status(msg: str):
        if status_cb:
            status_cb(msg)

    doc = pdb.get_document(document_id)
    if doc is None:
        raise ValueError(f"Документ #{document_id} не найден")
    text = pdb.get_layer(document_id, protocol_db.LAYER_CLEANED) or ""

    _status("NLP-разметка (переиспользуем бэкенд)...")
    tokens = backend.analyze(text) if text else []

    _status("Метрики (TTR, hapax, POS, архитектоника)...")
    from analyzer.metrics import calculate_metrics
    metrics = calculate_metrics(tokens, text)

    # Кандидаты ошибок: собственные офлайн-правила + LanguageTool СТРОГО в
    # локальном режиме (материалы дела нельзя отправлять на внешний сервер;
    # публичный API LT в протокольном пути не используется).
    _status("Кандидаты ошибок (офлайн-правила)...")
    errors = []
    punct_rules_version = ""
    try:
        from analyzer import punct_checker
        punct_rules_version = getattr(punct_checker, "RULES_VERSION", "")
        errors = punct_checker.check_with_tokens(text, tokens) or []
    except Exception:
        pass

    lt_meta = {"режим": "не использован", "версия": ""}
    if use_lt:
        try:
            from analyzer import lt_checker as lt_module
            lt = lt_module.get()
            _status("LanguageTool: инициализация (только локальный сервер)...")
            lt.ensure_loaded()
            if lt.mode == "local":
                _status("LanguageTool: проверка текста (локально)...")
                errors += lt.check(text) or []
                try:
                    from importlib.metadata import version as _pkg_version
                    lt_meta = {"режим": "local",
                               "версия": _pkg_version("language-tool-python")}
                except Exception:
                    lt_meta = {"режим": "local", "версия": "?"}
            else:
                # Публичный API доступен, но для протокола запрещён.
                lt_meta = {"режим": f"пропущен ({lt.mode or 'недоступен'})", "версия": ""}
        except Exception:
            lt_meta = {"режим": "ошибка инициализации", "версия": ""}

    # Слой фильтрации (единственная точка между детектором и feature_candidates).
    _status("Фильтрация срабатываний детектора...")
    filter_config, filter_hash = detector_filter.load_config()
    filtered = detector_filter.apply_filter(errors, filter_config)
    errors = [e for e, _rel in filtered.kept]
    error_reliabilities = [rel for _e, rel in filtered.kept]

    _status("Интернет-профиль...")
    internet_profile = None
    try:
        from analyzer.errors import analyze_internet_communication
        internet_profile = analyze_internet_communication(text)
    except Exception:
        pass

    _status("Лексическая стратификация...")
    strat_result = None
    try:
        from analyzer import stratification_engine
        strat_result = stratification_engine.get().analyze(text)
    except Exception:
        pass

    _status("Тематическая атрибуция...")
    thematic_result = None
    try:
        from analyzer import thematic_engine
        lemmas = [t.lemma.lower() for t in tokens
                  if _WORD_RE.search(t.text) and t.pos not in ("PUNCT", "NUM")]
        thematic_result = thematic_engine.get().analyze(lemmas)
    except Exception:
        pass

    autocorrect = has_autocorrect_flag(pdb, project_id, document_id)
    profile = build_profile(
        text, metrics,
        thematic_result=thematic_result, strat_result=strat_result,
        errors=errors, internet_profile=internet_profile,
        autocorrect_unreliable=autocorrect,
        error_reliabilities=error_reliabilities)

    pdb.clear_feature_candidates(document_id)
    n = pdb.save_feature_candidates(document_id, profile)
    pdb.log_action(
        "построен профиль (раздельное исследование)", project_id=project_id,
        details={"document_id": document_id, "filename": doc["filename"],
                 "элементов": n,
                 "групп": sorted({c["group_name"] for c in profile}),
                 "автокоррекция_ненадёжность": autocorrect,
                 # Воспроизводимость: версии движков и конфига фильтра.
                 "фильтр_конфиг_hash": filter_hash,
                 "версия_правил_пунктуации": punct_rules_version,
                 "languagetool": lt_meta,
                 # Подавленные срабатывания не исчезают бесследно.
                 "срабатываний_детектора": filtered.total_in,
                 "подавлено_всего": filtered.total_suppressed,
                 "подавлено_по_правилам": dict(filtered.suppressed)},
        program_version=program_version)

    return {"document_id": document_id, "count": n,
            "autocorrect_unreliable": autocorrect, "profile": profile,
            "detector_total": filtered.total_in,
            "suppressed": dict(filtered.suppressed),
            "filter_hash": filter_hash}
