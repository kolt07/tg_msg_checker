from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class MessageIn(BaseModel):
    id: str
    text: str

    @field_validator("id", mode="before")
    @classmethod
    def id_to_str(cls, value: object) -> str:
        return str(value)


class AnalyzeIn(BaseModel):
    messages: list[MessageIn]


class DictionaryIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    language: str
    tag: str = Field(min_length=1, max_length=100)
    words: list[str] = Field(min_length=1)
