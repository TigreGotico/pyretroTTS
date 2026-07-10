"""Port of `PartialNumberToPhonemes`'s cardinal-number reading
(`FrontEnd.c:1765-1888`), scoped to plain digit-string input (no
year/clock/dollar/cent special modes -- `kYearSpecial`/`kClockSpecial`/
`kAddDollar`/`kAddCent`, `FrontEnd.c:1783-1824`/`1893-1902`, not ported).

VERIFICATION STATUS (see docs/architecture.md "Known gaps" for the full
history): the individual number WORDS below (`ZERO`-`NINETEEN`,
`TWENTY`-`NINETY`, `AND`) are extracted directly from the compiled
`lintalker-c` `test_harness` (mid-utterance, avoiding the word-final
pronunciation artifact documented in `docs/architecture.md`) and are
bit-exact. `HUNDRED`/`THOUSAND`/`MILLION`/`BILLION` are ALSO extracted
this way, but from the MAIN dictionary word lookup path (typing
"hundred two." as text), NOT from the `Symbols` dictionary's numeric-key
lookup (`SearchAllDicts(vv, "\\p100", ...)`) `PartialNumberToPhonemes`
itself uses -- confirmed via direct instrumentation that THIS specific
compiled `Symbols` dictionary's "100"/"1000"-class numeric keys are
corrupted (resolve to the same phonemes as the digit "1", not "hundred"
-- see docs/architecture.md), so there is no way to extract a *verified*
value for these words from the reference at all. Using the ordinary
dictionary word's pronunciation instead is a well-justified substitute
(there's no reason "hundred" would be pronounced differently as a scale
word than as an ordinary word), but it is NOT independently confirmed
against a working reference. The GROUPING algorithm itself (which words
combine for which digit patterns, including the "AND" insertion rule)
is a faithful transcription of `PartialNumberToPhonemes`/
`AppendTwoDigitPhonemes`/`AppendThreeDigitPhonemes`, but --- because the
compiled reference's own bare-digit-string path is corrupted the same
way (confirmed: typing "123" produces "one ONE and twenty three", not
"one hundred and twenty three") --- there is no working reference to
verify the ASSEMBLED multi-digit output against either. In short: every
individual building block is verified bit-exact; the algorithm that
combines them is a careful, faithful port of the documented C logic,
but the combination itself is unverified end-to-end.
"""
from __future__ import annotations

from ._phonemes import _Word_

# Raw phoneme-id lists (no _Word_ prefix, no stress markers -- matches
# the plain frame-level phoneme stream, same representation
# _morph.py's suffix helpers operate on), extracted mid-utterance
# (e.g. "one two." with TWO's own trailing phonemes stripped) from the
# compiled lintalker-c test_harness. See module docstring for exactly
# which of these are independently verified vs. substituted.
_ONES = {
    0: [41, 17, 14],        # ZERO
    1: [28, 5, 34],          # ONE
    2: [46, 15],              # TWO
    3: [38, 30, 0],           # THREE
    4: [36, 20],               # FOUR
    5: [36, 11, 37],          # FIVE
    6: [40, 1, 48, 40],       # SIX
    7: [40, 2, 37, 8, 34],    # SEVEN
    8: [10, 46],               # EIGHT
    9: [34, 11, 34],          # NINE
}

_TEENS = {
    10: [46, 2, 34],                      # TEN
    11: [26, 2, 37, 8, 34],               # ELEVEN
    12: [46, 28, 2, 25, 37],              # TWELVE
    13: [38, 9, 53, 0, 34],               # THIRTEEN
    14: [36, 20, 53, 0, 34],              # FOURTEEN
    15: [36, 1, 36, 46, 0, 34],           # FIFTEEN
    16: [40, 1, 48, 40, 46, 0, 34],       # SIXTEEN
    17: [40, 2, 37, 8, 34, 46, 0, 34],    # SEVENTEEN
    18: [10, 53, 0, 34],                  # EIGHTEEN
    19: [34, 11, 34, 46, 0, 34],          # NINETEEN
}

_TENS = {
    2: [46, 28, 2, 34, 46, 0],   # TWENTY
    3: [38, 9, 53, 0],           # THIRTY
    4: [36, 20, 53, 0],          # FORTY
    5: [36, 1, 36, 46, 0],       # FIFTY
    6: [40, 1, 48, 40, 46, 0],   # SIXTY
    7: [40, 2, 37, 27, 46, 0],   # SEVENTY
    8: [10, 53, 0],              # EIGHTY
    9: [34, 11, 34, 46, 0],      # NINETY
}

_AND = [2, 34, 47]

