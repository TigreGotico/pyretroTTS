"""Port of `EmbeddedCmd.c`'s `char` command's `LTRL` (`kCharByChar`)
letter-by-letter spelling mode: `LiteralCharToPhonemes` (`FrontEnd.c:
1664-1694`)'s printable-character branch, which looks each character up
in the `Symbols` dictionary (`SearchAllDicts(vv, ch, tok, vv->Symbols,
true)`).

Unlike `_numbers.py`'s `HUNDRED`/`THOUSAND`/etc. (substituted from
ordinary dictionary words because the `Symbols` dictionary's `"\\p100"`-
style NUMERIC keys are confirmed corrupted in this specific compiled
build) or `_rawphon.py`'s `MAGIC_MAP` (a literal compile-time table, no
runtime lookup at all), the 26 letter-name pronunciations here ARE
extracted directly from the compiled `lintalker-c` `test_harness`'s real
`Symbols`-dictionary lookup and are bit-exact -- the corruption
previously found only affects the `"100"`/`"1000"`-class SCALE-WORD
numeric keys, not plain single-character keys (confirmed: digit lookups
0-9 already work correctly the same way, see `_numbers.py`'s module
docstring).

EXTRACTION METHOD: a single-letter token surrounded by tokens of length
1 forces `WordToPhonemes`'s real `kAlphaTok` branch into
`SpeakTokenCharByChar` (`FrontEnd.c:2010-2015`: `if (cur_Tok->tokStr[0]
== 1) { if ((prev_Tok->tokStr[0] > 1) || (next_Tok->tokStr[0] > 1))
WordToPhonemes(...) else SpeakTokenCharByChar(...); }`) -- so typing the
target letter as the FIRST word of a two-letter utterance (e.g. `"b z."`
to extract `"B"`) reaches the exact same `LiteralCharToPhonemes` path
`char LTRL` mode would use for any letter, without needing the
(unverifiable, see `_embeddedcmd.py`'s module docstring) bracket-command
parser to work at all. Placing the target letter in the SENTENCE-INITIAL
position specifically avoids a real, confirmed coarticulation artifact:
a vowel-initial letter name (e.g. "E" -> /iː/) preceded by another
vowel-final sound gets a spurious glottal-stop phoneme (`_QX_`) inserted
before it (a general vowel-hiatus juncture rule, not part of the letter
Ns own pronunciation) -- confirmed by comparing the same letter's
extraction in sentence-initial position (clean) against a
vowel-adjacent position (with the extra `_QX_`) for several letters
during this investigation.
"""
from __future__ import annotations

from ._phonemes import (
    _AH_,
    _AR_,
    _AY_,
    _CH_,
    _EH_,
    _EL_,
    _EY_,
    _IY_,
    _JH_,
    _LX_,
    _OW_,
    _UW_,
    _YU_,
    _b_,
    _d_,
    _f_,
    _k_,
    _m_,
    _n_,
    _p_,
    _s_,
    _t_,
    _v_,
    _w_,
    _Word_,
    _y_,
    _z_,
)

# Extracted mid-utterance (see module docstring). Raw phoneme lists,
# no _Word_ prefix -- matches _numbers.py's _ONES/_TEENS/etc. convention
# (a single _Word_ is added once by the caller, not per-letter).
LETTER_PHONEMES = {
    'A': [_EY_],
    'B': [_b_, _IY_],
    'C': [_s_, _IY_],
    'D': [_d_, _IY_],
    'E': [_IY_],
    'F': [_EH_, _f_],
    'G': [_JH_, _IY_],
    'H': [_EY_, _CH_],
    'I': [_AY_],
    'J': [_JH_, _EY_],
    'K': [_k_, _EY_],
    'L': [_EH_, _LX_],
    'M': [_EH_, _m_],
    'N': [_EH_, _n_],
    'O': [_OW_],
    'P': [_p_, _IY_],
    'Q': [_k_, _YU_],
    'R': [_AR_],
    'S': [_EH_, _s_],
    'T': [_t_, _IY_],
    'U': [_YU_],
    'V': [_v_, _IY_],
    'W': [_d_, _AH_, _b_, _EL_, _y_, _UW_],
    'X': [_EH_, _k_, _s_],
    'Y': [_w_, _AY_],
    'Z': [_z_, _IY_],
}


def spell_word(word: str) -> list:
    """Port of `SpeakTokenCharByChar` applied to an alphabetic token
    (`FrontEnd.c:2010-2015`/`1664-1694`): concatenates each character's
    `LETTER_PHONEMES` entry (non-letter characters, e.g. an apostrophe,
    are simply skipped -- `LiteralCharToPhonemes`'s control-character/
    non-ASCII branches substitute silence for those, which isn't ported
    here). `word` should already be uppercased (matches every other
    caller of this module, `_frontend.tokenize()` always uppercases).
    Returns a `_Word_`-prefixed phoneme list, matching every other word-
    phoneme source in this port.

    VERIFICATION CAVEAT: each INDIVIDUAL letter's phonemes in
    `LETTER_PHONEMES` are bit-exact (see module docstring). Plain
    concatenation for a MULTI-letter word is NOT independently verified
    end-to-end: confirmed via direct comparison (`"c a b."` spoken as
    three separate letter tokens) that the real engine inserts an extra
    glottal-stop phoneme (`_QX_`) between two ADJACENT letters where the
    first ends in a vowel and the second starts with one (e.g. between
    "C" /siː/ and "A" /eɪ/) -- a general vowel-hiatus juncture rule
    applied across ANY word boundary, not specific to spelled letters,
    and not ported here (same class of scope limit as `_numbers.py`'s
    grouping algorithm being faithful-but-unverified end-to-end for the
    same underlying reason: the individual pieces are confirmed, their
    assembly isn't).
    """

    out: list = []
    for ch in word:
        out += LETTER_PHONEMES.get(ch, [])
    return [_Word_] + out
