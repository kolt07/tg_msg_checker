from __future__ import annotations

import itertools
from functools import lru_cache

from tg_msg_checker.models import Dictionary
from tg_msg_checker.textnorm import normalize_phrase, normalize_token

MAX_COMBINATIONS = 256
_CASE_ORDER = ("nomn", "gent", "datv", "accs", "ablt", "loct", "voct")
_GENDER_ORDER = ("masc", "femn", "neut")


@lru_cache(maxsize=4)
def _morph(language: str):
    import pymorphy3

    return pymorphy3.MorphAnalyzer(lang=language)


def _rank(tag) -> tuple[int, int, int]:
    grams = tag.grammemes
    number = 0 if "sing" in grams else 1 if "plur" in grams else 2
    case = next((index for index, name in enumerate(_CASE_ORDER) if name in grams), 9)
    gender = next((index for index, name in enumerate(_GENDER_ORDER) if name in grams), 3)
    return number, case, gender


def _keep_form(form: str, original: str) -> bool:
    if not form or " " in form:
        return False
    if form != original and len(original) > 2 and len(form) <= 2:
        return False
    return True


def _english_forms(word: str) -> list[str]:
    from lemminflect import getAllInflections

    try:
        table = getAllInflections(word)
    except Exception:
        table = {}
    if not table:
        try:
            from lemminflect import getAllInflectionsOOV

            table = getAllInflectionsOOV(word, "NOUN") or {}
        except Exception:
            table = {}
    forms: list[str] = []
    if isinstance(table, dict):
        for bucket in table.values():
            for form in bucket:
                forms.append(normalize_token(str(form)))
    return forms


def expand_token(token: str, language: str) -> list[str]:
    original = normalize_token(token)
    if not original:
        return []
    ranked: list[tuple[tuple, str]] = []
    if language in {"uk", "ru"}:
        try:
            parses = _morph(language).parse(original)
        except Exception:
            parses = []
        for parse in parses[:3]:
            for form in parse.lexeme:
                word = normalize_token(form.word)
                if _keep_form(word, original):
                    ranked.append((_rank(form.tag), word))
    elif language == "en":
        for index, form in enumerate(_english_forms(original)):
            if _keep_form(form, original):
                ranked.append(((index,), form))
    ordered = [original]
    seen = {original}
    for _, word in sorted(ranked, key=lambda item: item[0]):
        if word not in seen:
            seen.add(word)
            ordered.append(word)
    return ordered


def _product_size(groups: list[list[str]]) -> int:
    total = 1
    for group in groups:
        total *= max(1, len(group))
        if total > MAX_COMBINATIONS:
            return total
    return total


def expand_entry(text: str, language: str) -> tuple[str, list[str]]:
    lemma = normalize_phrase(text)
    tokens = lemma.split()
    if not tokens:
        return "", []
    if len(tokens) == 1:
        return lemma, expand_token(tokens[0], language)

    lists: list[list[str]] = []
    for token in tokens:
        forms = expand_token(token, language)
        lists.append([token] + [form for form in forms if form != token])
    while _product_size(lists) > MAX_COMBINATIONS:
        index = max(range(len(lists)), key=lambda item: len(lists[item]))
        if len(lists[index]) <= 1:
            break
        lists[index] = lists[index][:-1]

    phrases: list[str] = []
    seen: set[str] = set()
    for combo in itertools.product(*lists):
        phrase = " ".join(combo)
        if phrase in seen:
            continue
        seen.add(phrase)
        phrases.append(phrase)
        if len(phrases) >= MAX_COMBINATIONS:
            break
    if lemma not in seen:
        phrases.append(lemma)
    return lemma, phrases


def build_form_index(
    entries: list[Dictionary],
) -> tuple[dict[str, list[dict[str, str]]], dict[str, dict[str, int]]]:
    forms: dict[str, list[dict[str, str]]] = {}
    stats: dict[str, dict[str, int]] = {}
    for entry in entries:
        own: set[str] = set()
        for word in entry.words:
            lemma, expanded = expand_entry(word, entry.language)
            if not lemma:
                continue
            for form in expanded:
                if not form:
                    continue
                own.add(form)
                payload = {"tag": entry.tag, "lemma": lemma}
                bucket = forms.setdefault(form, [])
                if payload not in bucket:
                    bucket.append(payload)
        stats[entry.id] = {"word_count": len(entry.words), "form_count": len(own)}
    return forms, stats
