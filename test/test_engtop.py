"""
Smoke test for the EngToP letter-to-sound port (pylintalker._engtop).

This validates _engtop.engtop() against bit-exact output captured from the
real C EngToP() (EngToP.c), compiled standalone against Sounds.c's Rules[]
table and the KindTBL/*ruletab tables from Data.c (via a throwaway harness
built with `#define __SPEECHSAY__`, which is exactly what EngToP.c expects
for standalone use -- see EngToP.c's `#ifndef __SPEECHSAY__` guard).

There is no committed C harness for this (test_harness.c only exposes the
full FrontEnd+BackEnd pipeline, not EngToP in isolation, and EngToP.c has no
other callers besides FrontEnd.c, which isn't ported). The expected values
below were captured once by hand from such a standalone build and pinned
here; they are not regenerated at test time.

This only exercises the letter-to-sound *rule* path -- there is no
tokenizer here, so multi-word input, punctuation-bearing tokens, numbers,
and english_lex dictionary words are all out of scope (Morph.c/FrontEnd.c
are not ported).
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from pylintalker._engtop import engtop
from pylintalker._phonemes import _Word_

# word -> expected opcode list, captured from a standalone C EngToP() build.
REFERENCE = {
    "HELLO": [64, 32, 2, 31, 57, 14],
    "CAT": [64, 48, 56, 3, 46],
    "THE": [64, 39, 57, 5],
    "GOODBYE": [64, 49, 56, 7, 47, 45, 0],
    "TESTING": [64, 46, 56, 2, 40, 46, 57, 1, 35],
    "BYE": [64, 45, 56, 11],
    "APPLE": [64, 56, 3, 44, 57, 7, 31],
    "ORANGE": [64, 14, 30, 56, 10, 34, 51],
    "STRENGTH": [64, 40, 46, 30, 56, 2, 35, 48, 38],
    "PHONE": [64, 36, 56, 14, 34],
    "KNIGHT": [64, 34, 56, 11, 46],
    "PSYCHOLOGY": [64, 40, 56, 11, 48, 56, 4, 31, 8, 51, 57, 0],
    "XYLOPHONE": [64, 41, 56, 1, 31, 8, 36, 57, 14, 34],
    "QUEUE": [64, 48, 28, 0, 56, 15],
    "RHYTHM": [64, 30, 56, 1, 38, 33],
    "SCIENCE": [64, 40, 56, 11, 57, 1, 34, 40],
    "NATION": [64, 34, 56, 10, 42, 57, 1, 34],
    "PICTURE": [64, 44, 56, 1, 48, 42, 57, 8, 30],
    "ISLAND": [64, 56, 11, 31, 57, 1, 34, 47],
    "WEDNESDAY": [64, 28, 2, 47, 34, 2, 41, 47, 57, 10],
    "COUGH": [64, 48, 56, 4, 36],
    "ROUGH": [64, 30, 56, 5, 36],
    "THROUGH": [64, 38, 30, 56, 13],
    "NIGHT": [64, 34, 56, 11, 46],
    "LAUGH": [64, 31, 56, 3, 36],
    "BOX": [64, 45, 56, 4, 48, 40],
    "QUICK": [64, 48, 28, 56, 1, 48],
    "EXTRA": [64, 2, 48, 40, 46, 30, 57, 5],
    "CIRCLE": [64, 40, 56, 8, 30, 48, 57, 7, 31],
    "STATION": [64, 40, 46, 56, 10, 42, 57, 1, 34],
    "MACHINE": [64, 33, 56, 3, 50, 57, 1, 34],
    "SUGAR": [64, 40, 56, 15, 49, 57, 8, 30],
    "VISION": [64, 37, 56, 1, 43, 57, 1, 34],
    "MEASURE": [64, 33, 56, 2, 43, 57, 8, 30],
    "HONEST": [64, 14, 34, 57, 1, 40, 46],
    "QUESTION": [64, 48, 28, 56, 2, 40, 50, 57, 1, 34],
}


def test_engtop_matches_c_reference():
    assert _Word_ == 64, "PHONEME opcode table drifted; re-check REFERENCE"
    failures = []
    for word, expected in REFERENCE.items():
        got = engtop(word)
        if got != expected:
            failures.append((word, expected, got))
    if failures:
        for word, expected, got in failures:
            print(f"MISMATCH {word}: expected {expected}, got {got}")
    assert not failures, f"{len(failures)}/{len(REFERENCE)} words mismatched"
    print(f"OK: {len(REFERENCE)}/{len(REFERENCE)} words matched bit-exact")


if __name__ == "__main__":
    test_engtop_matches_c_reference()
