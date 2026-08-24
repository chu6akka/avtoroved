"""Авто-экстракторы признаков. Импорт модулей регистрирует их в реестре экстракторов."""

from aved.features.extractors.base import (
    ExtractorContext,
    get_extractor,
    registered_names,
    run,
)

# импорт модулей запускает регистрацию экстракторов через декоратор @register
from aved.features.extractors import (  # noqa: E402,F401
    graphematics,
    lexicon,
    morphology,
    stats,
    style,
    syntax,
)

__all__ = ["ExtractorContext", "run", "get_extractor", "registered_names"]
