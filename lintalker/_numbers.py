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
