"""Разовая подготовка разработчиком. Не импортируется приложением."""
from pathlib import Path


def main():
    import stanza
    from authoroved_core.nlp.stanza_adapter import PROCESSORS
    target = Path(__file__).resolve().parents[1] / ".local" / "stanza_resources"
    print("Разовая загрузка официальных моделей Stanza. Для анализа сеть не требуется.")
    stanza.download("ru", model_dir=str(target), package=None, processors=PROCESSORS)


if __name__ == "__main__":
    main()
