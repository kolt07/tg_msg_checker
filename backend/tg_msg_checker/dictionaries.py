from __future__ import annotations

import json
import uuid
from pathlib import Path

from tg_msg_checker.models import Dictionary
from tg_msg_checker.textnorm import normalize_phrase

SUPPORTED_LANGUAGES = {"uk", "ru", "en"}


class DictionaryError(ValueError):
    pass


class DictionaryNotFound(DictionaryError):
    pass


def clean_words(words: list[str]) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in words:
        display = " ".join(str(raw).split())
        if not display:
            continue
        key = normalize_phrase(display)
        if not key or key in seen:
            continue
        if len(key.split()) > 4:
            raise DictionaryError(f"Фраза довша за 4 слова: {display}")
        seen.add(key)
        cleaned.append(display)
    if not cleaned:
        raise DictionaryError("Додайте хоча б одне слово")
    return cleaned


def validate_dictionary(name: str, language: str, tag: str, words: list[str]) -> tuple[str, str, str, list[str]]:
    name = " ".join(name.split())
    tag = " ".join(tag.split())
    language = language.strip().lower()
    if not name:
        raise DictionaryError("Вкажіть назву словника")
    if not tag:
        raise DictionaryError("Вкажіть тег")
    if language not in SUPPORTED_LANGUAGES:
        raise DictionaryError("Мова має бути uk, ru або en")
    return name, language, tag, clean_words(words)


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


class DictionaryStore:
    def __init__(self, path: Path):
        self.path = path
        self.entries: list[Dictionary] = []
        self.load()

    def load(self) -> None:
        if not self.path.exists():
            self.entries = []
            return
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        self.entries = [
            Dictionary(
                id=item["id"],
                name=item["name"],
                language=item["language"],
                tag=item["tag"],
                words=list(item.get("words") or []),
            )
            for item in raw
        ]

    def save(self) -> None:
        payload = [
            {
                "id": entry.id,
                "name": entry.name,
                "language": entry.language,
                "tag": entry.tag,
                "words": entry.words,
            }
            for entry in self.entries
        ]
        atomic_write_text(self.path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")

    def new_id(self) -> str:
        return uuid.uuid4().hex
