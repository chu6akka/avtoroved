"""Построить полный аудит производителей элементов профиля Автороведа."""
from __future__ import annotations

import csv
from pathlib import Path

import yaml


COLUMNS = (
    "producer", "feature_key", "label", "current_kind", "current_group",
    "current_subgroup", "current_id_value", "proposed_role", "proposed_group",
    "proposed_subgroup", "source_kind", "method_feature_id",
    "method_reference_informativeness", "automatic_or_expert", "notes",
)


def _row(key: str, label: str, kind: str, group: str, subgroup: str,
         old_id: str, role: str, source_kind: str, *, producer: str = "profile.py",
         method_id: str = "", reference: str = "", mode: str = "automatic",
         notes: str = "") -> dict:
    return dict(zip(COLUMNS, (
        producer, key, label, kind, group, subgroup, old_id, role, group,
        subgroup, source_kind, method_id, reference, mode, notes,
    )))


def active_rows() -> list[dict]:
    """Все типы строк, которые способен породить активный protocol/profile.py."""
    rows: list[dict] = []
    # Тематика: три зарегистрированных детектора и произвольный домен.
    for key, label, method_id in (
        ("politics", "Политическая направленность текста", "nn.smysl.political"),
        ("military", "Военная направленность текста", "nn.smysl.military"),
        ("everyday", "Бытовая тематика текста", "nn.smysl.everyday"),
    ):
        rows.append(_row(
            f"semantic.registered.{key}", label, "кандидат_признак", "смысловые",
            "тематические", "низкая", "METHOD_FEATURE", "METHOD",
            method_id=method_id, reference="низкая",
            notes="Cosine применяется только к обнаружению/надёжности детектора."))
    rows.append(_row(
        "semantic.arbitrary_domain", "Доминирующая тема: <домен>", "кандидат_признак",
        "смысловые", "тематические", "низкая", "AUX_METRIC", "ENGINEERING",
        notes="Незарегистрированный домен не является методическим признаком."))

    for key, label in (
        ("paragraph_count", "Число абзацев"),
        ("mean_paragraph_length", "Средняя длина абзаца (слов)"),
        ("word_count", "Всего слов"),
        ("sentence_count", "Всего предложений"),
        ("mean_sentence_length", "Средняя длина предложения (слов)"),
        ("sentence_length_variance", "Дисперсия длины предложений"),
    ):
        rows.append(_row(key, label, "счётчик", "текстологические", "архитектоника",
                         "", "AUX_METRIC", "ENGINEERING"))

    for key, label in (
        ("ttr", "Лексическое разнообразие (TTR)"),
        ("lemma_diversity", "Лемматическое разнообразие"),
        ("hapax_share", "Доля hapax-лемм"),
        ("mean_word_length", "Средняя длина слова (букв)"),
        ("register_layer_count", "Регистровый слой: <слой>"),
        ("nonliterary_ratio", "Доля нелитературной лексики"),
    ):
        rows.append(_row(key, label, "счётчик", "языковые", "лексические", "",
                         "AUX_METRIC", "ENGINEERING"))
    rows.append(_row("style_marker_count", "Стилевые маркеры: <класс>", "счётчик",
                     "языковые", "стилистические", "", "AUX_METRIC", "ENGINEERING"))

    for key, label, subgroup in (
        ("emoji_count", "Интернет-коммуникация: Эмодзи", "интернет-коммуникация"),
        ("emoticon_count", "Интернет-коммуникация: Эмотиконы", "интернет-коммуникация"),
        ("hashtag_count", "Интернет-коммуникация: Хэштеги", "интернет-коммуникация"),
        ("caps_count", "Интернет-коммуникация: Слова КАПСОМ", "интернет-коммуникация"),
        ("slang_count", "Интернет-коммуникация: Интернет-сленг", "интернет-коммуникация"),
        ("abbreviation_count", "Интернет-коммуникация: Аббревиатуры", "интернет-коммуникация"),
        ("repeated_punctuation_count", "Интернет-коммуникация: Повторная пунктуация",
         "пунктуационные"),
    ):
        rows.append(_row(key, label, "счётчик", "языковые", subgroup,
                         "высокая при count >= 2", "AUX_METRIC", "EXPERIMENTAL",
                         notes="Частота сохранена; автоматическая экспертная ценность удалена."))

    rows.append(_row("pos_share", "Доля POS: <часть речи>", "счётчик", "языковые",
                     "синтаксические", "", "AUX_METRIC", "ENGINEERING",
                     notes="Перенесено в морфологическую подгруппу."))
    rows[-1]["proposed_subgroup"] = "морфологические"
    for key, label, subgroup in (
        ("question_sentence_count", "Вопросительные предложения", "синтаксические"),
        ("exclamation_sentence_count", "Восклицательные предложения", "пунктуационные"),
        ("ellipsis_sentence_count", "Предложения с многоточием", "пунктуационные"),
    ):
        rows.append(_row(key, label, "счётчик", "языковые", subgroup, "",
                         "AUX_METRIC", "ENGINEERING"))

    for subgroup in ("орфографические", "пунктуационные", "грамматические",
                     "лексические", "стилистические"):
        rows.append(_row(
            f"error_hit.{subgroup}", "<тип ошибки>: <подтип>", "кандидат_признак",
            "языковые", subgroup, "err.significance/severity", "EVIDENCE", "ENGINEERING",
            notes="Rule id, fragment и detector reliability сохранены; severity не id value."))
    rows.append(_row(
        "suppressed_error_hit", "<ошибка, подавленная фильтром>", "кандидат_признак",
        "языковые", "<тип ошибки>", "", "EVIDENCE", "ENGINEERING",
        notes="Сохраняется для воспроизводимости и скрывается фильтром UI."))

    for key, label in (
        ("internet_slang_hit", "Интернет-сленг"), ("emoticon_hit", "Эмотикон"),
        ("emoji_hit", "Эмодзи"), ("repeated_punctuation_hit", "Повторная пунктуация"),
        ("hashtag_hit", "Хэштег"), ("caps_hit", "Слово КАПСОМ"),
    ):
        rows.append(_row(
            key, label, "кандидат_признак", "языковые", "интернет-коммуникация",
            "высокая при count >= 2", "EVIDENCE", "EXPERIMENTAL",
            notes="Повторяемость влияет только на detection reliability."))

    rows.append(_row(
        "marked_lexeme", "Маркированная лексика: <слой>", "кандидат_признак",
        "языковые", "лексические", "высокая для редких/некоторых слоёв", "EVIDENCE",
        "ENGINEERING", notes="Частотный ранг сохранён как справка, не экспертная оценка."))
    rows.append(_row(
        "ogorelkov.category", "Употребление: <класс>", "кандидат_признак",
        "языковые", "служебная лексика", "средняя", "AUX_METRIC", "ENGINEERING",
        notes="IPM/ratio — инструментальные измерения."))
    rows.append(_row(
        "ogorelkov.lemma_deviation", "Служебное слово <лемма>", "кандидат_признак",
        "языковые", "служебная лексика", "высокая", "EVIDENCE", "ENGINEERING",
        notes="Threshold отсеивает шум, но не задаёт экспертную ценность."))

    for skill in ("орфографический", "пунктуационный", "грамматический",
                  "лексико-фразеологический"):
        rows.append(_row(
            f"general_skill.{skill}", f"Степень развития: {skill} навык",
            "общий_признак", "языковые", skill, "высокая", "GENERAL_SKILL", "METHOD",
            mode="automatic measurement / expert interpretation",
            notes="Отдельный нейтральный контроль Вула/Минюста; не частный признак."))
    rows.append(_row(
        "general_skill.overall", "Общий уровень письменной речи", "общий_признак",
        "языковые", "общий уровень", "высокая", "GENERAL_SKILL", "METHOD",
        mode="automatic measurement / expert interpretation"))
    rows.append(_row(
        "psycho.marked_token", "Психолингвистический маркер: <слой>",
        "кандидат_признак", "психолингвистические", "лексические индикаторы",
        "средняя", "EVIDENCE", "ENGINEERING",
        notes="Единичная лексема не интерпретируется автоматически как свойство автора."))
    return rows


