"""Deterministic language-fuzzing mutations for injection text.

A defense that blocks one spelling of an attack has not been shown to work. So
each seed can be rendered many ways, and every mutation is a PURE, DETERMINISTIC
function of its input: the same text in always yields the same text out, so any
cell reproduces from the commit hash -- no RNG.

Every mutation preserves the exfil destination (the reserved-TLD address). That
is the operational core of the attack; obfuscating it would break the attack
itself rather than test a defense, so mutations skip any token that looks like a
destination.
"""

import re

# Tokens we must never mangle: emails and URLs (the exfil destination).
_TARGET_TOKEN = re.compile(r"(@|://|\.(?:test|example)\b)", re.I)

# Whole-word trigger synonyms. Kept deterministic and reversible-looking.
_SYNONYMS = {
    "ignore": "disregard",
    "send": "forward",
    "email": "message",
    "secret": "credential",
    "retrieve": "fetch",
    "urgent": "critical",
}

# Latin -> Cyrillic look-alikes (the same confusables a normaliser must fold).
_HOMOGLYPHS = str.maketrans({
    "a": "а", "e": "е", "o": "о",
    "p": "р", "c": "с", "x": "х",
})

_ZERO_WIDTH = "​"


def _is_target(token: str) -> bool:
    return bool(_TARGET_TOKEN.search(token))


def _map_words(text: str, fn) -> str:
    """Apply fn to each whitespace token that is not an exfil destination."""
    return " ".join(tok if _is_target(tok) else fn(tok) for tok in text.split(" "))


def identity(text: str) -> str:
    return text


def case_mangle(text: str) -> str:
    """Swap the case of every other letter -- defeats exact-case filters."""
    def mangle(tok):
        return "".join(c.swapcase() if i % 2 else c for i, c in enumerate(tok))
    return _map_words(text, mangle)


def synonym_swap(text: str) -> str:
    def swap(tok):
        bare = tok.lower().strip(".,!?()")
        return _SYNONYMS.get(bare, tok) if bare in _SYNONYMS else tok
    return _map_words(text, swap)


def zero_width(text: str) -> str:
    """Insert a zero-width space between the letters of non-destination words."""
    def spread(tok):
        return _ZERO_WIDTH.join(tok) if tok.isalpha() and len(tok) > 1 else tok
    return _map_words(text, spread)


def homoglyph(text: str) -> str:
    """Replace Latin letters with Cyrillic look-alikes in non-destination words."""
    return _map_words(text, lambda tok: tok.translate(_HOMOGLYPHS))


def delimiter_wrap(text: str) -> str:
    """Wrap the injection in fake system delimiters -- tests role confusion."""
    return f"<<SYSTEM>>\n{text}\n<</SYSTEM>>"


MUTATIONS = {
    "identity": identity,
    "case_mangle": case_mangle,
    "synonym_swap": synonym_swap,
    "zero_width": zero_width,
    "homoglyph": homoglyph,
    "delimiter_wrap": delimiter_wrap,
}


def apply(name: str, text: str) -> str:
    try:
        return MUTATIONS[name](text)
    except KeyError:
        raise ValueError(f"unknown mutation {name!r}; "
                         f"known: {sorted(MUTATIONS)}") from None
