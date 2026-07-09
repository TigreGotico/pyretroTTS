"""
Partial port of FrontEnd.c: raw text -> per-word phoneme-opcode tokens.

SCOPE (read before extending): this module ports only the *tokenization and
letter-to-sound* slice of FrontEnd.c -- splitting raw text into words and
end-of-word punctuation, and calling the already-verified rule engine
(`_engtop.engtop`) to convert each word into a phoneme-opcode list exactly
the way `WordToPhonemes` (FrontEnd.c:1614) does in its "no dictionary, no
morphology" fallback branch (FrontEnd.c:1628-1648).

It deliberately does NOT implement `text_to_phoneme_plan(text) ->
(phonemes, ctrls, durs, pitch_freq, pitch_time, pitch_flags)` as originally
scoped, and does NOT wire a `synthesize_text()` into api.py. That shape is
produced in the real engine by `Fill_Phon_Buf_2` (BackEnd.c:2469-2846, ~380
lines) together with `MarkSyllable`/`MarkSyllableStart` (BackEnd.c:3191/3379),
`Place_Stress_In_Consonant` (BackEnd.c:3300), `Mod_Duration` (BackEnd.c:1362),
and `Pitch_RaiseAndFall` (BackEnd.c:2127 and its near-duplicate at 2303) --
none of which exist anywhere in this Python port yet (`_backend.py` only
implements frame-level synthesis from an *already filled* phon_Buf_2 /
phon_Ctrl_Buf_2 / dur_Buf, per `_engine.py`'s own module docstring).
`Collect_FE_Tokens` (BackEnd.c:3712-4165) is the actual driver that pulls
tokens from FrontEnd.c and pushes them through that stress/duration/pitch
machinery one word at a time; `ParseSentence` (BackEnd.c:4165) is a thin
wrapper around it. FrontEnd.c's `WordToPhonemes`/tokenizer loop this module
covers is only the first of several stages needed for a correct ctrl/dur
plan -- producing one without the rest would silently emit wrong stress
placement, wrong phoneme durations, and no pitch contour, while looking
superficially like a working pipeline. Per the task's own instructions, that
is worse than not shipping it, so it is intentionally left unbuilt here.

What IS real and tested here (see test/test_frontend.py):
    * `tokenize(text)` -- splits text into (WORD, trailing_punct) pairs,
      following FrontEnd.c's word/punctuation boundary handling
      (FrontEnd.c:2114-2159: `.` -> _Period_, `,` -> _Comma_, `!` -> _Exclam_,
      `?` -> _Quest_).
    * `words_to_phonemes(text)` -- tokenize() + engtop() per word, with the
      matching punctuation phoneme opcode appended after each word's
      phoneme list (mirrors `cur_Tok->phonStr[1] = _Period_` etc. at
      FrontEnd.c:2120/2132/2145/2151/2159 -- the C code appends the
      punctuation phoneme as an extra one-phoneme "token" after the word).

Explicitly NOT ported (left for a follow-up agent, in priority order):
    1. `Fill_Phon_Buf_2` + syllable/stress/duration/pitch stages listed above
       (BackEnd.c) -- required before ANY of this can feed
       `api.synthesize_phonemes` correctly. This is the real Phase A
       remainder; it lives in BackEnd.c, not FrontEnd.c, contrary to the
       original task framing.
    2. `SearchAllDicts`/`english_lex` dictionary lookup (Phase B).
    3. `DoMorph` (Morph.c) and number/abbreviation expansion (Phase C).
"""
from __future__ import annotations

from ._phonemes import _Period_, _Comma_, _Quest_, _Exclam_
from ._engtop import engtop

_PUNCT_PHON = {
    '.': _Period_,
    ',': _Comma_,
    '!': _Exclam_,
    '?': _Quest_,
}


def tokenize(text: str) -> list[tuple[str, str | None]]:
    """Split raw text into (WORD, trailing_punct_or_None) pairs.

    Minimal stand-in for FrontEnd.c's `Collect_FE_Tokens`/word-scanning loop:
    splits on whitespace, strips a single trailing punctuation mark
    (one of `. , ! ?`) off each word (FrontEnd.c:2114-2159), and drops any
    other punctuation. Does not handle abbreviations, numbers, contractions
    beyond letters+apostrophe, or multi-char terminal punctuation (e.g. "...",
    "?!") -- FrontEnd.c has dedicated logic for those (search FrontEnd.c for
    `kAbbrev`/`ProcessNumberString`) that is not ported here.
    """
    tokens: list[tuple[str, str | None]] = []
    for raw in text.split():
        punct = None
        w = raw
        while w and not (w[-1].isalnum() or w[-1] == "'"):
            if w[-1] in _PUNCT_PHON:
                punct = w[-1]
            w = w[:-1]
        w = ''.join(c for c in w if c.isalpha() or c == "'")
        if not w:
            continue
        tokens.append((w.upper(), punct))
    return tokens


def words_to_phonemes(text: str) -> list[int]:
    """tokenize(text) + engtop() per word, with punctuation phonemes appended.

    Returns a flat list of phoneme opcodes -- NOT a (phonemes, ctrls, durs)
    plan. See module docstring: the ctrl/dur assembly stage
    (`Fill_Phon_Buf_2`, BackEnd.c:2469) is not ported, so this output cannot
    be fed to `api.synthesize_phonemes` as-is.
    """
    out: list[int] = []
    for word, punct in tokenize(text):
        out.extend(engtop(word))
        if punct is not None:
            out.append(_PUNCT_PHON[punct])
    return out
