"""
analyzer/diagnostic_engine.py — Диагностический профиль автора.

Реализует диагностические задачи авторовединой экспертизы по методике:
  «Комплексная методика судебно-авторовединой экспертизы» (ИКЭ ФСБ России).

Задачи:
  1. Пол автора (мужской / женский)
  2. Возрастная группа (17–25 / 25–50 / 50–65 лет)
  3. Уровень образования (низкий / средний / высший)
  4. Культура речи (низкая / средняя / высокая)
  5. Маскировка письменной речи (признаки есть / нет)
  6. Функциональный отпечаток (служебные слова)
"""
from __future__ import annotations
import re
import statistics
from collections import Counter
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple

# ── Словари-маркеры ─────────────────────────────────────────────────────────

# Слова категории состояния — маркер женской речи (по методике)
_STATE_WORDS = frozenset({
    "надо", "нельзя", "жаль", "жалко", "стыдно", "больно", "страшно",
    "обидно", "грустно", "весело", "смешно", "скучно", "холодно", "тепло",
    "нужно", "можно", "невозможно", "приятно", "неприятно", "странно",
    "понятно", "непонятно", "важно", "неважно", "трудно", "легко",
    "тяжело", "хорошо", "плохо", "ясно", "неясно", "видно", "слышно",
})

# Ограничительные частицы — маркер женской речи
_LIMITING_PARTICLES = frozenset({
    "только", "лишь", "всего", "всего лишь", "именно", "как раз",
})

# Вводные слова (устойчивые выражения)
_INTRODUCTORY = frozenset({
    "во-первых", "во-вторых", "в-третьих", "наконец", "итак", "следовательно",
    "таким образом", "однако", "впрочем", "тем не менее", "между тем",
    "конечно", "разумеется", "безусловно", "несомненно", "очевидно",
    "по-видимому", "пожалуй", "вероятно", "возможно", "по-моему",
    "по-твоему", "по-нашему", "с одной стороны", "с другой стороны",
    "кстати", "кстати говоря", "к слову", "к слову сказать",
    "к сожалению", "к счастью", "к несчастью", "к удивлению",
    "надо сказать", "следует отметить", "необходимо отметить",
    "нужно сказать", "можно сказать", "прежде всего", "главным образом",
})

# Молодёжный жаргон — маркер возраста 17–25
_YOUTH_JARGON = frozenset({
    "чел", "чик", "чика", "рофл", "лол", "кек", "мем", "хайп", "хайпить",
    "кринж", "кринжовый", "рандом", "рандомный", "ору", "ахаха", "ахах",
    "итт", "сасай", "сасный", "топ", "топовый", "лайк", "дизлайк", "репост",
    "залайкать", "задизлайкать", "гачи", "ну и", "ваще", "прикол",
    "прикольный", "прикольно", "короч", "короче", "чёт", "чото", "чтоли",
    "бро", "брат", "братан", "чилить", "чил", "катка", "катить", "рейтить",
    "флекс", "флексить", "дроп", "дропнуть", "скам", "скамить",
    "инфа", "инфо", "фото", "видос", "видосик", "стрим", "стримить",
    "гейм", "геймить", "лудить", "скилл", "нуб", "нубас", "профи",
    "gg", "wp", "ez", "имба", "имбовый", "крипер", "фарм", "фармить",
    "тг", "вк", "ютуб", "ютубер", "тикток", "инста", "инстаграм",
    "бомбить", "взрывать", "угарать", "кайфовать", "кайф", "кайфово",
})

# Архаизмы и устаревшие слова — маркер возраста 50–65
_ARCHAISMS = frozenset({
    "сей", "оный", "дабы", "ибо", "яко", "понеже", "доколе", "зане",
    "паче", "токмо", "зело", "вельми", "отколь", "откуда", "откель",
    "нежели", "кои", "кой", "коего", "намедни", "давеча", "нынче",
    "третьего дня", "ноне", "присно", "вовсе", "ажно", "ажник",
    "покамест", "покуда", "поелику", "благо", "небось", "авось",
    "ужели", "неужели", "никак", "этак", "этакий", "эдак", "эдакий",
    "нонче", "тотчас", "ныне", "давеча", "намедни", "третьего дня",
    "уж", "чай", "ишь", "вишь", "гляди", "смотри-ка",
})

