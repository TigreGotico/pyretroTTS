"""DECtalk US number/say-as expansion to a word sequence (`lts/l_us_con.c`).

The US word-reading front end turns a digit token into the word sequence it then
pronounces through the ordinary dictionary/letter-to-sound path: integers read
in three-digit groups (`one hundred and twenty three`), a decimal point read as
`point` followed by digit names, currency read as `<amount> dollars`, ordinals
(`1st` -> `first`), and four-digit years read in two halves. This ports that
word sequence; the pronunciation of each produced word is the existing word
layer's job, and the produced words are framed by `sentence_us.py` exactly as
typed words are.

Derived from the Fonix/Force DECtalk C source (`dectalk/dectalk`,
`src/dapi/src/lts/l_us_con.c`). FONIX Corporation declares that source
proprietary and confidential. This file is NOT covered by this project's MIT
licence. See NOTICE.
"""
from __future__ import annotations

_ONES = (
    "zero", "one", "two", "three", "four", "five", "six", "seven", "eight",
    "nine", "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen",
    "sixteen", "seventeen", "eighteen", "nineteen",
)
_TENS = (
    "", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty",
    "ninety",
)
_SCALE = ("", "thousand", "million", "billion", "trillion")

_ORDINAL = {
    "one": "first", "two": "second", "three": "third", "five": "fifth",
    "eight": "eighth", "nine": "ninth", "twelve": "twelfth",
}


def _below_100(n: int) -> list[str]:
    if n < 20:
        return [_ONES[n]]
    tens, ones = divmod(n, 10)
    return [_TENS[tens]] + ([_ONES[ones]] if ones else [])


def _below_1000(n: int) -> list[str]:
    if n < 100:
        return _below_100(n)
    hundreds, rest = divmod(n, 100)
    words = [_ONES[hundreds], "hundred"]
    if rest:
        words += ["and"] + _below_100(rest)
    return words


def say_cardinal(n: int) -> list[str]:
    """Integer as a word sequence (`one hundred and twenty three`)."""
    if n < 0:
        return ["minus"] + say_cardinal(-n)
    if n == 0:
        return ["zero"]
    groups: list[int] = []
    while n > 0:
        n, g = divmod(n, 1000)
        groups.append(g)
    words: list[str] = []
    top = len(groups) - 1
    for i in range(top, -1, -1):
        g = groups[i]
        if g == 0:
            continue
        # A trailing group below 100, after higher groups, reads with "and"
        # ("two thousand and five"); a leading or hundreds-bearing group does not.
        if i == 0 and g < 100 and words:
            words.append("and")
        words += _below_1000(g) if i else _below_1000(g)
        if i:
            words.append(_SCALE[i])
    return words


def say_ordinal(n: int) -> list[str]:
    """Integer as an ordinal word sequence (`21` -> `twenty first`)."""
    words = say_cardinal(n)
    words[-1] = _ORDINAL.get(words[-1], _suffix_ordinal(words[-1]))
    return words


def _suffix_ordinal(word: str) -> str:
    if word.endswith("y"):
        return word[:-1] + "tieth"
    return word + "th"


def say_digits(digits: str) -> list[str]:
    """Each digit as its name (`point one four`, `zero five`)."""
    return [_ONES[int(c)] for c in digits if c.isdigit()]


def say_year(n: int) -> list[str]:
    """Four-digit year read in two halves (`1984` -> `nineteen eighty four`)."""
    if not (1000 <= n <= 9999) or n % 100 == 0:
        return say_cardinal(n)
    hi, lo = divmod(n, 100)
    if lo < 10:
        return say_cardinal(hi) + ["oh"] + _below_100(lo)
    return say_cardinal(hi) + _below_100(lo)


def expand_number_token(token: str) -> list[str] | None:
    """Expand a numeric/currency/ordinal token to words, or None if not numeric."""
    t = token.strip()
    if not t:
        return None
    if t.startswith("$"):
        rest = t[1:].replace(",", "")
        if rest.isdigit():
            return say_cardinal(int(rest)) + [
                "dollar" if int(rest) == 1 else "dollars"]
        return None
    body = t.replace(",", "")
    m = _ORDINAL_RE.match(body)
    if m:
        return say_ordinal(int(m.group(1)))
    if "." in body:
        left, _, right = body.partition(".")
        if left.isdigit() and right.isdigit():
            whole = say_cardinal(int(left)) if left else ["zero"]
            return whole + ["point"] + say_digits(right)
        return None
    if body.isdigit():
        return say_cardinal(int(body))
    return None


import re  # noqa: E402

_ORDINAL_RE = re.compile(r"^(\d+)(?:st|nd|rd|th)$", re.IGNORECASE)


