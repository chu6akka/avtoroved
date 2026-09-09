"""Новый офлайн-адаптер: без legacy, скачивания и подмены torch.load."""
from importlib.metadata import version
from hashlib import sha256
from pathlib import Path

from authoroved_core.core.models import Span, Token

PROCESSORS = {"tokenize": "syntagrus", "pos": "syntagrus_charlm",
              "lemma": "syntagrus_nocharlm", "depparse": "syntagrus_charlm"}


def convert_document(parsed, text: str) -> list[Token]:
    result = []
    for sentence_id, sentence in enumerate(parsed.sentences):
        for token in sentence.tokens:
            for word in token.words:
                start, end = getattr(word, "start_char", None), getattr(word, "end_char", None)
                if start is None and len(token.words) == 1:
                    start, end = token.start_char, token.end_char
                span = Span(start, end) if isinstance(start, int) and isinstance(end, int) else None
                if span is not None and (not span.valid_for(text) or text[start:end] != word.text):
                    span = None
                feats = dict(part.split("=", 1) for part in (word.feats or "").split("|") if "=" in part)
                result.append(Token(word.text, word.lemma or word.text, word.upos or "X", feats,
                                    word.deprel or "", word.head or 0, sentence_id, word.id, span))
    return result


class StanzaAdapter:
    def __init__(self, model_dir: str):
        self.model_dir = Path(model_dir)
        self.pipeline = None
        self.model_hashes = {}

    def analyze(self, text: str) -> tuple[list[Token], dict]:
        if not (self.model_dir / "resources.json").is_file():
            raise RuntimeError("Не найдены локальные модели Stanza. Укажите папку в настройках.")
        if self.pipeline is None:
            import stanza
            import torch
            torch.set_num_threads(min(4, torch.get_num_threads()))
            self.pipeline = stanza.Pipeline("ru", dir=str(self.model_dir), package=None,
                                            processors=PROCESSORS, download_method=None,
                                            use_gpu=False, verbose=False)
            paths = {self.model_dir / "resources.json"}
            for processor in self.pipeline.processors.values():
                for name, value in processor.config.items():
                    if name.endswith("_path") and isinstance(value, str) and Path(value).is_file():
                        paths.add(Path(value))
            for path in sorted(paths):
                digest = sha256()
                with path.open("rb") as stream:
                    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                        digest.update(chunk)
                self.model_hashes[str(path)] = digest.hexdigest()
        parsed = self.pipeline(text)
        return convert_document(parsed, text), {
            "version": version("stanza"), "torch_version": version("torch"),
            "device": "cpu", "processors": PROCESSORS, "model_dir": str(self.model_dir),
            "resource_sha256": self.model_hashes,
        }