# Слова-морализаторы — маркер возраста 50–65 и женского пола
_MORALIZING = frozenset({
    "надобно", "следует", "должно", "нельзя же", "как можно",
    "позор", "стыд", "совесть", "честь", "долг", "нравственность",
    "безнравственный", "аморальный", "воспитание", "уважение",
    "порядочность", "приличие", "приличный", "неприличный",
    "скромность", "смирение", "смиренный",
})

# Союзы (для подсчёта вариативности)
_CONJ_TYPES = {
    "сочинительные": frozenset({
        "и", "а", "но", "да", "или", "либо", "зато", "однако", "же",
        "тоже", "также", "притом", "причём", "то", "ни",
    }),
    "подчинительные": frozenset({
        "что", "чтобы", "как", "когда", "если", "хотя", "потому что",
        "так как", "поскольку", "ибо", "чем", "пока", "после того как",
        "прежде чем", "с тех пор как", "для того чтобы", "несмотря на то что",
        "вследствие того что", "в связи с тем что", "при условии что",
        "хотя бы", "будто", "словно", "хоть", "лишь", "едва", "раз",
        "где", "куда", "откуда", "зачем", "почему", "отчего",
    }),
}


# ── Датаклассы результатов ───────────────────────────────────────────────────

@dataclass
class DiagnosticFinding:
    """Один вывод с доказательной базой."""
    label: str          # «мужской», «25–50 лет», «среднее» и т.д.
    confidence: str     # «вероятно», «предположительно», «данных недостаточно»
    score: float        # внутренний балл [0..1]
    evidence_for: List[str] = field(default_factory=list)   # признаки «за»
    evidence_against: List[str] = field(default_factory=list)  # признаки «против»


@dataclass
class FunctionWordProfile:
    """Частотный отпечаток служебных слов."""
    conjunctions: Dict[str, int] = field(default_factory=dict)    # союзы
    particles: Dict[str, int] = field(default_factory=dict)       # частицы
    prepositions: Dict[str, int] = field(default_factory=dict)    # предлоги
    introductory: Dict[str, int] = field(default_factory=dict)    # вводные слова
    total_function: int = 0
    diversity_index: float = 0.0  # уникальных типов / общее кол-во


@dataclass
class DiagnosticResult:
    gender: Optional[DiagnosticFinding] = None
    age: Optional[DiagnosticFinding] = None
    education: Optional[DiagnosticFinding] = None
    speech_culture: Optional[DiagnosticFinding] = None
    masquerade: Optional[DiagnosticFinding] = None
    function_words: Optional[FunctionWordProfile] = None
    sufficient_volume: bool = True   # ≥ 100 слов
    word_count: int = 0


# ── Движок ─────────────────────────────────────────────────────────────────

