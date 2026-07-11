"""DECtalk US inflectional-suffix stripping (`lts/ls_suff.c`).

When a word misses the main dictionary the C front end (`ls_dict_find_word`,
`ls_dict.c:450-458`) tries to strip an inflectional suffix before falling back to
the letter-to-sound rules: for words longer than two letters it calls
`ls_suff_suffix_find`, which walks the compiled `suffix_table`/`suffix_index`
trie (`suffix_data.py`). A rule matches the word's trailing letters, optionally
rewrites the tail (`-ies` -> `-y`, doubled final consonant, silent `-e`
restored), looks the resulting stem up in the main dictionary, and -- on a hit --
appends the suffix's own phonemes (`ls_suff_append_pron`), selected by a feature
test on the stem's last phoneme (`pfeat`): so `dogs` -> `dog` + `Z`, `cats` ->
`cat` + `S`, `buses` -> `bus` + `IX Z`.

This ports `ls_suff_suffix_find` and `ls_suff_append_pron` exactly, over the
verbatim `suffix_table`/`suffix_index` and the `pfeat` phoneme features. The
stem lookup re-enters the same `Dictionary`; a stem miss yields no result and the
caller falls through to the rule engine, as the C does.

Derived from the Fonix/Force DECtalk C source (`dectalk/dectalk`,
`src/dapi/src/lts/ls_suff.c`, `lts/ls_dict.c`, `lts/ls_dict.h`,
`lts/l_us_con.c`). FONIX Corporation declares that source proprietary and
confidential. This file is NOT covered by this project's MIT licence. See NOTICE.
"""
from __future__ import annotations

import struct

from .dictionary import Dictionary
from .lts_rules_data import PFEAT
from .suffix_data import SUFFIX_INDEX, SUFFIX_TABLE

# ls_suff.c:92-100 parse tokens.
_SF_END = 0xFF
_SF_STRIP = 0xFE
_SF_FC = 0xFD
_SF_REPLACE = 0xFC
_SF_REPLACE_WITH = 0xFB
_SF_REPLACE_END = 0xFA
_SF_RECURSE = 0xF9
_SF_PHONES = 0xF8
_SF_PHONES_END = 0xF7

_NO_RULE = 0xFFFF
# l_us_cha.c / ls_feat.tab: the vowel graphemes (CFEAT_vowel), lower case.
_VOWELS = frozenset("aeiouy")
# Phonemes are payload codes < 57; prosody/stress markers are >= 100.
_MAX_PHONE = 57


def _u32(off: int) -> int:
    return struct.unpack_from("<I", SUFFIX_TABLE, off)[0]


def _last_phone(codes: list[int]) -> int:
    for c in reversed(codes):
        if c < _MAX_PHONE:
            return c
    return 0


def _append_pron(pb: int, lphone: int) -> list[int]:
    """`ls_suff_append_pron`: the suffix phones for the stem's last phoneme.

    Scans the rule from `pb` for `SF_PHONES` fields; the first whose feature
    mask, ANDed with `pfeat[lphone]`, equals the field's target value supplies
    the appended phones (`ls_suff.c:337-362`).
    """
    feat = PFEAT[lphone] if 0 <= lphone < len(PFEAT) else 0
    while SUFFIX_TABLE[pb] != _SF_END:
        tok = SUFFIX_TABLE[pb]
        pb += 1
        if tok == _SF_PHONES:
            mask = SUFFIX_TABLE[pb]
            pb += 1
            target = SUFFIX_TABLE[pb]
            pb += 1
            if (mask & feat) == target:
                phones: list[int] = []
                while SUFFIX_TABLE[pb] != _SF_PHONES_END:
                    phones.append(SUFFIX_TABLE[pb])
                    pb += 1
                return phones
    return []


def _find(comp: list[str], str_end: int, str_vowel: int,
          dictionary: Dictionary) -> list[int] | None:
    last = comp[str_end]
    si = SUFFIX_INDEX[ord(last) - 0x61] if "a" <= last <= "z" \
        else SUFFIX_INDEX[26]
    while si != _NO_RULE:
        nxt = _u32(si)
        rule = si + 8
        # A chain-terminal offset can leave the rule body past the table's end;
        # the C reads the adjacent (never-matching) `.data` and follows `next`.
        if rule >= len(SUFFIX_TABLE):
            si = nxt
            continue
        bp = str_end
        sp = rule
        while SUFFIX_TABLE[sp] not in (_SF_STRIP, _SF_FC):
            if bp < 0 or comp[bp] != chr(SUFFIX_TABLE[sp]) or bp == str_vowel:
                break
            bp -= 1
            sp += 1
        if SUFFIX_TABLE[sp] == _SF_FC:
            return None
        if SUFFIX_TABLE[sp] == _SF_STRIP:
            sp += 1
            saved = list(comp)
            sbp = bp
            while SUFFIX_TABLE[sp] != _SF_END:
                tok = SUFFIX_TABLE[sp]
                sp += 1
                if tok != _SF_REPLACE:
                    continue
                while bp >= 0 and SUFFIX_TABLE[sp] == ord(comp[bp]):
                    sp += 1
                    bp -= 1
                if SUFFIX_TABLE[sp] == _SF_REPLACE_WITH:
                    sp += 1
                    np = bp + 1
                    while SUFFIX_TABLE[sp] != _SF_REPLACE_END:
                        comp[np] = chr(SUFFIX_TABLE[sp])
                        np += 1
                        sp += 1
                    comp[np] = "\0"
                    np += 1
                    sp += 1
                    codes: list[int] | None
                    if SUFFIX_TABLE[sp] == _SF_RECURSE:
                        sp += 1
                        codes = _find(comp, np - 1, str_vowel, dictionary)
                    else:
                        stem = "".join(comp[:comp.index("\0")])
                        codes = dictionary.lookup(stem)
                    if codes is not None:
                        return codes + _append_pron(sp, _last_phone(codes))
                    comp[:] = saved
                bp = sbp
            si = nxt
            continue
        si = nxt
    return None


def suffix_codes(word: str, dictionary: Dictionary) -> list[int] | None:
    """Phoneme+stress codes for an inflected `word`, or None on no strip.

    Reproduces the dictionary miss path (`ls_dict.c:450-458`): only words longer
    than two letters are tried, and only a stem found in the dictionary yields a
    result.
    """
    if dictionary is None or len(word) <= 2 or not word.isalpha():
        return None
    comp = list(word) + ["\0"]
    str_vowel = next((i for i, c in enumerate(word) if c in _VOWELS), None)
    if str_vowel is None:
        return None
    return _find(comp, len(word) - 1, str_vowel, dictionary)


__all__ = ["suffix_codes"]