def legacy_rows(repo_root: Path) -> list[dict]:
    significance = {"low": "низкая", "medium": "средняя", "high": "высокая"}
    group = {
        "smyslovye": "смысловые", "textological": "текстологические",
        "linguistic": "языковые", "psycholinguistic": "психолингвистические",
    }
    rows: list[dict] = []
    registry_dir = repo_root / "avtoroved2" / "data" / "features"
    for path in sorted(registry_dir.glob("registry_*.yaml")):
        for feature in yaml.safe_load(path.read_text(encoding="utf-8")) or []:
            category = feature.get("category", "")
            method = feature.get("method", "expert")
            rows.append(_row(
                feature["id"], feature.get("name", ""), "registry_feature",
                group.get(category, category), feature.get("subgroup", ""),
                significance.get(feature.get("significance"), feature.get("significance", "")),
                "METHOD_FEATURE", "METHOD", producer="avtoroved2.legacy_registry",
                method_id=feature["id"],
                reference=significance.get(feature.get("significance"), ""),
                mode=method,
                notes=(f"Источник {path.name}, {feature.get('source', 'раздел не указан')}; "
                       "используется контуром avtoroved2, но не активным "
                       "avtoroved-main/protocol/profile.py.")))
    return rows


def main() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    output = repo_root / "avtoroved-main" / "docs" / "feature_registry_audit.csv"
    rows = active_rows() + legacy_rows(repo_root)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"{output}: {len(rows)} records, {len(rows) + 1} CSV lines")


if __name__ == "__main__":
    main()
