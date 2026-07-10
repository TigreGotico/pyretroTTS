"""Port of `EmbeddedCmd.c`'s `mode` command's `PHON` (`modePhonemes`)
raw-phoneme input mode: `GetNextPhonemeOpcode`/`CollectPhonemeToken`
(`FrontEnd.c:247-345`).

Unlike the `Symbols`-dictionary lookups blocking `char`'s letter-name
spelling, this is a direct, bit-exact transcription of a literal
compile-time C source table -- `Data.c:3307`'s `MAGIC_CHAR_MAP[]` and
`Data.c:3394`'s `MAGIC_OPCODE_MAP[]` -- not a runtime dictionary lookup
subject to the `Symbols` corruption documented elsewhere in this port,
so it carries no verification caveat.

`MAGIC_CHAR_MAP` pairs a 1-or-2-character mnemonic (uppercase pairs for
vowels, e.g. `"AA"`/`"IY"`; lowercase singles for consonants, e.g.
`"p"`/`"t"`; punctuation/control characters for everything else, e.g.
`"1"`/`"2"` for primary/secondary stress, `"_"`/`"~"` for a word
boundary, `","`/`"."`/`"!"`/`"?"` for the matching punctuation phonemes)
with a phoneme opcode. `GetNextPhonemeOpcode` greedily tries a 2-char
match first, falling back to 1-char.
"""
from __future__ import annotations

from ._phonemes import (
    _AA_,
    _AE_,
    _AH_,
    _AO_,
    _AR_,
    _AW_,
    _AX_,
    _AY_,
    _CH_,
    _DD_,
    _DH_,
    _DX_,
    _EH_,
    _EL_,
    _EN_,
    _ER_,
    _EY_,
    _IH_,
    _IR_,
    _IX_,
    _IY_,
    _JH_,
    _LX_,
    _NG_,
    _OR_,
    _OW_,
    _OY_,
    _QX_,
    _RX_,
    _SH_,
    _SIL_,
    _TH_,
    _TX_,
    _UH_,
    _UR_,
    _UW_,
    _XR_,
    _YU_,
    _ZH_,
    _b_,
    _Comma_,
    _d_,
    _dDec_,
    _dInc_,
    _EmphWord_,
    _Exclam_,
    _f_,
    _g_,
    _h_,
    _k_,
    _l_,
    _m_,
    _n_,
    _p_,
    _Period_,
    _pFall_,
    _Prep_,
    _pRise_,
    _Quest_,
    _r_,
    _s_,
    _Stress1_,
    _Stress2_,
    _Syll_,
    _t_,
    _v_,
    _Verb_,
    _w_,
    _Word_,
    _y_,
    _z_,
)

# (char1, char2_or_None) -> opcode, transcribed in table order directly
# from Data.c:3307-3389/3394-3435. A single-character entry is keyed
# with a None second slot (matching the table's `\0` second byte).
MAGIC_MAP = {
    ('1', None): _Stress1_, ('2', None): _Stress2_, ('_', None): _Word_,
    (';', None): _Verb_, ('$', None): _Prep_,
    ('A', 'A'): _AA_, ('A', 'E'): _AE_, ('U', 'X'): _AH_, ('A', 'O'): _AO_,
    ('A', 'X'): _AX_, ('E', 'H'): _EH_, ('I', 'H'): _IH_, ('I', 'Y'): _IY_,
    ('E', 'R'): _ER_, ('U', 'H'): _UH_, ('U', 'W'): _UW_, ('A', 'W'): _AW_,
    ('A', 'Y'): _AY_, ('E', 'Y'): _EY_, ('O', 'W'): _OW_, ('O', 'Y'): _OY_,
    ('p', None): _p_, ('t', None): _t_, ('k', None): _k_, ('b', None): _b_,
    ('d', None): _d_, ('g', None): _g_, ('s', None): _s_, ('z', None): _z_,
    ('S', None): _SH_, ('Z', None): _ZH_, ('T', None): _TH_, ('D', None): _DH_,
    ('C', None): _CH_, ('J', None): _JH_, ('f', None): _f_, ('v', None): _v_,
    ('m', None): _m_, ('n', None): _n_, ('N', None): _NG_, ('r', None): _r_,
    ('l', None): _l_, ('w', None): _w_, ('y', None): _y_, ('h', None): _h_,
    ('D', 'X'): _DX_, ('I', 'X'): _IX_, ('E', 'L'): _EL_, ('E', 'N'): _EN_,
    ('Y', 'U'): _YU_, ('I', 'R'): _IR_, ('X', 'R'): _XR_, ('A', 'R'): _AR_,
    ('O', 'R'): _OR_, ('U', 'R'): _UR_, ('R', 'X'): _RX_, ('L', 'X'): _LX_,
    ('T', 'X'): _TX_, ('Q', 'X'): _QX_, ('D', 'D'): _DD_,
    (',', None): _Comma_, ('.', None): _Period_, ('!', None): _Exclam_,
    ('?', None): _Quest_, ('>', None): _dInc_, ('<', None): _dDec_,
    ('/', None): _pRise_, ('\\', None): _pFall_, ('+', None): _EmphWord_,
    ('~', None): _Word_, ('=', None): _Syll_, ('%', None): _SIL_,
    ('@', None): _SIL_, (':', None): _Comma_, ('(', None): _Comma_,
    (')', None): _Comma_, ('"', None): _Comma_, ("'", None): _Comma_,
    ('-', None): _Comma_, ('&', None): _SIL_,
}


def parse_raw_phonemes(text: str) -> list:
    """Port of `GetNextPhonemeOpcode`'s greedy 2-char-then-1-char scan
    (`FrontEnd.c:247-287`): returns the flat opcode list for `text`,
    skipping any character (or character pair) that matches nothing in
    `MAGIC_MAP` (matches `GetNextPhonemeOpcode`'s own behavior of simply
    advancing past an unrecognized character without producing an
    opcode for it).
    """
    opcodes = []
    i, n = 0, len(text)
    while i < n:
        pair = (text[i], text[i + 1] if i + 1 < n else None)
        if pair in MAGIC_MAP:
            opcodes.append(MAGIC_MAP[pair])
            i += 2
            continue
        single = (text[i], None)
        if single in MAGIC_MAP:
            opcodes.append(MAGIC_MAP[single])
        i += 1
    return opcodes


def split_into_word_groups(opcodes: list) -> list:
    """Port of `CollectPhonemeToken`'s word-splitting (`FrontEnd.c:311
    -316`): a `_Word_`/`_EmphWord_` opcode starts a new token EXCEPT
    when it's the very first opcode collected (`tokLen` still 0),
    matching `(opcode == _Word_ || opcode == _EmphWord_) && tokLen`.
    Returns a list of non-empty opcode groups, each a raw phoneme
    "word" ready to become one `FEWordToken.phon_str`.
    """
    groups: list = []
    current: list = []
    for op in opcodes:
        if op in (_Word_, _EmphWord_) and current:
            groups.append(current)
            current = [op]
        else:
            current.append(op)
    if current:
        groups.append(current)
    return groups
