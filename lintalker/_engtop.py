"""
English-to-phoneme rule engine: ASCII word -> phoneme opcode string.

Bit-for-bit port of EngToP.c (the NRL-style letter-to-sound rule interpreter).
This is the *only* text-to-phoneme path that is self-contained enough to port
without also porting Morph.c (tokenization/morphology, 2827 lines) or
FrontEnd.c (text normalization, punctuation, numbers, abbreviations, 2906
lines) or the `english_lex` exception-dictionary blob.

In the real engine, FrontEnd.c's `handle_word()` is the only caller of
EngToP(): it tokenizes raw text into words, looks each word up in
`english_lex` first, and only falls back to EngToP() (this module) for words
that are NOT in the dictionary. FrontEnd.c also pads/uppercases the word and
strips everything but letters/apostrophes/periods before calling EngToP.
None of that tokenization or dictionary lookup is implemented here.

So `engtop()` below can turn a single, already-isolated, all-caps English
word into a phoneme-opcode string exactly like the C engine does, but there
is no `text -> word list` stage yet: callers must supply pre-split words
themselves (see the smoke test in tests/test_engtop.py for exact usage).

Rule data consumed here (`Rules`, `KindTBL`, `dashruletab`, `atruletab`,
`lruletab`, `mruletab`, `zruletab`, `percentruletab`, `bruletab`) all live in
``_data.py`` and were ported from ``Sounds.c``/``Data.c`` verbatim.
"""
from __future__ import annotations

from ._consts import kEngToPPad
from ._data import (
    Rules, KindTBL, dashruletab, atruletab, lruletab, mruletab,
    zruletab, percentruletab, bruletab,
)
from ._phonemes import _Word_

# rule delimiter byte used throughout the rule tables (EngToP.c DELIMITER)
DELIMITER = 0xFF

# 'kind of char' bit flags (EngToP.c)
CONSON = 0x01
HISCON = 0x02   # sibilant consonant
UMODR = 0x04
VOICON = 0x08   # voiced consonant
VOWEL = 0x10
FRONT = 0x20    # front vowel
SPCHAR = 0x80   # special rule macro table

_HASH_SIZE = 26 * 2  # 26 little/big-endian-pair uint16 hash offsets

# hash[] = 26 big-endian uint16 offsets (one per letter A-Z) into rule[].
# (Rules[] is stored big-endian in Sounds.c; on Linux/x86 the reference
# engine byte-swaps it once at startup -- we just read it big-endian
# directly here instead of swapping in place.)
_hash = [
    (Rules[2 * i] << 8) | Rules[2 * i + 1]
    for i in range(26)
]
# rule[] = the rule bytes proper, addressed relative to the end of hash[].
_rule = Rules[_HASH_SIZE:]


class _EngToPState:
    """Stand-in for the fields of voiceVar that EngToP.c/dorule() touch.

    Only `e_direction` is mutated per call; everything else is static
    rule-table data shared across all calls (module-level `_rule`/`kind`/etc).
    """

    __slots__ = ("e_direction",)

    def __init__(self) -> None:
        self.e_direction = 1


def _kind(ch: int) -> int:
    if 0 <= ch < len(KindTBL):
        return KindTBL[ch]
    return 0


def find_consonant(g: _EngToPState, text: bytearray, i: int) -> "tuple[int, int] | None":
    """FindConsonant (EngToP.c). Returns (new_i, 0) on match, None on miss."""
    if _kind(text[i]) & CONSON:
        return i + g.e_direction
    if g.e_direction == -1:
        if text[i] == ord('U'):
            if text[i - 1] == ord('G') or text[i - 1] == ord('Q'):
                return i - 2
    else:  # e_direction == 1 -- unreachable in practice (per C comment)
        if text[i] == ord('Q') or text[i] == ord('G'):
            if text[i + 1] == ord('U'):
                return i + 2
    return None


def find_sibilant(g: _EngToPState, text: bytearray, i: int):
    """FindSibilant (EngToP.c)."""
    if _kind(text[i]) & HISCON:
        return i + g.e_direction
    if g.e_direction == 1:  # unreachable in practice (per C comment)
        if text[i] == ord('C') or text[i] == ord('S'):
            if text[i + 1] == ord('H'):
                return i + 2
    else:
        if text[i] == ord('H'):
            if text[i - 1] == ord('C') or text[i - 1] == ord('S'):
                return i - 2
    return None


def find_vowel(g: _EngToPState, text: bytearray, i: int):
    """FindVowel (EngToP.c)."""
    if _kind(text[i]) & VOWEL:
        return i + g.e_direction
    return None


def search_special(g: _EngToPState, text: bytearray, i: int, sprule: bytes):
    """search_special (EngToP.c). sprule entries are comma (44)-delimited,
    zero-terminated. Returns new_i on match, None on miss."""
    si = 0
    local_i = i
    while sprule[si] != 0:
        if text[local_i] != sprule[si]:
            while sprule[si] != 44:  # ','
                si += 1
            si += 1
            local_i = i
            continue
        local_i += g.e_direction
        si += 1
        if sprule[si] == 44:
            return local_i
    return None