# ---------------------------------------------------------------------------
# The digit-path number/currency reader (`lts/l_us_pr1.c` `ls_proc_do_number`,
# `ls_proc_do_digit_group`; `lts/ls_task.c` currency).
#
# The C reads a digit token by shipping fixed phoneme+marker lists straight
# into the phone stream (`ls_util_send_phone_list`), not by expanding to words
# and re-looking-them-up. Two of those lists diverge from the main dictionary:
# the hundreds/scale `and` (`pand`) carries a `VPSTART` and the vowel `EH`, not
# the closed-class `sdic` `and`; and the currency `dollar(s)` (`pdollar`) uses
# the vowel `AA` with no schwa, not the dictionary's stem. Reproducing the
# lists verbatim is what makes `123`, `2005`, `$5`, `$5.25` frame bit-exact.
# `ls_util_send_phone_list` stops at the terminating `SIL`, so the trailing
# `SIL` of each C list is a terminator and is not emitted.
# ---------------------------------------------------------------------------

# l_us_ph.h / l_com_ph.h codes used by the phone lists.
_SIL = 0
_IY, _IH, _EY, _EH, _AE, _AA, _AY, _AW, _AH, _AO, _OW, _OY = (
    1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12)
_UW, _RR, _AX, _OR, _W, _Y, _R, _LL, _HX = 14, 15, 17, 22, 24, 25, 26, 27, 28
_M, _N, _F, _V, _TH, _S, _Z, _P, _B, _T, _D, _K, _G = (
    31, 32, 37, 38, 39, 41, 42, 45, 46, 47, 48, 49, 50)
_IX = 18
_MBOUND, _WBOUND, _VPSTART = 109, 111, 113
_S1 = 103

# punits[0..9] (`l_us_con.c:637-716`).
_PUNITS = (
    (_Z, _S1, _IY, _R, _OW), (_W, _S1, _AH, _N), (_T, _S1, _UW),
    (_TH, _R, _S1, _IY), (_F, _S1, _OR), (_F, _S1, _AY, _V),
    (_S, _S1, _IH, _K, _S), (_S, _S1, _EH, _V, _AX, _N), (_S1, _EY, _T),
    (_N, _S1, _AY, _N),
)
# pteens[0..9] = p10..p19 (`l_us_con.c:749-800`).
_PTEENS = (
    (_T, _S1, _EH, _N), (_AX, _LL, _S1, _EH, _V, _AX, _N),
    (_T, _W, _S1, _EH, _LL, _V),
    (_TH, _S1, _RR, _MBOUND, _T, _S1, _IY, _N),
    (_F, _S1, _OR, _MBOUND, _T, _S1, _IY, _N),
    (_F, _S1, _IH, _F, _MBOUND, _T, _S1, _IY, _N),
    (_S, _S1, _IH, _K, _S, _MBOUND, _T, _S1, _IY, _N),
    (_S, _S1, _EH, _V, _AX, _N, _MBOUND, _T, _S1, _IY, _N),
    (_S1, _EY, _MBOUND, _T, _S1, _IY, _N),
    (_N, _S1, _AY, _N, _MBOUND, _T, _S1, _IY, _N),
)
# ptens[0..9]: p0/p1 are pnone (`l_us_con.c:812-855`).
_PTENS = (
    (), (), (_T, _W, _S1, _EH, _N, _T, _IY), (_TH, _S1, _RR, _T, _IY),
    (_F, _S1, _OR, _T, _IY), (_F, _S1, _IH, _F, _T, _IY),
    (_S, _S1, _IH, _K, _S, _T, _IY), (_S, _S1, _EH, _V, _AX, _N, _T, _IY),
    (_S1, _EY, _T, _IY), (_N, _S1, _AY, _N, _T, _IY),
)
# pordin[0..9] = p0th..p9th (`l_us_con.c:951-1005`).
_PORDIN = (
    (_Z, _S1, _IY, _R, _OW, _TH), (_F, _S1, _RR, _S, _T),
    (_S, _S1, _EH, _K, _AX, _N, _D), (_TH, _S1, _RR, _D),
    (_F, _S1, _OR, _TH), (_F, _S1, _IH, _F, _TH),
    (_S, _S1, _IH, _K, _S, _TH), (_S, _S1, _EH, _V, _AX, _N, _TH),
    (_S1, _EY, _TH), (_N, _S1, _AY, _N, _TH),
)
_PHUNDRED = (_HX, _S1, _AH, _N, _D, _R, _AX, _D)
_PTHOUSAND = (_TH, _S1, _AW, _Z, _AX, _N, _D)
_PMILLION = (_M, _S1, _IH, _LL, _Y, _AX, _N)
_PBILLION = (_B, _S1, _IH, _LL, _Y, _AX, _N)
_PTRILLION = (_T, _R, _S1, _IH, _LL, _Y, _AX, _N)
_PQUADRILLION = (_K, _W, _AO, _D, _R, _S1, _IH, _LL, _Y, _AX, _N)
# pand carries a VPSTART and the vowel EH (`l_us_con.c:873`). The C list opens
# with a WBOUND; `phsort` collapses it against the preceding boundary (its role
# is taken by the word boundary already emitted before every scale word), so the
# post-`phsort` form the oracle emits -- and the form spliced here, matching the
# codebase's post-`phsort` convention -- starts at the VPSTART.
_PAND = (_VPSTART, _EH, _N, _D, _WBOUND)
_PPOINT = (_P, _S1, _OY, _N, _T)
_PMINUS = (_M, _S1, _AY, _N, _AX, _S)
# pdollar/pcent carry a leading WBOUND (`l_us_con.c:857,869`).
_PDOLLAR = (_WBOUND, _D, _S1, _AA, _LL, _RR)
_PCENT = (_S, _S1, _EH, _N, _T)


