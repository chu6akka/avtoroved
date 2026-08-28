"""Подключаемые embedding backends для ThemeEngineV2.

Реальный backend работает только с локальным HuggingFace cache. Импорт
``sentence_transformers`` и загрузка модели выполняются исключительно при
явном shadow-вызове, поэтому обычный запуск приложения остаётся лёгким и
offline-safe.
"""
from __future__ import annotations

import hashlib
import math
import re
from importlib.metadata import PackageNotFoundError, version
from typing import Protocol, Sequence


DEFAULT_MODEL_NAME = "cointegrated/rubert-tiny2"
_WORD_RE = re.compile(r"[A-Za-zА-Яа-яЁё0-9]+")


class EmbeddingUnavailableError(RuntimeError):
    """Optional embedding backend или локальные веса недоступны."""


class EmbeddingBackend(Protocol):
    @property
    def cache_key(self) -> str: ...

    @property
    def model_info(self) -> dict: ...

    def encode(self, texts: Sequence[str]) -> list[tuple[float, ...]]: ...


def _normalise(vector: Sequence[float]) -> tuple[float, ...]:
    norm = math.sqrt(sum(float(value) ** 2 for value in vector))
    if norm <= 0:
        return tuple(0.0 for _ in vector)
    return tuple(float(value) / norm for value in vector)


class SentenceTransformerEmbeddingBackend:
    """Lazy offline-only адаптер для уже выбранной проектом ruBERT-модели."""

    def __init__(self, model_name: str = DEFAULT_MODEL_NAME,
                 model_revision: str | None = None,
                 device: str = "cpu"):
        self.model_name = model_name
        self.model_revision = model_revision
        self.device = device
        self._model = None
        self._load_attempted = False
        self._error: str | None = None
        self._library_version: str | None = None
        self._transformers_version: str | None = None
        self._torch_version: str | None = None
        self._resolved_revision: str | None = None
        self._pooling = "unknown"

    @property
    def loaded(self) -> bool:
        return self._model is not None

    @property
    def cache_key(self) -> str:
        revision = self._resolved_revision or self.model_revision or "unresolved"
        return f"sentence-transformers:{self.model_name}:{revision}"

    @property
    def model_info(self) -> dict:
        return {
            "backend": "sentence-transformers",
            "model_name": self.model_name,
            "model_revision": self._resolved_revision or self.model_revision,
            "tokenizer_revision": self._resolved_revision or self.model_revision,
            "library_version": self._library_version,
            "sentence_transformers_version": self._library_version,
            "transformers_version": self._transformers_version,
            "torch_version": self._torch_version,
            "device": self.device,
            "normalization": "l2",
            "pooling": self._pooling,
            "inference_parameters": {
                "local_files_only": True,
                "show_progress_bar": False,
                "normalize_embeddings": True,
            },
            "weights_sha256": None,
            "loaded": self.loaded,
            "error": self._error,
        }

    def _load(self) -> None:
        if self._model is not None:
            return
        if self._load_attempted:
            raise EmbeddingUnavailableError(
                self._error or "embedding backend not installed")
        self._load_attempted = True
        try:
            from sentence_transformers import SentenceTransformer
            try:
                self._library_version = version("sentence-transformers")
            except PackageNotFoundError:
                self._library_version = "unknown"
            try:
                self._transformers_version = version("transformers")
            except PackageNotFoundError:
                self._transformers_version = "unknown"
            try:
                self._torch_version = version("torch")
            except PackageNotFoundError:
                self._torch_version = "unknown"
            kwargs = {
                "device": self.device,
                "local_files_only": True,
            }
            if self.model_revision is not None:
                kwargs["revision"] = self.model_revision
            self._model = SentenceTransformer(self.model_name, **kwargs)
            self._resolved_revision = self._find_cached_revision()
            self._pooling = self._detect_pooling()
        except ImportError as exc:
            self._error = "embedding backend not installed"
            raise EmbeddingUnavailableError(self._error) from exc
        except Exception as exc:
            self._error = f"local embedding model unavailable: {exc}"
            raise EmbeddingUnavailableError(self._error) from exc

    def _find_cached_revision(self) -> str | None:
        """Получить commit hash через публичный Hugging Face cache API."""
        try:
            from huggingface_hub import scan_cache_dir
            matching = [
                repo for repo in scan_cache_dir().repos
                if repo.repo_type == "model" and repo.repo_id == self.model_name
            ]
            if not matching:
                return None
            revisions = list(matching[0].revisions)
            if self.model_revision:
                for revision in revisions:
                    if (revision.commit_hash == self.model_revision
                            or self.model_revision in revision.refs):
                        return revision.commit_hash
            if len(revisions) == 1:
                return revisions[0].commit_hash
        except Exception:
            return None
        return None

    def _detect_pooling(self) -> str:
        """Прочитать фактический pooling из загруженного SentenceTransformer."""
        try:
            for module in self._model._modules.values():
                if type(module).__name__ != "Pooling":
                    continue
                config = module.get_config_dict()
                return str(config.get("pooling_mode") or "unknown")
        except Exception:
            pass
        return "unknown"

    def encode(self, texts: Sequence[str]) -> list[tuple[float, ...]]:
        self._load()
        try:
            vectors = self._model.encode(
                list(texts),
                convert_to_numpy=True,
                show_progress_bar=False,
                normalize_embeddings=True,
            )
            return [_normalise(vector) for vector in vectors]
        except Exception as exc:
            raise EmbeddingUnavailableError(
                f"embedding inference failed: {exc}") from exc


class DeterministicEmbeddingBackend:
    """Стабильный hashing backend только для тестов и development tooling.

    Он не является научной semantic model и никогда не выбирается production
    facade автоматически.
    """

    def __init__(self, dimensions: int = 256):
        if dimensions < 16:
            raise ValueError("dimensions должно быть не меньше 16")
        self.dimensions = dimensions
        self.encode_calls = 0

    @property
    def cache_key(self) -> str:
        return f"deterministic-hashing:v1:{self.dimensions}"

    @property
    def model_info(self) -> dict:
        return {
            "backend": "deterministic-test",
            "model_name": "sha256-hashing-bag-of-words",
            "model_revision": "v1",
            "tokenizer_revision": "regex-v1",
            "library_version": "stdlib",
            "device": "cpu",
            "normalization": "l2",
            "pooling": "signed-token-sum",
            "inference_parameters": {"dimensions": self.dimensions},
            "weights_sha256": None,
            "loaded": True,
            "test_only": True,
        }

    def encode(self, texts: Sequence[str]) -> list[tuple[float, ...]]:
        self.encode_calls += 1
        return [self._encode_one(text) for text in texts]

    def _encode_one(self, text: str) -> tuple[float, ...]:
        vector = [0.0] * self.dimensions
        tokens = [match.group().lower().replace("ё", "е")
                  for match in _WORD_RE.finditer(text)]
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] & 1 else -1.0
            vector[index] += sign
        return _normalise(vector)


class UnavailableEmbeddingBackend:
    """Тестовый controlled-failure backend."""

    def __init__(self, reason: str = "embedding backend not installed"):
        self.reason = reason

    @property
    def cache_key(self) -> str:
        return "unavailable"

    @property
    def model_info(self) -> dict:
        return {
            "backend": "unavailable",
            "model_name": None,
            "model_revision": None,
            "error": self.reason,
            "loaded": False,
        }

    def encode(self, texts: Sequence[str]) -> list[tuple[float, ...]]:
        raise EmbeddingUnavailableError(self.reason)
