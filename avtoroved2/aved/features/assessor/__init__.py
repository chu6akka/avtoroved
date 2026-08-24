"""Оценщики качественных (неавтоматизируемых) признаков.

Локальная LLM (оффлайн, Ollama) предлагает оценку смысловых и психолингвистических
признаков по определению методики; эксперт подтверждает или правит каждое предложение.
"""

from aved.features.assessor.local_llm import OllamaAssessor
from aved.features.assessor.manual import ManualAssessor

__all__ = ["OllamaAssessor", "ManualAssessor"]