class DiagnosticEngine:
    """
    Диагностический анализатор по методике ИКЭ ФСБ России.
    Принимает результаты уже выполненного анализа (токены, метрики, ошибки, тематику).
    """

    MIN_WORDS = 100   # минимум для вывода (по методике)

    def analyze(
        self,
        tokens: list,
        metrics: dict,
        error_result=None,
        thematic_result=None,
    ) -> DiagnosticResult:
        from analyzer.stanza_backend import WORD_RE

        words = [t for t in tokens if WORD_RE.search(t.text) and t.pos != "PUNCT"]
        total = len(words)
        result = DiagnosticResult(word_count=total)

        if total < self.MIN_WORDS:
            result.sufficient_volume = False
            return result

        lemmas = [t.lemma.lower() for t in words]
        lemma_set = Counter(lemmas)

        # Служебные слова
        result.function_words = self._function_word_profile(tokens, lemmas)

        # Диагностические задачи
        result.gender         = self._diagnose_gender(tokens, lemmas, lemma_set,
                                                       metrics, thematic_result)
        result.age            = self._diagnose_age(tokens, lemmas, lemma_set,
                                                    metrics, thematic_result)
        result.education      = self._diagnose_education(tokens, lemmas,
                                                          metrics, error_result)
        result.speech_culture = self._diagnose_culture(tokens, lemmas,
                                                        metrics, error_result)
        result.masquerade     = self._diagnose_masquerade(tokens, metrics,
                                                           error_result)
        return result

    # ── Пол ─────────────────────────────────────────────────────────────────

    def _diagnose_gender(self, tokens, lemmas, lemma_set, metrics, thematic) -> DiagnosticFinding:
        score_m = 0.0   # очки «мужской»
        score_f = 0.0   # очки «женский»
        ev_m, ev_f = [], []

        total = len(lemmas)

        # 1. Повелительное наклонение глаголов → М
        imperative = sum(1 for t in tokens if "Наклонение: повелительное" in t.feats)
        if imperative > 0:
            rate = round(imperative / total * 100, 1)
            score_m += min(imperative / 5, 3.0)
            ev_m.append(f"Повелит. наклонение: {imperative} глаголов ({rate}%)")

        # 2. Слова категории состояния → Ж
        state_cnt = sum(lemma_set.get(w, 0) for w in _STATE_WORDS)
        if state_cnt > 0:
            rate = round(state_cnt / total * 100, 1)
            score_f += min(state_cnt / 3, 3.0)
            ev_f.append(f"Слова категории состояния: {state_cnt} ({rate}%)")

        # 3. Уменьшительно-ласкательные суффиксы → Ж
        dim_pattern = re.compile(r"(ечк|ичк|оньк|еньк|ушк|юшк|ышк|иньк|очк|инк)а?$")
        diminutives = [t.text for t in tokens if dim_pattern.search(t.lemma.lower())]
        if diminutives:
            score_f += min(len(diminutives) / 3, 3.0)
            uniq_dim = sorted(set(diminutives))
            ev_f.append(f"Уменьш.-ласк. суффиксы: {len(diminutives)} слов "
                        f"({', '.join(uniq_dim[:5])}…)" if len(uniq_dim) > 5
                        else f"Уменьш.-ласк. суффиксы: {', '.join(uniq_dim)}")

        # 4. Ограничительные частицы → Ж
        lim = sum(lemma_set.get(w, 0) for w in _LIMITING_PARTICLES)
        if lim > 0:
            score_f += min(lim / 4, 2.0)
            ev_f.append(f"Ограничит. частицы (только/лишь/именно): {lim}")

        # 5. Пространственные и временны́е наречия → М
        spatial_temporal = {"там", "здесь", "тут", "вчера", "сегодня", "завтра",
                            "потом", "затем", "сначала", "после", "прежде",
                            "слева", "справа", "впереди", "сзади", "рядом"}
        sp_cnt = sum(lemma_set.get(w, 0) for w in spatial_temporal)
        if sp_cnt >= 3:
            score_m += min(sp_cnt / 5, 2.0)
            ev_m.append(f"Пространственно-временные наречия: {sp_cnt}")

        # 6. Военная/силовая тематика → М
        if thematic:
            for ds in thematic.top_domains:
                if ds.key == "military" and ds.cosine > 0.05:
                    score_m += 3.0
                    ev_m.append(f"Военная/силовая тематика (cosine {ds.cosine:.3f})")
                elif ds.key == "law" and ds.cosine > 0.05:
                    score_m += 1.5
                    ev_m.append(f"Юридическая тематика (cosine {ds.cosine:.3f})")

        # 7. Бытовая/разговорная тематика → Ж
        if thematic:
            for ds in thematic.scores:
                if ds.key == "everyday" and ds.cosine > 0.05:
                    score_f += 2.0
                    ev_f.append(f"Бытовая/разговорная тематика (cosine {ds.cosine:.3f})")

        # 8. Подчинительные союзы → М (сложная аргументация)
        sconj = sum(1 for t in tokens if t.pos == "SCONJ")
        cconj = sum(1 for t in tokens if t.pos == "CCONJ")
        if sconj > cconj and sconj >= 3:
            score_m += 1.5
            ev_m.append(f"Подчинит. союзов больше сочинительных ({sconj} vs {cconj})")

        # 9. Морализаторские маркеры → Ж
        mor_cnt = sum(lemma_set.get(w, 0) for w in _MORALIZING)
        if mor_cnt >= 2:
            score_f += min(mor_cnt / 2, 2.0)
            ev_f.append(f"Морализаторская лексика: {mor_cnt} слов")

        # ── Итог ──
        total_score = score_m + score_f
        if total_score < 1.0:
            return DiagnosticFinding(
                label="неопределён", confidence="данных недостаточно",
                score=0.5, evidence_for=ev_m + ev_f)

        ratio_m = score_m / total_score
        if ratio_m > 0.65:
            label, conf = "мужской", ("вероятно" if ratio_m < 0.85 else "предположительно")
            return DiagnosticFinding(label=label, confidence=conf,
                                     score=ratio_m, evidence_for=ev_m, evidence_against=ev_f)
        elif ratio_m < 0.35:
            ratio_f = 1 - ratio_m
            label, conf = "женский", ("вероятно" if ratio_f < 0.85 else "предположительно")
            return DiagnosticFinding(label=label, confidence=conf,
                                     score=ratio_f, evidence_for=ev_f, evidence_against=ev_m)
        else:
            best = "мужской" if ratio_m >= 0.5 else "женский"
            return DiagnosticFinding(label=best, confidence="данных недостаточно",
                                     score=max(ratio_m, 1 - ratio_m),
                                     evidence_for=ev_m if best == "мужской" else ev_f,
                                     evidence_against=ev_f if best == "мужской" else ev_m)

    # ── Возраст ─────────────────────────────────────────────────────────────

    def _diagnose_age(self, tokens, lemmas, lemma_set, metrics, thematic) -> DiagnosticFinding:
        score = {"17–25": 0.0, "25–50": 0.0, "50–65": 0.0}
        evidence = {"17–25": [], "25–50": [], "50–65": []}

        total = len(lemmas)

        # 1. Молодёжный жаргон → 17–25
        jargon = [l for l in lemmas if l in _YOUTH_JARGON]
        if jargon:
            score["17–25"] += min(len(jargon) * 2, 6.0)
            evidence["17–25"].append(f"Молодёжный жаргон: {len(jargon)} слов "
                                     f"({', '.join(sorted(set(jargon))[:5])})")

        # 2. Интернет-аббревиатуры и сокращения → 17–25
        from analyzer.stanza_backend import WORD_RE
        abbrevs = [t.text for t in tokens if re.match(r'^[A-Za-zА-Яа-яЁё]{2,4}$', t.text)
                   and t.text.lower() in {"тг", "вк", "yt", "gg", "wp", "ez", "ок", "окей", "ок"}]
        if abbrevs:
            score["17–25"] += len(abbrevs) * 1.5
            evidence["17–25"].append(f"Интернет-сокращения: {', '.join(set(abbrevs))}")

        # 3. Архаизмы → 50–65
        archaic = [l for l in lemmas if l in _ARCHAISMS]
        if archaic:
            score["50–65"] += min(len(archaic) * 2.5, 6.0)
            evidence["50–65"].append(f"Архаизмы/устаревшие слова: {', '.join(set(archaic))}")

        # 4. Религиозная тематика → 50–65
        if thematic:
            for ds in thematic.scores:
                if ds.key == "religion" and ds.cosine > 0.04:
                    score["50–65"] += ds.cosine * 15
                    evidence["50–65"].append(f"Религиозная лексика (cosine {ds.cosine:.3f})")

        # 5. Морализаторские маркеры → 50–65
        mor_cnt = sum(lemma_set.get(w, 0) for w in _MORALIZING)
        if mor_cnt >= 2:
            score["50–65"] += min(mor_cnt, 3.0)
            evidence["50–65"].append(f"Морализаторская лексика: {mor_cnt} слов")

        # 6. Деловая/финансовая тематика → 25–50
        if thematic:
            for ds in thematic.top_domains:
                if ds.key == "economics" and ds.cosine > 0.04:
                    score["25–50"] += ds.cosine * 15
                    evidence["25–50"].append(f"Деловая/финансовая лексика (cosine {ds.cosine:.3f})")
                elif ds.key == "it" and ds.cosine > 0.04:
                    score["25–50"] += ds.cosine * 10
                    evidence["25–50"].append(f"IT-тематика (cosine {ds.cosine:.3f})")

        # 7. Сложность предложений (длинные → 25–50; простые → 17–25)
        add = metrics.get("дополнительно", {})
        avg_sent = add.get("Средняя длина предложения (слов)", 0)
        if avg_sent >= 18:
            score["25–50"] += 2.0
            evidence["25–50"].append(f"Средняя длина предложения: {avg_sent:.1f} слов (высокая)")
        elif avg_sent <= 9:
            score["17–25"] += 2.0
            evidence["17–25"].append(f"Средняя длина предложения: {avg_sent:.1f} слов (низкая)")

        # 8. Нестабильность навыка → 17–25
        disp = add.get("Дисперсия длины предложений", 0)
        if isinstance(disp, (int, float)) and disp > 80:
            score["17–25"] += 1.5
            evidence["17–25"].append(f"Высокая нестабильность предложений (дисперсия {disp:.1f})")

        # ── Итог ──
        best = max(score, key=lambda k: score[k])
        total_score = sum(score.values())

        if total_score < 1.0:
            return DiagnosticFinding(label="25–50 лет",
                                     confidence="данных недостаточно", score=0.4)

        conf_ratio = score[best] / total_score if total_score else 0
        conf = "вероятно" if conf_ratio >= 0.5 else "данных недостаточно"
        return DiagnosticFinding(
            label=f"{best} лет", confidence=conf,
            score=conf_ratio,
            evidence_for=evidence[best],
            evidence_against=[e for k, evs in evidence.items()
                               if k != best for e in evs],
        )

    # ── Уровень образования ─────────────────────────────────────────────────

    def _diagnose_education(self, tokens, lemmas, metrics, error_result) -> DiagnosticFinding:
        total = len(lemmas)
        add = metrics.get("дополнительно", {})

        ev_low, ev_mid, ev_high = [], [], []

        # 1. Ошибки на 200 слов (ключевой критерий методики)
        errors_per_200 = 0
        if error_result and hasattr(error_result, "total_unique_errors") and total > 0:
            errors_per_200 = round(error_result.total_unique_errors / total * 200, 1)
            label = f"Ошибок на 200 слов: {errors_per_200:.1f}"
            if errors_per_200 >= 10:
                ev_low.append(label + " (порог низкого: ≥10)")
            elif errors_per_200 >= 4:
                ev_mid.append(label + " (порог среднего: 4–9)")
            else:
                ev_high.append(label + " (порог высшего: <4)")

        # 2. Лексическое разнообразие (TTR)
        ttr = add.get("Лексическое разнообразие (TTR)", 0)
        if isinstance(ttr, float):
            if ttr >= 0.65:
                ev_high.append(f"TTR (лексич. богатство): {ttr:.3f} — высокий")
            elif ttr >= 0.45:
                ev_mid.append(f"TTR (лексич. богатство): {ttr:.3f} — средний")
            else:
                ev_low.append(f"TTR (лексич. богатство): {ttr:.3f} — низкий")

        # 3. Средняя длина предложения
        avg_sent = add.get("Средняя длина предложения (слов)", 0)
        if avg_sent >= 20:
            ev_high.append(f"Средняя длина предложения: {avg_sent:.1f} слов (высокая)")
        elif avg_sent >= 12:
            ev_mid.append(f"Средняя длина предложения: {avg_sent:.1f} слов (средняя)")
        else:
            ev_low.append(f"Средняя длина предложения: {avg_sent:.1f} слов (низкая)")

        # 4. Подчинительные союзы (сложноподч. предложения) → высокое образование
        sconj_count = sum(1 for t in tokens if t.pos == "SCONJ")
        sconj_rate = round(sconj_count / total * 100, 1) if total else 0
        if sconj_rate >= 5:
            ev_high.append(f"Подчинит. союзы: {sconj_count} ({sconj_rate}%) — сложный синтаксис")
        elif sconj_rate >= 2:
            ev_mid.append(f"Подчинит. союзы: {sconj_count} ({sconj_rate}%)")
        else:
            ev_low.append(f"Подчинит. союзы: {sconj_count} ({sconj_rate}%) — простой синтаксис")

        # 5. Причастия и деепричастия → высокое образование
        partic = sum(1 for t in tokens if "VerbForm=Part" in t.feats or "VerbForm=Conv" in t.feats)
        if partic > 0:
            rate = round(partic / total * 100, 1)
            if rate >= 5:
                ev_high.append(f"Причастия/деепричастия: {partic} ({rate}%) — книжный синтаксис")
            elif rate >= 2:
                ev_mid.append(f"Причастия/деепричастия: {partic} ({rate}%)")

        # ── Подсчёт баллов ──
        scores = {"низкое": len(ev_low), "среднее": len(ev_mid), "высшее": len(ev_high)}
        best = max(scores, key=lambda k: scores[k])
        total_ev = sum(scores.values())

        labels = {"низкое": "низкое / в пределах среднего",
                  "среднее": "среднее",
                  "высшее": "высшее / на уровне высшего"}
        ev_map = {"низкое": ev_low, "среднее": ev_mid, "высшее": ev_high}

        ratio = scores[best] / total_ev if total_ev else 0.5
        conf = "вероятно" if ratio >= 0.5 else "данных недостаточно"

        return DiagnosticFinding(
            label=labels[best], confidence=conf, score=ratio,
            evidence_for=ev_map[best],
            evidence_against=[e for k, ev in ev_map.items() if k != best for e in ev],
        )

    # ── Культура речи ────────────────────────────────────────────────────────

    def _diagnose_culture(self, tokens, lemmas, metrics, error_result) -> DiagnosticFinding:
        """Культура речи: низкая / средняя / высокая."""
        total = len(lemmas)
        lemma_set = Counter(lemmas)
        ev = {"низкая": [], "средняя": [], "высокая": []}

        # 1. Грубая/просторечная лексика
        crude = frozenset({"блин", "чёрт", "зараза", "дурак", "идиот", "придурок",
                            "козёл", "сволочь", "гад", "хам", "урод", "олень"})
        crude_cnt = sum(lemma_set.get(w, 0) for w in crude)
        if crude_cnt > 0:
            ev["низкая"].append(f"Грубая/сниженная лексика: {crude_cnt} слов")

        # 2. Вводные слова и обороты → высокая культура
        intro_cnt = sum(1 for t in tokens
                        if t.lemma.lower() in _INTRODUCTORY
                        or any(ph in t.text.lower() for ph in ["таким образом", "тем не менее",
                                                                 "следовательно", "во-первых"]))
        if intro_cnt >= 3:
            ev["высокая"].append(f"Вводные слова/обороты: {intro_cnt} употреблений")
        elif intro_cnt > 0:
            ev["средняя"].append(f"Вводные слова: {intro_cnt} употреблений")

        # 3. Синонимическое богатство (hapax ratio)
        hapax = metrics.get("дополнительно", {}).get("Доля hapax-лемм", 0)
        if isinstance(hapax, float):
            if hapax >= 0.60:
                ev["высокая"].append(f"Доля hapax-лемм: {hapax:.0%} — богатый словарь")
            elif hapax >= 0.40:
                ev["средняя"].append(f"Доля hapax-лемм: {hapax:.0%} — средний словарь")
            else:
                ev["низкая"].append(f"Доля hapax-лемм: {hapax:.0%} — ограниченный словарь")

        # 4. Стилистические ошибки
        if error_result and hasattr(error_result, "skill_levels"):
            for sl in error_result.skill_levels:
                if "стил" in sl.skill_name.lower() and sl.error_rate > 2:
                    ev["низкая"].append(f"Стилистические ошибки: {sl.error_count}")

        scores = {k: len(v) for k, v in ev.items()}
        best = max(scores, key=lambda k: scores[k]) if any(scores.values()) else "средняя"
        total_ev = sum(scores.values())
        ratio = scores[best] / total_ev if total_ev else 0.5
        conf = "вероятно" if ratio >= 0.5 else "данных недостаточно"

        return DiagnosticFinding(
            label=best, confidence=conf, score=ratio,
            evidence_for=ev[best],
            evidence_against=[e for k, evl in ev.items() if k != best for e in evl],
        )

    # ── Маскировка ──────────────────────────────────────────────────────────

    def _diagnose_masquerade(self, tokens, metrics, error_result) -> DiagnosticFinding:
        """
        Признаки маскировки: непоследовательность ошибок, несоответствие
        стилевого уровня и синтаксической сложности.
        """
        evidence = []
        score = 0.0

        from analyzer.stanza_backend import WORD_RE
        words = [t for t in tokens if WORD_RE.search(t.text) and t.pos != "PUNCT"]
        total = len(words)
        if total < 100:
            return DiagnosticFinding(label="анализ невозможен",
                                     confidence="объём текста недостаточен", score=0.0)

        add = metrics.get("дополнительно", {})

        # 1. Неравномерность ошибок по тексту
        if error_result and hasattr(error_result, "errors") and error_result.errors:
            block_size = max(total // 5, 20)
            positions = [e.position[0] for e in error_result.errors
                         if hasattr(e, "position") and e.position and e.position != (0, 0)]
            if positions and len(positions) >= 3:
                block_counts = Counter(p // block_size for p in positions)
                counts = list(block_counts.values())
                if len(counts) >= 2:
                    cv = statistics.pstdev(counts) / (statistics.mean(counts) + 0.001)
                    if cv > 1.2:
                        score += 2.5
                        evidence.append(f"Неравномерное распределение ошибок по тексту "
                                        f"(коэфф. вариации {cv:.2f} > 1.2)")

        # 2. Несоответствие лексики и синтаксиса
        ttr = add.get("Лексическое разнообразие (TTR)", 0)
        avg_sent = add.get("Средняя длина предложения (слов)", 0)
        if isinstance(ttr, float) and isinstance(avg_sent, (int, float)):
            ttr_high = ttr >= 0.60
            sent_low = avg_sent <= 8
            if ttr_high and sent_low:
                score += 2.0
                evidence.append(f"Богатый словарь (TTR {ttr:.2f}) + короткие предложения "
                                 f"({avg_sent:.1f} слов) — возможное занижение синтаксиса")

        # 3. Нестабильность длины предложений
        disp = add.get("Дисперсия длины предложений", 0)
        if isinstance(disp, (int, float)) and disp > 120:
            score += 1.5
            evidence.append(f"Аномально высокая вариативность длины предложений "
                             f"(дисперсия {disp:.1f})")

        if score >= 3.0:
            label = "признаки выявлены"
            conf = "вероятно"
        elif score >= 1.5:
            label = "отдельные признаки"
            conf = "предположительно"
        else:
            label = "признаков не выявлено"
            conf = ""
            evidence = ["Распределение ошибок и стилевой профиль последовательны"]

        return DiagnosticFinding(label=label, confidence=conf,
                                 score=min(score / 5, 1.0), evidence_for=evidence)

    # ── Служебные слова ──────────────────────────────────────────────────────

    def _function_word_profile(self, tokens, lemmas) -> FunctionWordProfile:
        profile = FunctionWordProfile()
        total_func = 0

        conj_counter = Counter()
        part_counter = Counter()
        prep_counter = Counter()
        intro_counter = Counter()

        text_lower = " ".join(t.text.lower() for t in tokens)

        # Фразовые вводные выражения
        for phrase in sorted(_INTRODUCTORY, key=len, reverse=True):
            count = text_lower.count(phrase)
            if count > 0:
                intro_counter[phrase] = count

        # Токенные служебные слова
        for tok in tokens:
            lemma = tok.lemma.lower()
            if tok.pos == "CCONJ" or tok.pos == "SCONJ":
                conj_counter[lemma] += 1
                total_func += 1
            elif tok.pos == "PART":
                if lemma not in {"бы", "б", "не", "ни"}:   # исключить синт. частицы
                    part_counter[lemma] += 1
                    total_func += 1
            elif tok.pos == "ADP":
                prep_counter[lemma] += 1
                total_func += 1

        total_func += sum(intro_counter.values())

        profile.conjunctions  = dict(conj_counter.most_common(20))
        profile.particles     = dict(part_counter.most_common(15))
        profile.prepositions  = dict(prep_counter.most_common(15))
        profile.introductory  = dict(intro_counter.most_common(10))
        profile.total_function = total_func

        all_types = (len(conj_counter) + len(part_counter) +
                     len(prep_counter) + len(intro_counter))
        profile.diversity_index = round(all_types / (total_func + 1), 3)

        return profile


# ── Синглтон ────────────────────────────────────────────────────────────────

_instance: Optional[DiagnosticEngine] = None


def get() -> DiagnosticEngine:
    global _instance
    if _instance is None:
        _instance = DiagnosticEngine()
    return _instance
