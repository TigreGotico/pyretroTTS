"""Language selection for the DECtalk front end.

The compiled DECtalk multilanguage build (`dtalkml/src/dtalk_ml.c`) selects a
per-language shared library `libtts_<lang>.so` and, inside it, a per-language
phoneme font byte (`include/l_all_ph.h`: `PFUSA 0x1E`, `PFUK 0x1D`, `PFGR 0x1C`,
`PFSP 0x1B`, `PFLA 0x1A`, `PFFR 0x19`). Every language shares the same
`ph/` frame chain (`ph_draw.c`, `ph_claus.c`) and the same `vtm/` synthesizer
(VTM1), but carries its own phoneme inventory render/parse tables, its own
letter-to-sound data, its own dictionary, and its own `ph/` target ROM / gettar
/ timing / intonation.

This module is the parameterization seam: a `Language` key selects a
`LanguageProfile` that names the font byte, the phoneme render/parse tables, and
the language tag the oracle's `LOG_PHONEMES` output uses. US is registered from
the existing `lts` module tables verbatim (the US path stays byte-identical);
UK is registered from `uk_phonemes`. The heavier per-language data (dictionary,
LTS rules, `ph/` ROM) attach here as they are ported.

Derived from the Fonix/Force DECtalk C source (`dectalk/dectalk`,
`src/dapi/src/dtalkml/src/dtalk_ml.c`, `src/dapi/src/include/l_all_ph.h`).
FONIX Corporation declares that source proprietary and confidential. This file
is NOT covered by this project's MIT licence. See NOTICE.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

from . import lts, uk_phonemes
from .settar import Allophones, us_gettar
from .settar_uk import uk_gettar


class Language(str, Enum):
    """A DECtalk front-end language (the `libtts_<lang>.so` selector)."""

    US = "us"
    UK = "uk"


@dataclass(frozen=True)
class LanguageProfile:
    """Per-language phoneme-alphabet parameters selected by `Language`.

    `font` is the `l_all_ph.h` font byte shifted into the top of a phoneme code
    (`code = (font << 8) | index`). `tag` is the `LOG_PHONEMES` language prefix
    (`phlog.c` `PrintLangBit`). `phoneme_names`/`phoneme_codes` are the raw
    index <-> ARPABET-name inventory. `arpa_pairs` is the two-character render
    table (`<lang>_arpa[]`). `total_allophones` is `<LANG>_TOT_ALLOPHONES`.
    """

    language: Language
    font: int
    tag: str
    phoneme_names: dict[int, str]
    phoneme_codes: dict[str, int]
    arpa_pairs: dict[int, tuple[str, str]]
    total_allophones: int
    gettar: Callable[[Allophones, int, int], int]

    def code(self, index: int) -> int:
        """Font-shifted phoneme code for a raw inventory `index`."""
        return (self.font << lts.PSFONT) | index

    def arpa_name(self, index: int) -> str:
        """ARPABET spelling of a raw phoneme `index`; '' if undefined."""
        pair = self.arpa_pairs.get(index)
        if pair is None:
            return ""
        a, b = pair
        return a if b == " " else a + b

    def render_token(self, index: int) -> str:
        """`LOG_PHONEMES` token for a raw phoneme `index` (`<tag><arpa>`)."""
        pair = self.arpa_pairs.get(index)
        if pair is None:
            return ""
        a, b = pair
        return f"{self.tag}{a} " if b == " " else f"{self.tag}{a}{b}"


_US_PROFILE = LanguageProfile(
    language=Language.US,
    font=lts.PFUSA,
    tag="us_",
    phoneme_names=lts.US_PHONEME_NAMES,
    phoneme_codes=lts.US_PHONEME_CODES,
    arpa_pairs={k: v for k, v in lts._ARPA_PAIRS.items() if k < 57},
    total_allophones=57,
    gettar=us_gettar,
)

_UK_PROFILE = LanguageProfile(
    language=Language.UK,
    font=uk_phonemes.PFUK,
    tag="uk_",
    phoneme_names=uk_phonemes.UK_PHONEME_NAMES,
    phoneme_codes=uk_phonemes.UK_PHONEME_CODES,
    arpa_pairs=uk_phonemes.UK_ARPA_PAIRS,
    total_allophones=uk_phonemes.UK_TOT_ALLOPHONES,
    gettar=uk_gettar,
)

_PROFILES: dict[Language, LanguageProfile] = {
    Language.US: _US_PROFILE,
    Language.UK: _UK_PROFILE,
}


def profile(language: Language) -> LanguageProfile:
    """The `LanguageProfile` for `language`."""
    return _PROFILES[language]
