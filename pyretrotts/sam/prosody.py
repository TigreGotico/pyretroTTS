"""Phoneme parsing, stress, and duration rules (sam.c's Parser1/Parser2 stage).

Derived from vidarh/SAM, which is an opcode-by-opcode translation of SoftVoice,
Inc.'s 6502 program; NOT covered by this project's MIT licence; see NOTICE.

These functions turn a phoneme-mnemonic string into the timed phoneme buffers
render.py consumes: Parser1 tokenises mnemonics and stress digits, Parser2
rewrites them (dipthong glides, softened plosives, glottal stops), and the
length rules assign and adjust per-phoneme frame counts.
"""
from __future__ import annotations

from .phonemes import (
    END,
    FLAG_ALVEOLAR,
    FLAG_CONSONANT,
    FLAG_DIP_YX,
    FLAG_DIPTHONG,
    FLAG_FRICATIVE,
    FLAG_LIQUIC,
    FLAG_NASAL,
    FLAG_PLOSIVE,
    FLAG_PUNCT,
    FLAG_STOPCONS,
    FLAG_VOICED,
    FLAG_VOWEL,
    flags,
    pD,
    pR,
    pT,
)
from .tables import (
    PHONEME_LENGTH_TABLE,
    PHONEME_STRESSED_LENGTH_TABLE,
    SIGN_INPUT_TABLE1,
    SIGN_INPUT_TABLE2,
    STRESS_INPUT_TABLE,
)


class Buffers:
    """The three parallel phoneme buffers the pipeline threads through.

    Mirrors sam.c's global phonemeindex/stress/phonemeLength arrays. `input`
    holds the phoneme-mnemonic string Parser1 reads, terminated by 0x9B.
    """

    def __init__(self, input_bytes: bytes) -> None:
        self.input = bytearray(256)
        self.input[: len(input_bytes)] = input_bytes
        self.phonemeindex = bytearray(256)
        self.stress = bytearray(256)
        self.phonemeLength = bytearray(256)
        # sam.c Init(): guards against buffer overflow on long inputs.
        self.phonemeindex[255] = END


def insert(st: Buffers, position: int, phoneme: int, length: int, stress: int) -> None:
    for i in range(253, position - 1, -1):
        st.phonemeindex[i + 1] = st.phonemeindex[i]
        st.phonemeLength[i + 1] = st.phonemeLength[i]
        st.stress[i + 1] = st.stress[i]
    st.phonemeindex[position] = phoneme
    st.phonemeLength[position] = length
    st.stress[position] = stress


def _full_match(sign1: int, sign2: int) -> int:
    y = 0
    while True:
        a = SIGN_INPUT_TABLE1[y]
        if a == sign1:
            b = SIGN_INPUT_TABLE2[y]
            if b != ord("*") and b == sign2:
                return y
        y += 1
        if y == 81:
            return -1


def _wild_match(sign1: int) -> int:
    y = 0
    while True:
        if SIGN_INPUT_TABLE2[y] == ord("*") and SIGN_INPUT_TABLE1[y] == sign1:
            return y
        y += 1
        if y == 81:
            return -1


def parser1(st: Buffers) -> bool:
    """Tokenise the input mnemonics and stress digits into the buffers."""
    for i in range(256):
        st.stress[i] = 0
    position = 0
    srcpos = 0
    while True:
        sign1 = st.input[srcpos]
        if sign1 == 155:
            break
        srcpos += 1
        sign2 = st.input[srcpos]
        match = _full_match(sign1, sign2)
        if match != -1:
            st.phonemeindex[position] = match
            position += 1
            srcpos += 1
        else:
            match = _wild_match(sign1)
            if match != -1:
                st.phonemeindex[position] = match
                position += 1
            else:
                match = 8
                while sign1 != STRESS_INPUT_TABLE[match] and match > 0:
                    match -= 1
                if match == 0:
                    return False
                st.stress[position - 1] = match
    st.phonemeindex[position] = END
    return True


def _change(st, pos, val):
    st.phonemeindex[pos] = val


def _change_rule(st, position, phoneme):
    st.phonemeindex[position] = 13
    insert(st, position + 1, phoneme, 0, st.stress[position])


def _rule_alveolar_uw(st, x):
    if flags(st.phonemeindex[x - 1]) & FLAG_ALVEOLAR:
        st.phonemeindex[x] = 16


def _rule_ch(st, x):
    insert(st, x + 1, 43, 0, st.stress[x])


def _rule_j(st, x):
    insert(st, x + 1, 45, 0, st.stress[x])


