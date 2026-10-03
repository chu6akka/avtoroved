"""Пометки о пригодности показателей по итогам проверки на корпусе.

Профиль `methodology/coefficient_validity_profile.json` получен проверкой на 120
авторах (`tools/coefficient_validity`). Здесь он превращается в пояснения для
эксперта: устойчив ли показатель, не отражает ли он тему вместо автора, хватает ли
объёма текста. Это сведения, а не нормативы: ни один показатель не скрывается и
не блокируется, вывод об авторстве по ним не делается.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import json
from pathlib import Path

DEFAULT_PROFILE = Path(__file__).resolve().parents[1] / "methodology" / "coefficient_validity_profile.json"

STATUS_LABELS = {
    "stable": "устойчивый показатель",
    "weak": "слабый показатель",
    "topic": "зависит от темы и жанра",
    "uninformative": "неинформативный показатель",
}
CLASSIC_PREFIXES = ("Индекс ", "Коэффициент ")


def _number(value: float) -> str:
    return f"{value:.2f}".replace(".", ",")


@dataclass(frozen=True)
class CoefficientProfile:
    metrics: dict
    source: str = ""
    max_tested_words: int = 0

    @classmethod
    def load(cls, path: Path = DEFAULT_PROFILE) -> "CoefficientProfile":
        """Профиль из файла; без файла — пустой профиль (пометок просто нет)."""
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return cls({})
        return cls(data.get("metrics", {}), data.get("source", ""), int(data.get("max_tested_words") or 0))

    def status(self, name: str) -> str | None:
        entry = self.metrics.get(name)
        return entry["status"] if entry else None

    def label(self, name: str) -> str | None:
        status = self.status(name)
        return STATUS_LABELS.get(status) if status else None

    def validity_note(self, name: str) -> str | None:
        entry = self.metrics.get(name)
        if not entry:
            return None
        auc = _number(entry["auc"]) if entry.get("auc") is not None else "—"
        basis = "По проверке на 120 авторах"
        return {
            "stable": f"{basis} показатель устойчиво различает авторов (AUC {auc}), в том числе на "
                      "текстах без общих тем; самостоятельным основанием вывода всё равно не служит.",
            "weak": f"{basis} показатель различает авторов слабо (AUC {auc}) и полезен лишь в совокупности "
                    "с другими.",
            "topic": f"{basis} различие по показателю исчезает на текстах без общих тем: он отражает тему и "
                     "жанр, а не автора. При разной тематике материалов не интерпретировать.",
            "uninformative": f"{basis} показатель не отличается от случайного и сведений об авторе не несёт.",
        }[entry["status"]]

    def volume_note(self, name: str, words: int | None) -> str | None:
        """Предупреждение, если объём меньше того, с которого значение устойчиво (±20 %)."""
        entry = self.metrics.get(name)
        if not entry or not words:
            return None
        threshold = entry.get("min_words_20")
        if threshold is None:
            return (f"Даже на {self.max_tested_words} словах значение отклоняется от устойчивого более "
                    f"чем на 20 %; при объёме {words} слов оно случайно.")
        if words < threshold:
            return (f"При объёме {words} слов значение может отклоняться от устойчивого более чем на 20 % "
                    f"(устойчиво с ~{threshold} слов).")
        return None

    def note(self, name: str, words: int | None = None) -> str | None:
        parts = [part for part in (self.validity_note(name), self.volume_note(name, words)) if part]
        return " ".join(parts) or None

    def volume_summary(self, words: int | None) -> str | None:
        """Сводка для раздела ограничений: сколько классических коэффициентов устойчивы при таком объёме."""
        if not words:
            return None
        classic = {name: entry for name, entry in self.metrics.items()
                   if name.startswith(CLASSIC_PREFIXES) and entry["status"] != "uninformative"}
        if not classic:
            return None
        stable = sum(1 for entry in classic.values()
                     if entry.get("min_words_20") is not None and entry["min_words_20"] <= words)
        return (f"Объём меньшего текста — {words} слов. По проверке на 120 авторах при таком объёме "
                f"устойчивы (отклонение до 20 %) {stable} из {len(classic)} информативных классических "
                "коэффициентов; значения остальных ориентирующие.")


@lru_cache(maxsize=1)
def default_profile() -> CoefficientProfile:
    return CoefficientProfile.load()
