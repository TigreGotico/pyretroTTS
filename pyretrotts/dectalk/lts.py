"""DECtalk US-English phoneme-symbol layer (the text front end's output alphabet).

Derived from the Fonix/Force DECtalk C source (`dectalk/dectalk`,
`src/dapi/src/include/l_us_ph.h`, `l_com_ph.h`, `include/usa_phon.tab`,
`ph/phlog.c`). FONIX Corporation declares that source proprietary and
confidential. This file is NOT covered by this project's MIT licence. See
NOTICE.

The full US letter-to-sound path (`lts/`: the `dtalk_us.dic` trie lookup and the
`l_us_*` rule engine) is not ported. What is ported here is the phoneme+stress
*alphabet* that layer emits: the phoneme codes (`l_us_ph.h`), the ARPABET render
table and single-character input alphabet (`usa_phon.tab`), and the
`LOG_PHONEMES` text renderer (`phlog.c`) that the C oracle prints for a
phoneme+stress stream. This pins the boundary the allophone stage consumes and
the exact text form captured from the oracle by `tools/dump_dectalk_lts.py`.
"""
from __future__ import annotations

from dataclasses import dataclass

# --- Phoneme codes: l_us_ph.h (offsets into the PFUSA font) -----------------
# US_TOT_ALLOPHONES == 71 in the compiled build; codes 0..56 are the phonemes.
SIL = 0
US_PHONEME_NAMES: dict[int, str] = {
    0: "SIL", 1: "IY", 2: "IH", 3: "EY", 4: "EH", 5: "AE", 6: "AA", 7: "AY",
    8: "AW", 9: "AH", 10: "AO", 11: "OW", 12: "OY", 13: "UH", 14: "UW",
    15: "RR", 16: "YU", 17: "AX", 18: "IX", 19: "IR", 20: "ER", 21: "AR",
    22: "OR", 23: "UR", 24: "W", 25: "Y", 26: "R", 27: "LL", 28: "HX",
    29: "RX", 30: "LX", 31: "M", 32: "N", 33: "NX", 34: "EL", 35: "DZ",
    36: "EN", 37: "F", 38: "V", 39: "TH", 40: "DH", 41: "S", 42: "Z",
    43: "SH", 44: "ZH", 45: "P", 46: "B", 47: "T", 48: "D", 49: "K",
    50: "G", 51: "DX", 52: "TX", 53: "Q", 54: "CH", 55: "JH", 56: "DF",
}
US_PHONEME_CODES: dict[str, int] = {v: k for k, v in US_PHONEME_NAMES.items()}

# --- Control / prosodic symbols: l_com_ph.h ---------------------------------
BLOCK_RULES = 100
S3 = 101      # tertiary stress
S2 = 102      # secondary stress
S1 = 103      # primary stress
SEMPH = 104   # emphatic stress
HAT_RISE = 105
HAT_FALL = 106
HAT_RF = 107
SBOUND = 108  # syllable boundary
MBOUND = 109  # morpheme boundary
HYPHEN = 110
WBOUND = 111  # word boundary
PPSTART = 112
VPSTART = 113
RELSTART = 114
COMMA = 115
PERIOD = 116
QUEST = 117
EXCLAIM = 118
NEW_PARAGRAPH = 119

PVALUE = 0x00FF   # cmd.h: the actual code value
PSFONT = 8        # cmd.h: font shift
PFUSA = 0x1E      # l_us_ph.h: American-English phoneme font

# --- ARPABET render table: usa_arpa[] (2 chars per code) --------------------
# phlog.c prints arpa[code*2], arpa[code*2+1]; a trailing space when the second
# char is ' '. Indexed by (phone & PVALUE).
_ARPA_PAIRS: dict[int, tuple[str, str]] = {
    0: ("_", " "), 1: ("i", "y"), 2: ("i", "h"), 3: ("e", "y"), 4: ("e", "h"),
    5: ("a", "e"), 6: ("a", "a"), 7: ("a", "y"), 8: ("a", "w"), 9: ("a", "h"),
    10: ("a", "o"), 11: ("o", "w"), 12: ("o", "y"), 13: ("u", "h"),
    14: ("u", "w"), 15: ("r", "r"), 16: ("y", "u"), 17: ("a", "x"),
    18: ("i", "x"), 19: ("i", "r"), 20: ("e", "r"), 21: ("a", "r"),
    22: ("o", "r"), 23: ("u", "r"), 24: ("w", " "), 25: ("y", "x"),
    26: ("r", " "), 27: ("l", "l"), 28: ("h", "x"), 29: ("r", "x"),
    30: ("l", "x"), 31: ("m", " "), 32: ("n", " "), 33: ("n", "x"),
    34: ("e", "l"), 35: ("d", "z"), 36: ("e", "n"), 37: ("f", " "),
    38: ("v", " "), 39: ("t", "h"), 40: ("d", "h"), 41: ("s", " "),
    42: ("z", " "), 43: ("s", "h"), 44: ("z", "h"), 45: ("p", " "),
    46: ("b", " "), 47: ("t", " "), 48: ("d", " "), 49: ("k", " "),
    50: ("g", " "), 51: ("d", "x"), 52: ("t", "x"), 53: ("q", " "),
    54: ("c", "h"), 55: ("j", "h"), 56: ("d", "f"),
    # control symbols share the render table (indices 100..104)
    BLOCK_RULES: ("~", " "), S3: ("=", " "), S2: ("`", " "),
    S1: ("'", " "), SEMPH: ('"', " "),
}

