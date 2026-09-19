"""Архив отвергнутых подходов не должен возвращаться в рабочий контур."""
from pathlib import Path

CORE = Path(__file__).parents[1]
ARCHIVE = CORE / "archive"


def test_archive_exists_with_its_grounds():
    readme = ARCHIVE / "llm_hint" / "README.md"

    assert readme.is_file()
    text = readme.read_text(encoding="utf-8")
    # Основание вывода должно лежать рядом с кодом, а не только в истории.
    assert "27,2 %" in text and "26,5 %" in text
    assert (ARCHIVE / "llm_hint" / "hint_accuracy.json").is_file()


def test_archive_is_not_a_package():
    """Без __init__.py архив нельзя импортировать по неосторожности."""
    assert not list(ARCHIVE.rglob("__init__.py"))


def test_no_live_module_imports_the_archive():
    live = [path for path in CORE.rglob("*.py") if ARCHIVE not in path.parents
            and path.parent != ARCHIVE]
    offenders = [path.name for path in live
                 if "archive" in path.read_text(encoding="utf-8")
                 and "import" in path.read_text(encoding="utf-8").split("archive")[0][-40:]]

    assert not offenders


def test_withdrawn_hint_module_is_gone_from_core():
    assert not (CORE / "core" / "qwen_classification.py").exists()
    assert not (CORE / "tools" / "measure_hint_accuracy.py").exists()