def _rule_g(st, pos):
    index = st.phonemeindex[pos + 1]
    if index != 255 and (flags(index) & FLAG_DIP_YX) == 0:
        st.phonemeindex[pos] = 63


def _rule_dipthong(st, p, pf, pos):
    a = 21 if (pf & FLAG_DIP_YX) else 20
    insert(st, pos + 1, a, 0, st.stress[pos])
    if p == 53:
        _rule_alveolar_uw(st, pos)
    elif p == 42:
        _rule_ch(st, pos)
    elif p == 44:
        _rule_j(st, pos)


def parser2(st: Buffers) -> None:
    """Apply SAM's phoneme rewrite rules in place."""
    pos = 0
    while True:
        p = st.phonemeindex[pos]
        if p == END:
            break
        if p == 0:
            pos += 1
            continue

        pf = flags(p)
        # C reads phonemeindex[pos-1] with int arithmetic, so at pos 0 the index
        # is -1, not 255; the reference build reads a zero there.
        prior = st.phonemeindex[pos - 1] if pos else 0

        if pf & FLAG_DIPTHONG:
            _rule_dipthong(st, p, pf, pos)
        elif p == 78:
            _change_rule(st, pos, 24)
        elif p == 79:
            _change_rule(st, pos, 27)
        elif p == 80:
            _change_rule(st, pos, 28)
        elif (pf & FLAG_VOWEL) and st.stress[pos]:
            if not st.phonemeindex[pos + 1]:
                p = st.phonemeindex[pos + 2]
                if p != END and (flags(p) & FLAG_VOWEL) and st.stress[pos + 2]:
                    insert(st, pos + 2, 31, 0, 0)
        elif p == pR:
            if prior == pT:
                _change(st, pos - 1, 42)
            elif prior == pD:
                _change(st, pos - 1, 44)
            elif flags(prior) & FLAG_VOWEL:
                _change(st, pos, 18)
        elif p == 24 and (flags(prior) & FLAG_VOWEL):
            _change(st, pos, 19)
        elif prior == 60 and p == 32:
            _change(st, pos, 38)
        elif p == 60:
            _rule_g(st, pos)
        else:
            if p == 72:
                y = st.phonemeindex[pos + 1]
                if (flags(y) & FLAG_DIP_YX) == 0 or y == END:
                    _change(st, pos, 75)
                    p = 75
                    pf = flags(p)

            if (flags(p) & FLAG_PLOSIVE) and prior == 32:
                st.phonemeindex[pos] = p - 12
            elif not (pf & FLAG_PLOSIVE):
                p = st.phonemeindex[pos]
                if p == 53:
                    _rule_alveolar_uw(st, pos)
                elif p == 42:
                    _rule_ch(st, pos)
                elif p == 44:
                    _rule_j(st, pos)

            if p == 69 or p == 57:
                if flags(st.phonemeindex[pos - 1] if pos else 0) & FLAG_VOWEL:
                    p = st.phonemeindex[pos + 1]
                    if not p:
                        p = st.phonemeindex[pos + 2]
                    if (flags(p) & FLAG_VOWEL) and not st.stress[pos + 1]:
                        _change(st, pos, 30)
        pos += 1


def copy_stress(st: Buffers) -> None:
    """Carry a stressed vowel's stress back onto a preceding voiced phoneme."""
    pos = 0
    while True:
        y = st.phonemeindex[pos]
        if y == END:
            break
        if flags(y) & 64:
            y = st.phonemeindex[pos + 1]
            if y != END and (flags(y) & 128) != 0:
                y = st.stress[pos + 1]
                if y and not (y & 128):
                    st.stress[pos] = y + 1
        pos += 1


def set_phoneme_length(st: Buffers) -> None:
    """Assign each phoneme its base or stressed frame length."""
    position = 0
    while st.phonemeindex[position] != 255:
        a = st.stress[position]
        if a == 0 or (a & 128) != 0:
            st.phonemeLength[position] = PHONEME_LENGTH_TABLE[st.phonemeindex[position]]
        else:
            st.phonemeLength[position] = PHONEME_STRESSED_LENGTH_TABLE[st.phonemeindex[position]]
        position += 1


def code41240(st: Buffers) -> None:
    """Expand plosive/affricate stop consonants into their release phonemes."""
    pos = 0
    while st.phonemeindex[pos] != END:
        index = st.phonemeindex[pos]
        if flags(index) & FLAG_STOPCONS:
            if flags(index) & FLAG_PLOSIVE:
                x = pos
                while True:
                    x = (x + 1) & 0xFF
                    if st.phonemeindex[x]:
                        break
                a = st.phonemeindex[x]
                if a != END and ((flags(a) & 8) or a == 36 or a == 37):
                    pos += 1
                    continue
            insert(st, pos + 1, index + 1, PHONEME_LENGTH_TABLE[index + 1], st.stress[pos])
            insert(st, pos + 2, index + 2, PHONEME_LENGTH_TABLE[index + 2], st.stress[pos])
            pos += 2
        pos += 1


