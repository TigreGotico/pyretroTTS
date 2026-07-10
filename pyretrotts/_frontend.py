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
map and the limitations that remain.

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
      `pitchBuf_In_Index` each call (feeding
      multi-sentence text to the real `test_harness` CLI only ever dumps
      one sentence's worth of `phon_Buf_2` at a time) means the real engine
      also processes one sentence's plan at a time, just within one
      continuous `Talk()` session/frame loop rather than independent
      `VoiceVar`s per sentence.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ._engtop import engtop
from ._lexicon import (
    lookup,
)
from ._phonemes import _Comma_, _Exclam_, _Period_, _Quest_

_PUNCT_PHON = {
    '.': _Period_,
    ',': _Comma_,
    '!': _Exclam_,
    '?': _Quest_,
}


@dataclass(frozen=True)
class TokenStream:
    """The word/punctuation stream, plus where the number readers must look.

    Each index list holds positions into `tokens` whose word needs a reader
    other than the plain cardinal one: a dollar amount, the fractional part
    of a decimal, a cents amount, or the minutes of a clock time.
    """

    tokens: list[tuple[str, str | None]] = field(default_factory=list)
    dollar: list[int] = field(default_factory=list)
    decimal_frac: list[int] = field(default_factory=list)
    cent: list[int] = field(default_factory=list)
    clock: list[int] = field(default_factory=list)


def tokenize(text: str) -> list[tuple[str, str | None]]:
    """Split raw text into (WORD, trailing_punct_or_None) pairs.

    Use `scan_tokens` when the number/currency/clock positions are needed too.
    """
    return scan_tokens(text).tokens


def scan_tokens(text: str) -> TokenStream:
    """Split raw text into (WORD, trailing_punct_or_None) pairs.

    Minimal stand-in for FrontEnd.c's `Collect_FE_Tokens`/word-scanning loop:
    splits on whitespace, strips a single trailing punctuation mark
    (one of `. , ! ?`) off each word (FrontEnd.c:2114-2159), and drops any
    other punctuation. Does not handle abbreviations, numbers, contractions
    beyond letters+apostrophe, or multi-char terminal punctuation (e.g. "...",
    "?!") -- FrontEnd.c has dedicated logic for those (search FrontEnd.c for
    `kAbbrev`/`ProcessNumberString`) that is not ported here.

    `dollar` gets the output-token INDEX of every
    `$<digits>` token appended to it (e.g. `"$5"` -> the digit token
    `"5"`, with its index recorded) -- a port of `GetNextToken`'s `$`
    handling (`FrontEnd.c:1017-1027`: a `$` immediately followed by a
    digit sets `tok->addFlags |= kAddDollar` and is itself consumed, not
    kept as its own token). This is a side-channel rather than a change
    to this function's `(word, punct)` return shape, matching how
    `_embeddedcmd.scan_bracket_commands`'s per-word override dicts are
    threaded through `_assembly.collect_fe_tokens` without altering
    `tokenize()`'s own contract.

    `decimal_frac` gets the output-token INDEX of
    the FRACTIONAL half of every `N.M`-shaped token (e.g. `"3.14"` splits
    into three tokens: `"3"`, `"POINT"`, `"14"` -- only the last one's
    index is recorded). Ports the `kPeriodTok` "KLUDGE" (`FrontEnd.c:
    2088-2109`): a `.` between two number-like tokens is turned into the
    literal WORD "POINT" (an ordinary dictionary word, looked up via
    `WordToPhonemes` exactly like any other word -- no `Symbols`-
    dictionary/corruption involved at all here), and the digits AFTER
    the point are forced into digit-by-digit reading by the following
    token inheriting `kDigitByDigit`-equivalent behavior (`lastType ==
    kDecimalTok` at `FrontEnd.c:2058`) -- e.g. "3.14" -> "three point one
    four", not "three point fourteen". Not applied to a `$`-prefixed
    token: that combination is `cent`'s job instead (see below).

    `cent` gets the output-token INDEX of the
    CENTS half of every `$N.M`-shaped token (e.g. `"$5.25"` splits into
    THREE tokens: `"5"` (recorded in `dollar`), `"AND"`, `"25"`
    (recorded here)). Ports `kPeriodTok`'s SEPARATE dollar-flagged
    branch (`FrontEnd.c:2096-2101`): unlike a plain decimal, a `.` right
    after a `kAddDollar` token becomes the word "AND" (not "POINT"),
    and the digits after it are read as a normal CARDINAL with
    "cent"/"cents" appended (`kAddCent`, `_numbers.cent_phonemes`) --
    NOT digit-by-digit -- e.g. `"$5.25"` -> "five dollars AND twenty
    five cents", not "five dollars point two five".

    `clock` gets the output-token INDEX of the
    MINUTES half of every `H:MM`-shaped token (e.g. `"3:45"` splits
    into `"3"` and `"45"`, only the latter's index recorded). Ports
    `GetNextToken`'s `:`-between-digits handling (`FrontEnd.c:1003
    -1011`, `kClockSpecial`): the hour is an ORDINARY numeric token
    (plain cardinal reading, no special treatment), and the minutes
    (exactly 2 digits -- `PartialNumberToPhonemes`'s `kClockSpecial`
    branch only fires when `tok->tokStr[0] == 2`) get `_numbers.clock_
    phonemes` instead (e.g. "3:45" -> "three forty five", "3:05" ->
    "three oh five", "3:00" -> "three o'clock"). Requires exactly 2
    minute digits, matching the real engine's own length check --
    `"3:5"` (1 minute digit) isn't recognized as clock-shaped here
    either, the same narrow scope the C source itself has.
    """
    tokens: list[tuple[str, str | None]] = []
    dollar: list[int] = []
    decimal_frac: list[int] = []
    cent: list[int] = []
    clock: list[int] = []
    for raw in text.split():
        punct = None
        w = raw
        while w and not (w[-1].isalnum() or w[-1] == "'"):
            if w[-1] in _PUNCT_PHON:
                punct = w[-1]
            w = w[:-1]
        is_dollar = False
        if len(w) > 1 and w[0] == '$' and (w[1:].isdigit() or (w[1:].count('.') == 1 and all(p.isdigit() for p in w[1:].split('.') if p))):
            w = w[1:]
            is_dollar = True
        if not is_dollar and w.count(':') == 1:
            _hour_part, _minute_part = w.split(':')
            if _hour_part.isdigit() and len(_minute_part) == 2 and _minute_part.isdigit():
                tokens.append((_hour_part, None))
                clock.append(len(tokens))
                tokens.append((_minute_part, punct))
                continue
        if is_dollar and w.count('.') == 1:
            # $5.25 -- kPeriodTok's SEPARATE branch for a dollar-flagged
            # token (FrontEnd.c:2096-2101): the "." becomes the word
            # "AND" (not "POINT") and the following digits are read as
            # a cardinal with "cent"/"cents" appended (kAddCent), not
            # digit-by-digit -- e.g. "five dollars AND twenty five
            # cents", not "five dollars point two five".
            _int_part, _frac_part = w.split('.')
            if _int_part and _frac_part and _int_part.isdigit() and _frac_part.isdigit():
                dollar.append(len(tokens))
                tokens.append((_int_part, None))
                tokens.append(("AND", None))
                cent.append(len(tokens))
                tokens.append((_frac_part, punct))
                continue
        if not is_dollar and w.count('.') == 1:
            _int_part, _frac_part = w.split('.')
            if _int_part and _frac_part and _int_part.isdigit() and _frac_part.isdigit():
                tokens.append((_int_part, None))
                tokens.append(("POINT", None))
                decimal_frac.append(len(tokens))
                tokens.append((_frac_part, punct))
                continue
        if w.isdigit():
            # Preserve a pure digit run as its own token instead of
            # stripping it (FrontEnd.c's kNumericTok path,
            # ProcessNumberString -- see _numbers.py for the cardinal-
            # reading port this feeds via _assembly.make_fe_word_token).
            if is_dollar:
                dollar.append(len(tokens))
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
            entry = lookup(w + '.')
            if entry is not None and entry.is_abbrev:
                w = w + '.'
                punct = None
        tokens.append((w, punct))
    return TokenStream(
        tokens=tokens, dollar=dollar, decimal_frac=decimal_frac,
        cent=cent, clock=clock,
    )


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
    `test/test_synthesize_text.py`), which assembling the whole input as one
    clause does not.
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
