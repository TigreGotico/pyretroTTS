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
