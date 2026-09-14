"""Неизменяемое представление результата базового NLP-разбора."""
from __future__ import annotations

from dataclasses import dataclass

from authoroved_core.core.models import Token


@dataclass(frozen=True)
class ParsedDocument:
    """Исходный текст и неизменённые токены Stanza/UD.

    Этот объект является границей между конкретным NLP backend и предметными
    интерпретаторами. Адаптеры могут читать токены, но не заменяют их.
    """

    text: str
    tokens: tuple[Token, ...]

    @classmethod
    def from_tokens(cls, text: str, tokens: list[Token] | tuple[Token, ...]) -> "ParsedDocument":
        return cls(text=text, tokens=tuple(tokens))

    def sentence_tokens(self, sentence_id: int) -> tuple[Token, ...]:
        return tuple(token for token in self.tokens if token.sentence == sentence_id)

    def token_at(self, sentence_id: int, token_id: int) -> Token | None:
        return next(
            (token for token in self.tokens
             if token.sentence == sentence_id and token.index == token_id),
            None,
        )

    def dependents_of(self, token: Token) -> tuple[Token, ...]:
        return tuple(
            candidate for candidate in self.tokens
            if candidate.sentence == token.sentence and candidate.head == token.index
        )