def _adjust_lengths_punctuation(st: Buffers) -> None:
    x = 0
    while True:
        index = st.phonemeindex[x]
        if index == END:
            break
        if (flags(index) & FLAG_PUNCT) == 0:
            x += 1
            continue
        loop_index = x
        while True:
            x = (x - 1) & 0xFF
            if x == 0 or (flags(st.phonemeindex[x]) & FLAG_VOWEL):
                break
        if x == 0:
            break
        while True:
            index = st.phonemeindex[x]
            if not (flags(index) & FLAG_FRICATIVE) or (flags(index) & FLAG_VOICED):
                a = st.phonemeLength[x]
                st.phonemeLength[x] = ((a >> 1) + a + 1) & 0xFF
            x += 1
            if x == loop_index:
                break
        x += 1


def adjust_lengths(st: Buffers) -> None:
    """Lengthen and shorten phonemes by their phonetic context."""
    _adjust_lengths_punctuation(st)

    loop_index = 0
    while True:
        index = st.phonemeindex[loop_index]
        if index == END:
            break
        x = loop_index

        if flags(index) & FLAG_VOWEL:
            index = st.phonemeindex[loop_index + 1]
            if not (flags(index) & FLAG_CONSONANT):
                if index in (18, 19):
                    index = st.phonemeindex[loop_index + 2]
                    if flags(index) & FLAG_CONSONANT:
                        st.phonemeLength[loop_index] = (st.phonemeLength[loop_index] - 1) & 0xFF
            else:
                flag = 65 if index == END else flags(index)
                if not (flag & FLAG_VOICED):
                    if flag & FLAG_PLOSIVE:
                        st.phonemeLength[loop_index] = (
                            st.phonemeLength[loop_index] - (st.phonemeLength[loop_index] >> 3)
                        ) & 0xFF
                else:
                    a = st.phonemeLength[loop_index]
                    st.phonemeLength[loop_index] = ((a >> 2) + a + 1) & 0xFF
        elif flags(index) & FLAG_NASAL:
            x = (x + 1) & 0xFF
            index = st.phonemeindex[x]
            if index != END and (flags(index) & FLAG_STOPCONS):
                st.phonemeLength[x] = 6
                st.phonemeLength[(x - 1) & 0xFF] = 5
        elif flags(index) & FLAG_STOPCONS:
            while True:
                x = (x + 1) & 0xFF
                index = st.phonemeindex[x]
                if index != 0:
                    break
            if index != END and (flags(index) & FLAG_STOPCONS):
                st.phonemeLength[x] = (st.phonemeLength[x] >> 1) + 1
                st.phonemeLength[loop_index] = (st.phonemeLength[loop_index] >> 1) + 1
                x = loop_index
        elif flags(index) & FLAG_LIQUIC:
            index = st.phonemeindex[(x - 1) & 0xFF]
            st.phonemeLength[x] = (st.phonemeLength[x] - 2) & 0xFF

        loop_index += 1


def insert_breath(st: Buffers) -> None:
    """Break long runs into clauses and insert glottal stops at the seams."""
    mem54 = 255
    length = 0
    pos = 0
    while True:
        index = st.phonemeindex[pos]
        if index == END:
            break
        length = (length + st.phonemeLength[pos]) & 0xFF
        if length < 232:
            if index == 254:
                pass
            elif not (flags(index) & FLAG_PUNCT):
                if index == 0:
                    mem54 = pos
            else:
                length = 0
                pos = (pos + 1) & 0xFF
                insert(st, pos, 254, 0, 0)
        else:
            # No breakpoint (space) was seen in this >=232-frame run. The
            # reference reciter never emits such spaceless runs, but malformed
            # phonetic input can; falling back to mem54 == 255 would jump past
            # the buffer's END sentinel and wrap to 0, looping forever. Break at
            # the current position instead so progress is always made.
            pos = pos if mem54 == 255 else mem54
            st.phonemeindex[pos] = 31
            st.phonemeLength[pos] = 4
            st.stress[pos] = 0
            length = 0
            pos = (pos + 1) & 0xFF
            insert(st, pos, 254, 0, 0)
        pos = (pos + 1) & 0xFF
