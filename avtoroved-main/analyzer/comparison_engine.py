"""
analyzer/comparison_engine.py — Структурное сравнительное исследование.

Методическая основа:
  «Комплексная методика производства судебно-автороведческих экспертиз»
  / Рубцова И.И., Ермолова Е.И., Безрукова А.И. и др. — М.: ЭКЦ МВД России, 2007.

Сравнительная стадия (3-я из четырёх: пригодность → раздельное → сравнительное
→ оценка; с. 80) ведётся по ТРЁМ уровням индивидуализации речемыслительного
навыка (с. 84–85):
  НН  — набор норм:          каким стилевым/категориальным нормам следует автор;
  НС  — набор свойств норм:  как реализуются нормы (грамматич./синтаксич. свойства);
  НСВ — набор средств выражения: конкретные использованные языковые средства.

Результат стадии — ДВА КОМПЛЕКСА признаков: СОВПАДАЮЩИЕ и РАЗЛИЧАЮЩИЕСЯ (с. 85).

ВАЖНО: движок НЕ выносит итоговый вывод. Он формирует структуру признаков,
вспомогательные объективизирующие показатели и ПОДСКАЗКУ по шкале (с. 85).
Окончательный вывод формулирует эксперт.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any

# Порог комплекса высокоинформативных признаков (с. 85)
MIN_HIGH_INFORMATIVE = 20

# Относительная близость числовых свойств уровня НС (доля),
# при которой свойство считается совпадающим.
_NS_REL_TOL = 0.15
_TTR_REL_TOL = 0.12

# Порядок степеней владения (для оценки «величины» расхождения на уровне НН)
_SKILL_ORDER = {"высокая": 2, "средняя": 1, "низкая": 0}


# ── Датаклассы ───────────────────────────────────────────────────────────────

@dataclass
class CompFeature:
    """Один сопоставляемый признак."""
    level: str            # "НН" | "НС" | "НСВ"
    name: str             # человекочитаемое название признака
    value1: str           # значение в тексте 1
    value2: str           # значение в тексте 2
    kind: str             # "match" (совпадающий) | "diff" (различающийся)
    high_informative: bool = False   # помечается экспертом (с. 35/85)
    stable: bool = False             # устойчивость/повторяемость по тексту (с. 85)
    note: str = ""        # пояснение (напр. конкретные лексемы)


@dataclass
class ComparisonResult:
    matches: List[CompFeature] = field(default_factory=list)   # совпадающие
    diffs:   List[CompFeature] = field(default_factory=list)   # различающиеся
    auxiliary: Dict[str, Any] = field(default_factory=dict)    # вспомогательные метрики
    # Счётчики (с. 85)
    total_features: int = 0
    high_informative_matches: int = 0
    high_informative_diffs: int = 0
    threshold: int = MIN_HIGH_INFORMATIVE
    # Подсказка (логика шкалы, НЕ вердикт)
    hint: str = ""
    hint_basis: List[str] = field(default_factory=list)
    # Сводка по уровням: {level: {"match": n, "diff": n}}
    level_summary: Dict[str, Dict[str, int]] = field(default_factory=dict)

    def by_level(self, kind: str, level: str) -> List[CompFeature]:
        src = self.matches if kind == "match" else self.diffs
        return [f for f in src if f.level == level]


# ── Извлечение признаков одного текста ───────────────────────────────────────

def build_bundle(name: str, text: str, tokens: list,
                 metrics: dict, error_result=None, strat_result=None) -> dict:
    """Упаковать готовые результаты анализа одного текста."""
    return {
        "name": name, "text": text, "tokens": tokens,
        "metrics": metrics or {},
        "error_result": error_result,
        "strat_result": strat_result,
    }


def _skill_map(error_result) -> Dict[str, str]:
    """{навык: степень} из ErrorAnalysisResult."""
    out: Dict[str, str] = {}
    if error_result and getattr(error_result, "skill_levels", None):
        for sl in error_result.skill_levels:
            out[sl.skill_name] = sl.level
    return out


def _leading_style(metrics: dict, strat_result) -> str:
    """
    Эвристика ведущего функционального/регистрового стиля (уровень НН).
    Опирается на долю нелитературной лексики (стратификация) и синтаксис.
    Это операционализация по примерам методики (с. 84); не строгая классификация.
    """
    add = metrics.get("дополнительно", {})
    avg_sent = add.get("Средняя длина предложения (слов)", 0) or 0
    marked = getattr(strat_result, "marked_ratio", 0.0) if strat_result else 0.0
    layer_counts = getattr(strat_result, "layer_counts", {}) if strat_result else {}
    reduced = sum(layer_counts.get(l, 0) for l in
                  ("colloquial_reduced", "vernacular", "general_jargon",
                   "youth_jargon", "criminal_jargon", "drug_jargon", "obscene"))

    if marked >= 0.04 and reduced >= 2:
        return "разговорно-сниженный"
    if isinstance(avg_sent, (int, float)) and avg_sent >= 18:
        return "книжно-письменный"
    return "нейтральный / смешанный"


def _num(metrics: dict, key) -> Optional[float]:
    v = metrics.get("дополнительно", {}).get(key, None)
    return v if isinstance(v, (int, float)) else None


# ── Сопоставление двух текстов ───────────────────────────────────────────────

def compare(bundle1: dict, bundle2: dict, auxiliary: dict) -> ComparisonResult:
    res = ComparisonResult(auxiliary=dict(auxiliary or {}))

    _compare_nn(bundle1, bundle2, res)
    _compare_ns(bundle1, bundle2, res)
    _compare_nsv(bundle1, bundle2, res, auxiliary or {})

    _finalize(res, bundle1, bundle2)
    return res


# ── Уровень НН: набор норм ───────────────────────────────────────────────────

def _compare_nn(b1, b2, res: ComparisonResult):
    er1, er2 = b1.get("error_result"), b2.get("error_result")

    # 1. Общий уровень владения литературным языком (с. 13).
    g1 = getattr(er1, "general_skill_level", "") if er1 else ""
    g2 = getattr(er2, "general_skill_level", "") if er2 else ""
    if g1 and g2:
        if g1 == g2:
            res.matches.append(CompFeature(
                "НН", "Общий уровень владения литературным языком",
                g1, g2, "match", stable=True,
                note="Совпадение общего признака письменной речи (с. 13, 84)."))
        else:
            gap = abs(_SKILL_ORDER.get(g1, 1) - _SKILL_ORDER.get(g2, 1))
            note = ("Расхождение общего признака на уровне норм."
                    + (" Различие значимое (через ступень) — признак "
                       "категорического отрицательного вывода (с. 85)."
                       if gap >= 2 else ""))
            res.diffs.append(CompFeature(
                "НН", "Общий уровень владения литературным языком",
                g1, g2, "diff", high_informative=(gap >= 2), stable=True, note=note))

    # 2. Степени развития пяти языковых навыков (с. 13).
    sm1, sm2 = _skill_map(er1), _skill_map(er2)
    for skill in sorted(set(sm1) | set(sm2)):
        l1, l2 = sm1.get(skill, "—"), sm2.get(skill, "—")
        if l1 == "—" or l2 == "—":
            continue
        kind = "match" if l1 == l2 else "diff"
        feat = CompFeature("НН", skill, l1, l2, kind)
        (res.matches if kind == "match" else res.diffs).append(feat)

    # 3. Ведущий функциональный/регистровый стиль (эвристика, с. 84).
    st1 = _leading_style(b1.get("metrics", {}), b1.get("strat_result"))
    st2 = _leading_style(b2.get("metrics", {}), b2.get("strat_result"))
    kind = "match" if st1 == st2 else "diff"
    (res.matches if kind == "match" else res.diffs).append(
        CompFeature("НН", "Ведущий регистровый/функциональный стиль",
                    st1, st2, kind,
                    note="Эвристическая оценка по стратификации и синтаксису (с. 84)."))


# ── Уровень НС: набор свойств норм ───────────────────────────────────────────

def _ns_numeric(res, name, v1, v2, tol, fmt="{:.3f}"):
    if v1 is None or v2 is None:
        return
    base = max(abs(v1), abs(v2), 1e-9)
    rel = abs(v1 - v2) / base
    kind = "match" if rel <= tol else "diff"
    (res.matches if kind == "match" else res.diffs).append(
        CompFeature("НС", name, fmt.format(v1), fmt.format(v2), kind,
                    note=f"Относительное расхождение {rel:.0%} (порог {tol:.0%})."))


def _compare_ns(b1, b2, res: ComparisonResult):
    m1, m2 = b1.get("metrics", {}), b2.get("metrics", {})

    # Количественные свойства как ОБЪЕКТИВИЗАЦИЯ (с. 84): TTR, синтаксис, профиль.
    _ns_numeric(res, "Лексическое разнообразие (TTR)",
                _num(m1, "Лексическое разнообразие (TTR)"),
                _num(m2, "Лексическое разнообразие (TTR)"), _TTR_REL_TOL)
    _ns_numeric(res, "Средняя длина предложения (слов)",
                _num(m1, "Средняя длина предложения (слов)"),
                _num(m2, "Средняя длина предложения (слов)"), _NS_REL_TOL, "{:.1f}")
    _ns_numeric(res, "Доля hapax-лемм",
                _num(m1, "Доля hapax-лемм"),
                _num(m2, "Доля hapax-лемм"), _NS_REL_TOL)

    # Соотношения частей речи (морфологический профиль).
    for key in ("Содержательные/служебные", "Существительные/глаголы"):
        v1, v2 = _num(m1, key), _num(m2, key)
        _ns_numeric(res, key, v1, v2, _NS_REL_TOL, "{:.2f}")

    # Близость POS-биграммного профиля (из вспомогательных метрик).
    bg = res.auxiliary.get("bigram_similarity")
    if isinstance(bg, (int, float)):
        kind = "match" if bg >= 0.85 else "diff"
        (res.matches if kind == "match" else res.diffs).append(
            CompFeature("НС", "Профиль POS-биграмм (сочетаемость частей речи)",
                        f"попарная близость {bg:.0%}",
                        "≥85% → совпадение" if kind == "match" else "<85% → различие",
                        kind,
                        note="Косинусная близость биграммных профилей (Litvinova)."))


# ── Уровень НСВ: набор средств выражения ─────────────────────────────────────

def _compare_nsv(b1, b2, res: ComparisonResult, aux: dict):
    # 1. Конкретные совпадающие знаменательные лексемы (с. 85).
    common = aux.get("common_lemmas", []) or []
    if common:
        shown = ", ".join(common[:25])
        res.matches.append(CompFeature(
            "НСВ", "Совпадающие знаменательные лексемы",
            f"{len(common)} лексем", f"{len(common)} лексем", "match",
            stable=len(common) >= 5,
            note=shown + ("…" if len(common) > 25 else "")))

    # 2. Стратификационные пласты: совпадающие и различающиеся средства.
    sr1, sr2 = b1.get("strat_result"), b2.get("strat_result")
    lw1 = getattr(sr1, "layer_words", {}) if sr1 else {}
    lw2 = getattr(sr2, "layer_words", {}) if sr2 else {}
    for layer in sorted(set(lw1) | set(lw2)):
        w1 = set(lw1.get(layer, []))
        w2 = set(lw2.get(layer, []))
        shared = sorted(w1 & w2)
        label = _LAYER_LABEL.get(layer, layer)
        if shared:
            res.matches.append(CompFeature(
                "НСВ", f"Пласт «{label}» — общие средства",
                ", ".join(sorted(w1)[:8]) or "—",
                ", ".join(sorted(w2)[:8]) or "—", "match",
                stable=len(shared) >= 2,
                note="Совпадающие лексемы пласта: " + ", ".join(shared[:10])))
        elif w1 and not w2:
            res.diffs.append(CompFeature(
                "НСВ", f"Пласт «{label}» — только в тексте 1",
                ", ".join(sorted(w1)[:8]), "—", "diff",
                note="Средства пласта присутствуют лишь в одном тексте."))
        elif w2 and not w1:
            res.diffs.append(CompFeature(
                "НСВ", f"Пласт «{label}» — только в тексте 2",
                "—", ", ".join(sorted(w2)[:8]), "diff",
                note="Средства пласта присутствуют лишь в одном тексте."))

    # 3. Маркеры интернет-коммуникации (Колокольцева; уровень НСВ).
    ip1 = getattr(b1.get("error_result"), "internet_profile", None)
    ip2 = getattr(b2.get("error_result"), "internet_profile", None)
    s1 = getattr(ip1, "internet_comm_score", 0.0) if ip1 else 0.0
    s2 = getattr(ip2, "internet_comm_score", 0.0) if ip2 else 0.0
    if s1 or s2:
        present1, present2 = s1 >= 0.5, s2 >= 0.5
        if present1 and present2:
            res.matches.append(CompFeature(
                "НСВ", "Маркеры интернет-коммуникации",
                f"индекс {s1:.1f}", f"индекс {s2:.1f}", "match"))
        elif present1 != present2:
            res.diffs.append(CompFeature(
                "НСВ", "Маркеры интернет-коммуникации",
                f"индекс {s1:.1f}", f"индекс {s2:.1f}", "diff"))


# Метки пластов для НСВ (краткие; полный список — в stratification_engine)
_LAYER_LABEL = {
    "literary_standard": "книжная/нейтральная",
    "colloquial_reduced": "разговорно-сниженная",
    "vernacular": "просторечие",
    "general_jargon": "общий жаргон",
    "youth_jargon": "молодёжный жаргон",
    "drug_jargon": "наркотический жаргон",
    "criminal_jargon": "криминальный жаргон",
    "archaic": "архаизмы",
    "dialectal": "диалектизмы",
    "euphemistic": "эвфемизмы",
    "obscene": "обсценная лексика",
}


# ── Счётчики и подсказка ─────────────────────────────────────────────────────

def _finalize(res: ComparisonResult, b1, b2):
    res.total_features = len(res.matches) + len(res.diffs)
    res.high_informative_matches = sum(1 for f in res.matches if f.high_informative)
    res.high_informative_diffs = sum(1 for f in res.diffs if f.high_informative)

    # Сводка по уровням
    for lvl in ("НН", "НС", "НСВ"):
        res.level_summary[lvl] = {
            "match": len(res.by_level("match", lvl)),
            "diff": len(res.by_level("diff", lvl)),
        }

    recompute_hint(res)


def recompute_hint(res: ComparisonResult) -> None:
    """
    Подсказка по шкале (с. 85) — ЛОГИКА, не вердикт.
    Пересчитывается после того, как эксперт пометил высокоинформативные признаки.
    """
    nn = res.level_summary.get("НН", {"match": 0, "diff": 0})
    ns = res.level_summary.get("НС", {"match": 0, "diff": 0})
    nsv = res.level_summary.get("НСВ", {"match": 0, "diff": 0})

    # Значимое различие на уровне норм: помеченное экспертом расхождение НН,
    # либо «через ступень» по общему признаку (high_informative-diff на НН).
    nn_significant_diff = any(
        f.high_informative for f in res.diffs if f.level == "НН"
    )

    basis: List[str] = []
    if nn_significant_diff:
        hint = "Признаки категорического ОТРИЦАТЕЛЬНОГО вывода (различие на уровне норм)"
        basis.append("значимое различие на уровне НН")
    elif ns["diff"] > ns["match"] and ns["diff"] >= 2:
        hint = "Признаки вероятного ОТРИЦАТЕЛЬНОГО вывода (различия и на уровне свойств НС)"
        basis.append("различия проявляются уже на уровне НС, не только НСВ")
    elif (nn["match"] >= 1 and ns["match"] >= 1
          and nsv["match"] == 0 and nn["diff"] == 0):
        hint = ("Признаки вероятного ПОЛОЖИТЕЛЬНОГО вывода / «нельзя исключить» "
                "(совпадения на НН и НС, на НСВ почти нет)")
        basis.append("совпадения на НН и НС при слабом НСВ")
    elif (res.high_informative_matches >= res.threshold
          and res.high_informative_diffs == 0
          and nn["match"] >= 1 and ns["match"] >= 1 and nsv["match"] >= 1):
        hint = "Признаки категорического ПОЛОЖИТЕЛЬНОГО вывода"
        basis.append(f"≥{res.threshold} высокоинформативных совпадений на всех трёх уровнях, "
                     "значимых различий нет")
    else:
        hint = "Совокупность признаков НЕДОСТАТОЧНА для категорического вывода"
        if res.high_informative_matches < res.threshold:
            basis.append(f"высокоинформативных совпадений {res.high_informative_matches} "
                         f"< порога {res.threshold}")
        if res.high_informative_diffs:
            basis.append("есть значимые различия")

    res.hint = hint
    res.hint_basis = basis
