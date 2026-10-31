from __future__ import annotations

from tg_msg_checker.models import Finding
from tg_msg_checker.textnorm import prepare_text


class LexicalAnalyzer:
    def __init__(self, forms: dict[str, list[dict[str, str]]]):
        self._automaton = None
        if not forms:
            return
        import ahocorasick

        automaton = ahocorasick.Automaton()
        added = 0
        for form, payloads in forms.items():
            if not form or not payloads:
                continue
            packed = tuple((item["tag"], item["lemma"]) for item in payloads)
            automaton.add_word(form, (len(form), packed))
            added += 1
        if not added:
            return
        automaton.make_automaton()
        self._automaton = automaton

    def analyze(self, text: str) -> list[Finding]:
        if not text or self._automaton is None:
            return []
        prepared, origins = prepare_text(text)
        if not prepared:
            return []
        found: list[Finding] = []
        for end_inclusive, (length, payloads) in self._automaton.iter(prepared):
            start = end_inclusive - length + 1
            end = end_inclusive + 1
            if start < 0 or end > len(origins) or start >= end:
                continue
            if not _word_border(prepared, start, end):
                continue
            origin_start = origins[start]
            origin_end = origins[end - 1] + 1
            snippet = text[origin_start:origin_end]
            for tag, lemma in payloads:
                found.append(
                    Finding(
                        kind="tag",
                        name=tag,
                        text=snippet,
                        start=origin_start,
                        end=origin_end,
                        payload={"lemma": lemma},
                    )
                )
        return found


def _word_border(text: str, start: int, end: int) -> bool:
    if start > 0 and text[start - 1].isalpha():
        return False
    if end < len(text) and text[end].isalpha():
        return False
    return True
