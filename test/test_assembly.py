"""Tests for `lintalker._assembly` -- Phase 1 of the `Collect_FE_Tokens`
(`BackEnd.c:3712-4157`) port.

VALIDATION STATUS (see `lintalker/_assembly.py`'s module docstring for the
full account): `test_harness.c` (`lintalker-c/test_harness.c:222-238`) only
ever prints `vv->phon_Buf_2`/`vv->phon_Ctrl_Buf_2` -- i.e. state AFTER
`Fill_Phon_Buf_2` has already run -- and `test/test_voices.py`'s
`parse_sentence_plan()` (lines 87-129) parses exactly those `S`/`P`/`N`
lines. There is no dump of `phon_Buf_1`/`phon_Ctrl_Buf_1` (what
`Collect_FE_Tokens` itself produces) anywhere in the compiled harness or
this repo's test tooling. This phase's output therefore CANNOT be
differentially tested against the C reference the way `test_voices.py`/
`test_lexicon.py`/`test_engtop.py` do for their respective stages.

What these tests DO check, with a real oracle:
  - `make_fe_word_token()` correctly reflects `_lexicon.lookup()`'s fields
    (verified bit-exact against the C reference by `test_lexicon.py`) for
    known dictionary words -- content-word POS classification, compound
    hint, abbreviation flag, alt-pronunciation fields.
  - The documented `pos_choice`/`is_content_word` fallback behavior for
    words `_lexicon.lookup()` misses (falls back to `_engtop.engtop()`).
  - `collect_fe_tokens()`'s sentence-level control flow (word count, stress
    counter, end-of-sentence punctuation detection, compound-noun flag
    reset at word/phrase boundaries) against hand-derived expectations from
    reading `BackEnd.c:3712-4157` directly -- these are NOT cross-checked
    against a live C run (no oracle exists yet; see above), so treat
    failures here as "diverged from this port's own prior behavior", not
    "diverged from the C reference".
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from lintalker._assembly import make_fe_word_token, collect_fe_tokens
from lintalker._consts import (
    kUndefPOS, kNoun, kArt, kPrimaryStress, kSecondaryStress,
    kEmphaticStress, kContent_Word, kWord_Start, kCompoundNoun,
    kTerm_Bound, kStressField,
)
from lintalker._phonemes import _Word_, _Period_, _Comma_, _Quest_, _Exclam_


# ---------------------------------------------------------------------------
# make_fe_word_token() -- per-word field mapping from _lexicon.lookup()
# ---------------------------------------------------------------------------

def test_dictionary_hit_carries_real_pos_and_content_word_flag():
    """THE is a dictionary hit with pos1=[19 (kArt), -1, -1, -1]
    (test_lexicon.py:59, bit-exact vs C). Articles are not in the
    content-word POS set (BackEnd.c:3971-3973), so is_content_word is False
    and pos_choice takes the documented placeholder value pos_code1[0]."""
    tok = make_fe_word_token("THE", None)
    assert tok.from_dictionary is True
    assert tok.pos_code1[0] == kArt
    assert tok.pos_choice == kArt
    assert tok.is_content_word is False
    assert tok.phon_str[0] == _Word_


def test_dictionary_hit_noun_is_content_word():
    """CHICKENPOX: pos1=[0 (kNoun), -1, -1, -1] (test_lexicon.py:82,
    bit-exact vs C) and is a compound-noun-flagged entry."""
    tok = make_fe_word_token("CHICKENPOX", None)
    assert tok.from_dictionary is True
    assert tok.pos_code1[0] == kNoun
    assert tok.pos_choice == kNoun
    assert tok.is_content_word is True
    assert tok.is_compound_hint is True


def test_dictionary_miss_falls_back_to_engtop_with_undef_pos():
    """CROMULENT has no dictionary entry (test_lexicon.py:359, confirmed
    None against the C reference). Per this phase's documented decision
    (mirroring FrontEnd.c:1917-1964's own kUndefPOS default), rule-fallback
    words always get pos_choice = kUndefPOS and are never content words."""
    tok = make_fe_word_token("CROMULENT", None)
    assert tok.from_dictionary is False
    assert tok.pos_choice == kUndefPOS
    assert tok.is_content_word is False
    assert all(p == kUndefPOS for p in tok.pos_code1)
    # engtop() fallback still produces a _Word_-prefixed phoneme string,
    # same shape as a dictionary hit.
    assert tok.phon_str[0] == _Word_
    assert len(tok.phon_str) > 1


def test_trailing_punct_maps_to_phrase_boundary():
    tok = make_fe_word_token("STOP", ".")
    assert tok.trailing_punct == "."
    from lintalker._consts import kBND_Decl
    assert tok.phrase_bnd == kBND_Decl

    tok2 = make_fe_word_token("STOP", None)
    from lintalker._consts import kBND_None
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
    from lintalker._phonemes import _Comp_
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
    all, the first vowel of the last word gets promoted to primary stress.
    A rule-fallback word (kUndefPOS, never content) generates only
    secondary-stress opcodes per BackEnd.c:3869-3877's demotion rule, so
    this path is exercised for any single unknown word."""
    sa = collect_fe_tokens("cromulent.")
    assert sa.stress_counter == 0  # CROMULENT is a dictionary miss -> demoted to secondary throughout
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


if __name__ == "__main__":
    import inspect
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