# --- Single-character input alphabet: usa_ascky[] ---------------------------
# The one-character phonemic notation accepted in `[:phoneme on]` mode.
_ASCKY: dict[int, str] = {
    0: "_", 1: "i", 2: "I", 3: "e", 4: "E", 5: "@", 6: "a", 7: "A",
    8: "W", 9: "^", 10: "c", 11: "o", 12: "O", 13: "U", 14: "u", 15: "R",
    16: "Y", 17: "x", 18: "|", 19: "B", 20: "K", 21: "P", 22: "M", 23: "j",
    24: "w", 25: "y", 26: "r", 27: "l", 28: "h", 29: "R", 30: "l", 31: "m",
    32: "n", 33: "G", 34: "L", 35: "D", 36: "N", 37: "f", 38: "v", 39: "T",
    40: "D", 41: "s", 42: "z", 43: "S", 44: "Z", 45: "p", 46: "b", 47: "t",
    48: "d", 49: "k", 50: "g", 51: "&", 52: "Q", 53: "q", 54: "C", 55: "J",
    56: "F",
}


@dataclass(frozen=True)
class Symbol:
    """One entry in the phoneme+stress stream: a phoneme or a prosodic mark."""

    code: int
    font: int = PFUSA


def arpa_name(code: int) -> str:
    """ARPABET spelling of a phoneme code, per `usa_arpa`; '' if undefined."""
    pair = _ARPA_PAIRS.get(code & PVALUE)
    if pair is None:
        return ""
    a, b = pair
    return a if b == " " else a + b


def render_symbol(sym: Symbol) -> str:
    """Reproduce `phlog.c`'s `LOG_PHONEMES` text for one stream symbol.

    A phoneme in the US font is preceded by the `us_` language tag
    (`PrintLangBit`); a single-character ARPABET name is followed by one space;
    prosodic control symbols carry no language tag.
    """
    pair = _ARPA_PAIRS.get(sym.code & PVALUE)
    prefix = "us_" if sym.font == PFUSA else ""
    if pair is None:
        return ""
    a, b = pair
    if b == " ":
        return f"{prefix}{a} "
    return f"{prefix}{a}{b}"


def render_stream(symbols: list[Symbol]) -> str:
    """Render a phoneme+stress stream to the oracle `LOG_PHONEMES` text."""
    return "".join(render_symbol(s) for s in symbols)


# Reverse ARPABET maps for decoding oracle `us_<name>` phoneme tokens.
_ARPA_TWO: dict[str, int] = {
    a + b: c for c, (a, b) in _ARPA_PAIRS.items() if b != " " and c < 57
}
_ARPA_ONE: dict[str, int] = {
    a: c for c, (a, b) in _ARPA_PAIRS.items() if b == " " and c < 57
}


def phonemes_in_log(text: str) -> list[int]:
    """Extract the US phoneme codes from oracle `LOG_PHONEMES` text.

    Each phoneme is emitted as `us_<name>` (`phlog.c` `PrintLangBit` + the
    ARPABET render), a two-character name written flush or a one-character name
    followed by a space. Raises `ValueError` on an `us_` token this alphabet
    cannot decode, which is the assertion the port is gated on.
    """
    return [c for c, _s, _e in phoneme_spans(text)]


def phoneme_spans(text: str) -> list[tuple[int, int, int]]:
    """Locate each `us_<name>` phoneme token: `(code, start, end)` spans.

    `text[start:end]` is the raw token the oracle wrote. Raises `ValueError` on
    an `us_` token this alphabet cannot decode.
    """
    spans: list[tuple[int, int, int]] = []
    i = 0
    tag = "us_"
    while True:
        j = text.find(tag, i)
        if j < 0:
            return spans
        k = j + len(tag)
        two = text[k:k + 2]
        one = text[k:k + 1]
        if two in _ARPA_TWO:
            spans.append((_ARPA_TWO[two], j, k + 2))
            i = k + 2
        elif one in _ARPA_ONE and text[k + 1:k + 2] == " ":
            spans.append((_ARPA_ONE[one], j, k + 2))
            i = k + 2
        else:
            raise ValueError(f"undecodable phoneme token at {j}: {text[j:j+6]!r}")
