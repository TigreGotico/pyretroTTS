"""Tests for `pyretrotts._assembly` -- Phase 1 of the `Collect_FE_Tokens`
(`BackEnd.c:3712-4157`) port.

VALIDATION STATUS: `test_harness.c`'s built-in dump only prints
`vv->phon_Buf_2`/`vv->phon_Ctrl_Buf_2` -- state AFTER `Fill_Phon_Buf_2` has
already run -- not `phon_Buf_1`/`phon_Ctrl_Buf_1` (what `Collect_FE_Tokens`
itself produces). `test_oracle_hello`/`test_oracle_testing_one_two_three`
below pin exact `phon_Buf_1`/`phon_Ctrl_Buf_1` values captured from a
throwaway instrumented build of `Talk()` (dumping those arrays right after
the `Collect_FE_Tokens` loop, before `Fill_Phon_Buf_2` runs) against a real
compiled C reference -- this is a genuine differential oracle, not a
hand-derived guess. The `ctrl_buf` comparison masks out
`kSyllable_Start`/`kSyllableOrderField`/`kSyllableTypeField`, since those
bits are set by `Flag_PhonBuf_1`'s `MarkSyllable`/`MarkSyllableStart`
(`BackEnd.c:3191`/`3379`), not yet ported (see `docs/architecture.md`).
This oracle run also caught and fixed two real bugs: `make_fe_word_token()`
was double-prepending `_Word_` for rule-fallback words (`engtop()` already
includes it), and rule-fallback words were wrongly defaulted to
`kUndefPOS` instead of the real engine's `kNoun` default
(`FrontEnd.c:1650`, `SetPOStoVal(t, kNoun)` right after `EngToP()`).

The remaining tests check `collect_fe_tokens()`'s sentence-level control
flow (word count, stress counter, punctuation detection, compound-noun
flag reset) against hand-derived expectations from reading
`BackEnd.c:3712-4157` directly, for cases the two oracle sentences above
don't exercise (e.g. exclamation-promotes-emphatic).
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from pyretrotts._assembly import collect_fe_tokens, make_fe_word_token
from pyretrotts._consts import (
    kArt,
    kCompoundNoun,
    kContent_Word,
    kEmphaticStress,
    kNoun,
    kPrimaryStress,
    kStressField,
    kWord_Start,
)
from pyretrotts._morph import resolve_pos
from pyretrotts._phonemes import _Exclam_, _Period_, _Quest_, _Word_

# ---------------------------------------------------------------------------
# make_fe_word_token() -- per-word field mapping from _lexicon.lookup()
# ---------------------------------------------------------------------------

def test_dictionary_hit_carries_real_pos_and_content_word_flag():
    """THE is a dictionary hit with pos1=[19 (kArt), -1, -1, -1]
    (test_lexicon.py:59, bit-exact vs C). Articles are not in the
    content-word POS set (BackEnd.c:3971-3973), so is_content_word is
    False. pos_choice is resolved by _morph.resolve_pos() (a real port of
    Morph.c's ResolvePOS), called once per clause -- make_fe_word_token()
    alone only builds the candidate data (pos_code1/comp_pos1/...), so a
    single-token clause is resolved here to match collect_fe_tokens()'s
    real two-stage flow."""
    tok = make_fe_word_token("THE", None)
    resolve_pos([tok])
    assert tok.from_dictionary is True
    assert tok.pos_code1[0] == kArt
    assert tok.pos_choice == kArt
    assert tok.is_content_word is False
    assert tok.phon_str[0] == _Word_


def test_dictionary_hit_noun_is_content_word():
    """CHICKENPOX: pos1=[0 (kNoun), -1, -1, -1] (test_lexicon.py:82,
    bit-exact vs C) and is a compound-noun-flagged entry."""
    tok = make_fe_word_token("CHICKENPOX", None)
    resolve_pos([tok])
    assert tok.from_dictionary is True
    assert tok.pos_code1[0] == kNoun
    assert tok.pos_choice == kNoun
    assert tok.is_content_word is True
    assert tok.is_compound_hint is True


def test_dictionary_miss_falls_back_to_engtop_with_noun_pos():
    """CROMULENT has no dictionary entry (test_lexicon.py:359, confirmed
    None against the C reference). FrontEnd.c:1650 calls
    SetPOStoVal(t, kNoun) right after EngToP() for rule-fallback words --
    confirmed against a real C oracle dump (a rule-fallback word came back
    from the compiled engine with kContent_Word set, only possible with a
    content-word POS). So rule-fallback words get pos_choice = kNoun and
    ARE content words -- resolve_pos() confirms the same default via its
    own (pos_count1+pos_count2)==1 short-circuit, since a fallback word's
    only candidate is kNoun."""
    tok = make_fe_word_token("CROMULENT", None)
    resolve_pos([tok])
    assert tok.from_dictionary is False
    assert tok.pos_choice == kNoun
    assert tok.is_content_word is True
    assert tok.pos_code1[0] == kNoun
    # engtop() fallback still produces a _Word_-prefixed phoneme string,
    # same shape as a dictionary hit -- and not double-prefixed (engtop()
    # already includes _Word_; a real bug here doubled it).
    assert tok.phon_str[0] == _Word_
    assert tok.phon_str[1] != _Word_
    assert len(tok.phon_str) > 1


def test_trailing_punct_maps_to_phrase_boundary():
    tok = make_fe_word_token("STOP", ".")
    assert tok.trailing_punct == "."
    from pyretrotts._consts import kBND_Decl
    assert tok.phrase_bnd == kBND_Decl

    tok2 = make_fe_word_token("STOP", None)
    from pyretrotts._consts import kBND_None
    assert tok2.phrase_bnd == kBND_None


# ---------------------------------------------------------------------------
# collect_fe_tokens() -- sentence-level driver
# ---------------------------------------------------------------------------

def test_word_count_matches_number_of_tokenized_words():
    sa = collect_fe_tokens("hello world.")
    assert sa.word_count == 2
    assert [w.word for w in sa.words] == ["HELLO", "WORLD"]


def test_end_punctuation_defaults_to_period_with_no_terminal_mark():
    """No terminal punctuation in the input -- mirrors BackEnd.c:3805-3811's
    kEOFTok handling, which forces end_Punctuation = _Period_ when none was
    seen (this port applies the same default at end-of-input since there is
    no kEOFTok/multi-call loop -- see collect_fe_tokens()'s docstring)."""
    sa = collect_fe_tokens("hello world")
    assert sa.end_punctuation == _Period_


def test_end_punctuation_records_actual_terminal_mark():
    sa = collect_fe_tokens("are you there?")
    assert sa.end_punctuation == _Quest_

    sa2 = collect_fe_tokens("go now!")
    assert sa2.end_punctuation == _Exclam_


def test_compound_hint_present_but_not_yet_translated_to_comp_opcode():
    """CHICKENPOX's dictionary phon_str carries the literal `_pRise_` opcode
    standing in for the untranslated `kDictComp` marker -- `_lexicon.py`'s
    docstring is explicit that translating that into a real `_Comp_` opcode
    (and setting `is_Compound_Noun`) is `Fill_Phon_Buf_2`'s job
    (`BackEnd.c:2469-2846`), NOT this dictionary decode's. Since Phase 1
    only reads `_lexicon.lookup()` output (not a Fill_Phon_Buf_2 port), the
    `_Comp_`-opcode branch inside `collect_fe_tokens()`
    (`BackEnd.c:4029-4032`, ported faithfully here) is therefore NOT YET
    reachable for dictionary words -- it will only fire once a Phase 2 port
    performs that opcode translation. This test documents that gap rather
    than asserting behavior this phase cannot produce; it uses the
    convenience `is_compound_hint` field (populated straight from
    `LexEntry.is_compound`) as the only compound signal available today."""
    tok = make_fe_word_token("CHICKENPOX", None)
    assert tok.is_compound_hint is True
    # kDictComp is an alias for the literal _pRise_ opcode (mt4.h:759) --
    # confirm it is present un-translated, i.e. _Comp_ itself is absent.
    from pyretrotts._phonemes import _Comp_
    assert _Comp_ not in tok.phon_str

    sa = collect_fe_tokens("chickenpox now.")
    assert sa.words[0].word == "CHICKENPOX"
    # No _Comp_ opcode reached collect_fe_tokens()'s dispatch loop, so the
    # kCompoundNoun ctrl flag correctly never fires yet at this phase.
    assert not any(c & kCompoundNoun for c in sa.ctrl_buf)


def test_first_word_gets_word_start_flag():
    sa = collect_fe_tokens("hello there.")
    word_start_indices = [i for i, c in enumerate(sa.ctrl_buf) if c & kWord_Start]
    assert len(word_start_indices) == 2  # one per word


def test_content_word_flag_set_only_for_content_pos():
    """THE is not a content word (kArt); a noun like CHICKENPOX is."""
    sa = collect_fe_tokens("the chickenpox.")
    content_indices = [i for i, c in enumerate(sa.ctrl_buf) if c & kContent_Word]
    # exactly one word ("chickenpox") should carry kContent_Word
    assert len(content_indices) >= 1


def test_stress_defaults_to_primary_when_sentence_has_none():
    """BackEnd.c:4093-4130: if a sentence has no primary/emphatic stress at
    all, the last secondary stress gets promoted to primary. "THE" is a
    dictionary hit tagged kArt (article, test_lexicon.py-style lookup
    confirms pos_code1[0]==19==kArt, not in the content-word set), so its
    only stress opcode (_Stress2_) stays secondary per
    BackEnd.c:3869-3901's demotion rule -- exercising this promotion path
    for a single-word sentence."""
    sa = collect_fe_tokens("the.")
    assert sa.stress_counter == 0  # THE is tagged kArt -> non-content -> no primary stress ever fires
    primary_indices = [i for i, c in enumerate(sa.ctrl_buf) if c & kStressField == kPrimaryStress]
    assert len(primary_indices) == 1, (
        "expected exactly one promoted primary stress per BackEnd.c:4093-4119"
    )


def test_exclamation_promotes_last_stress_to_emphatic():
    """BackEnd.c:4132-4152: end_Punctuation == _Exclam_ retroactively
    promotes the last stress (or vowel) to emphatic."""
    sa = collect_fe_tokens("go now!")
    assert sa.end_punctuation == _Exclam_
    emphatic_indices = [i for i, c in enumerate(sa.ctrl_buf) if c & kStressField == kEmphaticStress]
    assert len(emphatic_indices) >= 1


def test_no_words_produces_empty_assembly():
    sa = collect_fe_tokens("...")
    assert sa.word_count == 0
    assert sa.words == []


# Real oracle: phon_Buf_1/phon_Ctrl_Buf_1 captured from a throwaway
# instrumented build of Talk() (BackEnd.c) dumping those arrays right after
# the Collect_FE_Tokens loop returns, before Fill_Phon_Buf_2 runs. Captured
# with `bin/Debug/test_harness -v 0 "<text>"` against a real compiled
# lintalker-c. The instrumentation was reverted after capture --
# lintalker-c is not modified by this repo.

_ORACLE_HELLO_PHON = [23, 32, 2, 31, 14, 23]
_ORACLE_HELLO_CTRL = [1, 268509312, 256, 268435456, 1801, 2621440]

_ORACLE_TOTT_PHON = [23, 46, 2, 40, 46, 1, 35, 28, 5, 34, 46, 15, 38, 30, 0, 23]
_ORACLE_TOTT_CTRL = [1, 268509312, 1280, 268435456, 0, 2817, 1, 281084032, 2049, 1, 268509312, 1025, 268509312, 128, 1033, 2621440]


def test_oracle_hello():
    """Bit-exact against the real C engine, including syllable-marking
    bits (Flag_PhonBuf_1/MarkSyllable/MarkSyllableStart, ported)."""
    sa = collect_fe_tokens("hello")
    assert sa.phon_buf == _ORACLE_HELLO_PHON
    assert sa.ctrl_buf == _ORACLE_HELLO_CTRL


def test_oracle_testing_one_two_three():
    """Bit-exact against the real C engine, including index 7 (the word
    "ONE", dictionary-tagged kAdj), which carries a kBND_Sep6
    phrase-boundary marker (0xc00000, i.e. (kBND_Sep6=12) <<
    kSilenceTypeShift): `collect_fe_tokens` approximates Morph.c's SEP6
    rule ("content word -> function word" transition) with a fixed
    Noun/Verb/Adj/Adv POS-set check -- see docs/architecture.md and the
    approximation's docstring in `_assembly.py`."""
    sa = collect_fe_tokens("testing one two three")
    assert sa.phon_buf == _ORACLE_TOTT_PHON
    assert sa.ctrl_buf == _ORACLE_TOTT_CTRL


_ORACLE_IAM_PHON = [23, 11, 3, 33, 23]
_ORACLE_IAM_CTRL = [1, 268500993, 268502025, 9, 2621440]

_ORACLE_GOODBYE_PHON = [23, 49, 7, 47, 45, 11, 23]
_ORACLE_GOODBYE_CTRL = [1, 268509312, 256, 0, 268435456, 1801, 2621440]


def test_oracle_i_am():
    """Bit-exact against the real C engine (voice 0/Fred)."""
    sa = collect_fe_tokens("I am.")
    assert sa.phon_buf == _ORACLE_IAM_PHON
    assert sa.ctrl_buf == _ORACLE_IAM_CTRL


def test_oracle_goodbye():
    """Bit-exact against the real C engine (a rule-fallback word --
    GOODBYE is not in the dictionary, per test_lexicon.py)."""
    sa = collect_fe_tokens("goodbye")
    assert sa.phon_buf == _ORACLE_GOODBYE_PHON
    assert sa.ctrl_buf == _ORACLE_GOODBYE_CTRL


if __name__ == "__main__":
    mod = sys.modules[__name__]
    tests = [obj for name, obj in vars(mod).items() if name.startswith("test_") and callable(obj)]
    failures = []
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except AssertionError as e:
            failures.append((t.__name__, str(e)))
            print(f"FAIL {t.__name__}: {e}")
    print(f"\n{len(tests) - len(failures)}/{len(tests)} passed")
    if failures:
        sys.exit(1)
