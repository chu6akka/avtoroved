"""Морфологические показатели в терминах русской грамматики.

Разметка Stanza (Universal Dependencies) переводится в традиционные категории:
причастие и деепричастие выделяются из глагола по признаку VerbForm, местоимения
объединяют UD PRON и DET, разряды местоимений определяются по лемме, слова
категории состояния (предикативы) — по закрытому списку лемм. Всё это машинная
разметка: отдельные словоформы может понадобиться проверить эксперту.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Callable

from authoroved_core.core.models import Metric, Span, Token


GROUP_PARTS = "Морфология: части речи"
GROUP_CATEGORIES = "Морфология: грамматические категории"
GROUP_PRONOUNS = "Морфология: разряды местоимений"
GROUP_SOKOLOVA = "Морфологические индексы идиостиля"
GROUP_SAE = "Морфологические коэффициенты"
GROUP_BIGRAMS = "Морфология: сочетания частей речи"
MORPHOLOGY_GROUPS = (GROUP_PARTS, GROUP_CATEGORIES, GROUP_PRONOUNS,
                     GROUP_SOKOLOVA, GROUP_SAE, GROUP_BIGRAMS)

MACHINE_NOTE = ("Основание — автоматическая разметка Stanza (Universal Dependencies), "
                "переведённая в категории русской грамматики; это не ручной "
                "морфологический разбор, отдельные словоформы требуют проверки.")

# Слова категории состояния: Stanza размечает их как ADV (реже ADJ, VERB).
PREDICATIVE_LEMMAS = frozenset({
    "можно", "нельзя", "нужно", "надо", "необходимо", "жалко", "жаль", "больно",
    "стыдно", "скучно", "смешно", "страшно", "странно", "интересно", "важно",
    "видно", "слышно", "понятно", "ясно", "пора", "некогда", "незачем", "негде",
    "некуда", "неоткуда", "грустно", "весело", "холодно", "тепло", "жарко",
    "душно", "темно", "светло", "тихо", "обидно", "досадно", "лень", "охота",
    "невозможно", "возможно", "трудно", "легко", "тяжело", "приятно", "неприятно",
    "хорошо", "плохо", "одиноко", "тревожно", "радостно", "совестно",
})
PREDICATIVE_ONLY = frozenset({"можно", "нельзя", "нужно", "надо", "жаль", "пора",
                              "некогда", "незачем", "негде", "некуда", "неоткуда",
                              "лень", "охота", "необходимо"})

# Разряды местоимений по традиционной грамматике русского языка.
PRONOUN_CLASSES = (
    ("personal", "Личные местоимения",
     {"я", "ты", "он", "она", "оно", "мы", "вы", "они"}),
    ("reflexive", "Возвратное местоимение «себя»", {"себя"}),
    ("possessive", "Притяжательные местоимения",
     {"мой", "твой", "свой", "наш", "ваш", "его", "её", "ее", "их"}),
    ("demonstrative", "Указательные местоимения",
     {"этот", "тот", "такой", "таков", "столько", "сей", "оный", "этакий", "то", "это"}),
    ("attributive", "Определительные местоимения",
     {"весь", "всякий", "каждый", "сам", "самый", "любой", "иной", "другой", "всё", "все"}),
    ("interrogative", "Вопросительно-относительные местоимения",
     {"кто", "что", "какой", "каков", "который", "чей", "сколько"}),
    ("negative", "Отрицательные местоимения",
     {"никто", "ничто", "никакой", "ничей", "некого", "нечего"}),
    ("indefinite", "Неопределённые местоимения",
     {"некто", "нечто", "некоторый", "некий", "несколько"}),
)
INDEFINITE_AFFIXES = ("-то", "-либо", "-нибудь", "кое-", "кой-")
PRON_TYPE_TO_CLASS = {"Prs": "personal", "Dem": "demonstrative", "Tot": "attributive",
                      "Int": "interrogative", "Rel": "interrogative", "Neg": "negative",
                      "Ind": "indefinite", "Rcp": "reflexive"}

# Русские названия частей речи для сочетаний (биграмм).
POS_SHORT = {
    "noun": "сущ.", "adjective": "прил.", "participle": "прич.", "gerund": "дееприч.",
    "verb": "гл.", "infinitive": "инф.", "predicative": "сл. сост.", "adverb": "нар.",
    "pronoun": "мест.", "numeral": "числ.", "preposition": "предл.", "conjunction": "союз",
    "particle": "част.", "interjection": "межд.", "other": "проч.",
}

# Грамматические категории: (признак UD, русское название, значения, какие слова считать).
CATEGORY_VALUES = (
    ("Case", "Падеж", {
        "Nom": "именительный", "Gen": "родительный", "Dat": "дательный",
        "Acc": "винительный", "Ins": "творительный", "Loc": "предложный",
        "Par": "второй родительный (частичный)", "Voc": "звательная форма",
    }),
    ("Number", "Число", {"Sing": "единственное", "Plur": "множественное", "Ptan": "только множественное"}),
    ("Gender", "Род", {"Masc": "мужской", "Fem": "женский", "Neut": "средний", "Com": "общий"}),
    ("Animacy", "Одушевлённость", {"Anim": "одушевлённые", "Inan": "неодушевлённые"}),
    ("Aspect", "Вид", {"Perf": "совершенный", "Imp": "несовершенный"}),
    ("Tense", "Время", {"Past": "прошедшее", "Pres": "настоящее", "Fut": "будущее"}),
    ("Mood", "Наклонение", {"Ind": "изъявительное", "Imp": "повелительное", "Cnd": "сослагательное"}),
    ("Person", "Лицо", {"1": "1-е лицо", "2": "2-е лицо", "3": "3-е лицо"}),
    ("Voice", "Залог", {"Act": "действительный", "Pass": "страдательный",
                        "Mid": "возвратная форма на -ся (средний залог)"}),
    ("VerbForm", "Форма глагола", {"Fin": "спрягаемая (личная) форма", "Inf": "инфинитив",
                                   "Part": "причастие", "Conv": "деепричастие"}),
    ("Degree", "Степень сравнения", {"Pos": "положительная", "Cmp": "сравнительная",
                                     "Sup": "превосходная"}),
    ("Variant", "Полнота формы", {"Short": "краткая форма", "Long": "полная форма"}),
    ("Polarity", "Отрицание", {"Neg": "отрицательная", "Pos": "утвердительная"}),
    ("NumType", "Разряд числительного", {"Card": "количественное", "Ord": "порядковое",
                                         "Coll": "собирательное", "Frac": "дробное"}),
    ("Foreign", "Иноязычная запись", {"Yes": "иноязычное слово"}),
    ("Abbr", "Сокращение", {"Yes": "сокращённое написание"}),
)


def _number(value: float, digits: int = 3) -> str:
    return f"{value:.{digits}f}".rstrip("0").rstrip(".").replace(".", ",")


def _lemma(token: Token) -> str:
    return (token.lemma or token.text).casefold().replace("ё", "е")


def _is_predicative(token: Token, has_subject: bool) -> bool:
    """Слово категории состояния: «нужно», «жаль», «холодно» в безличном предложении.

    Stanza размечает такие слова как ADV или как краткое прилагательное среднего рода
    («Нужно» → лемма «нужный»), поэтому проверяется словоформа, а не только лемма.
    """
    form = token.text.casefold().replace("ё", "е")
    if token.pos not in {"ADV", "ADJ"}:
        return False
    if form in PREDICATIVE_ONLY:
        return True
    if form not in PREDICATIVE_LEMMAS or has_subject:
        return False
    if token.pos == "ADJ":
        return (token.feats.get("Variant") == "Short" and token.feats.get("Gender") == "Neut"
                and token.feats.get("Number", "Sing") == "Sing")
    return token.dependency.split(":", 1)[0] in {"root", "conj", "ccomp", "advcl", "parataxis"}


def morph_class(token: Token, has_subject: bool = True) -> str:
    """Часть речи в традиционной русской грамматике на основе UPOS и признаков.

    has_subject — есть ли у слова зависимое-подлежащее (nsubj); без него сказуемое
    «холодно», «интересно» понимается как слово категории состояния.
    """
    pos, feats = token.pos, token.feats
    verb_form = feats.get("VerbForm")
    dependency = token.dependency.split(":", 1)[0] if token.dependency else ""
    if verb_form == "Part":
        return "participle"
    if verb_form == "Conv":
        return "gerund"
    if pos in {"VERB", "AUX"}:
        return "infinitive" if verb_form == "Inf" else "verb"
    if _is_predicative(token, has_subject):
        return "predicative"
    if pos in {"NOUN", "PROPN"}:
        return "noun"
    if pos == "ADJ":
        return "adjective"
    if pos == "ADV":
        return "adverb"
    if pos in {"PRON", "DET"}:
        return "pronoun"
    if pos == "NUM":
        return "numeral"
    if pos == "ADP":
        return "preposition"
    if pos in {"CCONJ", "SCONJ"} or (pos == "PART" and dependency == "cc"):
        return "conjunction"
    if pos == "PART":
        return "particle"
    if pos == "INTJ":
        return "interjection"
    return "other"


_classify = morph_class

PART_OF_SPEECH = (
    ("noun", "Существительные", "UD NOUN и PROPN"),
    ("adjective", "Прилагательные", "UD ADJ без слов категории состояния"),
    ("numeral", "Числительные", "UD NUM"),
    ("pronoun", "Местоимения", "UD PRON и DET (в русской грамматике — одна часть речи)"),
    ("verb", "Глаголы в спрягаемой форме", "UD VERB и AUX с VerbForm=Fin или без формы"),
    ("infinitive", "Инфинитивы", "UD VERB/AUX с VerbForm=Inf"),
    ("participle", "Причастия", "признак VerbForm=Part"),
    ("gerund", "Деепричастия", "признак VerbForm=Conv"),
    ("adverb", "Наречия", "UD ADV без слов категории состояния"),
    ("predicative", "Слова категории состояния", "UD ADV/ADJ с леммой из закрытого списка предикативов"),
    ("preposition", "Предлоги", "UD ADP"),
    ("conjunction", "Союзы", "UD CCONJ и SCONJ, а также PART с синтаксической меткой cc"),
    ("particle", "Частицы", "UD PART"),
    ("interjection", "Междометия", "UD INTJ"),
)


def pronoun_class(token: Token) -> str | None:
    if token.pos not in {"PRON", "DET"}:
        return None
    lemma = _lemma(token)
    for key, _, lemmas in PRONOUN_CLASSES:
        if lemma in {item.replace("ё", "е") for item in lemmas}:
            return key
    if lemma.endswith(INDEFINITE_AFFIXES[:3]) or lemma.startswith(INDEFINITE_AFFIXES[3:]):
        return "indefinite"
    if lemma.startswith("ни"):
        return "negative"
    if lemma.startswith("не") and len(lemma) > 3:
        return "indefinite"
    return PRON_TYPE_TO_CLASS.get(token.feats.get("PronType", ""))


def _words(tokens: list[Token]) -> list[Token]:
    return [token for token in tokens if token.pos not in {"PUNCT", "SYM"}
            and any(char.isalpha() for char in token.text)]


def _spans(tokens) -> tuple[Span, ...]:
    return tuple(token.span for token in tokens if token.span is not None)


def _share(count: int, total: int) -> str:
    return f"{count} · {_number(count / total * 100, 2)} %" if total else f"{count}"


def _ratio(numerator: int | None, denominator: int | None) -> str:
    if numerator is None or denominator is None:
        return "Не рассчитывается автоматически"
    if not denominator:
        return f"Нет данных: знаменатель равен нулю (числитель {numerator})"
    return f"{_number(numerator / denominator)} ({numerator} / {denominator})"


def _counts_metric(title: str, selected: list[Token], total: int, explanation: str, group: str) -> Metric:
    return Metric(title, _share(len(selected), total), explanation, group, _spans(selected))


def morphology_metrics(tokens: list[Token]) -> list[Metric]:
    words = _words(tokens)
    total = len(words)
    if not total:
        return []
    with_subject = {(token.sentence, token.head) for token in tokens
                    if token.dependency.split(":", 1)[0] in {"nsubj", "csubj"}
                    and token.pos not in {"VERB", "AUX"}}
    classes = {id(token): _classify(token, (token.sentence, token.index) in with_subject)
               for token in words}

    def morph_class(token: Token) -> str:
        return classes[id(token)]

    by_class: dict[str, list[Token]] = defaultdict(list)
    for token in words:
        by_class[morph_class(token)].append(token)
    count = {key: len(value) for key, value in by_class.items()}

    def n(*keys: str) -> int:
        return sum(count.get(key, 0) for key in keys)

    def select(predicate: Callable[[Token], bool]) -> list[Token]:
        return [token for token in words if predicate(token)]

    metrics: list[Metric] = []

    # 1. Части речи в традиционной классификации.
    for key, title, basis in PART_OF_SPEECH:
        if not count.get(key):
            continue
        metrics.append(_counts_metric(
            title, by_class[key], total,
            f"Количество и доля от всех слов текста. Основание: {basis}. {MACHINE_NOTE}", GROUP_PARTS))
    propn = select(lambda t: t.pos == "PROPN")
    if propn:
        metrics.append(_counts_metric(
            "Имена собственные (в составе существительных)", propn, total,
            f"UD PROPN; доля от всех слов. {MACHINE_NOTE}", GROUP_PARTS))
    short_adj = select(lambda t: morph_class(t) == "adjective" and t.feats.get("Variant") == "Short")
    if short_adj:
        metrics.append(_counts_metric(
            "Краткие прилагательные", short_adj, total,
            f"Прилагательные с признаком Variant=Short; доля от всех слов. {MACHINE_NOTE}", GROUP_PARTS))
    short_part = select(lambda t: morph_class(t) == "participle" and t.feats.get("Variant") == "Short")
    if short_part:
        metrics.append(_counts_metric(
            "Краткие причастия", short_part, total,
            f"Причастия с признаком Variant=Short; доля от всех слов. {MACHINE_NOTE}", GROUP_PARTS))
    content = n("noun", "adjective", "numeral", "pronoun", "verb", "infinitive",
                "participle", "gerund", "adverb", "predicative")
    service = n("preposition", "conjunction", "particle")
    metrics.append(Metric(
        "Знаменательные слова", _share(content, total),
        "Существительные, прилагательные, числительные, местоимения, глаголы во всех формах, "
        f"наречия и слова категории состояния. {MACHINE_NOTE}", GROUP_PARTS))
    metrics.append(Metric(
        "Служебные слова", _share(service, total),
        f"Предлоги, союзы и частицы. {MACHINE_NOTE}", GROUP_PARTS,
        _spans(by_class["preposition"] + by_class["conjunction"] + by_class["particle"])))

    # 2. Грамматические категории: распределение значений среди слов, у которых категория размечена.
    for feature, title, values in CATEGORY_VALUES:
        bearing = [token for token in words if token.feats.get(feature) in values]
        if not bearing:
            continue
        distribution = Counter(token.feats[feature] for token in bearing)
        for code, value_title in values.items():
            if not distribution.get(code):
                continue
            selected = [token for token in bearing if token.feats[feature] == code]
            metrics.append(Metric(
                f"{title}: {value_title}", _share(len(selected), len(bearing)),
                f"Доля от всех {len(bearing)} словоформ, у которых Stanza указала категорию "
                f"«{title.casefold()}» (признак UD {feature}={code}). {MACHINE_NOTE}",
                GROUP_CATEGORIES, _spans(selected)))
    nominal = [token for token in words if morph_class(token) in {"noun", "pronoun"} and "Case" in token.feats]
    if nominal:
        cases = Counter(token.feats["Case"] for token in nominal)
        direct = cases.get("Nom", 0) + cases.get("Acc", 0)
        metrics.append(Metric(
            "Прямые падежи существительных и местоимений", _share(direct, len(nominal)),
            "Именительный и винительный падежи среди всех падежных форм существительных и "
            f"местоимений; остальные падежи — косвенные. {MACHINE_NOTE}", GROUP_CATEGORIES,
            _spans([t for t in nominal if t.feats["Case"] in {"Nom", "Acc"}])))
    reflexive_verbs = select(lambda t: morph_class(t) in {"verb", "infinitive", "participle", "gerund"}
                             and t.text.casefold().endswith(("ся", "сь")))
    verbs_all = select(lambda t: morph_class(t) in {"verb", "infinitive", "participle", "gerund"})
    if verbs_all:
        metrics.append(Metric(
            "Возвратные глагольные формы (-ся/-сь)", _share(len(reflexive_verbs), len(verbs_all)),
            "Доля глагольных форм (включая инфинитив, причастие и деепричастие), оканчивающихся "
            f"на -ся или -сь. Определяется по написанию. {MACHINE_NOTE}", GROUP_CATEGORIES,
            _spans(reflexive_verbs)))

    # 3. Разряды местоимений.
    pronouns = by_class["pronoun"]
    if pronouns:
        grouped: dict[str, list[Token]] = defaultdict(list)
        for token in pronouns:
            grouped[pronoun_class(token) or "other"].append(token)
        for key, title, _ in PRONOUN_CLASSES:
            if grouped.get(key):
                metrics.append(Metric(
                    title, _share(len(grouped[key]), len(pronouns)),
                    f"Доля от всех {len(pronouns)} местоимений (UD PRON и DET). Разряд определён по "
                    "лемме; «его/её/их» в роли притяжательного и личного по форме совпадают, "
                    "относительные и вопросительные не разграничиваются.", GROUP_PRONOUNS,
                    _spans(grouped[key])))
        if grouped.get("other"):
            metrics.append(Metric(
                "Местоимения без определённого разряда", _share(len(grouped["other"]), len(pronouns)),
                "Лемма не входит в списки разрядов; требуется проверка экспертом.", GROUP_PRONOUNS,
                _spans(grouped["other"])))

    # 4. Двадцать индексов идиостиля (ЛР № 11, Т. П. Соколова, МГЮА).
    sentences = {token.sentence for token in words}
    sentence_count = len(sentences) or 1
    noun_all, pron_all = n("noun"), n("pronoun")
    pron_substantive = len(select(lambda t: t.pos == "PRON"))
    verbs_finite = n("verb", "infinitive")
    verbs_with_forms = n("verb", "infinitive", "participle", "gerund")
    adj, adv, num = n("adjective"), n("adverb"), n("numeral")
    prep, conj, particle = n("preposition"), n("conjunction"), n("particle")
    determiners = len(select(lambda t: t.pos == "DET"))
    non_notional = prep + conj + particle + determiners + n("interjection")
    personal = len([t for t in pronouns if pronoun_class(t) == "personal"])
    tense = Counter(t.feats.get("Tense") for t in words
                    if morph_class(t) == "verb" and t.feats.get("Tense"))
    case_forms = [t for t in words if t.pos in {"NOUN", "PROPN", "PRON"} and "Case" in t.feats]
    nom_gen = sum(t.feats["Case"] in {"Nom", "Gen"} for t in case_forms)
    predicatives = n("predicative")
    sokolova = (
        ("Существительные / объём текста", noun_all, total),
        ("Местоимения / объём текста", pron_all, total),
        ("Глаголы (все формы) / объём текста", verbs_with_forms, total),
        ("Местоимения-существительные / незнаменательные слова", pron_substantive, non_notional),
        ("Личные местоимения / все местоимения", personal, pron_all),
        ("Имена собственные / все существительные", len(propn), noun_all),
        ("Абстрактные / конкретные существительные", None, None),
        ("Глаголы настоящего и будущего времени / прошедшего времени",
         tense.get("Pres", 0) + tense.get("Fut", 0), tense.get("Past", 0)),
        ("Существительные / (прилагательные + местоимения-прилагательные + частицы)",
         noun_all, adj + determiners + particle),
        ("Существительные / местоимения", noun_all, pron_all),
        ("Прилагательные / объём текста", adj, total),
        ("Причастия / объём текста", n("participle"), total),
        ("Деепричастия / объём текста", n("gerund"), total),
        ("Наречия / объём текста", adv, total),
        ("Незнаменательные слова / число предложений", non_notional, sentence_count),
        ("Именные части речи / (глаголы + слова категории состояния)",
         noun_all + adj + adv + num + pron_all, verbs_with_forms + predicatives),
        ("Служебные слова / объём текста", service, total),
        ("Союзы / предлоги", conj, prep),
        ("(Именительный + родительный падежи) / все падежные формы существительных и местоимений",
         nom_gen, len(case_forms)),
        ("(Глаголы + существительные) / объём текста", verbs_with_forms + noun_all, total),
    )
    for index, (title, numerator, denominator) in enumerate(sokolova, 1):
        explanation = (
            "Индекс идиостиля по методике лабораторной работы № 11 (Т. П. Соколова, МГЮА): "
            "отношение числителя к знаменателю; объём текста — число слов. ")
        if numerator is None:
            explanation = ("Требует семантической разметки существительных (абстрактные/конкретные), "
                           "которой нет в Stanza; определяется экспертом вручную.")
        metrics.append(Metric(f"Индекс {index:02d}. {title}", _ratio(numerator, denominator),
                              explanation + MACHINE_NOTE, GROUP_SOKOLOVA))

    # 5. Двадцать коэффициентов по методике судебной автороведческой экспертизы (С. М. Вул, Е. И. Галяшина).
    verbs_personal = n("verb")
    short_all = len(short_adj)
    possessive = len([t for t in pronouns if pronoun_class(t) == "possessive"])
    sae = (
        ("Местоимения / текст", pron_all, total),
        ("Глаголы / текст", verbs_finite, total),
        ("Прилагательные / текст", adj, total),
        ("Наречия / текст", adv, total),
        ("Краткие прилагательные / все прилагательные", short_all, adj),
        ("Притяжательные местоимения / все местоимения", possessive, pron_all),
        ("Прилагательные / существительные", adj, noun_all),
        ("Местоимения / прилагательные", pron_all, adj),
        ("Существительные / глаголы", noun_all, verbs_finite),
        ("Местоимения / глаголы", pron_all, verbs_finite),
        ("Числительные / текст", num, total),
        ("Предлоги / текст", prep, total),
        ("Частицы / текст", particle, total),
        ("Союзы / текст", conj, total),
        ("Наречия / прилагательные", adv, adj),
        ("Причастия / текст", n("participle"), total),
        ("Деепричастия / текст", n("gerund"), total),
        ("Глаголы / наречия", verbs_finite, adv),
        ("(Прилагательные + причастия) / деепричастия", adj + n("participle"), n("gerund")),
        ("(Прилагательные + числительные) / текст", adj + num, total),
    )
    for index, (title, numerator, denominator) in enumerate(sae, 1):
        metrics.append(Metric(
            f"Коэффициент {index:02d}. {title}", _ratio(numerator, denominator),
            "Морфологический коэффициент по методике судебной автороведческой экспертизы "
            "(С. М. Вул, Е. И. Галяшина). «Текст» — число слов; «глаголы» — спрягаемые формы и "
            f"инфинитив без причастий и деепричастий (личных форм: {verbs_personal}). {MACHINE_NOTE}",
            GROUP_SAE))
    ratios = (
        ("Индекс номинативности: существительные / глаголы (все формы)", noun_all, verbs_with_forms),
        ("Индекс качественности: (прилагательные + наречия) / (существительные + глаголы)",
         adj + adv, noun_all + verbs_with_forms),
        ("Индекс предметности: (существительные + прилагательные) / (глаголы + наречия)",
         noun_all + adj, verbs_with_forms + adv),
        ("Индекс местоименности: местоимения / существительные", pron_all, noun_all),
        ("Индекс динамичности: глаголы (все формы) / объём текста", verbs_with_forms, total),
        ("Индекс связности: (предлоги + союзы) / число предложений", prep + conj, sentence_count),
        ("Знаменательные / служебные слова", content, service),
        ("Причастия / деепричастия", n("participle"), n("gerund")),
        ("Совершенный / несовершенный вид глаголов",
         len(select(lambda t: t.feats.get("Aspect") == "Perf")),
         len(select(lambda t: t.feats.get("Aspect") == "Imp"))),
    )
    for title, numerator, denominator in ratios:
        metrics.append(Metric(
            title, _ratio(numerator, denominator),
            "Дополнительный стилеметрический индекс: отношение числителя к знаменателю по "
            f"частеречной разметке. Порогов и нормативных значений нет. {MACHINE_NOTE}", GROUP_SAE))

    # 6. Сочетания частей речи в линейном порядке слов внутри предложения.
    by_sentence: dict[int, list[Token]] = defaultdict(list)
    for token in words:
        by_sentence[token.sentence].append(token)
    pairs: Counter = Counter()
    pair_spans: dict[tuple[str, str], list[Span]] = defaultdict(list)
    for sentence in by_sentence.values():
        for left, right in zip(sentence, sentence[1:]):
            key = (morph_class(left), morph_class(right))
            pairs[key] += 1
            if left.span is not None and right.span is not None:
                pair_spans[key].append(Span(left.span.start, right.span.end))
    bigram_total = sum(pairs.values())
    for (left, right), value in sorted(pairs.items(), key=lambda item: (-item[1], item[0]))[:20]:
        metrics.append(Metric(
            f"Сочетание {POS_SHORT[left]} + {POS_SHORT[right]}", _share(value, bigram_total),
            f"Доля от всех {bigram_total} пар соседних слов внутри предложения (частеречные "
            f"биграммы; Литвинова и др., 2015–2016). {MACHINE_NOTE}", GROUP_BIGRAMS,
            tuple(pair_spans[(left, right)])))
    return metrics
