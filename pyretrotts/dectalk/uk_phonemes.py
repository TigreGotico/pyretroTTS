"""DECtalk UK-English phoneme-symbol layer (the UK front end's output alphabet).

The compiled UK library (`libtts_uk.so`, `-l uk`) emits phonemes in the `PFUK`
font (`0x1D`), one code page below US `PFUSA` (`0x1E`). The raw phoneme index
space is nearly identical to US: `include/l_all_ph.h` gives `UK_IY 1 .. UK_DF 56`
matching `US_IY 1 .. US_DF 56` position for position, with two inventory deltas:

  * index 29 is `UK_OH` (the RP LOT/CLOTH open-o vowel) where US has `US_RX`
    (the retroflex allophone), and
  * index 51 is `UK_YR`/`UK_DX` (a documented C aliasing, `l_all_ph.h:182-184`,
    "two 51s") where US has `US_DX`; US also defines index 57..60
    (`US_TZ/US_CZ/US_LY/US_RE`) which UK does not.

`UK_TOT_ALLOPHONES == 57` (`l_all_ph.h:350`), same as US. The render table
`uk_arpa[]` (`include/uk_phon.tab`) differs from `usa_arpa[]` at index 25
(`y ` vs `yx`), 27 (`l ` vs `ll`), 29 (`oh` vs `rx`), and 51 (`yr` vs `dx`).

UK non-rhoticity is not an inventory change: the centring vowels `IR/ER/AR/OR/UR`
(indices 19..23) and `RR` (15, the NURSE vowel) share their US codes, and the
post-vocalic `R` (26) the dictionary/LTS still emit is dropped by the shared
`ph/` reduction stage, not here. The UK-specific pronunciations live in the UK
dictionary (`dtalk_uk.dic`), the UK LTS rules (`lts/l_uk_*`), and the UK `ph/`
target ROM / gettar / timing / intonation (`ph/p_uk_*`), which are not ported
here.

Derived from the Fonix/Force DECtalk C source (`dectalk/dectalk`,
`src/dapi/src/include/l_all_ph.h`, `include/l_uk_ph.h`, `include/uk_phon.tab`,
`ph/phlog.c`). FONIX Corporation declares that source proprietary and
confidential. This file is NOT covered by this project's MIT licence. See
NOTICE. The tables are transcribed verbatim from that source, so they carry the
FONIX notice.
"""
from __future__ import annotations

# --- UK phoneme font: l_all_ph.h ------------------------------------------
PFUK = 0x1D  # British-English phoneme font (US PFUSA is 0x1E)

# --- UK phoneme inventory: l_all_ph.h UK_IY(1) .. UK_DF(56) ----------------
# Index 0 is silence; 1..56 are the phonemes. Position-for-position identical to
# US except index 29 (OH vs RX). US index 57..60 have no UK counterpart.
UK_TOT_ALLOPHONES = 57
UK_PHONEME_NAMES: dict[int, str] = {
    0: "SIL", 1: "IY", 2: "IH", 3: "EY", 4: "EH", 5: "AE", 6: "AA", 7: "AY",
    8: "AW", 9: "AH", 10: "AO", 11: "OW", 12: "OY", 13: "UH", 14: "UW",
    15: "RR", 16: "YU", 17: "AX", 18: "IX", 19: "IR", 20: "ER", 21: "AR",
    22: "OR", 23: "UR", 24: "W", 25: "Y", 26: "R", 27: "LL", 28: "HX",
    29: "OH", 30: "LX", 31: "M", 32: "N", 33: "NX", 34: "EL", 35: "DZ",
    36: "EN", 37: "F", 38: "V", 39: "TH", 40: "DH", 41: "S", 42: "Z",
    43: "SH", 44: "ZH", 45: "P", 46: "B", 47: "T", 48: "D", 49: "K",
    50: "G", 51: "YR", 52: "TX", 53: "Q", 54: "CH", 55: "JH", 56: "DF",
}
UK_PHONEME_CODES: dict[str, int] = {v: k for k, v in UK_PHONEME_NAMES.items()}

# --- UK ARPABET render table: uk_arpa[] (include/uk_phon.tab) ---------------
# phlog.c prints arpa[index*2], arpa[index*2+1]; a trailing space when the
# second char is ' '. Transcribed verbatim from uk_phon.tab (indices 0..56).
UK_ARPA_PAIRS: dict[int, tuple[str, str]] = {
    0: ("_", " "), 1: ("i", "y"), 2: ("i", "h"), 3: ("e", "y"), 4: ("e", "h"),
    5: ("a", "e"), 6: ("a", "a"), 7: ("a", "y"), 8: ("a", "w"), 9: ("a", "h"),
    10: ("a", "o"), 11: ("o", "w"), 12: ("o", "y"), 13: ("u", "h"),
    14: ("u", "w"), 15: ("r", "r"), 16: ("y", "u"), 17: ("a", "x"),
    18: ("i", "x"), 19: ("i", "r"), 20: ("e", "r"), 21: ("a", "r"),
    22: ("o", "r"), 23: ("u", "r"), 24: ("w", " "), 25: ("y", " "),
    26: ("r", " "), 27: ("l", " "), 28: ("h", "x"), 29: ("o", "h"),
    30: ("l", "x"), 31: ("m", " "), 32: ("n", " "), 33: ("n", "x"),
    34: ("e", "l"), 35: ("d", "z"), 36: ("e", "n"), 37: ("f", " "),
    38: ("v", " "), 39: ("t", "h"), 40: ("d", "h"), 41: ("s", " "),
    42: ("z", " "), 43: ("s", "h"), 44: ("z", "h"), 45: ("p", " "),
    46: ("b", " "), 47: ("t", " "), 48: ("d", " "), 49: ("k", " "),
    50: ("g", " "), 51: ("y", "r"), 52: ("t", "x"), 53: ("q", " "),
    54: ("c", "h"), 55: ("j", "h"), 56: ("d", "f"),
}

# --- UK single-character input alphabet: uk_ascky[] (uk_phon.tab) -----------
UK_ASCKY: dict[int, str] = {
    0: "_", 1: "i", 2: "I", 3: "e", 4: "E", 5: "@", 6: "a", 7: "A",
    8: "W", 9: "^", 10: "c", 11: "o", 12: "O", 13: "U", 14: "u", 15: "R",
    16: "Y", 17: "x", 18: "|", 19: "F", 20: "K", 21: "P", 22: "M", 23: "j",
    24: "w", 25: "y", 26: "r", 27: "l", 28: "h", 29: "B", 30: "X", 31: "m",
    32: "n", 33: "G", 34: "L", 35: "H", 36: "N", 37: "f", 38: "v", 39: "T",
    40: "D", 41: "s", 42: "z", 43: "S", 44: "Z", 45: "p", 46: "b", 47: "t",
    48: "d", 49: "k", 50: "g", 51: "V", 52: "Q", 53: "q", 54: "C", 55: "J",
}
