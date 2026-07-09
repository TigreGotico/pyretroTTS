"""
Bit-exact test for the english_lex dictionary-lookup port (lintalker._lexicon).

This validates `lintalker._lexicon.lookup()` against output captured from the
real C dictionary lookup, compiled as a standalone throwaway harness
(`lex_harness.c`, built and run against the actual compiled object files
`obj/Debug/{Data,english_lex,Linux,FrontEnd,Morph,EngToP,Sounds,Engine,
BackEnd,EmbeddedCmd,Say,formantSynth}.o` from `lintalker-c`, then deleted --
not part of the normal `lintalker-c` build; see `docs/architecture.md`). The
harness calls `_OpenSpeech()` to build the real `Dict` struct from the
embedded `english_lex_data` (`Linux.c:288`/`295`/`300`), then calls
`SearchAllDicts(vv, pascalWord, &tok, vv->Dict, true)` directly
(`FrontEnd.c:1592-1608`) for each test word and dumps `tok`'s decoded fields.

IMPORTANT finding from that harness run: `English.lex` ships with
`dict->type == kEncryptDict (1)`, NOT `kCompressDict (2)`
(`mt4.h:773-775`), so `SearchAllDicts` always routes it through the
uncompressed `SearchSingleDict` (`FrontEnd.c:1150-1321`), never through
`SearchSingleDict_C`'s `DecompressString`-based path (`FrontEnd.c:1383-1586`,
which is dead code for this dictionary). `SearchSingleDict` copies phoneme
bytes through verbatim -- no `kPrimeStress` flag-bit stripping and no
`kDictComp`/`kDictWord` -> `_Comp_`/`_Word_` substitution. Those raw
`_pRise_`/`_pFall_` opcodes (aliased as `kDictComp`/`kDictWord`, `mt4.h:759-
760`) pass straight through to whoever consumes `tok->phonStr` next --
`Fill_Phon_Buf_2` (`BackEnd.c:2469-2846`, not yet ported), not this
dictionary decode. `lintalker/_lexicon.py`'s docstring documents this in
detail.

REFERENCE below covers, by design:
  - common short/function words (THE, A, OF, AND, IS, ...) exercising the
    "before A" (lo=0) and normal hash-bucket search ranges;
  - words with no dictionary entry (XYLOPHONE, NOTAWORD123, CROMULENT,
    FROBNICATE) -- confirming the fallback-to-EngToP signal (`lookup() ->
    None`) is correct;
  - compound-noun words (CHICKENPOX, DOWNGRADE, DOWNTOWN, ETHERNET, FN,
    HORSEPOWER, MASTERCARD, NOBODY, PUSHBUTTON, RACETRACK, SNAPSHOT,
    TYPESET) -- every compound-flagged word in the whole dictionary,
    discovered by scanning `english_lex_data` for the literal `_pRise_`
    opcode, exercising the compound-noun code path exhaustively;
  - alt-pronunciation words (ABSENT, ABSTRACT, ABUSE, ADDICT, ..., all the
    way to MATURE) exercising `tok->hasAlt`/`tok->phonHold`/`tok->POScode2`;
  - abbreviations (FN, EST., DR., KGS., TBSP., TUES., MSECS, KHZ) exercising
    `tok->isAbbriv` (kAbriv POS code);
  - a uniform random sample of 200 additional words drawn from the full
    ~7173-word dictionary (`random.seed(42)`) for broad coverage beyond
    hand-picked cases.

All 250 words matched the C reference bit-exact at capture time.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from lintalker._lexicon import lookup
from lintalker._phonemes import _Word_

# word -> None (not found) or a dict of decoded fields, captured from the
# standalone C harness described above.
REFERENCE = {
    'THE': {'phon': [64, 39, 57, 5], 'pos1': [19, -1, -1, -1], 'comppos1': 524288, 'abbrev': 0, 'hasalt': 0},
    'A': {'phon': [64, 57, 5], 'pos1': [19, -1, -1, -1], 'comppos1': 524288, 'abbrev': 0, 'hasalt': 0},
    'OF': {'phon': [64, 56, 8, 37], 'pos1': [13, 3, -1, -1], 'comppos1': 8200, 'abbrev': 0, 'hasalt': 0},
    'SAID': {'phon': [64, 40, 57, 2, 47], 'pos1': [1, -1, -1, -1], 'comppos1': 2, 'abbrev': 0, 'hasalt': 0},
    'ABOUT': {'phon': [64, 57, 5, 45, 56, 13, 46], 'pos1': [3, -1, -1, -1], 'comppos1': 8, 'abbrev': 0, 'hasalt': 0},
    'AARON': {'phon': [64, 56, 2, 30, 22, 34], 'pos1': [0, -1, -1, -1], 'comppos1': 1, 'abbrev': 0, 'hasalt': 0},
    'ZURICH': {'phon': [64, 41, 56, 15, 30, 22, 48], 'pos1': [0, -1, -1, -1], 'comppos1': 1, 'abbrev': 0, 'hasalt': 0},
    'AND': {'phon': [64, 57, 2, 34, 47], 'pos1': [8, -1, -1, -1], 'comppos1': 256, 'abbrev': 0, 'hasalt': 0},
    'IS': {'phon': [64, 57, 1, 41], 'pos1': [5, -1, -1, -1], 'comppos1': 32, 'abbrev': 0, 'hasalt': 0},
    'ARE': {'phon': [64, 56, 4, 30], 'pos1': [5, -1, -1, -1], 'comppos1': 32, 'abbrev': 0, 'hasalt': 0},
    'HAVE': {'phon': [64, 32, 2, 37], 'pos1': [1, 5, -1, -1], 'comppos1': 34, 'abbrev': 0, 'hasalt': 0},
    'BEEN': {'phon': [64, 45, 56, 2, 34], 'pos1': [5, -1, -1, -1], 'comppos1': 32, 'abbrev': 0, 'hasalt': 0},
    'SHOULD': {'phon': [64, 42, 57, 7, 47], 'pos1': [4, -1, -1, -1], 'comppos1': 16, 'abbrev': 0, 'hasalt': 0},
    'SHALL': {'phon': [64, 42, 56, 2, 31], 'pos1': [5, -1, -1, -1], 'comppos1': 32, 'abbrev': 0, 'hasalt': 0},
    'MAYBE': {'phon': [64, 33, 56, 10, 45, 57, 0], 'pos1': [11, -1, -1, -1], 'comppos1': 2048, 'abbrev': 0, 'hasalt': 0},
    'THEREFORE': {'phon': [64, 39, 56, 2, 30, 36, 57, 14, 30], 'pos1': [11, -1, -1, -1], 'comppos1': 2048, 'abbrev': 0, 'hasalt': 0},
    'NEITHER': {'phon': [64, 34, 56, 0, 39, 57, 8, 30], 'pos1': [7, 16, -1, -1], 'comppos1': 65664, 'abbrev': 0, 'hasalt': 0},
    'WHATEVER': {'phon': [64, 28, 8, 53, 56, 2, 37, 57, 8, 30], 'pos1': [15, -1, -1, -1], 'comppos1': 32768, 'abbrev': 0, 'hasalt': 0},
    'WHOSOEVER': {'phon': [64, 32, 15, 40, 57, 14, 56, 2, 37, 57, 8, 30], 'pos1': [15, -1, -1, -1], 'comppos1': 32768, 'abbrev': 0, 'hasalt': 0},
    'XYLOPHONE': None,
    'NOTAWORD123': None,
    'CROMULENT': None,
    'FROBNICATE': None,
    'CHICKENPOX': {'phon': [64, 50, 56, 1, 48, 27, 59, 44, 4, 48, 40], 'pos1': [0, -1, -1, -1], 'comppos1': 1, 'abbrev': 0, 'hasalt': 0},
    'DOWNGRADE': {'phon': [64, 47, 56, 13, 34, 59, 49, 30, 10, 47], 'pos1': [2, 0, 1, -1], 'comppos1': 7, 'abbrev': 0, 'hasalt': 0},
    'DOWNTOWN': {'phon': [64, 47, 13, 34, 59, 46, 56, 13, 34], 'pos1': [11, 2, 0, -1], 'comppos1': 2053, 'abbrev': 0, 'hasalt': 0},
    'ETHERNET': {'phon': [64, 56, 0, 38, 9, 59, 34, 2, 46], 'pos1': [0, -1, -1, -1], 'comppos1': 1, 'abbrev': 0, 'hasalt': 0},
    'FN': {'phon': [64, 36, 56, 7, 46, 59, 34, 14, 46], 'pos1': [0, -1, -1, -1], 'comppos1': 1, 'abbrev': 1, 'hasalt': 0},
    'HORSEPOWER': {'phon': [64, 32, 56, 14, 30, 40, 59, 44, 13, 9], 'pos1': [0, -1, -1, -1], 'comppos1': 1, 'abbrev': 0, 'hasalt': 0},
    'MASTERCARD': {'phon': [64, 33, 56, 3, 40, 46, 9, 59, 48, 4, 30, 47], 'pos1': [0, -1, -1, -1], 'comppos1': 1, 'abbrev': 0, 'hasalt': 0},
    'NOBODY': {'phon': [64, 34, 56, 14, 59, 45, 57, 5, 47, 0], 'pos1': [0, 16, -1, -1], 'comppos1': 65537, 'abbrev': 0, 'hasalt': 0},
    'PUSHBUTTON': {'phon': [64, 44, 56, 7, 42, 59, 45, 57, 5, 46, 27], 'pos1': [0, -1, -1, -1], 'comppos1': 1, 'abbrev': 0, 'hasalt': 0},
    'RACETRACK': {'phon': [64, 30, 56, 10, 40, 59, 46, 30, 3, 48], 'pos1': [0, -1, -1, -1], 'comppos1': 1, 'abbrev': 0, 'hasalt': 0},
    'SNAPSHOT': {'phon': [64, 40, 34, 56, 4, 44, 59, 42, 4, 46], 'pos1': [0, -1, -1, -1], 'comppos1': 1, 'abbrev': 0, 'hasalt': 0},
    'TYPESET': {'phon': [64, 46, 56, 11, 44, 59, 40, 2, 46], 'pos1': [1, -1, -1, -1], 'comppos1': 2, 'abbrev': 0, 'hasalt': 0},
    'ABSENT': {'phon': [64, 56, 3, 45, 40, 22, 34, 46], 'pos1': [2, 3, -1, -1], 'comppos1': 12, 'abbrev': 0, 'hasalt': 1, 'altphon': [64, 3, 45, 40, 56, 2, 34, 46], 'pos2': [0, 1, -1, -1], 'comppos2': 3},
    'ABSTRACT': {'phon': [64, 3, 45, 40, 46, 30, 56, 3, 48, 46], 'pos1': [1, -1, -1, -1], 'comppos1': 2, 'abbrev': 0, 'hasalt': 1, 'altphon': [64, 56, 3, 45, 40, 46, 30, 57, 3, 48, 46], 'pos2': [2, 0, -1, -1], 'comppos2': 5},
    'ABUSE': {'phon': [64, 8, 45, 56, 16, 41], 'pos1': [1, -1, -1, -1], 'comppos1': 2, 'abbrev': 0, 'hasalt': 1, 'altphon': [64, 8, 45, 56, 16, 40], 'pos2': [0, -1, -1, -1], 'comppos2': 1},
    'ADDICT': {'phon': [64, 8, 47, 56, 1, 48, 46], 'pos1': [1, -1, -1, -1], 'comppos1': 2, 'abbrev': 0, 'hasalt': 1, 'altphon': [64, 56, 3, 47, 1, 48, 46], 'pos2': [0, -1, -1, -1], 'comppos2': 1},
    'ADDRESS': {'phon': [64, 56, 3, 47, 30, 57, 2, 40], 'pos1': [0, -1, -1, -1], 'comppos1': 1, 'abbrev': 0, 'hasalt': 1, 'altphon': [64, 8, 47, 30, 56, 2, 40], 'pos2': [1, -1, -1, -1], 'comppos2': 2},
    'ADVOCATE': {'phon': [64, 56, 3, 47, 37, 8, 48, 57, 10, 46], 'pos1': [1, -1, -1, -1], 'comppos1': 2, 'abbrev': 0, 'hasalt': 1, 'altphon': [64, 56, 3, 47, 37, 8, 48, 8, 46], 'pos2': [0, -1, -1, -1], 'comppos2': 1},
    'AFFECT': {'phon': [64, 8, 36, 56, 2, 48, 46], 'pos1': [1, -1, -1, -1], 'comppos1': 2, 'abbrev': 0, 'hasalt': 1, 'altphon': [64, 56, 3, 36, 57, 2, 48, 46], 'pos2': [0, -1, -1, -1], 'comppos2': 1},
    'AFFILIATE': {'phon': [64, 8, 36, 56, 1, 31, 0, 22, 46], 'pos1': [0, -1, -1, -1], 'comppos1': 1, 'abbrev': 0, 'hasalt': 1, 'altphon': [64, 8, 36, 56, 1, 31, 0, 57, 10, 46], 'pos2': [1, -1, -1, -1], 'comppos2': 2},
    'AFFIX': {'phon': [64, 8, 36, 56, 1, 48, 40], 'pos1': [1, -1, -1, -1], 'comppos1': 2, 'abbrev': 0, 'hasalt': 1, 'altphon': [64, 56, 3, 36, 57, 1, 48, 40], 'pos2': [0, -1, -1, -1], 'comppos2': 1},
    'AGGREGATE': {'phon': [64, 56, 3, 49, 30, 22, 49, 22, 46], 'pos1': [2, 0, -1, -1], 'comppos1': 5, 'abbrev': 0, 'hasalt': 1, 'altphon': [64, 56, 3, 49, 30, 22, 49, 57, 10, 46], 'pos2': [1, -1, -1, -1], 'comppos2': 2},
    'ALLOY': {'phon': [64, 56, 3, 31, 57, 12], 'pos1': [0, -1, -1, -1], 'comppos1': 1, 'abbrev': 0, 'hasalt': 1, 'altphon': [64, 8, 31, 56, 12], 'pos2': [1, -1, -1, -1], 'comppos2': 2},
    'ALTERNATE': {'phon': [64, 56, 6, 31, 46, 9, 34, 22, 46], 'pos1': [2, 0, -1, -1], 'comppos1': 5, 'abbrev': 0, 'hasalt': 1, 'altphon': [64, 56, 6, 31, 46, 9, 30, 34, 57, 10, 46], 'pos2': [1, -1, -1, -1], 'comppos2': 2},
    'ANIMATE': {'phon': [64, 56, 3, 34, 22, 33, 8, 46], 'pos1': [2, -1, -1, -1], 'comppos1': 4, 'abbrev': 0, 'hasalt': 1, 'altphon': [64, 56, 3, 34, 22, 33, 57, 10, 46], 'pos2': [1, -1, -1, -1], 'comppos2': 2},
    'ANNEX': {'phon': [64, 8, 34, 56, 2, 48, 40], 'pos1': [1, -1, -1, -1], 'comppos1': 2, 'abbrev': 0, 'hasalt': 1, 'altphon': [64, 56, 3, 34, 57, 2, 48, 40], 'pos2': [0, -1, -1, -1], 'comppos2': 1},
    'APPROPRIATE': {'phon': [64, 8, 44, 30, 56, 14, 44, 30, 0, 22, 46], 'pos1': [2, -1, -1, -1], 'comppos1': 4, 'abbrev': 0, 'hasalt': 1, 'altphon': [64, 8, 44, 30, 56, 14, 44, 30, 0, 57, 10, 46], 'pos2': [1, -1, -1, -1], 'comppos2': 2},
    'PROBABLE': {'phon': [64, 44, 30, 56, 4, 45, 57, 5, 45, 57, 7, 31], 'pos1': [2, -1, -1, -1], 'comppos1': 4, 'abbrev': 0, 'hasalt': 0},
    'BUSINESS': {'phon': [64, 45, 56, 1, 41, 34, 22, 40], 'pos1': [2, 0, -1, -1], 'comppos1': 5, 'abbrev': 0, 'hasalt': 0},
    'ALL': {'phon': [64, 56, 6, 31], 'pos1': [11, 16, -1, -1], 'comppos1': 67584, 'abbrev': 0, 'hasalt': 0},
    'SOVEREIGNTY': {'phon': [64, 40, 56, 4, 37, 30, 8, 34, 46, 0], 'pos1': [0, -1, -1, -1], 'comppos1': 1, 'abbrev': 0, 'hasalt': 0},
    'EROSION': {'phon': [64, 22, 30, 56, 14, 43, 22, 34], 'pos1': [0, -1, -1, -1], 'comppos1': 1, 'abbrev': 0, 'hasalt': 0},
    'DRAFTEE': {'phon': [64, 47, 30, 3, 36, 46, 56, 0], 'pos1': [0, -1, -1, -1], 'comppos1': 1, 'abbrev': 0, 'hasalt': 0},
    "DIDN'T": {'phon': [64, 47, 57, 1, 47, 27, 46], 'pos1': [5, -1, -1, -1], 'comppos1': 32, 'abbrev': 0, 'hasalt': 0},
    'CHRIST': {'phon': [64, 48, 30, 56, 11, 40, 46], 'pos1': [0, -1, -1, -1], 'comppos1': 1, 'abbrev': 0, 'hasalt': 0},
    'SOCIALISTIC': {'phon': [64, 40, 14, 42, 8, 31, 56, 1, 40, 46, 22, 48], 'pos1': [2, -1, -1, -1], 'comppos1': 4, 'abbrev': 0, 'hasalt': 0},
    'BOWEN': {'phon': [64, 45, 56, 14, 22, 34], 'pos1': [0, -1, -1, -1], 'comppos1': 1, 'abbrev': 0, 'hasalt': 0},
    'REGINALD': {'phon': [64, 30, 56, 2, 51, 57, 1, 34, 22, 31, 47], 'pos1': [0, -1, -1, -1], 'comppos1': 1, 'abbrev': 0, 'hasalt': 0},
    'SOUL': {'phon': [64, 40, 56, 14, 31], 'pos1': [2, 0, -1, -1], 'comppos1': 5, 'abbrev': 0, 'hasalt': 0},
    'NEURON': {'phon': [64, 34, 56, 9, 4, 34], 'pos1': [0, -1, -1, -1], 'comppos1': 1, 'abbrev': 0, 'hasalt': 0},
    'BELOW': {'phon': [64, 45, 57, 26, 56, 14], 'pos1': [11, 2, 3, -1], 'comppos1': 2060, 'abbrev': 0, 'hasalt': 0},
    'PARAMETER': {'phon': [64, 44, 57, 8, 30, 56, 3, 33, 1, 46, 57, 9], 'pos1': [0, -1, -1, -1], 'comppos1': 1, 'abbrev': 0, 'hasalt': 0},
    'INTERFAITH': {'phon': [64, 56, 1, 34, 46, 9, 36, 10, 38], 'pos1': [2, -1, -1, -1], 'comppos1': 4, 'abbrev': 0, 'hasalt': 0},
    'AMBITIOUS': {'phon': [64, 3, 33, 45, 56, 1, 42, 22, 40], 'pos1': [2, -1, -1, -1], 'comppos1': 4, 'abbrev': 0, 'hasalt': 0},
    'ALTO': {'phon': [64, 56, 3, 31, 46, 14], 'pos1': [0, -1, -1, -1], 'comppos1': 1, 'abbrev': 0, 'hasalt': 0},
    'BINOMIAL': {'phon': [64, 45, 11, 34, 56, 14, 33, 0, 26], 'pos1': [0, -1, -1, -1], 'comppos1': 1, 'abbrev': 0, 'hasalt': 0},
    'DETAIL': {'phon': [64, 47, 56, 0, 46, 57, 10, 31], 'pos1': [0, 1, -1, -1], 'comppos1': 3, 'abbrev': 0, 'hasalt': 0},
    'DISMISS': {'phon': [64, 47, 22, 40, 33, 56, 1, 40], 'pos1': [1, -1, -1, -1], 'comppos1': 2, 'abbrev': 0, 'hasalt': 0},
    'MELANIE': {'phon': [64, 33, 56, 2, 31, 8, 34, 0], 'pos1': [0, -1, -1, -1], 'comppos1': 1, 'abbrev': 0, 'hasalt': 0},
    'PERIGEE': {'phon': [64, 44, 56, 10, 30, 8, 51, 0], 'pos1': [0, -1, -1, -1], 'comppos1': 1, 'abbrev': 0, 'hasalt': 0},
    'ALLOT': {'phon': [64, 8, 31, 56, 4, 46], 'pos1': [1, -1, -1, -1], 'comppos1': 2, 'abbrev': 0, 'hasalt': 0},
    'OBTUSE': {'phon': [64, 57, 4, 45, 46, 56, 15, 40], 'pos1': [2, -1, -1, -1], 'comppos1': 4, 'abbrev': 0, 'hasalt': 0},
    'DAWN': {'phon': [64, 47, 56, 4, 34], 'pos1': [0, -1, -1, -1], 'comppos1': 1, 'abbrev': 0, 'hasalt': 0},
    'SCROLLBAR': {'phon': [64, 40, 48, 30, 56, 14, 31, 45, 57, 4, 30], 'pos1': [0, -1, -1, -1], 'comppos1': 1, 'abbrev': 0, 'hasalt': 0},
    'PUBLICATION': {'phon': [64, 44, 5, 45, 31, 57, 1, 48, 56, 10, 42, 57, 1, 34], 'pos1': [0, -1, -1, -1], 'comppos1': 1, 'abbrev': 0, 'hasalt': 0},
    'ROSALIE': {'phon': [64, 30, 56, 14, 41, 8, 31, 0], 'pos1': [0, -1, -1, -1], 'comppos1': 1, 'abbrev': 0, 'hasalt': 0},
    'NEON': {'phon': [64, 34, 56, 0, 4, 34], 'pos1': [0, -1, -1, -1], 'comppos1': 1, 'abbrev': 0, 'hasalt': 0},
    'INSUBORDINATE': {'phon': [64, 22, 34, 40, 8, 45, 56, 14, 30, 47, 27, 8, 46], 'pos1': [2, -1, -1, -1], 'comppos1': 4, 'abbrev': 0, 'hasalt': 0},
    'DEVALUATE': {'phon': [64, 47, 22, 37, 56, 3, 31, 16, 10, 46], 'pos1': [1, -1, -1, -1], 'comppos1': 2, 'abbrev': 0, 'hasalt': 0},
    'JUVENILE': {'phon': [64, 51, 56, 15, 37, 8, 34, 11, 31], 'pos1': [2, 0, -1, -1], 'comppos1': 5, 'abbrev': 0, 'hasalt': 0},
    'PANCREAS': {'phon': [64, 44, 56, 3, 35, 48, 30, 0, 22, 40], 'pos1': [0, -1, -1, -1], 'comppos1': 1, 'abbrev': 0, 'hasalt': 0},
    'ESTATE': {'phon': [64, 57, 1, 40, 46, 56, 10, 46], 'pos1': [0, -1, -1, -1], 'comppos1': 1, 'abbrev': 0, 'hasalt': 0},
    'UNABATED': {'phon': [64, 56, 5, 34, 8, 45, 56, 10, 46, 22, 47], 'pos1': [2, -1, -1, -1], 'comppos1': 4, 'abbrev': 0, 'hasalt': 0},
    'WRIGHT': {'phon': [64, 30, 56, 11, 46], 'pos1': [0, -1, -1, -1], 'comppos1': 1, 'abbrev': 0, 'hasalt': 0},
    'ACETIC': {'phon': [64, 8, 40, 56, 0, 46, 22, 48], 'pos1': [2, -1, -1, -1], 'comppos1': 4, 'abbrev': 0, 'hasalt': 0},
    'SUBSIDE': {'phon': [64, 40, 8, 45, 40, 56, 11, 47], 'pos1': [1, -1, -1, -1], 'comppos1': 2, 'abbrev': 0, 'hasalt': 0},
    'TURNER': {'phon': [64, 46, 56, 9, 34, 9], 'pos1': [0, -1, -1, -1], 'comppos1': 1, 'abbrev': 0, 'hasalt': 0},
    'COMPETENCE': {'phon': [64, 48, 56, 4, 33, 44, 8, 46, 22, 34, 40], 'pos1': [0, -1, -1, -1], 'comppos1': 1, 'abbrev': 0, 'hasalt': 0},
    'RIVERA': {'phon': [64, 30, 22, 37, 56, 2, 30, 8], 'pos1': [0, -1, -1, -1], 'comppos1': 1, 'abbrev': 0, 'hasalt': 0},
    'INTERMEDIATE': {'phon': [64, 22, 34, 46, 9, 33, 56, 0, 47, 0, 8, 46], 'pos1': [2, 0, -1, -1], 'comppos1': 5, 'abbrev': 0, 'hasalt': 0},
    'GOOD-BYE': {'phon': [64, 49, 7, 47, 45, 56, 11], 'pos1': [6, 0, -1, -1], 'comppos1': 65, 'abbrev': 0, 'hasalt': 0},
    'EST.': {'phon': [64, 22, 40, 46, 56, 3, 45, 31, 22, 42, 46], 'pos1': [0, -1, -1, -1], 'comppos1': 1, 'abbrev': 1, 'hasalt': 0},
    'COMFORTABLE': {'phon': [64, 48, 56, 5, 33, 36, 9, 46, 8, 45, 26], 'pos1': [2, -1, -1, -1], 'comppos1': 4, 'abbrev': 0, 'hasalt': 0},
    'DERRIERE': {'phon': [64, 47, 10, 30, 0, 56, 10, 30], 'pos1': [0, -1, -1, -1], 'comppos1': 1, 'abbrev': 0, 'hasalt': 0},
    'SUNDAY': {'phon': [64, 40, 56, 5, 34, 47, 10], 'pos1': [0, -1, -1, -1], 'comppos1': 1, 'abbrev': 0, 'hasalt': 0},
    'GIVEN': {'phon': [64, 49, 57, 1, 37, 27], 'pos1': [0, 1, -1, -1], 'comppos1': 3, 'abbrev': 0, 'hasalt': 0},
    'BOW': {'phon': [64, 45, 56, 13], 'pos1': [0, 1, -1, -1], 'comppos1': 3, 'abbrev': 0, 'hasalt': 1, 'altphon': [64, 45, 56, 14], 'pos2': [2, -1, -1, -1], 'comppos2': 4},
    'BICYCLE': {'phon': [64, 45, 56, 11, 40, 22, 48, 26], 'pos1': [0, 1, -1, -1], 'comppos1': 3, 'abbrev': 0, 'hasalt': 0},
    'HYPNOTIC': {'phon': [64, 32, 22, 44, 34, 56, 4, 46, 22, 48], 'pos1': [2, -1, -1, -1], 'comppos1': 4, 'abbrev': 0, 'hasalt': 0},
    'BLOODBATH': {'phon': [64, 45, 31, 56, 5, 47, 45, 3, 38], 'pos1': [0, -1, -1, -1], 'comppos1': 1, 'abbrev': 0, 'hasalt': 0},
    'HEATHER': {'phon': [64, 32, 56, 2, 39, 9], 'pos1': [0, -1, -1, -1], 'comppos1': 1, 'abbrev': 0, 'hasalt': 0},
    'WAGON': {'phon': [64, 28, 56, 3, 49, 57, 1, 34], 'pos1': [0, -1, -1, -1], 'comppos1': 1, 'abbrev': 0, 'hasalt': 0},
    'GRATUITOUS': {'phon': [64, 49, 30, 8, 46, 56, 15, 22, 46, 22, 40], 'pos1': [2, -1, -1, -1], 'comppos1': 4, 'abbrev': 0, 'hasalt': 0},
    'PEROXIDE': {'phon': [64, 44, 9, 56, 4, 48, 40, 11, 47], 'pos1': [0, 1, -1, -1], 'comppos1': 3, 'abbrev': 0, 'hasalt': 0},
    'ENDMOST': {'phon': [64, 56, 2, 34, 47, 33, 14, 40, 46], 'pos1': [2, -1, -1, -1], 'comppos1': 4, 'abbrev': 0, 'hasalt': 0},
    'TWOFOLD': {'phon': [64, 46, 56, 15, 36, 14, 31, 47], 'pos1': [11, 2, -1, -1], 'comppos1': 2052, 'abbrev': 0, 'hasalt': 0},
    'ANTAGONISM': {'phon': [64, 3, 34, 46, 56, 3, 49, 22, 34, 22, 41, 8, 33], 'pos1': [0, -1, -1, -1], 'comppos1': 1, 'abbrev': 0, 'hasalt': 0},
    'SHOWER': {'phon': [64, 42, 56, 13, 9], 'pos1': [0, 1, -1, -1], 'comppos1': 3, 'abbrev': 0, 'hasalt': 0},
    'LANGUAGE': {'phon': [64, 31, 56, 3, 35, 49, 28, 57, 1, 51], 'pos1': [0, -1, -1, -1], 'comppos1': 1, 'abbrev': 0, 'hasalt': 0},
    'MUNICIPAL': {'phon': [64, 33, 16, 34, 56, 1, 40, 8, 44, 26], 'pos1': [2, -1, -1, -1], 'comppos1': 4, 'abbrev': 0, 'hasalt': 0},
    'CARTEL': {'phon': [64, 48, 4, 30, 46, 56, 2, 31], 'pos1': [0, -1, -1, -1], 'comppos1': 1, 'abbrev': 0, 'hasalt': 0},
    'HYDRO': {'phon': [64, 32, 56, 11, 47, 30, 14], 'pos1': [0, -1, -1, -1], 'comppos1': 1, 'abbrev': 0, 'hasalt': 0},
    'BARRAGE': {'phon': [64, 45, 9, 56, 4, 51], 'pos1': [0, 1, -1, -1], 'comppos1': 3, 'abbrev': 0, 'hasalt': 0},
    'NONMETALLIC': {'phon': [64, 34, 4, 34, 33, 8, 46, 56, 3, 31, 22, 48], 'pos1': [2, -1, -1, -1], 'comppos1': 4, 'abbrev': 0, 'hasalt': 0},
    'EXTENT': {'phon': [64, 57, 2, 48, 40, 46, 56, 2, 34, 46], 'pos1': [0, -1, -1, -1], 'comppos1': 1, 'abbrev': 0, 'hasalt': 0},
    'UPTIME': {'phon': [64, 56, 5, 44, 46, 11, 33], 'pos1': [0, -1, -1, -1], 'comppos1': 1, 'abbrev': 0, 'hasalt': 0},
    'PRECOOK': {'phon': [64, 44, 30, 0, 48, 56, 7, 48], 'pos1': [1, -1, -1, -1], 'comppos1': 2, 'abbrev': 0, 'hasalt': 0},
    'POIGNANT': {'phon': [64, 44, 56, 12, 34, 29, 8, 34, 46], 'pos1': [2, -1, -1, -1], 'comppos1': 4, 'abbrev': 0, 'hasalt': 0},
    'WILBUR': {'phon': [64, 28, 56, 1, 31, 45, 9], 'pos1': [0, -1, -1, -1], 'comppos1': 1, 'abbrev': 0, 'hasalt': 0},
    'HENCEFORTH': {'phon': [64, 32, 56, 2, 34, 40, 36, 14, 30, 38], 'pos1': [11, -1, -1, -1], 'comppos1': 2048, 'abbrev': 0, 'hasalt': 0},
    'OUTFIGHT': {'phon': [64, 13, 46, 36, 56, 11, 46], 'pos1': [0, -1, -1, -1], 'comppos1': 1, 'abbrev': 0, 'hasalt': 0},
    'CUCKOO': {'phon': [64, 48, 56, 15, 48, 15], 'pos1': [2, 0, -1, -1], 'comppos1': 5, 'abbrev': 0, 'hasalt': 0},
    'RUNAWAY': {'phon': [64, 30, 56, 5, 34, 8, 28, 10], 'pos1': [0, -1, -1, -1], 'comppos1': 1, 'abbrev': 0, 'hasalt': 0},
    'AUTOMOBILE': {'phon': [64, 6, 46, 8, 33, 14, 45, 56, 0, 31], 'pos1': [0, -1, -1, -1], 'comppos1': 1, 'abbrev': 0, 'hasalt': 0},
    'ANTONIO': {'phon': [64, 3, 34, 46, 56, 14, 34, 0, 14], 'pos1': [0, -1, -1, -1], 'comppos1': 1, 'abbrev': 0, 'hasalt': 0},
    'RAUL': {'phon': [64, 30, 57, 13, 56, 15, 31], 'pos1': [0, -1, -1, -1], 'comppos1': 1, 'abbrev': 0, 'hasalt': 0},
    'DISASTROUS': {'phon': [64, 47, 22, 41, 56, 3, 40, 46, 30, 22, 40], 'pos1': [2, -1, -1, -1], 'comppos1': 4, 'abbrev': 0, 'hasalt': 0},
    'TABLESPOON': {'phon': [64, 46, 56, 10, 45, 26, 40, 44, 57, 15, 34], 'pos1': [0, -1, -1, -1], 'comppos1': 1, 'abbrev': 0, 'hasalt': 0},
    'EXIT': {'phon': [64, 56, 2, 49, 41, 22, 46], 'pos1': [0, -1, -1, -1], 'comppos1': 1, 'abbrev': 0, 'hasalt': 0},
    'BASELINE': {'phon': [64, 45, 56, 10, 40, 31, 11, 34], 'pos1': [0, -1, -1, -1], 'comppos1': 1, 'abbrev': 0, 'hasalt': 0},
    'WENDY': {'phon': [64, 28, 56, 2, 34, 47, 0], 'pos1': [0, -1, -1, -1], 'comppos1': 1, 'abbrev': 0, 'hasalt': 0},
    'DISMOUNT': {'phon': [64, 47, 1, 40, 33, 56, 13, 34, 46], 'pos1': [1, -1, -1, -1], 'comppos1': 2, 'abbrev': 0, 'hasalt': 1, 'altphon': [64, 47, 56, 1, 40, 33, 57, 13, 34, 46], 'pos2': [0, -1, -1, -1], 'comppos2': 1},
    'WOMANKIND': {'phon': [64, 28, 56, 7, 33, 8, 34, 48, 11, 34, 47], 'pos1': [0, -1, -1, -1], 'comppos1': 1, 'abbrev': 0, 'hasalt': 0},
    'BOSTON': {'phon': [64, 45, 56, 6, 40, 46, 8, 34], 'pos1': [0, -1, -1, -1], 'comppos1': 1, 'abbrev': 0, 'hasalt': 0},
    'HYPNOTISM': {'phon': [64, 32, 56, 1, 44, 34, 22, 46, 1, 41, 8, 33], 'pos1': [0, -1, -1, -1], 'comppos1': 1, 'abbrev': 0, 'hasalt': 0},
    'ESTABLISH': {'phon': [64, 2, 40, 46, 56, 3, 45, 31, 57, 1, 42], 'pos1': [1, -1, -1, -1], 'comppos1': 2, 'abbrev': 0, 'hasalt': 0},
    'KGS.': {'phon': [64, 48, 56, 1, 31, 8, 49, 30, 3, 33, 41], 'pos1': [0, -1, -1, -1], 'comppos1': 1, 'abbrev': 1, 'hasalt': 0},
    'PRESUPPOSE': {'phon': [64, 44, 30, 0, 40, 8, 44, 56, 14, 41], 'pos1': [1, -1, -1, -1], 'comppos1': 2, 'abbrev': 0, 'hasalt': 0},
    'VANCOUVER': {'phon': [64, 37, 3, 34, 48, 56, 15, 37, 9], 'pos1': [0, -1, -1, -1], 'comppos1': 1, 'abbrev': 0, 'hasalt': 0},
    'HEXAGONAL': {'phon': [64, 32, 2, 48, 40, 56, 3, 49, 22, 34, 26], 'pos1': [2, -1, -1, -1], 'comppos1': 4, 'abbrev': 0, 'hasalt': 0},
    'CONCEAL': {'phon': [64, 48, 8, 34, 40, 56, 0, 31], 'pos1': [1, -1, -1, -1], 'comppos1': 2, 'abbrev': 0, 'hasalt': 0},
    'HONEST': {'phon': [64, 56, 4, 34, 22, 40, 46], 'pos1': [2, -1, -1, -1], 'comppos1': 4, 'abbrev': 0, 'hasalt': 0},
    'HART': {'phon': [64, 32, 56, 4, 30, 46], 'pos1': [0, -1, -1, -1], 'comppos1': 1, 'abbrev': 0, 'hasalt': 0},
    'DELIVERY': {'phon': [64, 47, 26, 56, 1, 37, 30, 0], 'pos1': [0, -1, -1, -1], 'comppos1': 1, 'abbrev': 0, 'hasalt': 0},
    'RECONNAISSANCE': {'phon': [64, 30, 22, 48, 56, 4, 34, 22, 41, 22, 34, 40], 'pos1': [0, -1, -1, -1], 'comppos1': 1, 'abbrev': 0, 'hasalt': 0},
    'ENORMOUS': {'phon': [64, 57, 1, 34, 56, 14, 30, 33, 57, 1, 40], 'pos1': [2, -1, -1, -1], 'comppos1': 4, 'abbrev': 0, 'hasalt': 0},
    'ROSS': {'phon': [64, 30, 56, 4, 40], 'pos1': [0, -1, -1, -1], 'comppos1': 1, 'abbrev': 0, 'hasalt': 0},
    'REPEAT': {'phon': [64, 30, 57, 1, 44, 56, 0, 46], 'pos1': [0, 1, -1, -1], 'comppos1': 3, 'abbrev': 0, 'hasalt': 0},
    'PROVERB': {'phon': [64, 44, 30, 56, 4, 37, 9, 45], 'pos1': [0, -1, -1, -1], 'comppos1': 1, 'abbrev': 0, 'hasalt': 0},
    'AVOID': {'phon': [64, 8, 37, 56, 12, 47], 'pos1': [1, -1, -1, -1], 'comppos1': 2, 'abbrev': 0, 'hasalt': 0},
    'PHILIPPINES': {'phon': [64, 36, 56, 1, 31, 8, 44, 0, 34, 41], 'pos1': [0, -1, -1, -1], 'comppos1': 1, 'abbrev': 0, 'hasalt': 0},
    'PRESIDENT': {'phon': [64, 44, 30, 56, 2, 41, 22, 47, 22, 34, 46], 'pos1': [0, -1, -1, -1], 'comppos1': 1, 'abbrev': 0, 'hasalt': 0},
    'CONSOLE': {'phon': [64, 48, 8, 34, 40, 56, 14, 31], 'pos1': [1, -1, -1, -1], 'comppos1': 2, 'abbrev': 0, 'hasalt': 1, 'altphon': [64, 48, 56, 4, 34, 40, 57, 14, 31], 'pos2': [0, -1, -1, -1], 'comppos2': 1},
    'MSECS': {'phon': [64, 33, 56, 1, 31, 8, 40, 2, 48, 27, 41], 'pos1': [0, -1, -1, -1], 'comppos1': 1, 'abbrev': 1, 'hasalt': 0},
    'DR.': {'phon': [64, 47, 56, 4, 48, 46, 9], 'pos1': [0, -1, -1, -1], 'comppos1': 1, 'abbrev': 1, 'hasalt': 0},
    'CONCLAVE': {'phon': [64, 48, 56, 4, 35, 48, 31, 10, 37], 'pos1': [0, -1, -1, -1], 'comppos1': 1, 'abbrev': 0, 'hasalt': 0},
    'LAWSUIT': {'phon': [64, 31, 56, 6, 40, 15, 46], 'pos1': [0, -1, -1, -1], 'comppos1': 1, 'abbrev': 0, 'hasalt': 0},
    'HYMNAL': {'phon': [64, 32, 56, 1, 33, 34, 26], 'pos1': [0, -1, -1, -1], 'comppos1': 1, 'abbrev': 0, 'hasalt': 0},
    'ENTRANCE': {'phon': [64, 1, 34, 46, 30, 56, 3, 34, 40], 'pos1': [1, -1, -1, -1], 'comppos1': 2, 'abbrev': 0, 'hasalt': 1, 'altphon': [64, 56, 2, 34, 46, 30, 22, 34, 40], 'pos2': [0, -1, -1, -1], 'comppos2': 1},
    'PROCEDURE': {'phon': [64, 44, 30, 8, 40, 56, 0, 51, 9], 'pos1': [0, -1, -1, -1], 'comppos1': 1, 'abbrev': 0, 'hasalt': 0},
    'RESIGN': {'phon': [64, 30, 22, 41, 56, 11, 34], 'pos1': [1, -1, -1, -1], 'comppos1': 2, 'abbrev': 0, 'hasalt': 0},
    'NUCLEAR': {'phon': [64, 34, 56, 15, 48, 31, 0, 9], 'pos1': [2, -1, -1, -1], 'comppos1': 4, 'abbrev': 0, 'hasalt': 0},
    'DETERRENT': {'phon': [64, 47, 22, 46, 56, 9, 8, 34, 46], 'pos1': [2, 0, -1, -1], 'comppos1': 5, 'abbrev': 0, 'hasalt': 0},
    'REPLY': {'phon': [64, 30, 22, 44, 31, 56, 11], 'pos1': [0, 1, -1, -1], 'comppos1': 3, 'abbrev': 0, 'hasalt': 0},
    'FULFIL': {'phon': [64, 36, 7, 31, 36, 56, 1, 31], 'pos1': [1, -1, -1, -1], 'comppos1': 2, 'abbrev': 0, 'hasalt': 0},
    'VIRGIL': {'phon': [64, 37, 56, 9, 51, 57, 1, 31], 'pos1': [0, -1, -1, -1], 'comppos1': 1, 'abbrev': 0, 'hasalt': 0},
    'SURVEY': {'phon': [64, 40, 56, 9, 37, 57, 10], 'pos1': [0, -1, -1, -1], 'comppos1': 1, 'abbrev': 0, 'hasalt': 1, 'altphon': [64, 40, 9, 37, 56, 10], 'pos2': [1, -1, -1, -1], 'comppos2': 2},
    'TBSP.': {'phon': [64, 46, 56, 10, 45, 26, 40, 44, 57, 15, 34, 41], 'pos1': [0, -1, -1, -1], 'comppos1': 1, 'abbrev': 1, 'hasalt': 0},
    'ARISE': {'phon': [64, 8, 30, 56, 11, 41], 'pos1': [1, -1, -1, -1], 'comppos1': 2, 'abbrev': 0, 'hasalt': 0},
    'DISCONNECT': {'phon': [64, 47, 22, 40, 48, 22, 34, 56, 2, 48, 46], 'pos1': [1, -1, -1, -1], 'comppos1': 2, 'abbrev': 0, 'hasalt': 0},
    'UNMANAGEABLE': {'phon': [64, 56, 5, 34, 33, 56, 3, 34, 22, 51, 8, 45, 26], 'pos1': [2, -1, -1, -1], 'comppos1': 4, 'abbrev': 0, 'hasalt': 0},
    'AMBIVALENT': {'phon': [64, 3, 33, 45, 56, 1, 37, 26, 8, 34, 46], 'pos1': [2, -1, -1, -1], 'comppos1': 4, 'abbrev': 0, 'hasalt': 0},
    'TUES.': {'phon': [64, 46, 56, 15, 41, 47, 10], 'pos1': [0, -1, -1, -1], 'comppos1': 1, 'abbrev': 1, 'hasalt': 0},
    'FORGIVEN': {'phon': [64, 36, 14, 30, 49, 56, 1, 37, 8, 34], 'pos1': [1, -1, -1, -1], 'comppos1': 2, 'abbrev': 0, 'hasalt': 0},
    'INCONSEQUENTIAL': {'phon': [64, 22, 35, 48, 4, 34, 40, 22, 48, 28, 56, 2, 34, 42, 26], 'pos1': [2, -1, -1, -1], 'comppos1': 4, 'abbrev': 0, 'hasalt': 0},
    'ENSIGN': {'phon': [64, 56, 2, 34, 40, 27], 'pos1': [0, -1, -1, -1], 'comppos1': 1, 'abbrev': 0, 'hasalt': 0},
    'ATTEND': {'phon': [64, 8, 46, 56, 2, 34, 47], 'pos1': [1, -1, -1, -1], 'comppos1': 2, 'abbrev': 0, 'hasalt': 0},
    'DEMOLISH': {'phon': [64, 47, 8, 33, 56, 4, 31, 22, 42], 'pos1': [1, -1, -1, -1], 'comppos1': 2, 'abbrev': 0, 'hasalt': 0},
    'OLSEN': {'phon': [64, 56, 14, 31, 40, 22, 34], 'pos1': [0, -1, -1, -1], 'comppos1': 1, 'abbrev': 0, 'hasalt': 0},
    'SEDATE': {'phon': [64, 40, 22, 47, 56, 10, 46], 'pos1': [2, 1, -1, -1], 'comppos1': 6, 'abbrev': 0, 'hasalt': 0},
    'FOREWARN': {'phon': [64, 36, 14, 30, 28, 56, 14, 30, 34], 'pos1': [1, -1, -1, -1], 'comppos1': 2, 'abbrev': 0, 'hasalt': 0},
    'DENOTATION': {'phon': [64, 47, 0, 34, 14, 46, 56, 10, 42, 22, 34], 'pos1': [0, -1, -1, -1], 'comppos1': 1, 'abbrev': 0, 'hasalt': 0},
    'QUIET': {'phon': [64, 48, 28, 56, 11, 57, 1, 46], 'pos1': [2, 1, -1, -1], 'comppos1': 6, 'abbrev': 0, 'hasalt': 0},
    'MATINEE': {'phon': [64, 33, 3, 46, 22, 34, 56, 10], 'pos1': [0, -1, -1, -1], 'comppos1': 1, 'abbrev': 0, 'hasalt': 0},
    'IMPROPER': {'phon': [64, 22, 33, 44, 30, 56, 4, 44, 9], 'pos1': [2, -1, -1, -1], 'comppos1': 4, 'abbrev': 0, 'hasalt': 0},
    'PROJECT': {'phon': [64, 44, 30, 56, 4, 51, 57, 2, 48, 46], 'pos1': [0, 1, -1, -1], 'comppos1': 3, 'abbrev': 0, 'hasalt': 0},
    'LAMBERT': {'phon': [64, 31, 56, 3, 33, 45, 9, 46], 'pos1': [0, -1, -1, -1], 'comppos1': 1, 'abbrev': 0, 'hasalt': 0},
    'CLANDESTINE': {'phon': [64, 48, 31, 3, 34, 47, 56, 2, 40, 46, 22, 34], 'pos1': [2, -1, -1, -1], 'comppos1': 4, 'abbrev': 0, 'hasalt': 0},
    'ENDOWMENT': {'phon': [64, 22, 34, 47, 56, 13, 33, 8, 34, 46], 'pos1': [0, -1, -1, -1], 'comppos1': 1, 'abbrev': 0, 'hasalt': 0},
    'DUAL': {'phon': [64, 47, 56, 15, 26], 'pos1': [2, -1, -1, -1], 'comppos1': 4, 'abbrev': 0, 'hasalt': 0},
    'SPONGY': {'phon': [64, 40, 44, 56, 5, 34, 51, 0], 'pos1': [2, -1, -1, -1], 'comppos1': 4, 'abbrev': 0, 'hasalt': 0},
    'OBVIATE': {'phon': [64, 56, 4, 45, 37, 0, 10, 46], 'pos1': [1, -1, -1, -1], 'comppos1': 2, 'abbrev': 0, 'hasalt': 0},
    'NAGEL': {'phon': [64, 34, 56, 10, 49, 7, 31], 'pos1': [0, -1, -1, -1], 'comppos1': 1, 'abbrev': 0, 'hasalt': 0},
    'EMPTY': {'phon': [64, 56, 2, 33, 44, 46, 57, 0], 'pos1': [2, 0, 1, -1], 'comppos1': 7, 'abbrev': 0, 'hasalt': 0},
    'STACY': {'phon': [64, 40, 46, 56, 10, 40, 0], 'pos1': [0, -1, -1, -1], 'comppos1': 1, 'abbrev': 0, 'hasalt': 0},
    'OVERTONE': {'phon': [64, 56, 14, 37, 9, 46, 14, 34], 'pos1': [0, -1, -1, -1], 'comppos1': 1, 'abbrev': 0, 'hasalt': 0},
    'INVOICE': {'phon': [64, 56, 1, 34, 37, 12, 40], 'pos1': [0, 1, -1, -1], 'comppos1': 3, 'abbrev': 0, 'hasalt': 0},
    'OVERSEAS': {'phon': [64, 14, 37, 9, 40, 56, 0, 41], 'pos1': [11, 2, -1, -1], 'comppos1': 2052, 'abbrev': 0, 'hasalt': 0},
    'INCIPIENT': {'phon': [64, 22, 34, 40, 56, 1, 44, 0, 8, 34, 46], 'pos1': [2, -1, -1, -1], 'comppos1': 4, 'abbrev': 0, 'hasalt': 0},
    'HER': {'phon': [64, 32, 57, 8, 30], 'pos1': [15, -1, -1, -1], 'comppos1': 32768, 'abbrev': 0, 'hasalt': 0},
    'DETERIORATION': {'phon': [64, 47, 22, 46, 57, 0, 30, 0, 9, 56, 10, 42, 22, 34], 'pos1': [0, -1, -1, -1], 'comppos1': 1, 'abbrev': 0, 'hasalt': 0},
    'CHLORINE': {'phon': [64, 48, 31, 14, 30, 56, 0, 34], 'pos1': [0, -1, -1, -1], 'comppos1': 1, 'abbrev': 0, 'hasalt': 0},
    'METEORIC': {'phon': [64, 33, 0, 46, 0, 56, 14, 30, 22, 48], 'pos1': [2, -1, -1, -1], 'comppos1': 4, 'abbrev': 0, 'hasalt': 0},
    'MARILYN': {'phon': [64, 33, 56, 3, 30, 22, 31, 1, 34], 'pos1': [0, -1, -1, -1], 'comppos1': 1, 'abbrev': 0, 'hasalt': 0},
    'BETWEEN': {'phon': [64, 45, 57, 8, 46, 28, 56, 0, 34], 'pos1': [11, 3, -1, -1], 'comppos1': 2056, 'abbrev': 0, 'hasalt': 0},
    'STYLEWRITER': {'phon': [64, 40, 46, 56, 11, 31, 57, 28, 30, 11, 53, 57, 8, 30], 'pos1': [0, -1, -1, -1], 'comppos1': 1, 'abbrev': 0, 'hasalt': 0},
    'ANYTHING': {'phon': [64, 56, 2, 34, 0, 38, 22, 35], 'pos1': [16, -1, -1, -1], 'comppos1': 65536, 'abbrev': 0, 'hasalt': 0},
    'WHOSO': {'phon': [64, 32, 56, 15, 40, 14], 'pos1': [7, -1, -1, -1], 'comppos1': 128, 'abbrev': 0, 'hasalt': 0},
    'BUREAU': {'phon': [64, 45, 29, 56, 9, 14], 'pos1': [0, -1, -1, -1], 'comppos1': 1, 'abbrev': 0, 'hasalt': 0},
    'COLLOID': {'phon': [64, 48, 56, 4, 31, 12, 47], 'pos1': [0, -1, -1, -1], 'comppos1': 1, 'abbrev': 0, 'hasalt': 0},
    'PREARRANGE': {'phon': [64, 44, 30, 0, 9, 56, 10, 34, 51], 'pos1': [1, -1, -1, -1], 'comppos1': 2, 'abbrev': 0, 'hasalt': 0},
    'COMPLACENCE': {'phon': [64, 48, 5, 33, 44, 31, 56, 10, 40, 27, 40], 'pos1': [0, -1, -1, -1], 'comppos1': 1, 'abbrev': 0, 'hasalt': 0},
    'TOMATO': {'phon': [64, 46, 8, 33, 56, 10, 46, 14], 'pos1': [0, -1, -1, -1], 'comppos1': 1, 'abbrev': 0, 'hasalt': 0},
    'RELIED': {'phon': [64, 30, 22, 31, 56, 11, 47], 'pos1': [1, -1, -1, -1], 'comppos1': 2, 'abbrev': 0, 'hasalt': 0},
    'INTERIM': {'phon': [64, 56, 1, 34, 46, 9, 8, 33], 'pos1': [2, 0, -1, -1], 'comppos1': 5, 'abbrev': 0, 'hasalt': 0},
    'PATRON': {'phon': [64, 44, 56, 10, 46, 30, 8, 34], 'pos1': [0, -1, -1, -1], 'comppos1': 1, 'abbrev': 0, 'hasalt': 0},
    'ASYLUM': {'phon': [64, 8, 40, 56, 11, 31, 8, 33], 'pos1': [0, -1, -1, -1], 'comppos1': 1, 'abbrev': 0, 'hasalt': 0},
    'IDOL': {'phon': [64, 56, 11, 47, 26], 'pos1': [0, -1, -1, -1], 'comppos1': 1, 'abbrev': 0, 'hasalt': 0},
    'I': {'phon': [64, 11], 'pos1': [25, -1, -1, -1], 'comppos1': 33554432, 'abbrev': 0, 'hasalt': 0},
    'PATRIARCHAL': {'phon': [64, 44, 10, 46, 30, 0, 56, 4, 30, 48, 26], 'pos1': [2, -1, -1, -1], 'comppos1': 4, 'abbrev': 0, 'hasalt': 0},
    'LEWIS': {'phon': [64, 31, 56, 15, 1, 40], 'pos1': [0, -1, -1, -1], 'comppos1': 1, 'abbrev': 0, 'hasalt': 0},
    'MORALE': {'phon': [64, 33, 9, 56, 3, 31], 'pos1': [0, -1, -1, -1], 'comppos1': 1, 'abbrev': 0, 'hasalt': 0},
    'ED': {'phon': [64, 56, 2, 47], 'pos1': [0, -1, -1, -1], 'comppos1': 1, 'abbrev': 0, 'hasalt': 0},
    'NORMALCY': {'phon': [64, 34, 56, 14, 30, 33, 26, 40, 0], 'pos1': [0, -1, -1, -1], 'comppos1': 1, 'abbrev': 0, 'hasalt': 0},
    'WHOMEVER': {'phon': [64, 32, 15, 33, 56, 2, 37, 9], 'pos1': [15, -1, -1, -1], 'comppos1': 32768, 'abbrev': 0, 'hasalt': 0},
    'ADIOS': {'phon': [64, 57, 4, 47, 0, 56, 14, 40], 'pos1': [6, -1, -1, -1], 'comppos1': 64, 'abbrev': 0, 'hasalt': 0},
    'RELIABLE': {'phon': [64, 30, 22, 31, 56, 11, 8, 45, 26], 'pos1': [2, -1, -1, -1], 'comppos1': 4, 'abbrev': 0, 'hasalt': 0},
    'SENSUOUS': {'phon': [64, 40, 56, 2, 34, 42, 15, 22, 40], 'pos1': [2, -1, -1, -1], 'comppos1': 4, 'abbrev': 0, 'hasalt': 0},
    'CADILLAC': {'phon': [64, 48, 56, 3, 47, 26, 3, 48], 'pos1': [0, -1, -1, -1], 'comppos1': 1, 'abbrev': 0, 'hasalt': 0},
    'REMINISCE': {'phon': [64, 30, 2, 33, 8, 34, 56, 1, 40], 'pos1': [1, -1, -1, -1], 'comppos1': 2, 'abbrev': 0, 'hasalt': 0},
    'MUSIC': {'phon': [64, 33, 56, 16, 41, 22, 48], 'pos1': [0, -1, -1, -1], 'comppos1': 1, 'abbrev': 0, 'hasalt': 0},
    'STEWART': {'phon': [64, 40, 46, 56, 15, 9, 46], 'pos1': [0, -1, -1, -1], 'comppos1': 1, 'abbrev': 0, 'hasalt': 0},
    'ENLIST': {'phon': [64, 22, 34, 31, 56, 1, 40, 46], 'pos1': [1, -1, -1, -1], 'comppos1': 2, 'abbrev': 0, 'hasalt': 0},
    'SURVIVAL': {'phon': [64, 40, 9, 37, 56, 11, 37, 26], 'pos1': [0, -1, -1, -1], 'comppos1': 1, 'abbrev': 0, 'hasalt': 0},
    'PRODIGAL': {'phon': [64, 44, 30, 56, 4, 47, 22, 49, 26], 'pos1': [2, 0, -1, -1], 'comppos1': 5, 'abbrev': 0, 'hasalt': 0},
    'GONZALES': {'phon': [64, 49, 56, 4, 34, 41, 56, 4, 31, 2, 41], 'pos1': [0, -1, -1, -1], 'comppos1': 1, 'abbrev': 0, 'hasalt': 0},
    'BUSINESSMAN': {'phon': [64, 45, 56, 1, 41, 34, 22, 40, 33, 8, 34], 'pos1': [0, -1, -1, -1], 'comppos1': 1, 'abbrev': 0, 'hasalt': 0},
    'EXTIRPATE': {'phon': [64, 56, 2, 48, 40, 46, 9, 44, 10, 46], 'pos1': [1, -1, -1, -1], 'comppos1': 2, 'abbrev': 0, 'hasalt': 0},
    'ISOSCELES': {'phon': [64, 11, 40, 56, 4, 40, 26, 0, 41], 'pos1': [2, -1, -1, -1], 'comppos1': 4, 'abbrev': 0, 'hasalt': 0},
    'COMMUNISTIC': {'phon': [64, 48, 4, 33, 16, 34, 56, 1, 40, 46, 22, 48], 'pos1': [2, -1, -1, -1], 'comppos1': 4, 'abbrev': 0, 'hasalt': 0},
    'KHZ': {'phon': [64, 48, 56, 1, 31, 8, 32, 9, 46, 40], 'pos1': [0, -1, -1, -1], 'comppos1': 1, 'abbrev': 1, 'hasalt': 0},
    'ABSCOUND': {'phon': [64, 3, 45, 40, 48, 56, 4, 34, 47], 'pos1': [1, -1, -1, -1], 'comppos1': 2, 'abbrev': 0, 'hasalt': 0},
    'SEQUESTER': {'phon': [64, 40, 22, 48, 28, 56, 2, 40, 46, 9], 'pos1': [1, -1, -1, -1], 'comppos1': 2, 'abbrev': 0, 'hasalt': 0},
    'SEMICONDUCTOR': {'phon': [64, 40, 56, 2, 33, 0, 48, 22, 34, 47, 57, 5, 48, 46, 9], 'pos1': [0, -1, -1, -1], 'comppos1': 1, 'abbrev': 0, 'hasalt': 0},
    'ENCLAVE': {'phon': [64, 56, 2, 35, 48, 31, 10, 37], 'pos1': [0, -1, -1, -1], 'comppos1': 1, 'abbrev': 0, 'hasalt': 0},
    'MATURE': {'phon': [64, 33, 8, 50, 56, 15, 30], 'pos1': [2, 1, -1, -1], 'comppos1': 6, 'abbrev': 0, 'hasalt': 0},
}


def _check_entry(word, expected):
    got = lookup(word)
    if expected is None:
        if got is not None:
            return f"expected not-found, got a match: {got}"
        return None

    if got is None:
        return "expected a match, got not-found"

    problems = []
    if got.phon_str != expected['phon']:
        problems.append(f"phon_str {got.phon_str} != {expected['phon']}")
    if got.pos_code1 != expected['pos1']:
        problems.append(f"pos_code1 {got.pos_code1} != {expected['pos1']}")
    if got.comp_pos1 != expected['comppos1']:
        problems.append(f"comp_pos1 {got.comp_pos1} != {expected['comppos1']}")
    if int(got.is_abbrev) != expected['abbrev']:
        problems.append(f"is_abbrev {got.is_abbrev} != {expected['abbrev']}")
    if int(got.has_alt) != expected['hasalt']:
        problems.append(f"has_alt {got.has_alt} != {expected['hasalt']}")
    if expected['hasalt']:
        if got.phon_hold != expected['altphon']:
            problems.append(f"phon_hold {got.phon_hold} != {expected['altphon']}")
        if got.pos_code2 != expected['pos2']:
            problems.append(f"pos_code2 {got.pos_code2} != {expected['pos2']}")
        if got.comp_pos2 != expected['comppos2']:
            problems.append(f"comp_pos2 {got.comp_pos2} != {expected['comppos2']}")
    return "; ".join(problems) if problems else None


def test_lexicon_matches_c_reference():
    assert _Word_ == 64, "PHONEME opcode table drifted; re-check REFERENCE"
    failures = []
    for word, expected in REFERENCE.items():
        problem = _check_entry(word, expected)
        if problem:
            failures.append((word, problem))
    if failures:
        for word, problem in failures:
            print(f"MISMATCH {word}: {problem}")
    assert not failures, f"{len(failures)}/{len(REFERENCE)} words mismatched"
    print(f"OK: {len(REFERENCE)}/{len(REFERENCE)} words matched bit-exact")


def test_not_found_words_signal_fallback_to_engtop():
    """Words with no dictionary entry must return None so the caller falls
    back to _engtop.engtop(), exactly as FrontEnd.c:2039 does."""
    for word in ("XYLOPHONE", "NOTAWORD123", "CROMULENT", "FROBNICATE"):
        assert lookup(word) is None, f"{word} unexpectedly found in dictionary"


def test_compound_noun_hint_flags_every_compound_word_in_the_dictionary():
    """CHICKENPOX .. TYPESET are the exhaustive set of compound-flagged
    entries in the whole ~7173-word English.lex (found by scanning the raw
    dictionary for the literal kDictComp/_pRise_ opcode)."""
    compound_words = [
        "CHICKENPOX", "DOWNGRADE", "DOWNTOWN", "ETHERNET", "FN",
        "HORSEPOWER", "MASTERCARD", "NOBODY", "PUSHBUTTON", "RACETRACK",
        "SNAPSHOT", "TYPESET",
    ]
    for word in compound_words:
        entry = lookup(word)
        assert entry is not None, word
        assert entry.is_compound, f"{word} should be flagged compound"


if __name__ == "__main__":
    test_lexicon_matches_c_reference()
    test_not_found_words_signal_fallback_to_engtop()
    test_compound_noun_hint_flags_every_compound_word_in_the_dictionary()
