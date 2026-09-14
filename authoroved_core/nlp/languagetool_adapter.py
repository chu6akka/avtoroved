"""Штатный локальный CLI LanguageTool. Ни HTTP, ни сервера, ни загрузок."""
import json
import os
import subprocess
from hashlib import sha256
from pathlib import Path

from authoroved_core.core.models import Candidate, Span
from authoroved_core.nlp.settings import LocalSettings

CATEGORY_LABELS = {
    "TYPOS": "Орфография", "SPELLING": "Орфография", "CASING": "Регистр букв",
    "GRAMMAR": "Грамматика", "PUNCTUATION": "Пунктуация", "TYPOGRAPHY": "Типографика",
    "STYLE": "Стилистическая рекомендация", "REDUNDANCY": "Избыточность",
    "SEMANTICS": "Словоупотребление", "CONFUSED_WORDS": "Смешение слов",
    "COLLOQUIALISMS": "Рекомендация по словоупотреблению",
}

UNKNOWN_WORD_RULES = {"MORFOLOGIK_RULE_RU_RU"}
UNKNOWN_WORD_CATEGORY = "Слово не распознано словарём"
UNKNOWN_WORD_EXPLANATION = (
    "LanguageTool не нашёл эту форму в своём словаре. Это ещё не означает ошибку: "
    "в тексте может быть разговорное, диалектное, профессиональное или новое слово, "
    "имя либо намеренная авторская форма. Предлагаемое раздельное написание может быть "
    "лишь догадкой словаря, а не исправлением. Словоформу классифицирует эксперт."
)


def utf16_boundaries(text: str) -> dict[int, int]:
    boundaries, units = {0: 0}, 0
    for index, char in enumerate(text):
        units += len(char.encode("utf-16-le")) // 2
        boundaries[units] = index + 1
    return boundaries


def candidates_from_matches(document_id: str, text: str, matches) -> list[Candidate]:
    result = []
    boundaries = utf16_boundaries(text)
    for match in matches:
        # Оба конца Java UTF-16 переводятся в индексы исходной строки Python.
        start, length = match["offset"], match["length"]
        if start not in boundaries or start + length not in boundaries or length < 0:
            raise ValueError("LanguageTool вернул некорректный диапазон текста; результат не принят.")
        span = Span(boundaries[start], boundaries[start + length])
        rule_id = match["rule"]["id"]
        category = CATEGORY_LABELS.get(match["rule"].get("category", {}).get("id", "").upper(), "Другая рекомендация LanguageTool")
        explanation = match["message"]
        if rule_id in UNKNOWN_WORD_RULES:
            category = UNKNOWN_WORD_CATEGORY
            explanation = UNKNOWN_WORD_EXPLANATION
        identity = f"{document_id}:{rule_id}:{start}:{length}"
        result.append(Candidate(sha256(identity.encode()).hexdigest()[:24], document_id,
                                category, category, explanation, text[span.start:span.end],
                                span, rule_id, tuple(r["value"] for r in match.get("replacements", []))))
    return result


class LanguageToolAdapter:
    def __init__(self, settings: LocalSettings):
        self.settings = settings

    def analyze(self, document_id: str, text: str) -> tuple[list[Candidate], dict]:
        directory = Path(self.settings.languagetool_dir)
        jar = directory / "languagetool-commandline.jar"
        if not jar.is_file():
            raise RuntimeError("Не найден локальный LanguageTool. Укажите папку в настройках.")
        java = Path(self.settings.java_executable)
        if not java.is_file():
            raise RuntimeError("Не найдена Java. Укажите java.exe в настройках.")
        process = subprocess.run(
            [str(java), "-Dfile.encoding=UTF-8", "-jar", str(jar), "--json", "--language", "ru-RU",
             "--encoding", "utf-8", "-"], input=text.encode("utf-8"),
            capture_output=True, timeout=120, check=True,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        response = json.loads(process.stdout.decode("utf-8"))
        if response.get("warnings", {}).get("incompleteResults"):
            raise RuntimeError("LanguageTool вернул неполный результат проверки.")
        return candidates_from_matches(document_id, text, response["matches"]), {
            "version": response.get("software", {}).get("version", "unknown"),
            "build_date": response.get("software", {}).get("buildDate"),
            "distribution": directory.name, "directory": str(directory), "java": str(java),
            "mode": "local-cli", "jar_sha256": sha256(jar.read_bytes()).hexdigest(),
        }
