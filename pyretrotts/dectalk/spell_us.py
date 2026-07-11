"""DECtalk US letter-name speller for vowelless tokens (`lts/ls_spel.c`).

A word the word-reading front end cannot pronounce -- in the US path, a token
with no vowel letter -- is spelled letter by letter, each letter spoken as its
name (`ls_task` letter-name code 111). Each letter name is the phoneme+stress
code stream the C emits for that letter; `LETTER_NAMES` holds those streams
captured from the instrumented oracle (one process per letter, the pre-`ph/`
`phclause`-input boundary), which is why this data carries the FONIX notice.

Derived from the Fonix/Force DECtalk C source (`dectalk/dectalk`,
`src/dapi/src/lts/ls_spel.c`, `l_us_spe.c`). FONIX Corporation declares that
source proprietary and confidential. This file is NOT covered by this project's
MIT licence. See NOTICE.
"""
from __future__ import annotations

# Per-letter phoneme+stress send codes (pre font-shift), captured verbatim from
# the oracle: phonemes are codes < 100, `103` is S1 stress, `109` a HYPHEN
# marker inside a compound letter name ("double-u").
LETTER_NAMES: dict[str, tuple[int, ...]] = {
    "a": (103, 3),
    "b": (46, 103, 1),
    "c": (41, 103, 1),
    "d": (48, 103, 1),
    "e": (103, 1),
    "f": (103, 4, 37),
    "g": (55, 103, 1),
    "h": (103, 3, 54),
    "i": (103, 7),
    "j": (55, 103, 3),
    "k": (49, 103, 3),
    "l": (103, 4, 27),
    "m": (103, 4, 31),
    "n": (103, 4, 32),
    "o": (103, 11),
    "p": (45, 103, 1),
    "q": (49, 103, 16),
    "r": (103, 6, 26),
    "s": (103, 4, 41),
    "t": (47, 103, 1),
    "u": (25, 103, 14),
    "v": (38, 103, 1),
    "w": (48, 103, 9, 46, 34, 109, 25, 14),
    "x": (103, 4, 49, 41),
    "y": (24, 103, 7),
    "z": (42, 103, 1),
}

_VOWELS = frozenset("aeiou")


def is_spelled(token: str) -> bool:
    """True if the US front end spells `token` (an all-alpha token with no vowel)."""
    low = token.lower()
    if not low or not all("a" <= c <= "z" for c in low):
        return False
    return not any(c in _VOWELS for c in low)


def spell_codes(token: str) -> list[tuple[int, ...]]:
    """Per-letter send-code streams for a spelled token (one per letter)."""
    return [LETTER_NAMES[c] for c in token.lower() if c in LETTER_NAMES]