def dorule(g: _EngToPState, text: bytearray, i_ptr: int, r_ptr: int):
    """dorule (EngToP.c). Returns new r_ptr (index into _rule) past the
    delimiter on match, or None on a missed match. Recursive, exactly as
    in C."""
    if _rule[r_ptr] == DELIMITER:
        return r_ptr + 1

    while _rule[r_ptr] != DELIMITER:
        rc = _rule[r_ptr]
        if _kind(rc) == SPCHAR:
            if rc == ord('*'):          # one or more consonants
                res = find_consonant(g, text, i_ptr)
                if res is None:
                    return None
                i_ptr = res
                while _kind(text[i_ptr]) & CONSON:
                    r_local = dorule(g, text, i_ptr, r_ptr + 1)
                    if r_local is not None:
                        return r_local
                    i_ptr += g.e_direction
            elif rc == ord('$'):        # one vowel
                res = find_vowel(g, text, i_ptr)
                if res is None:
                    return None
                i_ptr = res
            elif rc == ord('^'):        # one consonant
                res = find_consonant(g, text, i_ptr)
                if res is None:
                    return None
                i_ptr = res
            elif rc == ord(':'):        # 0 or more consonants
                res = find_consonant(g, text, i_ptr)
                if res is not None:
                    i_ptr = res
                while _kind(text[i_ptr]) & CONSON:
                    r_local = dorule(g, text, i_ptr, r_ptr + 1)
                    if r_local is not None:
                        return r_local
                    i_ptr += g.e_direction
            elif rc == ord('+'):        # front vowel
                if not (_kind(text[i_ptr]) & FRONT):
                    return None
                i_ptr += g.e_direction
            elif rc == ord('v'):        # 0 or more vowels
                res = find_vowel(g, text, i_ptr)
                if res is not None:
                    i_ptr = res
                while _kind(text[i_ptr]) & VOWEL:
                    r_local = dorule(g, text, i_ptr, r_ptr + 1)
                    if r_local is not None:
                        return r_local
                    i_ptr += g.e_direction
            elif rc == ord('l'):
                res = search_special(g, text, i_ptr, bytes(lruletab))
                if res is None:
                    return None
                i_ptr = res
            elif rc == ord('-'):
                res = search_special(g, text, i_ptr, bytes(dashruletab))
                if res is None:
                    return None
                i_ptr = res
            elif rc == ord('%'):
                res = search_special(g, text, i_ptr, bytes(percentruletab))
                if res is None:
                    return None
                i_ptr = res
            elif rc == ord('z'):
                res = search_special(g, text, i_ptr, bytes(zruletab))
                if res is None:
                    return None
                i_ptr = res
            elif rc == ord('b'):
                res = search_special(g, text, i_ptr, bytes(bruletab))
                if res is None:
                    return None
                i_ptr = res
            elif rc == ord('#'):        # one or more vowels
                res = find_vowel(g, text, i_ptr)
                if res is None:
                    return None
                i_ptr = res
                while _kind(text[i_ptr]) & VOWEL:
                    r_local = dorule(g, text, i_ptr, r_ptr + 1)
                    if r_local is not None:
                        return r_local
                    i_ptr += g.e_direction
            elif rc == ord('.'):        # voiced consonant
                if not (_kind(text[i_ptr]) & VOICON):
                    return None
                i_ptr += g.e_direction
            elif rc == ord('&'):        # sibilant consonant
                res = find_sibilant(g, text, i_ptr)
                if res is None:
                    return None
                i_ptr = res
            elif rc == ord('@'):
                res = search_special(g, text, i_ptr, bytes(atruletab))
                if res is None:
                    return None
                i_ptr = res
            elif rc == ord('m'):
                res = search_special(g, text, i_ptr, bytes(mruletab))
                if res is None:
                    return None
                i_ptr = res
            r_ptr += 1
        else:
            if text[i_ptr] != rc:
                return None
            r_ptr += 1
            i_ptr += g.e_direction
    return r_ptr + 1


def engtop(word: str) -> list[int]:
    """EngToP (EngToP.c): all-caps ASCII word -> list of phoneme opcodes.

    Unlike the C original this does not mutate caller buffers or deal with
    length-prefixed Pascal strings -- it takes a plain word and returns a
    plain list of ints. `'` and `.` are ignored, matching the C loop.
    Output is prefixed with `_Word_` (normal-stress word-prominence opcode),
    matching EngToP.c line 71. Rule phoneme bytes have their C `-1` bias
    removed, exactly as in `*phonStr = (*rule_ptr) - 1;`.
    """
    g = _EngToPState()
    word_u = word.upper()

    # text buffer layout mirrors EngToP.c: 1 sentinel space before the word
    # (inalpha[0] = ' '), the word itself, and kEngToPPad trailing spaces
    # (added upstream by FrontEnd.c before EngToP is called).
    text = bytearray(b' ' + word_u.encode('ascii', 'replace') + b' ' * kEngToPPad)

    phon: list[int] = [_Word_]
    input_ptr = 1  # index of the first real letter, past the sentinel space

    while text[input_ptr] != ord(' '):
        ch = text[input_ptr]
        if ch == ord("'") or ch == ord('.'):
            input_ptr += 1
            continue

        nextrule = _hash[ch - ord('A')]

        while True:
            scan_ptr = input_ptr
            rule_ptr = nextrule
            nextrule = rule_ptr + _rule[rule_ptr]  # location of next rule
            rule_ptr += 1  # past the length byte

            while True:
                scan_ptr += 1
                if text[scan_ptr] != _rule[rule_ptr]:
                    break
                rule_ptr += 1

            if _rule[rule_ptr] != DELIMITER:
                continue  # this rule's middle pattern didn't match
            rule_ptr += 1  # past the delimiter

            g.e_direction = -1
            r = dorule(g, text, input_ptr - 1, rule_ptr)
            if r is None:
                continue
            rule_ptr = r

            g.e_direction = 1
            r = dorule(g, text, scan_ptr, rule_ptr)
            if r is None:
                continue
            rule_ptr = r

            input_ptr = scan_ptr

            while _rule[rule_ptr] != DELIMITER:
                phon.append((_rule[rule_ptr] - 1) & 0xFF)
                rule_ptr += 1
            break

    return phon