# NOT independently verified -- see module docstring's "VERIFICATION
# STATUS" for exactly why (extracted from the main dictionary's ordinary
# word entries, substituting for the compiled Symbols dictionary's
# corrupted numeric-key lookup for these specific words).
_HUNDRED = [32, 5, 34, 47, 30, 8, 47]
_THOUSAND = [38, 13, 41, 27, 47]
_MILLION = [33, 1, 25, 29, 1, 34]
_BILLION = [45, 1, 25, 29, 1, 34]
_POWERS = {1: _THOUSAND, 2: _MILLION, 3: _BILLION}

# "OH" -- unlike _HUNDRED/_THOUSAND/etc. above (extracted from ordinary
# dictionary words as a corruption workaround), this is a DIRECT,
# bit-exact transcription of `Data.c:3840`'s compiled-in constant
# `OhPhonStr[] = {3, _Word_, _Stress1_, _OW_}` (a literal C source byte
# array, not a runtime dictionary lookup -- no Symbols-dictionary
# corruption or verification caveat applies to it at all), with the
# leading `_Word_` opcode dropped for the same reason `_ONES`/`_TEENS`/
# `_TENS` above don't carry one either (this port's number-reading
# functions add a single `_Word_` prefix once, at the very start of
# their output, rather than one per real-engine sub-word group).
_OH = [56, 14]

# Same direct, bit-exact transcription as `_OH` above -- literal
# compile-time constants (`Data.c:3837`'s `DollarPhonStr[] = {7, _Word_,
# _d_, _Stress1_, _AA_, _l_, _ER_, _z_}` and `Data.c:3838`'s
# `CentPhonStr[] = {7, _Word_, _s_, _Stress1_, _EH_, _n_, _t_, _s_}`),
# leading `_Word_` dropped for the same reason as `_OH`. Each is the
# PLURAL form ("dollars"/"cents"); `Parse_Number...`'s singular case
# (`FrontEnd.c:1896`/`1902`: `tok->phonStr[0] -= 1`) just drops the
# final phoneme -- the trailing `_z_`/`_s_` -- to get "dollar"/"cent".
_DOLLAR = [47, 56, 4, 31, 9, 41]
_CENT = [40, 56, 2, 34, 46, 40]


def _two_digit_phonemes(tens: int, units: int) -> list:
    """Port of `AppendTwoDigitPhonemes` (`FrontEnd.c:1708-1738`)."""
    if tens == 0:
        return list(_ONES[units])
    if tens == 1:
        return list(_TEENS[10 + units])
    out = list(_TENS[tens])
    if units != 0:
        out += _two_digit_phonemes(0, units)
    return out


def _three_digit_phonemes(hundreds: int, tens: int, units: int) -> list:
    """Port of `AppendThreeDigitPhonemes` (`FrontEnd.c:1745-1763`)."""
    out = []
    if hundreds > 0:
        out += _two_digit_phonemes(0, hundreds)
        out += _HUNDRED
    if tens != 0 or units != 0:
        out += _two_digit_phonemes(tens, units)
    return out


def number_to_phonemes(digits: str):
    """Port of `PartialNumberToPhonemes`'s cardinal-reading algorithm
    (`FrontEnd.c:1765-1888`), collapsed into a single non-incremental
    pass (the real function is called repeatedly, once per "chunk", by
    a token-at-a-time synthesis loop this port doesn't have -- see
    `_assembly.py`'s adaptation notes for the same class of
    simplification elsewhere). `digits` must be a non-empty string of
    decimal digit characters (no sign, decimal point, or grouping
    commas -- those belong to `ProcessNumberString`, not ported).
    Returns a `_Word_`-prefixed phoneme opcode list, matching every
    other word-phoneme source in this port (`_lexicon.lookup`,
    `_engtop.engtop`, `_morph.try_do_morph`).

    Numbers of 13+ digits (beyond `BILLION`) fall back to reading NO
    power-of-1000 label at all for the excess high-order group (the
    real engine's `PowerStr`/`SearchAllDicts` mechanism has no such
    limit, but extracting labels beyond "billion" wasn't attempted here
    -- a documented, narrow scope limit, not a correctness bug for any
    number under 10^12).
    """
    n = len(digits)
    out = []
    pos = 0
    while pos < n:
        digits_left = n - pos
        have_spoken = bool(out)
        if digits_left == 1:
            out += _two_digit_phonemes(0, int(digits[pos]))
            pos += 1
        elif digits_left == 2:
            tens, units = int(digits[pos]), int(digits[pos + 1])
            if tens != 0 or units != 0 or not have_spoken:
                if n >= 3 and have_spoken:
                    out += _AND
                out += _two_digit_phonemes(tens, units)
            pos += 2
        elif digits_left == 3:
            out += _three_digit_phonemes(int(digits[pos]), 0, 0)
            pos += 1
        else:
            power = (digits_left - 1) // 3
            rem = digits_left % 3
            if rem == 0:
                h, t, u = int(digits[pos]), int(digits[pos + 1]), int(digits[pos + 2])
                pos += 3
            elif rem == 2:
                h, t, u = 0, int(digits[pos]), int(digits[pos + 1])
                pos += 2
            else:
                h, t, u = 0, 0, int(digits[pos])
                pos += 1
            if h or t or u:
                out += _three_digit_phonemes(h, t, u)
                if power in _POWERS:
                    out += _POWERS[power]
    return [_Word_] + out


