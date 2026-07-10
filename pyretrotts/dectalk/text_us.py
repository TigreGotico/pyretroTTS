"""DECtalk US text front end: word -> phoneme+stress -> `phclause` symbols.

Ties the ported layers together for the compiled US path: a word is looked up in
the main dictionary (`dictionary.py`, `ls_dict.c`); on a miss the letter-to-sound
rule engine (`lts_rules.py`, `ls_rule*.c`) pronounces it. Either way the result
is the same phoneme+stress code stream the C hands to `ls_util_send_phone`.

`single_word_symbols` wraps that stream in the sentence structure the
`cmd/`+`phsort` layer builds for a lone statement word spoken with no markup
(`[7680, 111, <font-shifted phonemes / raw prosody>, 116]`: a leading font
silence, the word marker, then the clause-final PERIOD), producing the
`symbols[]` array `phclause.speak_phonemes` consumes. This composes the whole
US text-to-speech path for a single out-of-dictionary or dictionary word.

Multi-word / multi-clause sentence framing (inter-word markers, comma/question
clause splitting, the word-reading and number/abbreviation front end) is the
`cmd/` effect and word-reading layer, which is not ported here.

Derived from the Fonix/Force DECtalk C source (`dectalk/dectalk`,
`src/dapi/src/lts/`, `src/dapi/src/cmd/`). FONIX Corporation declares that source
proprietary and confidential. This file is NOT covered by this project's MIT
licence. See NOTICE.
"""
from __future__ import annotations

from .dictionary import Dictionary
from .lts_rules import pronounce

# cmd/phsort framing for a lone statement word (PFUSA<<PSFONT == 7680; the word
# marker 111 and clause-final PERIOD 116 are l_com_ph.h prosody codes).
_FONT = 7680
_WORD_MARKER = 111
_PERIOD = 116


def word_to_codes(word: str, dictionary: Dictionary | None) -> tuple[list[int], str]:
    """Phoneme+stress send codes for `word`; ``"dict"`` hit or ``"rule"`` miss."""
    if dictionary is not None:
        hit = dictionary.lookup(word)
        if hit is not None:
            return hit, "dict"
    return list(pronounce(word).codes), "rule"


def single_word_symbols(codes: list[int]) -> tuple[int, ...]:
    """Wrap a send-code stream as the `symbols[]` for one lone statement word."""
    body = [(_FONT + c if c < 100 else c) for c in codes]
    return tuple([_FONT, _WORD_MARKER, *body, _PERIOD])


def word_to_pcm(voice: int, word: str, dictionary: Dictionary | None) -> bytes:
    """Full US text-to-speech for one lone word: text -> phonemes -> PCM."""
    from .phclause import Clause, speak_phonemes

    codes, _src = word_to_codes(word, dictionary)
    return speak_phonemes(voice, [Clause(single_word_symbols(codes))])
