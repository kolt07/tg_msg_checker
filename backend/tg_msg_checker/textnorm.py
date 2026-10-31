from __future__ import annotations

# Однакові за довжиною замінники, щоб індекси після lower() лишались зіставними.
_APOSTROPHES = {
    "\u2019": "'",
    "\u2018": "'",
    "\u02bc": "'",
    "\u0060": "'",
    "\u00b4": "'",
    "\u02b9": "'",
}


def normalize_char(ch: str) -> str:
    return _APOSTROPHES.get(ch, ch).lower()


def normalize_token(token: str) -> str:
    return "".join(normalize_char(ch) for ch in token.strip())


def normalize_phrase(text: str) -> str:
    return " ".join(normalize_token(part) for part in text.split() if part.strip())


def prepare_text(text: str) -> tuple[str, list[int]]:
    """Нижній регістр, єдиний апостроф і стиснені пробіли.

    Другий елемент — індекс оригінального символу для кожної позиції
    підготовленого рядка. Пробіли на краях відкидаються.
    """
    chars: list[str] = []
    origins: list[int] = []
    prev_space = True
    for index, ch in enumerate(text):
        if ch.isspace():
            if prev_space:
                continue
            chars.append(" ")
            origins.append(index)
            prev_space = True
            continue
        prev_space = False
        for out_ch in normalize_char(ch):
            chars.append(out_ch)
            origins.append(index)
    if chars and chars[-1] == " ":
        chars.pop()
        origins.pop()
    return "".join(chars), origins