def is_year_number(digits: str) -> bool:
    """Port of `SpeakTokenAsNumber`'s automatic `kYearSpecial` detection
    (`FrontEnd.c:1978-1990`): a plain 4-digit number token starting with
    `1` (i.e. 1001-1999) is automatically read year-style instead of as
    a grouped cardinal, UNLESS it's exactly `"1000"`. This is a real,
    narrow limitation of the C reference ITSELF -- years starting with
    any other digit (e.g. "2023") are never detected this way, matching
    `tok->tokStr[1] == '1'`'s literal check -- not a scope reduction made
    by this port. (The real engine also suppresses this when the token
    carries `kAddDollar`/`kAddCent`/`kHasComma` flags -- i.e. currency
    amounts and comma-grouped numbers are never read as years -- but
    since those flags aren't set anywhere in this port's simplified
    tokenizer to begin with, plain 4-digit tokens never carry them.)
    """
    return len(digits) == 4 and digits[0] == '1' and digits != '1000'


def year_to_phonemes(digits: str):
    """Port of `PartialNumberToPhonemes`'s `kYearSpecial` branch
    (`FrontEnd.c:1778-1795`, invoked repeatedly by the real incremental
    synth loop -- collapsed into one pass here, the same simplification
    `number_to_phonemes` already makes): splits a 4-digit year into two
    2-digit groups and reads each with `AppendTwoDigitPhonemes`, EXCEPT
    when a group's tens digit is `0`: `01`-`09` is read "oh" + the units
    digit (`vv->OhPhonStr`, see `_OH` above) rather than just the units
    digit alone (unlike the generic 2-digit case, which has no such "oh"
    insertion), and `00` is read as `_HUNDRED` (a direct port of the
    `SearchAllDicts(vv, "\\p100", ...)` call in that branch -- the same
    `Symbols`-dictionary numeric key already confirmed corrupted for the
    general 1000s-labeling case, substituted here the same well-justified
    way: as the ordinary dictionary word "hundred"). No `AND` insertion
    (unlike the generic case): the year branch has no equivalent of the
    generic 2-digit case's `haveSpoken`/`AND` logic at all. `digits` must
    satisfy `is_year_number(digits)`.
    """
    def _group(tens: int, units: int) -> list:
        if tens != 0:
            return _two_digit_phonemes(tens, units)
        if units != 0:
            return _OH + _two_digit_phonemes(0, units)
        return list(_HUNDRED)

    out = _group(int(digits[0]), int(digits[1])) + _group(int(digits[2]), int(digits[3]))
    return [_Word_] + out


def dollar_phonemes(digits: str):
    """Port of the `kAddDollar` suffix applied by `PartialNumberToPhonemes`
    (`FrontEnd.c:1893-1897`): a plain digit string preceded by `$`
    (`GetNextToken`'s `$`-followed-by-digit handling, `FrontEnd.c:1017
    -1027`) is read as a grouped cardinal number (same as `number_to_
    phonemes`, INCLUDING automatic year detection being bypassed --
    `SpeakTokenAsNumber`'s `kYearSpecial` check explicitly excludes
    tokens with `kAddDollar` set, `FrontEnd.c:1982-1983`) followed by
    "dollar"/"dollars" (`_DOLLAR`, singular when the amount is exactly
    1 -- `FrontEnd.c`'s `kMoreThanOne` flag, `!= 1` in plain digit
    terms).
    """
    body = number_to_phonemes(digits)[1:]  # strip its own leading _Word_
    suffix = list(_DOLLAR) if int(digits) != 1 else _DOLLAR[:-1]
    return [_Word_] + body + suffix


def digit_by_digit_phonemes(digits: str):
    """Port of `SpeakTokenCharByChar`'s digit-by-digit branch
    (`FrontEnd.c:2057-2062`, `kDigitByDigit`/`EmbeddedCmd.c`'s `nmbr LTRL`
    command): each digit is read out on its own (e.g. "123" -> "one two
    three") instead of being grouped into a cardinal number. Reuses the
    same bit-exact `_ONES` words `number_to_phonemes` does -- unlike the
    grouping algorithm, this needs no `HUNDRED`/`THOUSAND`/`AND` at all,
    so it carries no additional verification caveat beyond the
    already-bit-exact single-digit words themselves.
    """
    out = []
    for ch in digits:
        out += _ONES[int(ch)]
    return [_Word_] + out
