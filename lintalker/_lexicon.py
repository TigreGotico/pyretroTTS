"""Python port of the `english_lex` binary pronunciation-exception dictionary.

C reference:
  - Binary format parser: `Linux.c:MakeDictPtrsAbsolute` (`lintalker-c/src/Linux.c:174-214`)
  - Lookup routine actually exercised by `English.lex`: `FrontEnd.c:SearchSingleDict`
    (`lintalker-c/src/FrontEnd.c:1150-1321`), reached through the dispatcher
    `SearchAllDicts` (`FrontEnd.c:1592-1608`), which only calls the OTHER
    variant, `SearchSingleDict_C` (`FrontEnd.c:1383-1586`, decompressing
    5-bit-packed text via `DecompressString`), when `dict->type ==
    kCompressDict`. `English.lex` ships with `type == kEncryptDict (1)`, so
    the compressed/`_C` path is dead code for this dictionary -- confirmed
    empirically by linking a standalone harness against the real compiled
    `FrontEnd.o`/`Linux.o` and diffing its output against this port (see
    `test/test_lexicon.py`).

    IMPORTANT: `SearchSingleDict` (the path that actually runs) copies
    phoneme bytes from the dictionary **verbatim** -- it does NOT strip the
    `kPrimeStress` flag bit and does NOT translate `kDictComp`/`kDictWord`
    bytes to `_Comp_`/`_Word_` (that translation only exists in
    `SearchSingleDict_C`, which never runs for this dictionary). Confirmed by
    the harness: e.g. `AARON` decodes with a literal `_Stress1_` opcode
    already in the stream (not a flagged byte), and `DOWNGRADE` decodes with
    a literal `_pRise_` opcode standing in for the compound-word marker
    (`kDictComp` is `#define`d as an alias for `_pRise_`, `mt4.h:759`) --
    the translation of that raw `_pRise_`/`_pFall_` opcode into `_Comp_`/
    `_Word_`, and the setting of `is_Compound_Noun`, is `Fill_Phon_Buf_2`'s
    job (`BackEnd.c:2469-2846`, not yet ported), not this dictionary decode's.
    This port therefore also passes phoneme bytes through unmodified, and
    exposes `LexEntry.is_compound` only as a convenience hint (see its
    docstring) -- it is not a substitute for Fill_Phon_Buf_2's own scan.
  - Dict/DictDisk struct layout: `mt4.h:790-824`
  - Constants: `mt4.h:220` (kMaxWordSize), `mt4.h:573` (HASH_ENTRIES),
    `mt4.h:759-761` (kDictComp/kDictWord/kPrimeStress), `mt4.h:767-768`
    (kAltFlag/kEndFlag), `mt4.h:773-775` (dict type codes), `mt4.h:22-53`
    (POS codes / kPOSmask / kUndefPOS / kAbriv)

Binary layout of `English.lex` (big-endian 32-bit "Mac" binary, `struct DictDisk`):

    offset  0: uint32  nextDict_off   (unused by this port; always ignored, same as C)
    offset  4: uint32  version
    offset  8: uint32  type            (0=kUserDict, 1=kEncryptDict, 2=kCompressDict;
                                         English.lex ships with type=1 -- despite the
                                         name kEncryptDict this is NOT the compressed
                                         5-bit-per-char format; SearchAllDicts routes
                                         type==kCompressDict(2) through the
                                         DecompressString path and everything else
                                         through the plain-ASCII path. English.lex's
                                         words are stored as plain uppercase ASCII
                                         Pascal strings, confirmed against the raw
                                         bytes: b'\\x05ABOUT...' etc.)
    offset 12: uint32  wordCount
    offset 16: uint32  hash[HASH_ENTRIES]   (HASH_ENTRIES = ord('Z')-ord('A')+2 = 27)
    offset 16+4*27=124: int16 POScodes[128][4]   (128*4*2 = 1024 bytes)
    offset 1148: uint32 words_off   (offset from start of buffer to word data --
                                      for English.lex this equals the end of the
                                      header, i.e. the header has no gap/padding)
    offset 1152: uint32 index_off   (offset from start of buffer to the index array)
    offset 1156: uint32 flags
    offset 1160: word data + index array (index array occupies the tail of the file,
                 index_off to index_off + 4*wordCount == len(raw))

Word-entry format at each index-array offset, matching the comment at
`FrontEnd.c:1227-1231` (`SearchSingleDict`, the function actually exercised
for `English.lex`):

    len(1 byte) | word chars (len bytes, uppercase ASCII) |
    phoneme byte* (until one has kEndFlag (0x80) set) |
    POSindex byte (that terminating byte, ANDed with ~kEndFlag) |
    [ kAltFlag (0xFF) | alt phoneme byte* (until kEndFlag) | alt POSindex byte ]

Each phoneme byte in the string is copied through unchanged
(`FrontEnd.c:1245`/`1288`) -- it is already a phoneme id from the
`mt4.h:288-315` enum, mirrored in `lintalker/_phonemes.py`. This includes
literal `_Stress1_`/`_Stress2_` opcodes (stress is NOT flag-bit-packed in
this dictionary) and literal `_pRise_`/`_pFall_` opcodes standing in for the
not-yet-ported compound/word-boundary markers (`kDictComp`/`kDictWord`,
`mt4.h:759-760`) -- see the module-level note above.

The decoded phoneme string is prefixed with a `_Word_` opcode
(`FrontEnd.c:1240`/`1283`) representing word-prominence, matching
`tok->phonStr` / `tok->phonHold` in the C struct.

The POSindex byte selects a row of up to 4 POS codes from
`dict.POScodes[POSindex]` (`FrontEnd.c:1508-1526`); `kUndefPOS` (-1) entries
are skipped. `kAbriv` (`kMaxPOS + kNoun` = 32) marks the word as an
abbreviation (`tok->isAbbriv`, `FrontEnd.c:1514-1515`/`1563-1564`).

This module does NOT implement `Morph.c` (prefix/suffix stripping) or the
letter-to-sound fallback (`_engtop.py` already covers that) -- only the direct
dictionary lookup, matching the scope of `SearchAllDicts`/`SearchSingleDict_C`
for the (uncompressed) `English.lex` dictionary. Wiring this into
`Fill_Phon_Buf_2` (`BackEnd.c:2469-2846`) is left to a future port.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import Optional

from ._data import english_lex_data
from ._phonemes import _Word_

# --- mt4.h constants -------------------------------------------------------

HASH_ENTRIES = ord('Z') - ord('A') + 2          # mt4.h:573 -> 27
kPOS_Slots = 128                                # mt4.h:752

kUserDict = 0                                   # mt4.h:775
kEncryptDict = 1                                # mt4.h:774
kCompressDict = 2                                # mt4.h:773

kAltFlag = 0xFF                                 # mt4.h:767
kEndFlag = 0x80                                  # mt4.h:768
kPrimeStress = 0x40                              # mt4.h:761

# kDictComp/kDictWord are aliases for phoneme-enum values (mt4.h:759-760);
# _pRise_ and _pFall_ are never used as literal phonemes inside a dict entry,
# so the byte values are repurposed as the "compound noun" / "word" markers.
from ._phonemes import _pRise_ as kDictComp      # mt4.h:759
from ._phonemes import _pFall_ as kDictWord      # mt4.h:760

# POS codes (mt4.h:22-53)
kNoun, kVerb, kAdj, kPrep, kVaux, kRVaux, kInterj, kConj = range(8)
kCConj, kInterr, kDet, kAdv, kInf, kGen, kRelPro, kPPron = range(8, 16)
kIPron, kRPron, kDPron, kArt, kQuant, kNeg, kSadv, kContr = range(16, 24)
kVPart, kSubjPron, kObjPron = range(24, 27)
kMaxPOS = 32
kPOSmask = kMaxPOS - 1
kUndefPOS = -1
kAbriv = kMaxPOS + kNoun                         # 32


@dataclass
class DictHeader:
    """Parsed `DictDisk` header (`mt4.h:790-805`, parsed by
    `Linux.c:MakeDictPtrsAbsolute`)."""

    version: int
    type: int
    word_count: int
    hash: tuple  # HASH_ENTRIES uint32 values
    pos_codes: list  # [kPOS_Slots][4] int16
    flags: int
    words_off: int
    index_off: int
    raw: bytes
    index: list = field(default_factory=list)  # absolute byte offsets, one per word


def parse_dict(raw: bytes) -> DictHeader:
    """Port of `Linux.c:MakeDictPtrsAbsolute` (`Linux.c:174-214`).

    Parses a big-endian `DictDisk` binary blob (`English.lex`'s exact bytes,
    or the `Symbols` dictionary in the C reference -- symbols aren't ported
    here) into a `DictHeader` with an absolute-offset index array, mirroring
    the C code's absolute-pointer conversion.
    """
    off = 0
    # nextDict_off (4 bytes) is read but never stored (out->nextDict = NULL
    # unconditionally in the C reference, Linux.c:187) -- skip it the same way.
    off += 4
    version, dtype, word_count = struct.unpack_from('>3I', raw, off)
    off += 12
    hash_vals = struct.unpack_from('>%dI' % HASH_ENTRIES, raw, off)
    off += 4 * HASH_ENTRIES
    pos_codes = []
    for _ in range(kPOS_Slots):
        pos_codes.append(list(struct.unpack_from('>4h', raw, off)))
        off += 8
    words_off, index_off, flags = struct.unpack_from('>3I', raw, off)
    off += 12

    index = list(struct.unpack_from('>%dI' % word_count, raw, index_off))

    return DictHeader(
        version=version,
        type=dtype,
        word_count=word_count,
        hash=hash_vals,
        pos_codes=pos_codes,
        flags=flags,
        words_off=words_off,
        index_off=index_off,
        raw=raw,
        index=index,
    )


@dataclass
class LexEntry:
    """Result of a successful dictionary lookup -- the fields a future
    `Fill_Phon_Buf_2` port needs from `FETokenPtr` after `SearchAllDicts`
    succeeds (`FrontEnd.c:1222-1315`).

    `phon_str`/`phon_hold` are raw opcode lists straight out of the
    dictionary (matching `tok->phonStr`/`tok->phonHold` byte-for-byte) --
    they may contain literal `_pRise_`/`_pFall_` opcodes standing in for
    not-yet-translated compound/word markers (see module docstring).
    `is_compound` is a convenience hint computed here (True if the literal
    `kDictComp` opcode -- i.e. `_pRise_` -- appears in `phon_str` or
    `phon_hold`), NOT a port of `Fill_Phon_Buf_2`'s `is_Compound_Noun`; a
    future port of that function should scan `phon_str` itself the same way
    the C code does rather than trust this flag as authoritative.
    """

    phon_str: list          # primary phoneme opcode list, `_Word_`-prefixed (tok->phonStr)
    pos_code1: list         # up to 4 POS codes, kUndefPOS-padded (tok->POScode1)
    comp_pos1: int          # composite POS bitmask (tok->compPOS1)
    is_abbrev: bool         # tok->isAbbriv
    is_compound: bool       # convenience hint -- see docstring above
    has_alt: bool           # tok->hasAlt
    phon_hold: Optional[list] = None    # alt-pronunciation phoneme opcodes (tok->phonHold)
    pos_code2: Optional[list] = None    # alt-pronunciation POS codes (tok->POScode2)
    comp_pos2: int = 0                  # tok->compPOS2


def _decode_phon_string(raw: bytes, pos: int):
    """Decode one phoneme-opcode run starting at `pos`, stopping at the first
    byte with `kEndFlag` set (that byte is the POSindex, not a phoneme).

    Mirrors `FrontEnd.c:1240-1247` (`SearchSingleDict`, the function actually
    exercised for `English.lex` -- see module docstring) and the identical
    alt-pronunciation copy at `1283-1290`. Phoneme bytes are copied through
    UNCHANGED: no `kPrimeStress` bit-stripping, no `kDictComp`/`kDictWord`
    substitution -- that logic lives only in the dead-for-this-dictionary
    `SearchSingleDict_C` (`FrontEnd.c:1489-1498`). Returns
    `(phon_opcodes, pos_index, pos_after_posindex_byte)`.
    """
    phon_out = [_Word_]  # word-prominence opcode prefix (FrontEnd.c:1240/1283)
    while not (raw[pos] & kEndFlag):
        phon_out.append(raw[pos])
        pos += 1
    pos_index = raw[pos] & ~kEndFlag
    pos += 1
    return phon_out, pos_index, pos


def _decode_pos_row(dict_header: DictHeader, pos_index: int):
    """Port of the POScode1/POScode2 fill loop (`FrontEnd.c:1254-1272` /
    `1292-1310`, `SearchSingleDict`). Returns `(codes, composite_bitmask,
    is_abbrev)`."""
    codes = []
    composite = 0
    is_abbrev = False
    row = dict_header.pos_codes[pos_index]
    for i in range(4):
        pos_val = row[i]
        if pos_val != kUndefPOS:
            if pos_val == kAbriv:
                is_abbrev = True
            code = pos_val & kPOSmask
            codes.append(code)
            composite |= (1 << code)
        else:
            codes.append(kUndefPOS)
    return codes, composite, is_abbrev


def search_single_dict(word: str, dict_header: DictHeader) -> Optional[LexEntry]:
    """Port of `FrontEnd.c:SearchSingleDict` (`FrontEnd.c:1150-1321`) -- the
    function actually exercised by `SearchAllDicts` for `English.lex`, since
    `dict.type == kEncryptDict (1)`, not `kCompressDict (2)` (confirmed
    against the raw bytes: words are stored as plain uppercase ASCII Pascal
    strings, e.g. `b'\\x05ABOUT'`, not 5-bit-packed). `SearchSingleDict_C`
    (`FrontEnd.c:1383-1586`, the `DecompressString`-based compressed-dict
    path) is dead code for this dictionary and is intentionally NOT ported
    here -- see the module docstring for how this was verified against a
    standalone build of the real C code.

    `word` must already be uppercase (as `EngToP`/`FrontEnd.c` callers do --
    see `test/test_engtop.py` for the same isolation convention).
    Returns `None` if the word is not in the dictionary (caller should fall
    back to `_engtop.engtop()`).
    """
    raw = dict_header.raw
    index = dict_header.index
    text = word.encode('ascii', errors='ignore')
    t_len = len(text)
    if t_len == 0:
        return None

    first = chr(text[0]) if t_len else ''
    if 'A' <= first <= 'Z':
        diff = ord(first) - ord('A')
        lo = dict_header.hash[diff]
        hi = dict_header.hash[diff + 1] - 1
    elif first < 'A':
        lo = 0
        hi = dict_header.hash[0] - 1
    else:
        lo = dict_header.hash[ord('Z') - ord('A')]
        hi = dict_header.word_count - 1

    while lo <= hi:
        test_key = (hi + lo) >> 1
        entry_off = index[test_key]

        d_len = raw[entry_off]
        dict_word = raw[entry_off + 1: entry_off + 1 + d_len]

        n = min(t_len, d_len)
        cmp_diff = 0
        for i in range(n):
            cmp_diff = text[i] - dict_word[i]
            if cmp_diff != 0:
                break
        if cmp_diff == 0:
            cmp_diff = t_len - d_len

        if cmp_diff > 0:
            lo = test_key + 1
        elif cmp_diff < 0:
            hi = test_key - 1
        else:
            # Match. Decode the entry (FrontEnd.c:1222-1315).
            pos = entry_off + 1 + d_len
            phon_str, pos_index, pos = _decode_phon_string(raw, pos)
            pos_code1, comp_pos1, abbrev1 = _decode_pos_row(dict_header, pos_index)
            is_abbrev = abbrev1
            is_compound = kDictComp in phon_str

            has_alt = raw[pos] == kAltFlag
            phon_hold = None
            pos_code2 = None
            comp_pos2 = 0
            if has_alt:
                pos += 1  # skip kAltFlag
                phon_hold, alt_pos_index, pos = _decode_phon_string(raw, pos)
                pos_code2, comp_pos2, abbrev2 = _decode_pos_row(dict_header, alt_pos_index)
                if abbrev2:
                    is_abbrev = True
                if kDictComp in phon_hold:
                    is_compound = True

            return LexEntry(
                phon_str=phon_str,
                pos_code1=pos_code1,
                comp_pos1=comp_pos1,
                is_abbrev=is_abbrev,
                is_compound=is_compound,
                has_alt=has_alt,
                phon_hold=phon_hold,
                pos_code2=pos_code2,
                comp_pos2=comp_pos2,
            )

    return None


# --- module-level singleton dictionary + public lookup API -----------------

_english_dict: Optional[DictHeader] = None


def _get_english_dict() -> DictHeader:
    global _english_dict
    if _english_dict is None:
        _english_dict = parse_dict(english_lex_data)
    return _english_dict


def lookup(word: str) -> Optional[LexEntry]:
    """Port of `SearchAllDicts(vv, text, tok, vv->Dict, true)`
    (`FrontEnd.c:1592-1608`) against the main `English.lex` dictionary only
    (app-specific user dictionaries and the `Symbols` dictionary --
    `FrontEnd.c:1679` etc -- are out of scope for this port).

    `word` should be the already-uppercased word text, same convention as
    `_engtop.engtop()`. Returns `None` if not found -- the caller should fall
    back to `_engtop.engtop()` for letter-to-sound rules, exactly as
    `FrontEnd.c:2039` does (`if (SearchAllDicts(...)) ... else DoMorph/EngToP`).
    """
    dict_header = _get_english_dict()
    return search_single_dict(word, dict_header)
