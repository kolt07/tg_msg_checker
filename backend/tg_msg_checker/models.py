from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Message:
    id: str
    text: str


@dataclass(frozen=True)
class Finding:
    kind: str
    name: str
    text: str
    start: int
    end: int
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Dictionary:
    id: str
    name: str
    language: str
    tag: str
    words: list[str]
