"""
Partial port of FrontEnd.c: raw text -> per-word phoneme-opcode tokens.

SCOPE: this module ports the *tokenization and letter-to-sound* slice of
FrontEnd.c -- splitting raw text into words and end-of-word punctuation,
and calling the already-verified rule engine (`_engtop.engtop`) to convert
each word into a phoneme-opcode list exactly the way `WordToPhonemes`
(FrontEnd.c:1614) does in its "no dictionary, no morphology" fallback
branch (FrontEnd.c:1628-1648).

`tokenize()`'s output feeds `_assembly.collect_fe_tokens()` (sentence-level
stress/word/punctuation/syllable bookkeeping, adapted from
`Collect_FE_Tokens`+`Flag_PhonBuf_1`), which in turn feeds
`_phonbuf2.fill_phon_buf_2`/`_pitchcontour.pitch_raise_and_fall`/
`_moduration.mod_duration`/`_pitchbuf.fill_pitch_buf` -- the full chain
`api.synthesize_text()` composes. See docs/architecture.md for the module
map and "Known gaps" for what's not covered (Morph.c, number/abbreviation
expansion, non-punctuation phrase boundaries, embedded commands).

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
    * `split_sentences(text)` -- splits text on sentence-terminal
      punctuation (`. ! ?`, not `,`) into per-sentence substrings. Used by
      `api.synthesize_text()` for multi-sentence input -- see that
      function's docstring for the exact (documented, non-bit-exact)
      approximation this makes: each sentence is synthesized with an
      independently-reset `VoiceVar` rather than the real engine's shared
      `Talk()` session, so cross-sentence prosody continuity (baseline
      pitch drift, compound-noun state) isn't preserved. `Collect_FE_Tokens`
      returning per-sentence and `ParseSentence` resetting `phon_Buf_2`/
      `pitchBuf_In_Index` each call (confirmed by inspection: feeding
      multi-sentence text to the real `test_harness` CLI only ever dumps
      one sentence's worth of `phon_Buf_2` at a time) means the real engine
      also processes one sentence's plan at a time, just within one
      continuous `Talk()` session/frame loop rather than independent
      `VoiceVar`s per sentence.
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


def split_sentences(text: str) -> list[str]:
    """Split `text` into per-sentence substrings on sentence-terminal
    punctuation (`. ! ?`, not `,`), each substring retaining its own
    terminal mark. A trailing fragment with no terminal punctuation (e.g.
    unpunctuated input) is returned as its own final "sentence".

    Whitespace-only or empty results are dropped. This is a plain string
    splitter, not a further port of FrontEnd.c/Morph.c sentence-boundary
    logic (which also handles abbreviations like "Dr." not ending a
    sentence) -- see module docstring.
    """
    import re
    sentences: list[str] = []
    start = 0
    for m in re.finditer(r'[.!?]', text):
        chunk = text[start:m.end()].strip()
        if chunk:
            sentences.append(chunk)
        start = m.end()
    tail = text[start:].strip()
    if tail:
        sentences.append(tail)
    return sentences


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
