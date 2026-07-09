"""Port of `Collect_FE_Tokens` (`BackEnd.c:3712-4157`), the sentence-level
token-collection driver in the BackEnd.c assembly stage.

SCOPE (read before extending): this module ports `Collect_FE_Tokens` itself,
verified against a real C oracle (see "VALIDATION STATUS" below). It does
NOT port `Fill_Phon_Buf_2` (`BackEnd.c:2469-2846`), `Flag_PhonBuf_1`
(`BackEnd.c:3481-3519`, including `MarkSyllable`/`MarkSyllableStart`,
`BackEnd.c:3191`/`3379`), `Mod_Duration` (`BackEnd.c:1362`), or
`Pitch_RaiseAndFall` (`BackEnd.c:2127`/`2303`) -- see `docs/architecture.md`
"Known gaps" and the handoff notes at the bottom of this docstring.
(`Place_Stress_In_Consonant`, `BackEnd.c:3300`, does not need porting: its
only call site is commented out in the C reference itself, `BackEnd.c:3510`.)

WHY THIS IS AN ADAPTATION, NOT A LITERAL PORT
----------------------------------------------
The real `Collect_FE_Tokens` pulls tokens one at a time from
`vv->funcList->e_ParseNextWord_FUNC` (`BackEnd.c:3790`), which returns an
`OpTokRec` (`mt4.h`) populated by the real `FrontEnd.c` tokenizer + `Morph.c`
+ `english_lex` pipeline: `hasAlt`/`altChoice`, `phonHold`/`phonStr`,
`tokType` (kEOFTok/kECommandTok/kLiteralTok/kRawPhonemeTok/...), `add_BND`,
`phrasingBND`, `tokEmphasis` (kEmphasizeWord/kDeemphasizeWord), `POSchoice`
(set only by `Morph.c`'s `Set_POS`, `Morph.c:830-991`, itself fed by
`POScode1`/`POScode2`/`compPOS1`/`compPOS2` from the dictionary decode).

None of `Morph.c`, the embedded-command parser (`EmbeddedCmd.c`), or the real
`FrontEnd.c` token stream are ported in this repo (see
`docs/architecture.md`). Per this phase's task, `Collect_FE_Tokens` is
therefore adapted to consume:
  - `lintalker/_frontend.py:tokenize()` for the word/punctuation stream
    (stand-in for the `e_ParseNextWord_FUNC` token source), and
  - `lintalker/_lexicon.py:lookup()` for real dictionary fields
    (`pos_code1`/`pos_code2`/`comp_pos1`/`comp_pos2`/`is_compound`/
    `phon_str`/`phon_hold`/`is_abbrev`/`has_alt`) when the word is in
    `english_lex`, falling back to `_engtop.engtop()` for words the
    dictionary doesn't cover -- the same `None`-means-fall-back contract
    `FrontEnd.c:2039` uses.

FIELD-BY-FIELD MAPPING (C -> Python)
-------------------------------------
`Collect_FE_Tokens` builds *sentence-level* running state (stress indices,
compound-noun flag, content-word flag, word count, buffer indices into
`phon_Buf_1`) while walking tokens one phoneme-opcode at a time. That
buffer-index bookkeeping (`vv->phonBuf_1_In_Index`, `Store_Phon_In_PhonBuf_1`,
the yellow/red-zone overflow handling at `BackEnd.c:3777-3789`/`3844-3856`)
is driven by a live `voiceVarPtr` and the real opcode stream; this port
keeps that as `collect_fe_tokens()`'s *inner* per-opcode walk (see below),
but its *outer* per-word data source is the adapted token defined here:
`FEWordToken`, one per `_frontend.tokenize()` word, replacing `OpTokRec`.

    C field (OpTokRec / dict decode)         Python (`FEWordToken`)
    ---------------------------------------  ------------------------------
    tok->phonStr (dict hit)                  phon_str        (from LexEntry)
    tok->phonHold (dict hit, alt pron.)      phon_hold       (from LexEntry)
    tok->hasAlt / altChoice==1               has_alt         (LexEntry.has_alt;
                                              altChoice selection itself is
                                              not modeled -- no consumer of
                                              alt-pronunciation choice exists
                                              yet in this port)
    tok->POScode1 / POScode2                 pos_code1 / pos_code2
    tok->compPOS1 / compPOS2                 comp_pos1 / comp_pos2
    tok->isAbbriv                            is_abbrev
    tok->POSchoice (Set_POS, Morph.c,         pos_choice -- NOT a port of
      NOT ported)                            Set_POS. Documented stand-in:
                                              pos_code1[0] if the word hit
                                              the dictionary, else kNoun
                                              (confirmed real default for
                                              rule-fallback words -- see
                                              "POS-default" note below).
    tok->tokEmphasis                         word_emphasis -- always
                                              "none" (no emphasis-markup
                                              source is ported; see
                                              docs/architecture.md).
    tok->add_BND / phrasingBND                phrase_bnd -- derived only
                                              from _frontend.py's trailing
                                              `. , ! ?` punctuation
                                              (kBND_Decl/kBND_Pause/
                                              kBND_Quest/kBND_Emph); no
                                              other boundary source (verb
                                              phrase, paren, conjunction,
                                              etc.) is detected.
    tok->tokType == kEOFTok                  end of the `_frontend.tokenize()`
                                              list (no kECommandTok/
                                              kLiteralTok distinction --
                                              EmbeddedCmd.c is not ported)
    (dictionary miss -> engtop() fallback)    phon_str = [_Word_] + engtop(word);
                                              pos_code1 = [kUndefPOS]*4;
                                              is_compound = False

POS-DEFAULT-FOR-RULE-FALLBACK-WORDS
------------------------------------
For words `_lexicon.lookup()` misses (falls back to `_engtop.engtop()`),
`FrontEnd.c:1650` calls `SetPOStoVal(t, kNoun)` immediately after the
`EngToP()` call, then refines via `SetPOS_FromSuffix` (`Morph.c:1027`,
NOT ported here -- a suffix-based heuristic, e.g. "-LY" -> adverb). This
was confirmed by diffing this module's output against a real C oracle
(a throwaway instrumented `Talk()` dumping `phon_Buf_1`/`phon_Ctrl_Buf_1`
right after `Collect_FE_Tokens` returns): a rule-fallback word ("TESTING",
not in the dictionary) came back from the real engine with `kContent_Word`
set, which is only possible if its POS is one of the content-word set
(`BackEnd.c:3971-3980`) -- confirming `kNoun`, not `kUndefPOS`, is the real
default. `pos_choice = kNoun` for rule-fallback words here reflects that;
`SetPOS_FromSuffix`'s refinement is not applied, so suffix-driven
reclassification (e.g. an adverb ending in "-LY") is not yet modeled.

For dictionary HITS, `pos_choice` is set to `pos_code1[0]` (if not
`kUndefPOS`) as a documented placeholder for the real `Set_POS`
(`Morph.c:830-991`, which considers surrounding words' POS codes and
disambiguates via `compPOS1`/`compPOS2` bitmasks) -- it is NOT that
algorithm. A `Morph.c` port must replace this placeholder before
POS-gated stress placement can be considered fully validated for
dictionary words.

VALIDATION STATUS
-----------------
The standard `test_harness.c` only dumps `vv->phon_Buf_2`/`vv->phon_Ctrl_Buf_2`
-- state *after* `Fill_Phon_Buf_2` has run -- not `phon_Buf_1`/
`phon_Ctrl_Buf_1` (what `Collect_FE_Tokens` itself produces), so there's no
standing oracle for this stage in the committed test tooling. `test/test_assembly.py`'s
`test_oracle_hello`/`test_oracle_testing_one_two_three` close that gap: they
pin `phon_Buf_1`/`phon_Ctrl_Buf_1` values captured from a throwaway
instrumented build of `Talk()` (a temporary `fprintf` dump inserted right
after the `Collect_FE_Tokens` loop, reverted afterward -- `lintalker-c` is
not modified by this repo; see `docs/architecture.md` for how to
re-capture). That oracle run found and fixed two real bugs:
  - `make_fe_word_token()` was double-prepending `_Word_` for rule-fallback
    words (`engtop()` already includes it in its own output) -- this
    silently shifted every subsequent phoneme by one position for any word
    that missed the dictionary.
  - Rule-fallback words were defaulted to `pos_choice = kUndefPOS`; the
    real engine defaults them to `kNoun` (`FrontEnd.c:1650`,
    `SetPOStoVal(t, kNoun)` right after `EngToP()`). The `kUndefPOS`
    assumption came from an earlier reading of `FrontEnd.c` that missed
    this call site -- confirmed wrong once a rule-fallback word came back
    from the real engine with `kContent_Word` set, which is only possible
    with a content-word POS.

After both fixes, `collect_fe_tokens()`'s `phon_buf`/`ctrl_buf` match the C
oracle exactly except for: (a) `kSyllable_Start`/`kSyllableOrderField`/
`kSyllableTypeField` bits, set by the unported `Flag_PhonBuf_1` (called
from *inside* `Collect_FE_Tokens`, `BackEnd.c:4154` -- not a separate later
stage, correcting an earlier assumption that placed it in a later phase),
and (b) one narrow phrase-boundary gap (a `kBND_Sep6` marker on certain
dictionary-tagged words like "ONE" that `_frontend.py`'s
punctuation-only boundary detection doesn't produce). Both are documented,
narrow, and don't affect phoneme identity -- see `test_oracle_*`'s masks
and `docs/architecture.md`.

HANDOFF -- what `Fill_Phon_Buf_2` must consume next
----------------------------------------------------
  1. Per-word fields this module produces: `phon_str` (opcode list,
     `_Word_`-prefixed), `phon_hold` (alt pronunciation, if any),
     `pos_choice` (a documented placeholder for the real `Set_POS`
     disambiguation algorithm for dictionary hits -- see "POS-DEFAULT"
     above), `is_compound` (raw dictionary hint, NOT `is_Compound_Noun` --
     still needs a scan for the literal `_Comp_`/`kDictComp` opcode per
     `BackEnd.c:4029-4032`), `phrase_bnd`, `is_abbrev`, `has_alt`.
  2. Sentence-level running state: `SentenceAssembly.phon_buf`/`ctrl_buf`
     (the `phon_Buf_1`/`phon_Ctrl_Buf_1` stand-in, already syllable-bit-free
     until `Flag_PhonBuf_1` is ported), `word_count`, `stress_counter`,
     `end_punctuation`, `last_word_index`, `last_stress_1/2_index`,
     `last_vowel_index`.
  3. `Flag_PhonBuf_1`/`MarkSyllable`/`MarkSyllableStart` should be ported
     before or alongside `Fill_Phon_Buf_2`, since the latter's R-coloring,
     glottal, and t-flap rules branch on syllable-boundary bits
     (`BackEnd.c:2650`, `2685`, `2757`).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from ._consts import (
    kUndefPOS, kNoun, kVerb, kAdj, kAdv, kInterr, kInterj, kVPart, kQuant,
    kIPron, kRPron,
    kPrimaryStress, kSecondaryStress, kEmphaticStress, kStressField,
    kContent_Word, kWord_Start, kWord_Initial_Consonant, kCompoundNoun,
    kTerm_Bound, kPrep_Start, kVerb_Start, kSilenceTypeShift,
    kBND_Pause, kBND_Decl, kBND_Quest, kBND_Emph, kBND_None,
)
from ._phonemes import (
    _SIL_, _Word_, _Period_, _Comma_, _Quest_, _Exclam_, _Comp_, _Prep_,
    _Verb_,
)
from ._frontend import tokenize
from ._lexicon import lookup, LexEntry
from ._engtop import engtop

# BackEnd.c:3971-3973 -- the POS set that marks a word a "content word"
# (`kContent_Word`, gates primary-vs-secondary stress at 3869-3877).
_CONTENT_POS = {
    kNoun, kVerb, kAdj, kAdv, kInterr, kInterj, kVPart, kQuant, kIPron, kRPron,
}

# FrontEnd.c:2114-2159 -- trailing punctuation -> phoneme opcode and phrase
# boundary type. `_frontend.py:tokenize()` only recognizes these four marks;
# this dict mirrors that limitation exactly (see module docstring: no
# kBND_Paren_L/R, kBND_Sep1-7, conjunction/preposition boundaries).
_PUNCT_TO_PHON = {
    '.': _Period_,
    ',': _Comma_,
    '!': _Exclam_,
    '?': _Quest_,
}
_PUNCT_TO_BND = {
    '.': kBND_Decl,
    ',': kBND_Pause,
    '!': kBND_Emph,
    '?': kBND_Quest,
}


@dataclass
class FEWordToken:
    """Per-word state `Collect_FE_Tokens` consumes at its `_Word_` opcode
    case (`BackEnd.c:3903-3982`), adapted to `_frontend.py`/`_lexicon.py`
    per this phase's scope. See module docstring for the full C->Python
    field mapping and the documented defaults used when a field has no
    ported C source.
    """

    word: str                          # uppercased word text
    phon_str: list                     # _Word_-prefixed opcode list (dict hit or engtop() fallback)
    from_dictionary: bool              # True if _lexicon.lookup() hit, False if engtop() fallback
    pos_code1: list                    # up to 4 POS codes; [kUndefPOS]*4 for fallback words
    comp_pos1: int = 0                 # composite POS bitmask; 0 for fallback words
    is_abbrev: bool = False
    is_compound_hint: bool = False     # LexEntry.is_compound raw hint -- NOT is_Compound_Noun (see docstring)
    has_alt: bool = False
    phon_hold: Optional[list] = None
    pos_code2: Optional[list] = None
    comp_pos2: int = 0
    pos_choice: int = kUndefPOS        # documented placeholder for Set_POS (Morph.c, unported) -- see docstring
    is_content_word: bool = False      # BackEnd.c:3971-3980
    word_emphasis: str = "none"        # documented default: no emphasis-markup source ported
    trailing_punct: Optional[str] = None   # one of '.', ',', '!', '?', or None
    phrase_bnd: int = kBND_None        # kBND_Decl/Pause/Quest/Emph from trailing_punct, else kBND_None


def make_fe_word_token(word: str, punct: Optional[str]) -> FEWordToken:
    """Build one `FEWordToken` for `word` (already uppercased by
    `_frontend.tokenize()`), consulting `_lexicon.lookup()` first and
    falling back to `_engtop.engtop()` -- the same dictionary-then-rules
    order `FrontEnd.c:2039` uses.
    """
    entry: Optional[LexEntry] = lookup(word)

    if entry is not None:
        tok = FEWordToken(
            word=word,
            phon_str=list(entry.phon_str),
            from_dictionary=True,
            pos_code1=list(entry.pos_code1),
            comp_pos1=entry.comp_pos1,
            is_abbrev=entry.is_abbrev,
            is_compound_hint=entry.is_compound,
            has_alt=entry.has_alt,
            phon_hold=list(entry.phon_hold) if entry.phon_hold is not None else None,
            pos_code2=list(entry.pos_code2) if entry.pos_code2 is not None else None,
            comp_pos2=entry.comp_pos2,
        )
        # Documented placeholder for Set_POS (Morph.c:830-991, unported):
        # take the first non-undefined POS code. This is NOT the real
        # disambiguation algorithm -- see module docstring.
        first_pos = tok.pos_code1[0] if tok.pos_code1 else kUndefPOS
        tok.pos_choice = first_pos if first_pos != kUndefPOS else kUndefPOS
    else:
        # No dictionary entry -> _engtop.engtop() rule-engine fallback.
        # FrontEnd.c:1650 calls SetPOStoVal(t, kNoun) right after EngToP(),
        # then SetPOS_FromSuffix (Morph.c:1027, not ported -- see module
        # docstring) refines it. pos_choice = kNoun here, confirmed against
        # a real C oracle dump (see "POS-DEFAULT-FOR-RULE-FALLBACK-WORDS").
        tok = FEWordToken(
            word=word,
            # engtop() already prefixes its output with _Word_ -- do not
            # prepend it again here (that was a genuine bug: it produced
            # phon_str=[_Word_, _Word_, ...], corrupting every rule-fallback
            # word's opcode stream by one and shifting all subsequent
            # phonemes, confirmed against a real C oracle dump).
            phon_str=list(engtop(word)),
            from_dictionary=False,
            pos_code1=[kNoun, kUndefPOS, kUndefPOS, kUndefPOS],
            comp_pos1=0,
            is_abbrev=False,
            is_compound_hint=False,
            has_alt=False,
            pos_choice=kNoun,
        )

    tok.is_content_word = tok.pos_choice in _CONTENT_POS
    tok.trailing_punct = punct
    tok.phrase_bnd = _PUNCT_TO_BND.get(punct, kBND_None) if punct else kBND_None
    return tok


@dataclass
class SentenceAssembly:
    """Sentence-level running state `Collect_FE_Tokens` accumulates while
    walking tokens (`BackEnd.c:3717-3754` locals, promoted to a return
    value here since there is no live `voiceVarPtr` buffer to write into
    for this adapted, harness-unvalidated phase -- see module docstring).
    """

    phon_buf: list = field(default_factory=lambda: [_SIL_])
    ctrl_buf: list = field(default_factory=lambda: [0])
    word_count: int = 0
    stress_counter: int = 0
    end_punctuation: int = 0
    last_word_index: int = 0
    last_stress_1_index: Optional[int] = None
    last_stress_2_index: Optional[int] = None
    last_vowel_index: Optional[int] = None
    is_compound_noun: bool = False
    words: list = field(default_factory=list)   # list[FEWordToken], in order


def collect_fe_tokens(text: str) -> SentenceAssembly:
    """Adapted port of `Collect_FE_Tokens` (`BackEnd.c:3712-4157`).

    Walks `_frontend.tokenize(text)` word-by-word (stand-in for the real
    `e_ParseNextWord_FUNC` token source -- see module docstring), applying
    the SAME per-opcode control-flow `Collect_FE_Tokens` uses:
      - `_Stress1_`/`_Stress2_`/`_EmphStress_`: primary/secondary/emphatic
        stress classification gated on `is_Compound_Noun` and
        `is_content_word`, exactly mirroring `BackEnd.c:3869-3901`. Like the
        C code, these opcodes flag the CURRENT (not-yet-written) buffer slot
        -- the stress opcode always precedes the phoneme it modifies in the
        opcode stream -- and do not themselves consume a buffer slot.
      - `_Word_`: word-boundary bookkeeping, content-word POS
        classification, deferred emphasis-stress promotion, mirroring
        `BackEnd.c:3903-3982` (minus the `WordCB` callback machinery,
        which depends on the unported literal-token/raw-phoneme-token
        buffer offsets).
      - `_Prep_`/`_Verb_`/`_Comp_`: flag the current slot with
        kPrep_Start/kVerb_Start/kCompoundNoun, `BackEnd.c:3984-3990`/
        `4029-4032`.
      - `_Comma_`/`_Period_`/`_Quest_`/`_Exclam_`: sentence-end handling,
        `BackEnd.c:3992-4007`.
      - Vowel/consonant classification via `_phonemes.py`'s `PhonFlags2`
        (`kVowelF`) and word-initial-consonant flagging, `BackEnd.c:4042-4058`.

    Only the SENTENCE-END loop-back (re-entering `Collect_FE_Tokens` for the
    next sentence, `BackEnd.c:4225`/`4286`) and the end-of-input
    post-processing (`BackEnd.c:4068-4155`: deferred emphasis promotion,
    default-stress-if-none, `_Exclam_`-promotes-last-stress-to-emphatic) are
    ported here, applied once at the end of `text` (this port treats the
    whole input as one sentence rather than looping per terminal-punctuation
    boundary -- a further scope reduction consistent with `_frontend.py` not
    modeling multi-sentence input either).

    NOT ported (see module docstring "WHY THIS IS AN ADAPTATION" and
    "VALIDATION STATUS"): buffer overflow/yellow-red-zone handling
    (`BackEnd.c:3777-3789`/`3844-3856` -- no fixed-size buffer exists here),
    embedded commands (`kECommandTok`/`Parse_Embedded_Command`), the
    `WordCB` callback, and `Flag_PhonBuf_1` (called at `BackEnd.c:4154`,
    itself a separate unported function, `BackEnd.c:3481-3519`).
    """
    from ._data import PhonFlags2
    from ._consts import kVowelF

    sa = SentenceAssembly()
    in_index = [1]  # mutable box so nested helpers can advance it; mirrors phonBuf_1_In_Index

    def ensure(i: int) -> None:
        while len(sa.phon_buf) <= i:
            sa.phon_buf.append(None)
            sa.ctrl_buf.append(0)

    def flag_current(flag: int) -> None:
        ensure(in_index[0])
        sa.ctrl_buf[in_index[0]] |= flag

    def store(phon: int) -> int:
        """Stand-in for `Store_Phon_In_PhonBuf_1` (`BackEnd.c:3527`): writes
        `phon` at the current index and advances it, returning the index
        just written."""
        ensure(in_index[0])
        sa.phon_buf[in_index[0]] = phon
        written = in_index[0]
        in_index[0] += 1
        return written

    word_initial = True
    word_stress_1_index: Optional[int] = None
    word_stress_2_index: Optional[int] = None
    word_vowel_index: Optional[int] = None
    word_was_emph = False

    def promote_word_emphasis() -> None:
        """BackEnd.c:3908-3927 / 4072-4090 -- if the previous word carried
        emphasis markup, retroactively promote its last stress (or first
        vowel, if no stress at all) to kEmphaticStress."""
        temp_index = None
        if word_stress_1_index is not None:
            temp_index = word_stress_1_index
        elif word_stress_2_index is not None:
            temp_index = word_stress_2_index
        elif word_vowel_index is not None:
            temp_index = word_vowel_index
        if temp_index is not None:
            sa.ctrl_buf[temp_index] &= ~kStressField
            sa.ctrl_buf[temp_index] |= kEmphaticStress

    for word, punct in tokenize(text):
        tok = make_fe_word_token(word, punct)
        sa.words.append(tok)

        # --- _Word_ opcode case (BackEnd.c:3903-3982) ---
        if word_was_emph:
            promote_word_emphasis()
            word_was_emph = False

        flag_current(kWord_Start)
        word_initial = True
        sa.is_compound_noun = False
        sa.last_word_index = in_index[0]
        sa.word_count += 1

        if tok.is_content_word:
            flag_current(kContent_Word)

        word_stress_1_index = None
        word_stress_2_index = None
        word_vowel_index = None
        if tok.word_emphasis == "emphasize":
            word_was_emph = True
        elif tok.word_emphasis == "deemphasize":
            pass  # BackEnd.c tracks wordWasDeemph but never reads it back -- BackEnd.c:3959/3967

        # phon_str is _Word_-prefixed (both dictionary decode and the
        # engtop() fallback synthesize that prefix -- see make_fe_word_token
        # and _lexicon.py's _decode_phon_string); the _Word_ opcode's own
        # side effects were just applied above, so walk the rest.
        opcodes = tok.phon_str[1:] if tok.phon_str and tok.phon_str[0] == _Word_ else tok.phon_str

        for cur_phon in opcodes:
            if cur_phon == _Comp_:
                sa.is_compound_noun = True
                flag_current(kCompoundNoun)
                continue
            if cur_phon == _Prep_:
                flag_current(kPrep_Start)
                continue
            if cur_phon == _Verb_:
                flag_current(kVerb_Start)
                continue
            if _is_stress1(cur_phon):
                if sa.is_compound_noun or not tok.is_content_word:
                    flag_current(kSecondaryStress)
                    sa.last_stress_2_index = in_index[0]
                    if word_stress_2_index is None:
                        word_stress_2_index = in_index[0]
                else:
                    flag_current(kPrimaryStress)
                    sa.last_stress_1_index = in_index[0]
                    if word_stress_1_index is None:
                        word_stress_1_index = in_index[0]
                    sa.stress_counter += 1
                continue
            if _is_stress2(cur_phon):
                if not sa.is_compound_noun:
                    flag_current(kSecondaryStress)
                    if word_stress_2_index is None:
                        word_stress_2_index = in_index[0]
                sa.last_stress_2_index = in_index[0]
                continue
            if _is_emph_stress(cur_phon):
                flag_current(kEmphaticStress)
                sa.stress_counter += 1
                continue

            # --- ordinary phoneme (BackEnd.c:4041-4061) ---
            flags = PhonFlags2[cur_phon] if 0 <= cur_phon < len(PhonFlags2) else 0
            if flags & kVowelF:
                word_initial = False
                word_vowel_index = in_index[0]
                sa.last_vowel_index = in_index[0]
            else:
                if word_initial:
                    flag_current(kWord_Initial_Consonant)
            store(cur_phon)

        # --- end-of-word punctuation (BackEnd.c:3992-4007) ---
        if punct is not None and punct in _PUNCT_TO_PHON:
            phon = _PUNCT_TO_PHON[punct]
            written = store(_SIL_)
            sa.ctrl_buf[written] |= kTerm_Bound
            sa.ctrl_buf[written] |= (tok.phrase_bnd << kSilenceTypeShift)
            sa.end_punctuation = phon
            word_initial = True
            sa.is_compound_noun = False

    # --- implicit terminal silence on EOF with no punctuation seen
    # (BackEnd.c:3805-3814): if the input never hit a recognized terminal
    # mark, the real engine still stores a _SIL_ with kTerm_Bound/kBND_Decl
    # and defaults end_Punctuation to _Period_, exactly as if a period had
    # been typed. Without this, plain unpunctuated input (the common case)
    # is missing its final silence phoneme and boundary flag entirely.
    if not sa.end_punctuation:
        written = store(_SIL_)
        sa.ctrl_buf[written] |= kTerm_Bound
        sa.ctrl_buf[written] |= (kBND_Decl << kSilenceTypeShift)
        sa.end_punctuation = _Period_

    # --- end-of-input post-processing (BackEnd.c:4068-4155) ---
    if word_was_emph:
        promote_word_emphasis()

    if sa.word_count:
        if sa.stress_counter == 0:
            if sa.last_stress_2_index is None:
                for index in range(sa.last_word_index, in_index[0]):
                    cur_phon = sa.phon_buf[index]
                    if cur_phon is not None and PhonFlags2[cur_phon] & kVowelF:
                        sa.ctrl_buf[index] |= kPrimaryStress
                        sa.last_stress_1_index = index
                        break
            else:
                sa.ctrl_buf[sa.last_stress_2_index] &= ~kStressField
                sa.ctrl_buf[sa.last_stress_2_index] |= kPrimaryStress
                sa.last_stress_1_index = sa.last_stress_2_index

        if sa.end_punctuation == _Exclam_:
            temp_index = None
            if sa.last_stress_1_index is not None:
                temp_index = sa.last_stress_1_index
            elif sa.last_stress_2_index is not None:
                temp_index = sa.last_stress_2_index
            elif sa.last_vowel_index is not None:
                temp_index = sa.last_vowel_index
            if temp_index is not None:
                sa.ctrl_buf[temp_index] &= ~kStressField
                sa.ctrl_buf[temp_index] |= kEmphaticStress
        # Flag_PhonBuf_1 (BackEnd.c:3481-3519) is NOT ported -- see module
        # docstring "PHASE 2 HANDOFF". Its output would further annotate
        # sa.ctrl_buf (syllable marks, consonant stress placement).

    # Trim unwritten trailing placeholder slots (from `ensure()` overshoot,
    # which cannot happen here since flag_current always targets the slot
    # store() is about to fill next -- kept as a defensive truncation).
    sa.phon_buf = sa.phon_buf[:in_index[0]]
    sa.ctrl_buf = sa.ctrl_buf[:in_index[0]]

    return sa


def _is_stress1(phon: int) -> bool:
    from ._phonemes import _Stress1_
    return phon == _Stress1_


def _is_stress2(phon: int) -> bool:
    from ._phonemes import _Stress2_
    return phon == _Stress2_


def _is_emph_stress(phon: int) -> bool:
    from ._phonemes import _EmphStress_
    return phon == _EmphStress_
