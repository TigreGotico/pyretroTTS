"""SAM's phoneme inventory: names, per-phoneme flags, and length tables.

Derived from vidarh/SAM, which is an opcode-by-opcode translation of SoftVoice,
Inc.'s 6502 program; NOT covered by this project's MIT licence; see NOTICE.

SAM phonemes are two-character mnemonics indexed 0..80. The first and second
characters live in SIGN_INPUT_TABLE1/2; a '*' second character marks a
single-character (wildcard) mnemonic such as ``R*``. FLAGS carries the
per-phoneme bit field the parser and length rules test.
"""
from __future__ import annotations

from .tables import (
    FLAGS,
    FLAGS_OOB_TAIL,
    PHONEME_LENGTH_TABLE,
    PHONEME_STRESSED_LENGTH_TABLE,
    SIGN_INPUT_TABLE1,
    SIGN_INPUT_TABLE2,
    STRESS_INPUT_TABLE,
)

# The parser and length rules index flags[] with a phoneme id that is sometimes
# 255 (the END sentinel). In the C that reads past the 81-entry array; this
# 256-entry view reproduces the reference build's out-of-bounds bytes so those
# rules decide as the reference does.
_FLAGS256 = tuple(FLAGS) + tuple(FLAGS_OOB_TAIL)

# Phoneme flag bits (SamTabs.h loc_9F8C).
FLAG_PLOSIVE = 0x0001
FLAG_STOPCONS = 0x0002
FLAG_VOICED = 0x0004
FLAG_DIPTHONG = 0x0010
FLAG_DIP_YX = 0x0020
FLAG_CONSONANT = 0x0040
FLAG_VOWEL = 0x0080
FLAG_PUNCT = 0x0100
FLAG_ALVEOLAR = 0x0400
FLAG_NASAL = 0x0800
FLAG_LIQUIC = 0x1000
FLAG_FRICATIVE = 0x2000

#: end-of-list sentinel placed in the phoneme index buffer
END = 255
#: clause-break sentinel PrepareOutput splits render segments on
BREAK = 254

# Named phoneme ids referenced by the parser rules (sam.c enum + rule bodies).
pR = 23
pD = 57
pT = 69


def flags(phoneme: int) -> int:
    """The flag word for a phoneme id (0..255, reproducing the C's OOB reads)."""
    return _FLAGS256[phoneme]


def mnemonic(phoneme: int) -> str:
    """The two-character mnemonic for a phoneme id (second char '*' dropped)."""
    a = chr(SIGN_INPUT_TABLE1[phoneme])
    b = SIGN_INPUT_TABLE2[phoneme]
    return a if b == ord("*") else a + chr(b)


__all__ = [
    "FLAGS",
    "PHONEME_LENGTH_TABLE",
    "PHONEME_STRESSED_LENGTH_TABLE",
    "SIGN_INPUT_TABLE1",
    "SIGN_INPUT_TABLE2",
    "STRESS_INPUT_TABLE",
    "FLAG_PLOSIVE",
    "FLAG_STOPCONS",
    "FLAG_VOICED",
    "FLAG_DIPTHONG",
    "FLAG_DIP_YX",
    "FLAG_CONSONANT",
    "FLAG_VOWEL",
    "FLAG_PUNCT",
    "FLAG_ALVEOLAR",
    "FLAG_NASAL",
    "FLAG_LIQUIC",
    "FLAG_FRICATIVE",
    "END",
    "BREAK",
    "pR",
    "pD",
    "pT",
    "flags",
    "mnemonic",
]
