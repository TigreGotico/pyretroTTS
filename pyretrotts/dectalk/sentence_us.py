"""DECtalk US sentence front end: text -> per-clause `phclause` symbol streams.

Extends the lone-word path (`text_us.py`) to whole sentences, reproducing the
`cmd/`+`lts/` framing the C builds before `phclause`: the input is split into
clauses on punctuation, each clause is framed with a leading font silence and
an inter-word boundary marker before every word, and the clause is closed by the
terminator code that drives `phinton`'s clause-final intonation -- a
continuation-rise comma (`,` `;` `:`), a declarative period (`.` or an
unpunctuated end), a question rise (`?`), or an exclamation (`!`). Numbers,
currency, ordinals and abbreviations expand to words first (`numbers_us.py`, the
abbreviation table below); a vowelless token is spelled letter by letter
(`spell_us.py`). Each produced word then runs through the dictionary/rule word
layer (`text_us.word_to_codes`) exactly as a typed word does.

The word boundary marker emitted here is the plain `WBOUND` (111). The C's
syntactic parser (`cmd/par_*.c`) instead promotes some boundaries to phrase
markers (`PPSTART`/`VPSTART`/`RELSTART`) and reassigns function-word stress; that
grammar layer is not ported, so the framing here is faithful for clauses the
parser leaves at plain word boundaries. See `docs/dectalk.md`.

Derived from the Fonix/Force DECtalk C source (`dectalk/dectalk`,
`src/dapi/src/cmd/`, `src/dapi/src/lts/ls_task.c`). FONIX Corporation declares
that source proprietary and confidential. This file is NOT covered by this
project's MIT licence. See NOTICE.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .dictionary import Dictionary
from .grammar_us import SDIC, article_a_codes, word_markers
from .numbers_us import number_token_send_codes, say_cardinal
from .spell_us import is_spelled, spell_codes
from .text_us import word_to_codes

# l_com_ph.h prosody codes.
_FONT = 7680
_WBOUND = 111
_COMMA = 115
_PERIOD = 116
_QUEST = 117
_EXCLAIM = 118

# Punctuation -> clause terminator code. `;` and `:` read as a comma clause.
_TERMINATORS: dict[str, int] = {
    ",": _COMMA, ";": _COMMA, ":": _COMMA,
    ".": _PERIOD, "?": _QUEST, "!": _EXCLAIM,
}

# US abbreviation expansions (`l_us_con.c` abbreviation handling). Each maps a
# lowercased token (period stripped) to the word sequence it reads as.
ABBREVIATIONS: dict[str, list[str]] = {
    "dr": ["doctor"], "mr": ["mister"], "mrs": ["missus"], "ms": ["miz"],
    "st": ["saint"], "mt": ["mount"], "ft": ["fort"], "vs": ["versus"],
    "etc": ["etcetera"], "jr": ["junior"], "sr": ["senior"],
    "jan": ["january"], "feb": ["february"], "mar": ["march"],
    "apr": ["april"], "jun": ["june"], "jul": ["july"], "aug": ["august"],
    "sep": ["september"], "sept": ["september"], "oct": ["october"],
    "nov": ["november"], "dec": ["december"],
}

# A run of alphanumerics/currency/apostrophe (a candidate word or number) or a
# single punctuation mark.
_TOKEN = re.compile(r"\$?\d[\d,]*(?:\.\d+)?(?:st|nd|rd|th)?|[A-Za-z][A-Za-z']*|[.,;:?!]")


@dataclass(frozen=True)
class _Clause:
    """One clause's word list and its terminator code."""

    words: tuple[str, ...]
    terminator: int


def _font(code: int) -> int:
    return _FONT + code if code < 100 else code


def _split_clauses(text: str) -> list[_Clause]:
    """Tokenize `text` and split it into clauses on punctuation."""
    tokens = _TOKEN.findall(text)
    clauses: list[_Clause] = []
    words: list[str] = []
    last_abbrev = False
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok in _TERMINATORS:
            # A period closing a known abbreviation is consumed by that word,
            # not a clause terminator.
            if tok == "." and last_abbrev:
                last_abbrev = False
                i += 1
                continue
            clauses.append(_Clause(tuple(words), _TERMINATORS[tok]))
            words = []
            last_abbrev = False
            i += 1
            continue
        words.extend(_expand_token(tok))
        last_abbrev = tok.lower() in ABBREVIATIONS
        i += 1
    if words:
        clauses.append(_Clause(tuple(words), _PERIOD))
    return [c for c in clauses if c.words]


def _expand_token(tok: str) -> list[str]:
    """Expand one raw token to the words it reads as (abbrev/number/plain).

    A numeric or currency token is kept as a single token: `_word_symbols`
    reads it through the digit path (`number_token_send_codes`) rather than the
    word/dictionary path. An abbreviation still expands to its word sequence.
    """
    low = tok.lower()
    if low in ABBREVIATIONS:
        return ABBREVIATIONS[low]
    return [tok]


def _word_symbols(
    word: str, dictionary: Dictionary | None, clause_final: bool
) -> list[int]:
    """Font-shifted send codes for a single word, spelling vowelless tokens."""
    number = number_token_send_codes(word)
    if number is not None:
        return [_WBOUND, *(_font(c) for c in number)]
    if is_spelled(word):
        out: list[int] = []
        for letter in spell_codes(word):
            out.append(_WBOUND)
            out.extend(_font(c) for c in letter)
        return out
    article = article_a_codes(word, clause_final)
    if article is not None:
        return [_WBOUND, *(_font(c) for c in article)]
    low = word.lower()
    markers = word_markers(low, dictionary)
    if low in SDIC:
        body = SDIC[low]
    else:
        body, _src = word_to_codes(low, dictionary)
    lead = list(markers) if markers is not None else [_WBOUND]
    return [*lead, *(_font(c) for c in body)]


def _clause_symbols(clause: _Clause, dictionary: Dictionary | None) -> tuple[int, ...]:
    syms: list[int] = [_FONT]
    last = len(clause.words) - 1
    for i, word in enumerate(clause.words):
        syms.extend(_word_symbols(word, dictionary, clause_final=i == last))
    syms.append(clause.terminator)
    return tuple(syms)


def sentence_to_clauses(text: str, dictionary: Dictionary | None):
    """Text -> a `phclause.Clause` per clause (the `phclause` input stream).

    Reproduces the front-end framing the C hands to `phclause`, one clause per
    punctuation-delimited span, ready for `phclause.speak_phonemes`.
    """
    from .phclause import Clause

    return [Clause(_clause_symbols(c, dictionary)) for c in _split_clauses(text)]


def sentence_to_pcm(voice: int, text: str, dictionary: Dictionary | None) -> bytes:
    """Full US text-to-speech for a whole sentence: text -> phonemes -> PCM."""
    from .phclause import speak_phonemes

    clauses = sentence_to_clauses(text, dictionary)
    if not clauses:
        return b""
    return _pcm_bytes(speak_phonemes(voice, clauses))


def _pcm_bytes(samples: list[int]) -> bytes:
    import struct

    return struct.pack(f"<{len(samples)}h", *samples)


__all__ = [
    "ABBREVIATIONS",
    "sentence_to_clauses",
    "sentence_to_pcm",
    "say_cardinal",
]
