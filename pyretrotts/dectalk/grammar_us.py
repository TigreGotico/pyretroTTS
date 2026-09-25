"""DECtalk US word-level syntactic marking: phrase markers + closed-class words.

The US front end has no runtime syntactic parser (the `cmd/par_*.c` files are a
text preprocessor, not a POS parser). The phrase markers `phclause` reads in its
`symbols[]` stream come from two places in the word-reading path, both of which
this module reproduces:

- **Dictionary form class.** After a word is found in `dtalk_us.dic`, its stored
  form-class bitfield (`ls_dict.c:759-763`, `pent->fc[0]`, decoded through the
  identity `DICT_FC_ACCESS` for the compiled US path) decides a phrase marker:
  `PPSTART` when `(fc & PPHRASE) == PPHRASE` and `VPSTART` when
  `(fc & VPHRASE) == VPHRASE` or `fc == FC_VERB` (`ls_defs.h:658-659`,
  `VPHRASE = FC_VERB|FC_CHARACTER`, `PPHRASE = FC_PREP|FC_CHARACTER`). The verb
  marker replaces the ordinary word boundary in the stream `phclause` receives
  (the `ph_task.c:870-897` marker-strength collapse drops the weaker `WBOUND`
  before the stronger `VPSTART`); the prep marker follows the boundary.
- **The closed-class mini-dictionary `sdic[]`** (`l_us_con.c:1157`,
  `ls_task_minidic_search`, `ls_task.c:1874`). The words `for`, `and`, `to` are
  looked up here before the main dictionary and pronounced from a fixed list
  that begins with `PPSTART`, so they carry a prep-phrase marker and their own
  (reduced) pronunciation regardless of the main dictionary.

Clause-final promotion of a prep-phrase function word (`ph_sort.c:1116`, the
"kludge to compensate for lack of a decent parser": demote `PPSTART` to
`WBOUND`, un-reduce the vowel, raise the stress) runs inside `phclause`'s
`phsort` stage (`allophones.py`), so it is not applied here; this module emits
the mid-clause form and lets that stage promote a clause-final occurrence.

Derived from the Fonix/Force DECtalk C source (`dectalk/dectalk`,
`src/dapi/src/lts/ls_dict.c`, `lts/l_us_con.c`, `lts/ls_task.c`). FONIX
Corporation declares that source proprietary and confidential. This file is NOT
covered by this project's MIT licence. See NOTICE.
"""
from __future__ import annotations

from .dictionary import Dictionary

# l_com_ph.h prosody codes.
_WBOUND = 111
_PPSTART = 112
_VPSTART = 113

# fc_def.tab form-class bits (the compiled US mask is the stored field directly).
_FC_CHARACTER = 0x02000000
_FC_PREP = 0x00001000
_FC_VERB = 0x00020000
# ls_defs.h:658-659.
_VPHRASE = _FC_VERB | _FC_CHARACTER
_PPHRASE = _FC_PREP | _FC_CHARACTER

# l_all_ph.h phoneme codes.
_US_AE, _US_UH, _US_RR, _US_N, _US_F, _US_T, _US_D = 5, 13, 15, 32, 37, 47, 48
_US_AX = 17

# l_com_ph.h control code (`SPECIALWORD`, deleted by `phsort`, allophones.py:672).
_SPECIALWORD = 120

# l_us_con.c sdic[]: the closed-class words looked up before the main dictionary,
# each pronounced from a PPSTART-led fixed list. The SIL that ends every sdic
# entry is a boundary that does not reach the captured symbol stream; the codes
# here are the reduced pronunciation the oracle emits mid-clause (verified).
SDIC: dict[str, tuple[int, ...]] = {
    "for": (_US_F, _US_RR),
    "and": (_US_AE, _US_N, _US_D),
    "to": (_US_T, _US_UH),
}


def article_a_codes(word: str, clause_final: bool) -> tuple[int, ...] | None:
    """Reduced schwa codes for a standalone in-context article ``a``, else None.

    `ls_task.c:2632-2645` special-cases the single-character word ``a``/``A``:
    when it is not stripped by an adjacent quote/paren and the next item is
    whitespace (another word follows before any punctuation), it is read as the
    reduced article ``[SPECIALWORD, US_AX]`` (form class `FC_ART`) instead of the
    dictionary citation spelling ``['e]`` = ``[S1, EY]``. `phsort`
    (`ph_sort.c:1024`, allophones.py:672) then deletes the `SPECIALWORD`, so the
    post-`phsort` body the oracle emits is the bare schwa ``US_AX``; that is what
    this returns. A clause-final ``a`` (against punctuation or the input end) is
    not whitespace-followed, so it keeps the citation form -- return None then.
    """
    if word not in ("a", "A") or clause_final:
        return None
    return (_US_AX,)


def _is_verb(fc: int) -> bool:
    return (fc & _VPHRASE) == _VPHRASE or fc == _FC_VERB


def _is_prep(fc: int) -> bool:
    return (fc & _PPHRASE) == _PPHRASE


def word_markers(word: str, dictionary: Dictionary | None) -> tuple[int, ...] | None:
    """Leading marker codes for `word`, or None to use the plain word boundary.

    Returns the boundary/phrase codes that precede the word's phonemes:
    `(VPSTART,)` for a dictionary verb (the verb marker replaces the boundary),
    `(WBOUND, PPSTART)` for a closed-class prep-phrase word, or None when the
    caller should emit its own plain `WBOUND`.
    """
    if word in SDIC:
        return (_WBOUND, _PPSTART)
    if dictionary is None:
        return None
    fc = dictionary.lookup_fc(word)
    if fc is None:
        return None
    if _is_verb(fc):
        return (_VPSTART,)
    if _is_prep(fc):
        return (_WBOUND, _PPSTART)
    return None


__all__ = ["SDIC", "article_a_codes", "word_markers"]
