"""IPA as a universal input notation for all three engines.

An IPA string is parsed into a small phonetic intermediate representation, then
translated into whichever internal phonetic alphabet the target engine speaks
and rendered through that engine's existing synthesis seam. No text front end is
involved: IPA goes straight to native phones to PCM.

    from pyretrotts import MacInTalkEngine
    MacInTalkEngine().say_ipa("həˈloʊ wɜrld", path="hello.wav")

The three engines have English-centric phoneme inventories, so the mapping is
faithful for General American consonants and vowels and lossy for anything
else. See `IPA_LOSS` for the per-engine summary and `docs/ipa.md` for the table.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ._phonemes import (
    _SIL_,
    PHONEME_NAMES,
    PHONEME_NAMES_BY_INDEX,
    _Comma_,
    _Exclam_,
    _Period_,
    _Quest_,
)

__all__ = [
    "Stress",
    "IpaPhone",
    "IpaClause",
    "Fallback",
    "parse_ipa",
    "ipa_to_native",
    "native_to_ipa",
    "IPA_LOSS",
]


class Stress(Enum):
    """The three stress levels an IPA stress mark can carry."""

    NONE = 0
    PRIMARY = 1
    SECONDARY = 2


@dataclass(frozen=True)
class IpaPhone:
    """One IPA segment and the stress attached to it."""

    symbol: str
    stress: Stress = Stress.NONE


@dataclass(frozen=True)
class IpaClause:
    """One clause of IPA segments and the punctuation it ended on."""

    phones: tuple[IpaPhone, ...]
    #: the clause terminator character (`.`, `,`, `?`, `!`), or `""` at input end
    terminator: str = "."


@dataclass(frozen=True)
class Fallback:
    """An IPA segment with no faithful target, and the nearest one chosen."""

    symbol: str
    engine: str
    #: the native mnemonic/name the segment was approximated by
    target: str


# --- IPA tokenizing ---------------------------------------------------------

#: primary/secondary stress marks
_PRIMARY = "ˈ"     # ˈ
_SECONDARY = "ˌ"   # ˌ

#: length and nasalization diacritics absorbed into a segment's symbol
_LENGTH = "ː"
_NASAL = "̃"       # combining tilde
_DIACRITICS = frozenset({_LENGTH, _NASAL})

#: terminators a clause can end on
_TERMINATORS = frozenset({".", ",", "?", "!"})

#: two-codepoint IPA segments the tokenizer matches before single ones
_MULTIGRAPHS = frozenset({
    "eɪ", "aɪ", "ɔɪ", "aʊ", "oʊ",   # diphthongs
    "ju",                                                          # /ju/
    "tʃ", "dʒ",                                          # affricates
    "ɪɚ", "ɛɚ", "ɑɚ",               # r-coloured
    "ɔɚ", "ʊɚ",
})

#: base IPA symbols that are vowels (stress attaches to the next of these)
_VOWELS = frozenset({
    "i", "ɪ", "ɛ", "e", "æ", "ɑ", "ɒ", "a", "ʌ",
    "ɔ", "ʊ", "ə", "ɐ", "ɝ", "ɜ", "ɚ",
    "ɨ", "o", "u",
    "eɪ", "aɪ", "ɔɪ", "aʊ", "oʊ", "ju",
    "ɪɚ", "ɛɚ", "ɑɚ", "ɔɚ", "ʊɚ",
})


def _strip_diacritics(symbol: str) -> str:
    """`symbol` without length/nasalization diacritics."""
    return "".join(c for c in symbol if c not in _DIACRITICS)


def _is_vowel(symbol: str) -> bool:
    return _strip_diacritics(symbol) in _VOWELS


def parse_ipa(text: str) -> list[IpaClause]:
    """Parse an IPA string into clauses of stressed segments.

    Clauses split on `.,?!`. A leading `ˈ`/`ˌ` attaches to the next
    vowel segment. Segments are tokenized longest-match first, so diphthongs,
    affricates and r-coloured vowels are read as single units; a following `ː`
    or combining tilde is absorbed into the segment it modifies.
    """
    clauses: list[IpaClause] = []
    phones: list[IpaPhone] = []
    pending = Stress.NONE
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch in _TERMINATORS:
            clauses.append(IpaClause(tuple(phones), ch))
            phones = []
            pending = Stress.NONE
            i += 1
            continue
        if ch == _PRIMARY:
            pending = Stress.PRIMARY
            i += 1
            continue
        if ch == _SECONDARY:
            pending = Stress.SECONDARY
            i += 1
            continue
        if ch.isspace():
            i += 1
            continue
        pair = text[i:i + 2]
        if pair in _MULTIGRAPHS:
            symbol, i = pair, i + 2
        else:
            symbol, i = ch, i + 1
        while i < n and text[i] in _DIACRITICS:
            symbol += text[i]
            i += 1
        if pending is not Stress.NONE and _is_vowel(symbol):
            phones.append(IpaPhone(symbol, pending))
            pending = Stress.NONE
        else:
            phones.append(IpaPhone(symbol, Stress.NONE))
    if phones:
        clauses.append(IpaClause(tuple(phones), ""))
    return clauses


# --- per-engine mapping tables ----------------------------------------------
# Each forward table is keyed on the IPA base symbol (diacritics stripped) and
# gives the engine's own phoneme name; the id/code tables below resolve those
# names to the integers each engine's seam consumes. Reverse tables give the
# canonical IPA for each engine phoneme.

_IPA_TO_MACINTALK_NAME = {
    "i": "IY", "ɪ": "IH", "ɛ": "EH", "e": "EH", "æ": "AE",
    "ɑ": "AA", "ɒ": "AA", "a": "AA", "ʌ": "AH", "ɔ": "AO",
    "ʊ": "UH", "ə": "AX", "ɐ": "AX", "ɝ": "ER",
    "ɜ": "ER", "ɚ": "ER", "ɨ": "IX", "o": "OW", "u": "UW",
    "eɪ": "EY", "aɪ": "AY", "ɔɪ": "OY", "aʊ": "AW",
    "oʊ": "OW", "ju": "YU",
    "ɪɚ": "IR", "ɛɚ": "XR", "ɑɚ": "AR",
    "ɔɚ": "OR", "ʊɚ": "UR",
    "p": "p", "b": "b", "t": "t", "d": "d", "k": "k", "g": "g",
    "tʃ": "CH", "dʒ": "JH", "f": "f", "v": "v", "θ": "TH",
    "ð": "DH", "s": "s", "z": "z", "ʃ": "SH", "ʒ": "ZH",
    "m": "m", "n": "n", "ŋ": "NG", "l": "l", "ɫ": "LX",
    "r": "r", "ɹ": "r", "w": "w", "j": "y", "h": "h",
    "ɾ": "DX", "ʔ": "QX",
}

_MACINTALK_TO_IPA = {
    "IY": "i", "IH": "ɪ", "EH": "ɛ", "AE": "æ", "AA": "ɑ",
    "AH": "ʌ", "AO": "ɔ", "UH": "ʊ", "AX": "ə", "ER": "ɝ",
    "EY": "eɪ", "AY": "aɪ", "OY": "ɔɪ", "AW": "aʊ",
    "OW": "oʊ", "UW": "u", "YU": "ju", "IR": "ɪɚ",
    "XR": "ɛɚ", "AR": "ɑɚ", "OR": "ɔɚ",
    "UR": "ʊɚ", "IX": "ɨ", "RX": "ɹ", "LX": "ɫ",
    "EL": "l", "EN": "n", "w": "w", "y": "j", "r": "ɹ", "l": "l",
    "h": "h", "m": "m", "n": "n", "NG": "ŋ", "f": "f", "v": "v",
    "TH": "θ", "DH": "ð", "s": "s", "z": "z", "SH": "ʃ",
    "ZH": "ʒ", "p": "p", "b": "b", "t": "t", "d": "d", "k": "k",
    "g": "g", "CH": "tʃ", "JH": "dʒ", "TX": "t", "DX": "ɾ",
    "QX": "ʔ", "DD": "d",
}

_IPA_TO_DECTALK_NAME = {
    "i": "IY", "ɪ": "IH", "e": "EY", "ɛ": "EH", "æ": "AE",
    "ɑ": "AA", "ɒ": "AA", "a": "AA", "ʌ": "AH", "ɔ": "AO",
    "ʊ": "UH", "u": "UW", "ɝ": "RR", "ɜ": "RR", "ə": "AX",
    "ɐ": "AX", "ɨ": "IX", "o": "OW", "ɚ": "ER",
    "eɪ": "EY", "aɪ": "AY", "ɔɪ": "OY", "aʊ": "AW",
    "oʊ": "OW", "ju": "YU",
    "ɪɚ": "IR", "ɛɚ": "ER", "ɑɚ": "AR",
    "ɔɚ": "OR", "ʊɚ": "UR",
    "p": "P", "b": "B", "t": "T", "d": "D", "k": "K", "g": "G",
    "tʃ": "CH", "dʒ": "JH", "f": "F", "v": "V", "θ": "TH",
    "ð": "DH", "s": "S", "z": "Z", "ʃ": "SH", "ʒ": "ZH",
    "m": "M", "n": "N", "ŋ": "NX", "l": "LL", "ɫ": "LX",
    "r": "R", "ɹ": "R", "w": "W", "j": "Y", "h": "HX",
    "ɾ": "DX", "ʔ": "Q",
}

_DECTALK_TO_IPA = {
    "IY": "i", "IH": "ɪ", "EY": "eɪ", "EH": "ɛ", "AE": "æ",
    "AA": "ɑ", "AY": "aɪ", "AW": "aʊ", "AH": "ʌ",
    "AO": "ɔ", "OW": "oʊ", "OY": "ɔɪ", "UH": "ʊ",
    "UW": "u", "RR": "ɝ", "YU": "ju", "AX": "ə", "IX": "ɨ",
    "IR": "ɪɚ", "ER": "ɚ", "AR": "ɑɚ",
    "OR": "ɔɚ", "UR": "ʊɚ", "W": "w", "Y": "j", "R": "ɹ",
    "LL": "l", "HX": "h", "RX": "ɹ", "LX": "ɫ", "M": "m", "N": "n",
    "NX": "ŋ", "EL": "l", "DZ": "d", "EN": "n", "F": "f", "V": "v",
    "TH": "θ", "DH": "ð", "S": "s", "Z": "z", "SH": "ʃ",
    "ZH": "ʒ", "P": "p", "B": "b", "T": "t", "D": "d", "K": "k", "G": "g",
    "DX": "ɾ", "TX": "t", "Q": "ʔ", "CH": "tʃ", "JH": "dʒ",
    "DF": "d",
}

_IPA_TO_SAM_NAME = {
    "i": "IY", "ɪ": "IH", "ɛ": "EH", "e": "EH", "æ": "AE",
    "ɑ": "AA", "ɒ": "AA", "a": "AA", "ʌ": "AH", "ɔ": "AO",
    "ʊ": "UH", "ə": "AX", "ɐ": "AX", "ɨ": "IX",
    "ɝ": "ER", "ɜ": "ER", "ɚ": "ER", "o": "OW", "u": "UW",
    "eɪ": "EY", "aɪ": "AY", "ɔɪ": "OY", "aʊ": "AW",
    "oʊ": "OW", "ju": "UW",
    "ɪɚ": "ER", "ɛɚ": "ER", "ɑɚ": "AA",
    "ɔɚ": "AO", "ʊɚ": "UH",
    "p": "P", "b": "B", "t": "T", "d": "D", "k": "K", "g": "G",
    "tʃ": "CH", "dʒ": "J", "f": "F", "v": "V", "θ": "TH",
    "ð": "DH", "s": "S", "z": "Z", "ʃ": "SH", "ʒ": "ZH",
    "m": "M", "n": "N", "ŋ": "NX", "l": "L", "ɫ": "LX",
    "r": "R", "ɹ": "R", "w": "W", "j": "Y", "h": "/H",
    "ɾ": "DX", "ʔ": "Q",
}

_SAM_TO_IPA = {
    "IY": "i", "IH": "ɪ", "EH": "ɛ", "AE": "æ", "AA": "ɑ",
    "AH": "ʌ", "AO": "ɔ", "UH": "ʊ", "AX": "ə",
    "IX": "ɨ", "ER": "ɝ", "UX": "u", "OH": "ɔ", "RX": "ɹ",
    "LX": "ɫ", "WX": "w", "YX": "j", "WH": "w", "R": "ɹ", "L": "l",
    "W": "w", "Y": "j", "M": "m", "N": "n", "NX": "ŋ", "DX": "ɾ",
    "Q": "ʔ", "S": "s", "SH": "ʃ", "F": "f", "TH": "θ",
    "/H": "h", "/X": "h", "Z": "z", "ZH": "ʒ", "V": "v", "DH": "ð",
    "CH": "tʃ", "J": "dʒ", "EY": "eɪ", "AY": "aɪ",
    "OY": "ɔɪ", "AW": "aʊ", "OW": "oʊ", "UW": "u",
    "B": "b", "D": "d", "G": "g", "GX": "g", "P": "p", "T": "t", "K": "k",
    "KX": "k", "UL": "l", "UM": "m", "UN": "n",
}


# --- native id/name resolution ----------------------------------------------

def _macintalk_id(name: str) -> int:
    return PHONEME_NAMES[name]


def _dectalk_code(name: str) -> int:
    from .dectalk.lts import US_PHONEME_CODES

    return US_PHONEME_CODES[name]


def _sam_index() -> dict[str, int]:
    from .sam.phonemes import mnemonic
    from .sam.tables import SIGN_INPUT_TABLE1

    out: dict[str, int] = {}
    for index in range(len(SIGN_INPUT_TABLE1)):
        out.setdefault(mnemonic(index).strip(), index)
    return out


# --- IPA -> native ----------------------------------------------------------

#: default per-segment durations for the MacinTalk seam, in 5 ms frames
_MAC_CONS_FRAMES = 8
_MAC_VOWEL_FRAMES = 14
_MAC_STRESS_BONUS = 6
_MAC_LEAD_SIL = 2
_MAC_TAIL_SIL = 8

#: MacinTalk terminator ids by clause punctuation
_MAC_TERMINATORS = {
    ",": _Comma_, ".": _Period_, "?": _Quest_, "!": _Exclam_, "": _Period_,
}

_MAC_VOWEL_IDS = frozenset(
    PHONEME_NAMES[n] for n in
    ("IY", "IH", "EH", "AE", "AA", "AH", "AO", "UH", "AX", "ER", "EY", "AY",
     "OY", "AW", "OW", "UW", "YU", "IR", "XR", "AR", "OR", "UR", "IX")
)

# DECtalk prosody codes (l_com_ph.h).
_DEC_FONT = 7680
_DEC_S1 = 103
_DEC_S2 = 102
_DEC_WBOUND = 111
_DEC_TERMINATORS = {",": 115, ".": 116, "?": 117, "!": 118, "": 116}
_DEC_VOWEL_NAMES = frozenset({
    "IY", "IH", "EY", "EH", "AE", "AA", "AY", "AW", "AH", "AO", "OW", "OY",
    "UH", "UW", "RR", "YU", "AX", "IX", "IR", "ER", "AR", "OR", "UR",
})

#: SAM stress digits (1..8); a stressed vowel takes a higher one
_SAM_PRIMARY = "5"
_SAM_SECONDARY = "3"


def _lookup(table: dict[str, str], symbol: str) -> tuple[str, bool]:
    """Map an IPA `symbol` to an engine name, dropping diacritics as a fallback.

    Returns the name and whether a fallback (diacritic drop or unknown symbol)
    was taken. An unknown base symbol falls back to schwa's target.
    """
    if symbol in table:
        return table[symbol], False
    base = _strip_diacritics(symbol)
    if base in table:
        return table[base], True
    return table["ə"], True


def _mac_clause(clause: IpaClause) -> tuple[object, list[Fallback]]:
    from .api import PhonemePlan

    phonemes = [_SIL_]
    ctrls = [0]
    durs = [_MAC_LEAD_SIL]
    fallbacks: list[Fallback] = []
    for phone in clause.phones:
        name, fell = _lookup(_IPA_TO_MACINTALK_NAME, phone.symbol)
        pid = _macintalk_id(name)
        if fell:
            fallbacks.append(Fallback(phone.symbol, "macintalk", name))
        ctrl = 0
        dur = _MAC_VOWEL_FRAMES if pid in _MAC_VOWEL_IDS else _MAC_CONS_FRAMES
        if phone.stress is Stress.PRIMARY:
            from ._consts import kPrimaryStress
            ctrl = kPrimaryStress
            dur += _MAC_STRESS_BONUS
        elif phone.stress is Stress.SECONDARY:
            from ._consts import kStressField
            ctrl = kStressField & 0x0800
            dur += _MAC_STRESS_BONUS // 2
        phonemes.append(pid)
        ctrls.append(ctrl)
        durs.append(dur)
    phonemes.append(_SIL_)
    ctrls.append(0)
    durs.append(_MAC_TAIL_SIL)
    plan = PhonemePlan(
        phonemes=phonemes, ctrls=ctrls, durs=durs,
        end_punctuation=_MAC_TERMINATORS[clause.terminator],
    )
    return plan, fallbacks


def _dectalk_clause(clause: IpaClause) -> tuple[object, list[Fallback]]:
    from .dectalk.phclause import Clause

    symbols: list[int] = [_DEC_FONT, _DEC_WBOUND]
    fallbacks: list[Fallback] = []
    for phone in clause.phones:
        name, fell = _lookup(_IPA_TO_DECTALK_NAME, phone.symbol)
        code = _dectalk_code(name)
        if fell:
            fallbacks.append(Fallback(phone.symbol, "dectalk", name))
        if name in _DEC_VOWEL_NAMES:
            if phone.stress is Stress.PRIMARY:
                symbols.append(_DEC_S1)
            elif phone.stress is Stress.SECONDARY:
                symbols.append(_DEC_S2)
        symbols.append(_DEC_FONT + code)
    symbols.append(_DEC_TERMINATORS[clause.terminator])
    return Clause(tuple(symbols)), fallbacks


def _sam_clause(clause: IpaClause) -> tuple[str, list[Fallback]]:
    sam_index = _sam_index()
    parts: list[str] = []
    fallbacks: list[Fallback] = []
    for phone in clause.phones:
        name, fell = _lookup(_IPA_TO_SAM_NAME, phone.symbol)
        if fell:
            fallbacks.append(Fallback(phone.symbol, "sam", name))
        token = name
        if name in sam_index and (sam_index[name] and _sam_is_vowel(sam_index[name])):
            if phone.stress is Stress.PRIMARY:
                token += _SAM_PRIMARY
            elif phone.stress is Stress.SECONDARY:
                token += _SAM_SECONDARY
        parts.append(token)
    return "".join(parts), fallbacks


def _sam_is_vowel(index: int) -> bool:
    from .sam.phonemes import FLAG_VOWEL, flags

    return bool(flags(index) & FLAG_VOWEL)


def ipa_to_native(engine: str, clauses: list[IpaClause]) -> tuple[object, list[Fallback]]:
    """Translate parsed IPA into an engine's synthesis input and the fallbacks.

    Returns `(payload, fallbacks)` where `payload` is what the engine's seam
    consumes: a list of `PhonemePlan` (MacinTalk), a list of `Clause` (DECtalk),
    or a mnemonic string (SAM). `fallbacks` lists every segment that had no
    faithful target and the nearest one chosen for it.
    """
    engine = engine.lower()
    fallbacks: list[Fallback] = []
    if engine == "macintalk":
        plans = []
        for clause in clauses:
            plan, fell = _mac_clause(clause)
            plans.append(plan)
            fallbacks.extend(fell)
        return plans, fallbacks
    if engine == "dectalk":
        out = []
        for clause in clauses:
            clause_obj, fell = _dectalk_clause(clause)
            out.append(clause_obj)
            fallbacks.extend(fell)
        return out, fallbacks
    if engine == "sam":
        parts = []
        for clause in clauses:
            source, fell = _sam_clause(clause)
            parts.append(source)
            term = clause.terminator if clause.terminator in (".", ",", "?") else ""
            if term:
                parts.append(term)
            fallbacks.extend(fell)
        return "".join(parts), fallbacks
    raise ValueError(f"unknown engine {engine!r}")


# --- native -> IPA ----------------------------------------------------------

def native_to_ipa(engine: str, ids: list[int]) -> list[str]:
    """The IPA for a sequence of an engine's native phoneme ids/codes.

    Unmapped ids (silence, prosodic marks) are dropped.
    """
    engine = engine.lower()
    if engine == "macintalk":
        names = (PHONEME_NAMES_BY_INDEX.get(i) for i in ids)
        return [_MACINTALK_TO_IPA[n] for n in names if n in _MACINTALK_TO_IPA]
    if engine == "dectalk":
        from .dectalk.lts import US_PHONEME_NAMES

        names = (US_PHONEME_NAMES.get(c & 0x00FF) for c in ids)
        return [_DECTALK_TO_IPA[n] for n in names if n in _DECTALK_TO_IPA]
    if engine == "sam":
        from .sam.phonemes import mnemonic

        names = (mnemonic(i).strip() for i in ids)
        return [_SAM_TO_IPA[n] for n in names if n in _SAM_TO_IPA]
    raise ValueError(f"unknown engine {engine!r}")


IPA_LOSS: dict[str, str] = {
    "macintalk": (
        "Consonants map nearly one to one. General American vowels are faithful; "
        "ɑ and ɒ collapse to one vowel, and vowel length and "
        "nasalization have no target and are dropped."
    ),
    "dectalk": (
        "Consonants map nearly one to one. General American vowels are faithful; "
        "ɛɚ has no r-coloured target and reduces to ER, and vowel "
        "length and nasalization are dropped."
    ),
    "sam": (
        "The coarsest inventory: no /ju/ (reduces to UW) and no distinct "
        "r-coloured vowels (they collapse to ER, AA, AO or UH). Vowel length and "
        "nasalization are dropped."
    ),
}