def _non_zero(digits: str) -> bool:
    return any(c != "0" for c in digits)


def _do_digit_group(buf: str, oflag: bool, out: list[int]) -> None:
    """`ls_proc_do_digit_group` (`l_us_pr1.c:427`): one three-digit group."""
    if buf[0] != "0":
        out.extend(_PUNITS[int(buf[0])])
        out.append(_WBOUND)
        out.extend(_PHUNDRED)
        if buf[1] == "0" and buf[2] == "0":
            if oflag:
                out.append(_TH)
            return
        out.extend(_PAND)
    if buf[1] == "1":
        out.extend(_PTEENS[int(buf[2])])
        if oflag:
            out.append(_TH)
        return
    if buf[1] != "0":
        out.extend(_PTENS[int(buf[1])])
        if buf[2] == "0":
            if oflag:
                out.append(_IX)
                out.append(_TH)
            return
        out.append(_WBOUND)
    out.extend(_PORDIN[int(buf[2])] if oflag else _PUNITS[int(buf[2])])


_SCALES = (
    (0, _PQUADRILLION), (3, _PTRILLION), (6, _PBILLION), (9, _PMILLION),
    (12, _PTHOUSAND),
)


def _do_number(digits: str, oflag: bool, out: list[int]) -> bool:
    """`ls_proc_do_number` (`l_us_pr1.c:508`) for a bare integer; returns plural.

    Ports the compiled (non-HLSYN) integer path: right-justify up to 18 digits
    into three-digit groups, read each scale group with its scale word, and join
    with a `VPSTART` (only the final ones digit left), `pand` (a bare final tens),
    or a comma. Leading-zero and >18-digit tokens fall back to per-digit reading.
    """
    n = len(digits)
    if n == 0:
        return False
    if n > 18 or (n > 1 and digits[0] == "0"):
        for i, c in enumerate(digits):
            out.extend(_PUNITS[int(c)])
            if i != n - 1:
                out.append(_WBOUND)
        return True
    buf = digits.rjust(18, "0")
    pflag = not (n == 1 and digits == "1")
    for start, word in _SCALES:
        if not _non_zero(buf[start:start + 3]):
            continue
        _do_digit_group(buf[start:start + 3], False, out)
        out.append(_WBOUND)
        out.extend(word)
        if not _non_zero(buf[start + 3:]):
            if oflag:
                out.append(_TH)
            return pflag
        if not _non_zero(buf[start + 4:start + 6]):
            out.append(_VPSTART)
        elif not _non_zero(buf[start + 3:start + 4]):
            out.extend(_PAND)
        else:
            out.append(_WBOUND)  # COMMA in C; see note in module docstring
    _do_digit_group(buf[15:], oflag, out)
    return pflag


def number_token_send_codes(token: str) -> list[int] | None:
    """Raw send-code stream for a numeric/currency token, or None if not numeric.

    Returns the phoneme + marker codes the digit path ships (no leading word
    boundary; `sentence_us` supplies that), for a plain integer, an ordinal
    (`1st`), a signed integer, currency (`$5`, `$5.25`), or a decimal (`3.14`).
    """
    t = token.strip()
    if not t:
        return None
    out: list[int] = []
    if t.startswith("$"):
        rest = t[1:].replace(",", "")
        if "." in rest:
            whole, _, frac = rest.partition(".")
            if not (whole.isdigit() and frac.isdigit()):
                return None
            plural = _do_number(whole, False, out)
            out.extend(_PDOLLAR)
            if plural:
                out.append(_Z)
            if frac not in ("", "0", "00"):
                out.extend(_PAND)
                cents = frac[1:] if frac[0] == "0" else frac
                cplural = _do_number(cents, False, out)
                out.append(_WBOUND)
                out.extend(_PCENT)
                if cplural:
                    out.append(_S)
            return out
        if not rest.isdigit():
            return None
        plural = _do_number(rest, False, out)
        out.extend(_PDOLLAR)
        if plural:
            out.append(_Z)
        return out
    body = t.replace(",", "")
    m = _ORDINAL_RE.match(body)
    if m:
        _do_number(m.group(1), True, out)
        return out
    neg = False
    if body.startswith("-"):
        neg, body = True, body[1:]
    if "." in body:
        left, _, right = body.partition(".")
        if not right.isdigit() or (left and not left.isdigit()):
            return None
        if neg:
            out.extend(_PMINUS)
            out.append(_WBOUND)
        if left:
            _do_number(left, False, out)
            out.append(_WBOUND)
        out.extend(_PPOINT)
        for c in right:
            out.append(_WBOUND)
            out.extend(_PUNITS[int(c)])
        return out
    if not body.isdigit():
        return None
    if neg:
        out.extend(_PMINUS)
        out.append(_WBOUND)
    _do_number(body, False, out)
    return out
