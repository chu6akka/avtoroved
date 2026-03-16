"""
Тематические словари для профессиональной атрибуции текстов.
10 тематических областей с лексическими базами.
"""
from __future__ import annotations
import json
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "thematic")

DOMAIN_META = {
    "law":        {"label": "Юридическая / правовая",     "color": "#1565c0"},
    "medicine":   {"label": "Медицинская / фармацевтика",  "color": "#c62828"},
    "it":         {"label": "IT / цифровые технологии",   "color": "#00695c"},
    "economics":  {"label": "Экономика / финансы",         "color": "#f57f17"},
    "military":   {"label": "Военная / силовые структуры", "color": "#4e342e"},
    "science":    {"label": "Научная / академическая",     "color": "#6a1b9a"},
    "religion":   {"label": "Религиозная / духовная",      "color": "#880e4f"},
    "politics":   {"label": "Политическая / государственная","color": "#1a237e"},
    "sports":     {"label": "Спортивная / физкультура",    "color": "#2e7d32"},
    "everyday":   {"label": "Бытовая / разговорная",       "color": "#37474f"},
}


@dataclass
class ThematicResult:
    domains: Dict[str, dict] = field(default_factory=dict)
    top_domains: List[str] = field(default_factory=list)
    total_words: int = 0


class ThematicAnalyzer:
    """Анализ тематической принадлежности текста по лексическим словарям."""

    _cache: Dict[str, set] = {}

    def load_domain(self, domain: str) -> set:
        if domain in self._cache:
            return self._cache[domain]
        path = os.path.join(DATA_DIR, f"{domain}.json")
        if not os.path.exists(path):
            self._cache[domain] = set()
            return set()
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        lemmas = set(data) if isinstance(data, list) else set(data.keys())
        self._cache[domain] = lemmas
        return lemmas

    def analyze(self, lemmas: List[str]) -> ThematicResult:
        """
        Определить тематическую принадлежность текста.

        Args:
            lemmas: Список лемм (из StanzaBackend).

        Returns:
            ThematicResult с плотностями по доменам.
        """
        lemma_set_lower = [l.lower() for l in lemmas]
        total = max(len(lemma_set_lower), 1)

        domains = {}
        for domain, meta in DOMAIN_META.items():
            vocab = self.load_domain(domain)
            if not vocab:
                continue
            found = [l for l in lemma_set_lower if l in vocab]
            count = len(found)
            density = round(count / total * 1000, 2)  # на 1000 слов
            domains[domain] = {
                "label": meta["label"],
                "color": meta["color"],
                "count": count,
                "density": density,
                "examples": list(dict.fromkeys(found))[:8],
            }

        top_domains = sorted(domains.keys(),
                             key=lambda d: -domains[d]["density"])[:3]

        return ThematicResult(
            domains=domains,
            top_domains=top_domains,
            total_words=total,
        )

    def format_report(self, result: ThematicResult) -> str:
        lines = ["=" * 60, "ТЕМАТИЧЕСКАЯ АТРИБУЦИЯ ТЕКСТА", "=" * 60, ""]
        lines.append(f"Всего слов в тексте: {result.total_words}")
        lines.append("")

        if not result.domains:
            lines.append("Тематические словари не загружены.")
            lines.append(f"Ожидаемая директория: {DATA_DIR}")
            return "\n".join(lines)

        lines.append("Плотность тематической лексики (на 1000 слов):")
        lines.append("")

        sorted_domains = sorted(result.domains.items(),
                                key=lambda x: -x[1]["density"])
        for domain, data in sorted_domains:
            marker = "★" if domain in result.top_domains else " "
            lines.append(f"  {marker} {data['label']}")
            lines.append(f"      Слов: {data['count']}, плотность: {data['density']}")
            if data["examples"]:
                lines.append(f"      Примеры: {', '.join(data['examples'][:5])}")
            lines.append("")

        if result.top_domains:
            lines.append("-" * 40)
            lines.append("ВЫВОД:")
            top = result.top_domains[0]
            top_data = result.domains[top]
            lines.append(f"Предположительная тематическая сфера:")
            lines.append(f"  {top_data['label']}")
            lines.append(f"  (плотность: {top_data['density']} слов/1000)")
            if len(result.top_domains) > 1:
                second = result.top_domains[1]
                lines.append(f"Дополнительно: {result.domains[second]['label']}")

        return "\n".join(lines)
