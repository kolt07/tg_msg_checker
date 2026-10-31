from __future__ import annotations

from phonenumbers import PhoneNumberFormat, PhoneNumberMatcher, format_number, is_valid_number

from tg_msg_checker.models import Finding


class PhoneAnalyzer:
    def __init__(self, region: str = "UA"):
        self.region = (region or "UA").upper()

    def analyze(self, text: str) -> list[Finding]:
        if not text:
            return []
        found: list[Finding] = []
        matcher = PhoneNumberMatcher(text, self.region)
        for match in matcher:
            if not is_valid_number(match.number):
                continue
            found.append(
                Finding(
                    kind="entity",
                    name="phone",
                    text=text[match.start : match.end],
                    start=match.start,
                    end=match.end,
                    payload={"normalized": format_number(match.number, PhoneNumberFormat.E164)},
                )
            )
        return found
