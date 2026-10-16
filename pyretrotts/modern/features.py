"""IPA to articulatory-feature decomposition for the generative front ends.

The feature model is adapted from Distinctive Feature Theory as implemented in
``phonematcher`` (TigreGotico, MIT licence; itself derived from lingz/pyphone).
``phonematcher`` maps each IPA phone to a 21-element boolean distinctive-feature
vector (syllabic, consonantal, voice, nasal, place, height/backness/round ...)
and scores segment similarity with a weighted feature distance. This module
borrows that *idea* -- decompose a symbol into articulatory features, then reason
over feature distance rather than symbol identity -- but keeps its own compact,
synthesis-oriented representation: instead of booleans it stores the quantities a
Klatt or additive synthesizer actually needs (formant targets, place index,
manner, voicing, secondary articulation).

Vowel formant targets are male-voice reference values drawn from the classic
acoustic-phonetics literature (Peterson & Barney 1952 for the English monophthong
cardinals; Klatt 1980 "Software for a cascade/parallel formant synthesizer" for
the synthesis-tuned values; Catford 1988 and Vallee 1994 for the non-English
cardinal and front-rounded vowels). Consonant place loci and frication centres
follow the locus-theory values in Stevens 1998 "Acoustic Phonetics".

No ``phonematcher`` code is imported or copied verbatim; the decomposition and
distance below are reimplemented for this package.
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass, replace

__all__ = [
    "FeatureBundle", "decompose", "nearest_target", "PLACES",
    "DECOMPOSABLE_SYMBOLS", "DIPHTHONGS", "expand",
]

# Manner classes recognised by the parameter generators.
MANNER_VOWEL = "vowel"
MANNER_STOP = "stop"
MANNER_FRICATIVE = "fricative"
MANNER_AFFRICATE = "affricate"
MANNER_NASAL = "nasal"
MANNER_APPROXIMANT = "approximant"
MANNER_LATERAL = "lateral"
MANNER_TRILL = "trill"
MANNER_TAP = "tap"

#: place name -> (F2 locus Hz, frication/burst spectral centre Hz, ordinal).
#: The ordinal (front-to-back rank) drives the articulatory distance metric.
#: F2 loci follow locus theory (Stevens 1998, *Acoustic Phonetics*; Delattre,
#: Liberman & Cooper 1955 JASA 27(4)) and are pinned to the shipped DECtalk US
#: consonant targets on this exact synth (US_MALTAR: /n/ 1540, velar /ŋ/ 1600,
#: /m/ 1120, /f/ 1100, /ð/ 1300). The alveolar CV-transition locus is held at
#: 1700 (measured best on this front end; DECtalk's /t d n/ closure value 1540-
#: 1600 is the locus a full transition model bends *toward*, not the target
#: itself). Frication centres are the noise spectral peaks in Stevens 1998
#: (sibilant /s/ ~5-8 kHz, /ʃ/ ~2.5-3.5 kHz).
PLACES: dict[str, tuple[int, int, int]] = {
    "bilabial": (1000, 1000, 0),
    "labiodental": (1100, 4500, 1),
    "dental": (1400, 4200, 2),
    "alveolar": (1700, 5200, 3),
    "postalveolar": (1800, 3000, 4),
    "retroflex": (1600, 2500, 5),
    "palatal": (2100, 3200, 6),
    "velar": (1600, 1900, 7),
    "uvular": (1050, 1500, 8),
    "pharyngeal": (1000, 1200, 9),
    "glottal": (1500, 1000, 10),
}


@dataclass(frozen=True)
class FeatureBundle:
    """Articulatory features generated from one IPA segment.

    Formant fields carry Hz targets. For vowels they are the steady-state
    formants; for consonants ``f1``/``f2``/``f3`` are the transition locus the
    neighbouring vowel bends toward, and ``fric_center`` the noise centre.
    """

    symbol: str
    is_vowel: bool
    voiced: bool = True
    nasal: bool = False
    long: bool = False
    rhotic: bool = False
    rounded: bool = False
    lateral: bool = False
    aspirated: bool = False
    f1: int = 500
    f2: int = 1500
    f3: int = 2500
    fric_center: int = 2500
    manner: str = MANNER_VOWEL
    place: str = ""


# --- vowel formant table (male voice, Hz): F1, F2, F3 -----------------------
# F1 tracks openness (higher = more open), F2 tracks backness (higher = more
# front) and rounding lowers F2/F3.
#
# The English monophthongs are calibrated to the *shipped DECtalk* US male target
# ROM (``pyretrotts.dectalk.targets.US_MALTAR`` / ``US_MALDIP``, the steady value
# of each vowel's own trajectory on this exact synthesizer) and cross-checked
# against measured American-English formants (Hillenbrand, Getty, Clark & Wheeler
# 1995 JASA 97(5) Table V, adult males; Peterson & Barney 1952 JASA 24(2)). The
# key correction over a naive Peterson-Barney transcription is F3: on this synth
# DECtalk keeps English F3 in a 2300-2800 Hz band (e.g. /i/ F3 2500-2779, not
# 3010), so an over-high F3 pushed vowels out of the region the DECtalk cascade
# is tuned for. Non-English cardinals and front-rounded vowels use Klatt 1980
# (JASA 67(3), synthesis-tuned), Catford 1988 and Vallee 1994, with F3 held to
# the same synth band for consistency.
_VOWELS: dict[str, tuple[int, int, int]] = {
    "i": (300, 2200, 2600), "y": (300, 1800, 2300),
    "ɪ": (480, 1700, 2500), "ʏ": (450, 1600, 2200),
    "e": (450, 1950, 2500), "ø": (430, 1550, 2400),
    "ɛ": (620, 1650, 2500), "œ": (560, 1450, 2400),
    "æ": (680, 1650, 2500), "a": (750, 1500, 2500),
    "ɶ": (750, 1350, 2400),
    "ɨ": (320, 1650, 2400), "ʉ": (320, 1400, 2200),
    "ɘ": (450, 1500, 2500), "ɵ": (470, 1400, 2300),
    "ə": (550, 1300, 2550), "ɜ": (560, 1400, 2500),
    "ɞ": (560, 1450, 2400), "ɐ": (650, 1400, 2500),
    "ʌ": (620, 1200, 2550), "ɑ": (780, 1150, 2600),
    "ɒ": (700, 1000, 2500), "ɔ": (650, 1000, 2500),
    "o": (500, 900, 2450), "ɤ": (460, 1300, 2450),
    "ʊ": (480, 1100, 2450), "u": (350, 900, 2300),
    "ɯ": (320, 1350, 2300),
}

#: vowels the table stores as rounded (drives lip-rounding secondary articulation)
_ROUND_VOWELS = frozenset("yʏøœɶʉɵɞoɔuʊ")

# --- consonant table: symbol -> (place, manner, voiced, lateral) ------------
_CONSONANTS: dict[str, tuple[str, str, bool, bool]] = {
    # plosives
    "p": ("bilabial", MANNER_STOP, False, False),
    "b": ("bilabial", MANNER_STOP, True, False),
    "t": ("alveolar", MANNER_STOP, False, False),
    "d": ("alveolar", MANNER_STOP, True, False),
    "ʈ": ("retroflex", MANNER_STOP, False, False),
    "ɖ": ("retroflex", MANNER_STOP, True, False),
    "c": ("palatal", MANNER_STOP, False, False),
    "ɟ": ("palatal", MANNER_STOP, True, False),
    "k": ("velar", MANNER_STOP, False, False),
    "g": ("velar", MANNER_STOP, True, False),
    "ɡ": ("velar", MANNER_STOP, True, False),
    "q": ("uvular", MANNER_STOP, False, False),
    "ɢ": ("uvular", MANNER_STOP, True, False),
    "ʔ": ("glottal", MANNER_STOP, False, False),
    # fricatives
    "ɸ": ("bilabial", MANNER_FRICATIVE, False, False),
    "β": ("bilabial", MANNER_FRICATIVE, True, False),
    "f": ("labiodental", MANNER_FRICATIVE, False, False),
    "v": ("labiodental", MANNER_FRICATIVE, True, False),
    "θ": ("dental", MANNER_FRICATIVE, False, False),
    "ð": ("dental", MANNER_FRICATIVE, True, False),
    "s": ("alveolar", MANNER_FRICATIVE, False, False),
    "z": ("alveolar", MANNER_FRICATIVE, True, False),
    "ʃ": ("postalveolar", MANNER_FRICATIVE, False, False),
    "ʒ": ("postalveolar", MANNER_FRICATIVE, True, False),
    "ɕ": ("palatal", MANNER_FRICATIVE, False, False),
    "ʑ": ("palatal", MANNER_FRICATIVE, True, False),
    "ʂ": ("retroflex", MANNER_FRICATIVE, False, False),
    "ʐ": ("retroflex", MANNER_FRICATIVE, True, False),
    "ç": ("palatal", MANNER_FRICATIVE, False, False),
    "ʝ": ("palatal", MANNER_FRICATIVE, True, False),
    "x": ("velar", MANNER_FRICATIVE, False, False),
    "ɣ": ("velar", MANNER_FRICATIVE, True, False),
    "χ": ("uvular", MANNER_FRICATIVE, False, False),
    "ʁ": ("uvular", MANNER_FRICATIVE, True, False),
    "ħ": ("pharyngeal", MANNER_FRICATIVE, False, False),
    "ʕ": ("pharyngeal", MANNER_FRICATIVE, True, False),
    "h": ("glottal", MANNER_FRICATIVE, False, False),
    "ɦ": ("glottal", MANNER_FRICATIVE, True, False),
    # affricates
    "ʧ": ("postalveolar", MANNER_AFFRICATE, False, False),
    "ʤ": ("postalveolar", MANNER_AFFRICATE, True, False),
    # nasals
    "m": ("bilabial", MANNER_NASAL, True, False),
    "ɱ": ("labiodental", MANNER_NASAL, True, False),
    "n": ("alveolar", MANNER_NASAL, True, False),
    "ɳ": ("retroflex", MANNER_NASAL, True, False),
    "ɲ": ("palatal", MANNER_NASAL, True, False),
    "ŋ": ("velar", MANNER_NASAL, True, False),
    "ɴ": ("uvular", MANNER_NASAL, True, False),
    # approximants
    "ʋ": ("labiodental", MANNER_APPROXIMANT, True, False),
    "ɹ": ("alveolar", MANNER_APPROXIMANT, True, False),
    "ɻ": ("retroflex", MANNER_APPROXIMANT, True, False),
    "j": ("palatal", MANNER_APPROXIMANT, True, False),
    "ɥ": ("palatal", MANNER_APPROXIMANT, True, False),
    "ɰ": ("velar", MANNER_APPROXIMANT, True, False),
    "w": ("velar", MANNER_APPROXIMANT, True, False),
    # laterals
    "l": ("alveolar", MANNER_LATERAL, True, True),
    "ɫ": ("velar", MANNER_LATERAL, True, True),
    "ɭ": ("retroflex", MANNER_LATERAL, True, True),
    "ʎ": ("palatal", MANNER_LATERAL, True, True),
    "ʟ": ("velar", MANNER_LATERAL, True, True),
    # trills / taps
    "r": ("alveolar", MANNER_TRILL, True, False),
    "ʀ": ("uvular", MANNER_TRILL, True, False),
    "ʙ": ("bilabial", MANNER_TRILL, True, False),
    "ɾ": ("alveolar", MANNER_TAP, True, False),
    "ɽ": ("retroflex", MANNER_TAP, True, False),
}

#: rounded/labialised approximants
_ROUND_CONSONANTS = frozenset("wɥ")

#: multi-codepoint affricates the caller may pass as two symbols
_AFFRICATE_PAIRS = {
    "tʃ": "ʧ", "dʒ": "ʤ", "ts": None, "dz": None, "pf": None,
}


#: diphthongs / r-coloured vowels parse_ipa emits as single multigraph tokens,
#: expanded here into (start, end) segment pairs so the front ends can glide.
DIPHTHONGS: dict[str, tuple[str, str]] = {
    "eɪ": ("e", "ɪ"), "aɪ": ("a", "ɪ"), "ɔɪ": ("ɔ", "ɪ"),
    "aʊ": ("a", "ʊ"), "oʊ": ("o", "ʊ"), "ju": ("j", "u"),
    "ɪɚ": ("ɪ", "ɚ"), "ɛɚ": ("ɛ", "ɚ"), "ɑɚ": ("ɑ", "ɚ"),
    "ɔɚ": ("ɔ", "ɚ"), "ʊɚ": ("ʊ", "ɚ"),
}

#: every base symbol :func:`decompose` handles directly; the fallback pool.
DECOMPOSABLE_SYMBOLS: tuple[str, ...] = tuple(_VOWELS) + tuple(_CONSONANTS)


def expand(symbol: str) -> list[str]:
    """Split a diphthong/r-coloured multigraph into segments, else ``[symbol]``."""
    if symbol in DIPHTHONGS:
        return list(DIPHTHONGS[symbol])
    return [symbol]


def _apply_diacritics(bundle: FeatureBundle, marks: str) -> FeatureBundle:
    """Fold IPA diacritics/modifier letters into ``bundle``."""
    if "ː" in marks:
        bundle = replace(bundle, long=True)
    if "̃" in marks:  # combining tilde: nasalisation
        bundle = replace(bundle, nasal=True)
    if "˞" in marks or "ɚ" in marks or "ɝ" in marks:
        bundle = replace(bundle, rhotic=True, f3=min(bundle.f3, 1600))
    if "ʰ" in marks:
        bundle = replace(bundle, aspirated=True)
    if "̥" in marks or "̊" in marks:  # voiceless diacritic
        bundle = replace(bundle, voiced=False)
    if "ʲ" in marks:  # palatalisation raises F2
        bundle = replace(bundle, f2=min(2400, bundle.f2 + 400))
    if "ʷ" in marks:  # labialisation rounds and lowers F2/F3
        bundle = replace(bundle, rounded=True, f2=max(700, bundle.f2 - 300),
                         f3=max(1800, bundle.f3 - 200))
    if "ˠ" in marks:  # velarisation lowers F2
        bundle = replace(bundle, f2=max(700, bundle.f2 - 250))
    if "ˤ" in marks:  # pharyngealisation lowers F2, raises F1
        bundle = replace(bundle, f2=max(700, bundle.f2 - 250),
                         f1=min(900, bundle.f1 + 120))
    return bundle


def decompose(symbol: str) -> FeatureBundle:
    """Return the :class:`FeatureBundle` for one IPA segment.

    Raises ``KeyError`` if the base symbol is not in the vowel or consonant
    tables (the caller falls back through :func:`nearest_target`).
    """
    nfd = unicodedata.normalize("NFD", symbol)
    # Split base (spacing letters) from combining marks / modifier letters.
    base_chars = []
    marks = []
    for ch in nfd:
        cat = unicodedata.category(ch)
        if cat in ("Mn", "Lm") or ch in ("ː", "˞", "ʰ", "ʲ", "ʷ", "ˠ", "ˤ"):
            marks.append(ch)
        else:
            base_chars.append(ch)
    base = "".join(base_chars)
    mark_str = "".join(marks) + "".join(
        c for c in symbol if c in ("ɚ", "ɝ") and c not in base)

    # Precomposed affricate digraphs.
    base = _AFFRICATE_PAIRS.get(base, base) or base

    if base in ("ɚ", "ɝ"):
        f1, f2, f3 = _VOWELS["ə"]
        b = FeatureBundle(symbol, True, f1=f1, f2=f2, f3=1500, rhotic=True)
        return _apply_diacritics(b, mark_str)

    if base in _VOWELS:
        f1, f2, f3 = _VOWELS[base]
        b = FeatureBundle(
            symbol, True, f1=f1, f2=f2, f3=f3,
            rounded=base in _ROUND_VOWELS)
        return _apply_diacritics(b, mark_str)

    if base in _CONSONANTS:
        place, manner, voiced, lateral = _CONSONANTS[base]
        locus, center, _ = PLACES[place]
        # English rhotic approximants /ɹ ɻ/ are defined acoustically by a very
        # low F3 (Espy-Wilson et al. 2000 JASA 108(1); DECtalk US R F2 1030,
        # F3 1380), which the neighbouring vowel bends toward. Give them the
        # low F2/F3 locus rather than the generic alveolar/retroflex values.
        rhotic_appr = base in ("ɹ", "ɻ")
        if rhotic_appr:
            f2_locus, f3_locus = 1100, 1400
        elif place == "retroflex":
            f2_locus, f3_locus = locus, 1600
        else:
            f2_locus, f3_locus = locus, 2500
        b = FeatureBundle(
            symbol, False, voiced=voiced, lateral=lateral,
            nasal=(manner == MANNER_NASAL),
            rounded=base in _ROUND_CONSONANTS, rhotic=rhotic_appr,
            f1=(280 if manner in (MANNER_NASAL, MANNER_STOP) else 400),
            f2=f2_locus, f3=f3_locus,
            fric_center=center, manner=manner, place=place)
        if base in _ROUND_CONSONANTS:  # /w/, /ɥ/ lip rounding
            b = replace(b, f2=max(700, b.f2 - 300))
        return _apply_diacritics(b, mark_str)

    raise KeyError(symbol)


# --- articulatory distance for graceful fallback ----------------------------
# Reimplements phonematcher's weighted-feature-distance idea over this package's
# synthesis-oriented features. Vowel distance is dominated by formant geometry;
# consonant distance by place/manner/voicing, the major classificatory axes.

def _distance(a: FeatureBundle, b: FeatureBundle) -> float:
    if a.is_vowel != b.is_vowel:
        return 10.0
    if a.is_vowel:
        # Normalise formant gaps against their perceptual ranges.
        d = (abs(a.f1 - b.f1) / 700.0
             + abs(a.f2 - b.f2) / 1500.0
             + abs(a.f3 - b.f3) / 1500.0)
        d += 0.5 * (a.rounded != b.rounded)
        d += 0.8 * (a.rhotic != b.rhotic)
        d += 0.4 * (a.nasal != b.nasal)
        return d
    pa = PLACES.get(a.place, (0, 0, 0))[2]
    pb = PLACES.get(b.place, (0, 0, 0))[2]
    d = abs(pa - pb) / 5.0
    d += 1.5 * (a.manner != b.manner)
    d += 0.6 * (a.voiced != b.voiced)
    d += 0.4 * (a.lateral != b.lateral)
    d += 0.3 * (a.nasal != b.nasal)
    return d


def nearest_target(symbol: str, candidates: list[str]) -> str:
    """Return the ``candidates`` entry articulatorily closest to ``symbol``.

    Used when a symbol cannot be decomposed directly: pick the reachable target
    with the smallest feature distance rather than an arbitrary English preset.
    """
    if not candidates:
        raise ValueError("candidates is empty")
    try:
        target = decompose(symbol)
    except KeyError:
        return candidates[0]
    best = candidates[0]
    best_d = float("inf")
    for cand in candidates:
        try:
            d = _distance(target, decompose(cand))
        except KeyError:
            continue
        if d < best_d:
            best_d, best = d, cand
    return best
