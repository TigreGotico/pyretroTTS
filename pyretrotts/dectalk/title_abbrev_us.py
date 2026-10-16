"""DECtalk US title-abbreviation disambiguation: `Dr.`/`St.` title vs word.

`ls_task.c:2910` (`ls_task_Dr_St_process`) reads `Dr.` and `St.` from a dedicated
fixed phone list rather than the dictionary, choosing between a destressed TITLE
reading before a name (`pdoctor`/`psaint`) and the full WORD reading otherwise
(`pdrive`/`pstreet`). The four lists live in `l_us_con.c:615-629`. Only `Dr` and
`St` have this treatment; `Mr`/`Mrs`/`Ms` expand through the ordinary
abbreviation table.

The selection rule (`ls_task.c:2931-2977`), reached only when a `.` follows the
abbreviation:

- abbreviation is clause-final (no word follows, only punctuation/end): WORD;
- the following word is capitalized (a name) and is not itself a back-to-back
  `Dr`/`St`: TITLE (`ls_task.c:2944-2955`);
- the following word is capitalized but is exactly `Dr`/`St`: WORD (the
  back-to-back fix, `ls_task.c:2947-2953`);
- the following word is lowercase and the abbreviation is the first word of the
  sentence (`cur_word_index == 1`, `ls_task.c:2961`): TITLE;
- otherwise: WORD.

The fixed lists each end in `SIL`; that trailing boundary does not reach the
captured `phclause` symbol stream (as with the `sdic[]` entries in
`grammar_us.py`), so the bodies here omit it and carry a plain word boundary.

Derived from the Fonix/Force DECtalk C source (`dectalk/dectalk`,
`src/dapi/src/lts/ls_task.c`, `lts/l_us_con.c`). FONIX Corporation declares that
source proprietary and confidential. This file is NOT covered by this project's
MIT licence. See NOTICE.
"""
from __future__ import annotations

from dataclasses import dataclass

# `l_us_ph.h` phoneme codes (raw send-code bodies, matching `numbers_us.py`).
_D, _AA, _K, _T, _RR = 48, 6, 49, 47, 15
_R, _AY, _V = 26, 7, 38
_S, _EY, _N = 41, 3, 32
_IY = 1
# `l_com_ph.h` stress marks.
_S1, _S2 = 103, 102

# `l_us_con.c:615-629`, trailing `SIL` dropped (boundary, not a stream symbol).
_PDOCTOR: tuple[int, ...] = (_D, _AA, _K, _T, _RR)
_PDRIVE: tuple[int, ...] = (_D, _R, _S1, _AY, _V)
_PSAINT: tuple[int, ...] = (_S, _EY, _N, _T)
_PSTREET: tuple[int, ...] = (_S, _T, _R, _S2, _IY, _T)


@dataclass(frozen=True)
class _TitleReading:
    """The two fixed phone-list readings of one title abbreviation."""

    title: tuple[int, ...]
    word: tuple[int, ...]


# The abbreviations with a dedicated title/word phone list (`ls_task.c:2936`).
TITLE_ABBREVIATIONS: dict[str, _TitleReading] = {
    "dr": _TitleReading(title=_PDOCTOR, word=_PDRIVE),
    "st": _TitleReading(title=_PSAINT, word=_PSTREET),
}


def title_abbrev_body(
    abbrev: str, next_word: str | None, sentence_initial: bool
) -> tuple[int, ...] | None:
    """Fixed phone body for a `.`-terminated title abbreviation, else None.

    `abbrev` is the lowercased token (`dr`/`st`); `next_word` is the raw word
    that follows the abbreviation's period in the same clause, or None when the
    abbreviation is clause-final. `sentence_initial` is whether the abbreviation
    is the sentence's first word (`cur_word_index == 1`).
    """
    reading = TITLE_ABBREVIATIONS.get(abbrev)
    if reading is None:
        return None
    if next_word is None:
        return reading.word
    if next_word[:1].isupper() and next_word.lower() not in TITLE_ABBREVIATIONS:
        return reading.title
    if next_word[:1].isupper():
        return reading.word
    if sentence_initial:
        return reading.title
    return reading.word


__all__ = ["TITLE_ABBREVIATIONS", "title_abbrev_body", "_TitleReading"]
