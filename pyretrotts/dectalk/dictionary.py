"""DECtalk US main-dictionary load and lookup (`lts/ls_dict.c`, `loaddict.c`).

Derived from the Fonix/Force DECtalk C source (`dectalk/dectalk`,
`src/dapi/src/lts/ls_dict.c`, `loaddict.c`, `ls_dict.h`, `l_us_cha.c`). FONIX
Corporation declares that source proprietary and confidential; the compiled
dictionary `dtalk_us.dic` is FONIX data. This file, and any phonemes it returns
by reading that data, are NOT covered by this project's MIT licence. See NOTICE.

`dtalk_us.dic` is a flat, case-insensitively sorted array of records
(`loaddict.c:317-568`):

    header:  U32 entries, U32 data_bytes            (little-endian)
    index:   entries * U32 offsets into the data blob
    data:    per record: U32 fc, "graphemes\0phonemes\0"

The phoneme payload is one byte per phone: the US phoneme font offsets
(`l_us_ph.h`; 0=SIL, 1=IY, ... 56=DF) and the prosody markers >= 100
(`l_com_ph.h`; 103=S1 primary stress, ...). No letter-to-sound rules are needed
for a hit; the bytes are final phonemes.

Lookup ports `ls_dict_find_word` (`ls_dict.c:489`), `ls_dict_dlook`
(`ls_dict.c:832`), and `ls_dict_where_to_look` (`ls_dict.c:1057`): the
non-standard halving search that starts at `entries/2`, the same-direction
crawl, and the `ls_upper` case folding. Homograph selection (`ls_homo_homo`,
gated on `FC_HOMOGRAPH`) needs the part-of-speech stage and is NOT ported; a
homograph hit returns its base record's phonemes.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass

# ls_dict.h / ls_defs.h return codes.
_MISS = 0
_HIT = 1
_LOOK_HIGHER = 0xFFFF
_LOOK_LOWER = 0xFFFE

# ls_defs.h:658-659 form-class phrase bits, and the homograph flag.
FC_HOMOGRAPH = 0x00000400  # ls_defs.h fc_def.tab

# l_us_cha.c ls_upper.tab: fold a-z -> A-Z, identity elsewhere (ASCII path).
_LS_UPPER = bytes(
    (c - 0x20) if 0x61 <= c <= 0x7A else c for c in range(256)
)


def _is_upper(c: int) -> bool:
    return 0x41 <= c <= 0x5A


def _is_lower(c: int) -> bool:
    return 0x61 <= c <= 0x7A


@dataclass(frozen=True)
class _Entry:
    fc: int
    text: bytes  # "graphemes\0phonemes" (trailing NUL stripped by slicing)


class Dictionary:
    """The loaded `dtalk_us.dic`, searched exactly as `ls_dict.c` does."""

    def __init__(self, data: bytes) -> None:
        entries, data_bytes = struct.unpack_from("<II", data, 0)
        index_off = 8
        blob_off = index_off + entries * 4
        self._entries = entries
        self._offsets = struct.unpack_from(f"<{entries}I", data, index_off)
        self._blob = data[blob_off:blob_off + data_bytes]

    @classmethod
    def load(cls, path: str) -> Dictionary:
        with open(path, "rb") as f:
            return cls(f.read())

    def _record(self, index: int) -> _Entry:
        off = self._offsets[index]
        fc = struct.unpack_from("<I", self._blob, off)[0]
        text = self._blob[off + 4:]
        end = text.index(0, text.index(0) + 1)  # up to and incl. phon NUL
        return _Entry(fc=fc, text=text[:end])

    def _dlook(self, comp: bytes, index: int) -> tuple[int, int, _Entry | None]:
        """Port of `ls_dict_dlook`: returns (status, localoff, entry)."""
        limit = self._entries - 1
        if index < 0:
            return (_LOOK_HIGHER, 0, None)
        if index > limit:
            return (_LOOK_LOWER, 0, None)
        ent = self._record(index)
        text = ent.text
        i = 0
        while i < len(text) and text[i] != 0:
            ci = comp[i] if i < len(comp) else 0
            if ci == 0:
                return (_LOOK_LOWER, 0, None)
            ti = text[i]
            if ci == ti:
                i += 1
                continue
            if _is_lower(ti) and ci == _LS_UPPER[ti]:
                i += 1
                continue
            if index == 0:
                return (_LOOK_HIGHER, 0, None)
            if index == limit:
                return (_LOOK_LOWER, 0, None)
            return (self._where_to_look(comp, ent), 0, None)
        ci = comp[i] if i < len(comp) else 0
        if ci == 0:
            return (_HIT, i, ent)
        return (_LOOK_HIGHER, 0, None)

    def _where_to_look(self, comp: bytes, ent: _Entry) -> int:
        """Port of `ls_dict_where_to_look`."""
        text = ent.text
        i = 0
        pivot = 0
        while i < len(comp) and comp[i] != 0:
            ti = text[i] if i < len(text) else 0
            pivot = _LS_UPPER[ti]
            if _LS_UPPER[comp[i]] != pivot:
                break
            i += 1
        ci = comp[i] if i < len(comp) else 0
        ti = text[i] if i < len(text) else 0
        if ci == 0 and ti == 0:
            return _LOOK_HIGHER
        if _LS_UPPER[ci] > pivot:
            return _LOOK_HIGHER
        return _LOOK_LOWER

    def _find(self, comp: bytes) -> _Entry | None:
        """Port of `ls_dict_find_word`'s search (without phrase markers)."""
        limit = self._entries
        offset = limit >> 1
        base = offset
        limit -= 1
        stat = _MISS
        ent: _Entry | None = None
        while True:
            offset >>= 1
            stat, _lo, e = self._dlook(comp, base)
            if stat == _HIT:
                ent = e
                break
            if stat == _LOOK_HIGHER:
                base += offset
            else:
                base -= offset
            if offset == 0:
                break
        if stat != _HIT:
            if stat == _LOOK_HIGHER:
                while stat == _LOOK_HIGHER:
                    base += 1
                    stat, _lo, ent = self._dlook(comp, base)
                if stat != _HIT:
                    base += 1
                    stat, _lo, ent = self._dlook(comp, base)
            elif stat == _LOOK_LOWER:
                while stat == _LOOK_LOWER:
                    base -= 1
                    stat, _lo, ent = self._dlook(comp, base)
        if stat != _HIT or ent is None:
            return None
        # Capitalization / homograph-reverse probe (ls_dict.c:657-711).
        cap = _is_upper(comp[0]) and len(comp) > 1 and _is_lower(comp[1])
        t0 = ent.text[0]
        if (cap and _is_lower(t0)) or (not cap and _is_upper(t0)):
            new_base = base - 1 if cap else base + 1
            stat, _lo, e2 = self._dlook(comp, new_base)
            if stat == _HIT:
                ent = e2
            else:
                new_base = base + 1
                stat, _lo, e2 = self._dlook(comp, new_base)
                if stat == _HIT:
                    ent = e2
                else:
                    stat, _lo, ent = self._dlook(comp, base)
        return ent

    def lookup(self, word: str) -> list[int] | None:
        """Return the phoneme+stress code stream for `word`, or None on miss.

        `word` is matched against the graphemes; the returned codes are the raw
        payload bytes (phonemes < 57, prosody markers >= 100).
        """
        comp = word.encode("latin-1", "replace")
        if not comp:
            return None
        ent = self._find(comp)
        if ent is None:
            return None
        nul = ent.text.index(0)
        return list(ent.text[nul + 1:])
