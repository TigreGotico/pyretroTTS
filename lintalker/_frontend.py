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
        if w.isdigit():
            # Preserve a pure digit run as its own token instead of
            # stripping it (FrontEnd.c's kNumericTok path,
            # ProcessNumberString -- see _numbers.py for the cardinal-
            # reading port this feeds via _assembly.make_fe_word_token).
            tokens.append((w, punct))
            continue
        w = ''.join(c for c in w if c.isalpha() or c == "'")
        if not w:
            continue
        w = w.upper()
        if punct == '.':
            # A known dictionary abbreviation (e.g. "MR.", looked up
            # WITH the period as part of its key, is_abbrev=True) keeps
            # the period as part of the word instead of trailing
            # punctuation -- matches SearchAllDicts finding tok->tokStr
            # with the period appended (FrontEnd.c:524-526) and setting
            # tok->isAbbriv, rather than treating it as end-of-clause.
            from ._lexicon import lookup
            entry = lookup(w + '.')
            if entry is not None and entry.is_abbrev:
                w = w + '.'
                punct = None
        tokens.append((w, punct))
    return tokens


def _is_abbreviation_period(text: str, period_pos: int) -> bool:
    """Port of the abbreviation-period check `GetNextToken` makes before
    treating a `.` as sentence-terminal (`FrontEnd.c:515-545`/`1514-1515`/
    `1563-1564`): a `.` right after a word that's a DICTIONARY entry
    WITH the period included as part of its lookup key (e.g. `"MR."`,
    confirmed present in `_lexicon.py` with `is_abbrev=True` -- the real
    engine's `SearchAllDicts` sets `tok->isAbbriv` from exactly this) is
    NOT a sentence boundary, provided there's more text after it
    (`vv->NextCh != kEOFCh` -- if the abbreviation is the very last
    thing in the input, it's still treated as the end, matching
    `FrontEnd.c:527`/`541`'s `&& (vv->NextCh != kEOFCh)` guard).
    """
    if period_pos + 1 >= len(text):
        return False  # abbreviation at the very end of input -> real sentence end
    j = period_pos
    while j > 0 and (text[j - 1].isalpha() or text[j - 1] == "'"):
        j -= 1
    word = text[j:period_pos]
    if not word:
        return False
    from ._lexicon import lookup
    entry = lookup(word.upper() + '.')
    return bool(entry is not None and entry.is_abbrev)


def _split_on(text: str, pattern: str) -> list[str]:
    import re
    chunks: list[str] = []
    start = 0
    for m in re.finditer(pattern, text):
        if m.group() == '.' and _is_abbreviation_period(text, m.start()):
            continue  # e.g. "Mr." -- not a real boundary, keep scanning
        chunk = text[start:m.end()].strip()
        if chunk:
            chunks.append(chunk)
        start = m.end()
    tail = text[start:].strip()
    if tail:
        chunks.append(tail)
    return chunks


def split_sentences(text: str) -> list[str]:
    """Split `text` into per-sentence substrings on sentence-terminal
    punctuation (`. ! ?`, not `,`), each substring retaining its own
    terminal mark. A trailing fragment with no terminal punctuation (e.g.
    unpunctuated input) is returned as its own final "sentence".

    A `.` immediately after a known dictionary ABBREVIATION (e.g. "Mr.",
    "Dr.", "St." -- see `_is_abbreviation_period`) does NOT end a
    sentence here, matching the real engine's `tok->isAbbriv` check
    (`FrontEnd.c:515-545`). Whitespace-only or empty results are dropped.
    """
    return _split_on(text, r'[.!?]')


def split_clauses(text: str) -> list[str]:
    """Split `text` on ANY of `. , ! ?` (unlike `split_sentences()`, which
    only splits on sentence-terminal `. ! ?`), each substring retaining its
    own trailing mark. Like `split_sentences()`, a `.` immediately after a
    known dictionary abbreviation does not split here either.

    This matches `Collect_FE_Tokens`'s real behavior, confirmed by reading
    `BackEnd.c:3991-4006`: a comma sets `gotSentence = true` and returns
    from `Collect_FE_Tokens` exactly the same way a period/`!`/`?` does --
    i.e. what looks like one English "sentence" containing a comma is
    actually processed by the real engine as two separate
    `Collect_FE_Tokens`/`ParseSentence`/plan-assembly cycles, continuing
    seamlessly within the same audio stream. `api.synthesize_text()` uses
    this (not `split_sentences()`) to decide where to start a fresh
    assembly pipeline call, which is why a comma-containing sentence like
    "good morning everyone, welcome to the show." synthesizes correctly
    (confirmed frame-exact against the C reference,
    `test/test_synthesize_text.py`) while naively assembling the whole
    thing as one clause does not (a real, confirmed divergence found via
    frame-count mismatches before this function existed).
    """
    return _split_on(text, r'[.,!?]')


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
