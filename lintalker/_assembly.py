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
    kIPron, kRPron, kPrep, kConj, kRelPro,
    kArt, kDet, kCConj, kObjPron, kSubjPron, kContr, kInf, kVaux, kRVaux,
    kPrimaryStress, kSecondaryStress, kEmphaticStress, kStressField,
    kContent_Word, kWord_Start, kWord_Initial_Consonant, kCompoundNoun,
    kTerm_Bound, kPrep_Start, kVerb_Start, kSilenceTypeShift, kSilenceTypeField,
    kBND_Pause, kBND_Decl, kBND_Quest, kBND_Emph, kBND_None,
    kBND_Sep1, kBND_Sep2, kBND_Sep3, kBND_Sep4, kBND_Sep5, kBND_Sep6,
    kSilenceDuration, kHas_Adj,
)
from ._morph import _pos_count_and_hi_rank
from ._phonemes import (
    _SIL_, _Word_, _Period_, _Comma_, _Quest_, _Exclam_, _Comp_, _Prep_,
    _Verb_,
)
from ._frontend import tokenize
from ._lexicon import lookup, LexEntry
from ._engtop import engtop
from ._morph import try_s_morph, try_do_morph, apply_pos_from_suffix

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
    pos_choice: int = kUndefPOS        # resolved by _morph.resolve_pos() (Morph.c's ResolvePOS)
    alt_choice: int = kUndefPOS        # tok->altChoice -- see _morph.py; unused downstream so far
    is_content_word: bool = False      # BackEnd.c:3971-3980
    word_emphasis: str = "none"        # documented default: no emphasis-markup source ported
    trailing_punct: Optional[str] = None   # one of '.', ',', '!', '?', or None
    phrase_bnd: int = kBND_None        # kBND_Decl/Pause/Quest/Emph from trailing_punct, else kBND_None


def make_fe_word_token(word: str, punct: Optional[str], digit_by_digit: bool = False, is_dollar: bool = False) -> FEWordToken:
    """Build one `FEWordToken` for `word` (already uppercased by
    `_frontend.tokenize()`), consulting `_lexicon.lookup()` first and
    falling back to `_engtop.engtop()` -- the same dictionary-then-rules
    order `FrontEnd.c:2039` uses.

    A pure digit string (`_frontend.tokenize()` now preserves these
    instead of stripping them) bypasses the dictionary/`DoMorph`/
    `EngToP` chain entirely, matching `WordToPhonemes`'s real
    `kNumericTok`/`SpeakTokenAsNumber` branch: `_numbers.number_to_
    phonemes` builds the cardinal-reading phoneme opcodes (see that
    module's docstring for its verification status), and
    `PartialNumberToPhonemes`'s own final step (`FrontEnd.c:1886-1889`:
    `tok->POScode1[0] = kAdj; tok->compPOS1 = kHas_Adj; tok->hiRank =
    kAdj; tok->POScount1 = 1`) is matched directly. `digit_by_digit`
    (set when the `nmbr` embedded command's `LTRL` mode is active at
    this word's position, `EmbeddedCmd.c`'s `ChangeNumberMode`/
    `FrontEnd.c:2057-2062`'s `kDigitByDigit` check) routes to
    `_numbers.digit_by_digit_phonemes` instead, reading each digit on
    its own rather than grouping them into a cardinal number. A plain
    4-digit token matching `_numbers.is_year_number` (e.g. "1984") is
    automatically read year-style (`_numbers.year_to_phonemes`) instead
    of grouped, matching `SpeakTokenAsNumber`'s automatic `kYearSpecial`
    detection (`FrontEnd.c:1978-1990`) -- this happens by default, not
    behind any embedded command, the same way it does in the real engine.
    `is_dollar` (set when `_frontend.tokenize()`'s `_dollar_out` recorded
    this word as a `$<digits>` token) routes to `_numbers.dollar_
    phonemes` instead, appending "dollar"/"dollars" and bypassing year
    detection -- matching `SpeakTokenAsNumber`'s `kAddDollar` exclusion.
    """
    if word.isdigit():
        from ._numbers import (
            number_to_phonemes, digit_by_digit_phonemes, is_year_number,
            year_to_phonemes, dollar_phonemes,
        )

        if digit_by_digit:
            _digits_phon_str = digit_by_digit_phonemes(word)
        elif is_dollar:
            _digits_phon_str = dollar_phonemes(word)
        elif is_year_number(word):
            _digits_phon_str = year_to_phonemes(word)
        else:
            _digits_phon_str = number_to_phonemes(word)

        return FEWordToken(
            word=word,
            phon_str=_digits_phon_str,
            from_dictionary=True,
            pos_code1=[kAdj, kUndefPOS, kUndefPOS, kUndefPOS],
            comp_pos1=kHas_Adj,
            is_abbrev=False,
            is_compound_hint=False,
            has_alt=False,
            pos_choice=kAdj,
            trailing_punct=punct,
            phrase_bnd=_PUNCT_TO_BND.get(punct, kBND_None) if punct else kBND_None,
        )

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
        # pos_choice is intentionally left at its kUndefPOS default here --
        # it's resolved for the WHOLE clause at once by _morph.resolve_pos()
        # (a real port of Morph.c's ResolvePOS), called from
        # collect_fe_tokens() once all of a clause's tokens are built, since
        # disambiguating one word can require looking at neighboring words'
        # own candidate POS sets.
    elif (morphed := (try_s_morph(word) or try_do_morph(word))) is not None:
        # DoMorph succeeded -- either Do_S_Morph/Store_S_or_Z
        # (Morph.c:2306-2322, tried first, matching DoMorph's own
        # unconditional S-before-Search_Suffix order) or one of the other
        # ported suffix functions (see _morph.py's try_do_morph
        # docstring for exactly which). WordToPhonemes does NOT default a
        # morphed word's POS to kNoun the way it does for the true
        # EngToP fallback below (FrontEnd.c:1628-1648): SearchAllDicts
        # populates the token's POS fields from the ROOT it found, which
        # `SetPOS_FromSuffix` (`Morph.c:1027-1189`) then either leaves
        # alone (kS_suffix and several fallback suffix codes with no
        # switch case) or overrides entirely with a suffix-derived POS
        # (most suffixes -- e.g. -ED always forces kVerb regardless of
        # the root's own dictionary POS, matching a real English
        # zero-derivation pattern: "time" is kNoun/kVerb, but "timed" is
        # unambiguously kVerb). `has_alt` comes from the ROOT's own
        # dictionary entry (a homograph pair like "close"/"lead"), which
        # SearchAllDicts would have populated onto the token in the real
        # engine too -- when true, `apply_pos_from_suffix` ports
        # `SetPOS_FromSuffix`'s `hasAlt`-true `Zap_POS` branch (picks
        # between `pos_code1`/`pos_code2`, e.g. "close"+"-er"->"closer"
        # forces `kNoun`, found in "close"'s ALT reading, not its primary
        # verb reading).
        build_phon_str, root_entry, suffix_type = morphed
        _pos_code2 = list(root_entry.pos_code2) if root_entry.pos_code2 is not None else None
        _pc1, _pc2, _ = _pos_count_and_hi_rank(root_entry.pos_code1, root_entry.pos_code2)
        pos_code1, comp_pos1, pos_code2, comp_pos2, alt_choice = apply_pos_from_suffix(
            list(root_entry.pos_code1), root_entry.comp_pos1,
            _pos_code2, root_entry.comp_pos2,
            _pc1, root_entry.has_alt, suffix_type,
        )
        # When the ALT (pos_code2) reading won, the real engine also
        # switches to the root's ALTERNATE pronunciation (phon_hold),
        # not just its POS -- e.g. "winded" (root WIND, -ED forces
        # kVerb, matching WIND's pos_code2 verb reading) uses WIND's
        # /waɪnd/ phon_hold, not its /wɪnd/ phon_str.
        _base = root_entry.phon_hold if (alt_choice == 1 and root_entry.phon_hold is not None) else root_entry.phon_str
        morphed_phon_str = build_phon_str(_base)
        tok = FEWordToken(
            word=word,
            phon_str=morphed_phon_str,
            from_dictionary=True,
            pos_code1=pos_code1,
            comp_pos1=comp_pos1,
            is_abbrev=root_entry.is_abbrev,
            is_compound_hint=root_entry.is_compound,
            has_alt=root_entry.has_alt,
            pos_code2=pos_code2,
            comp_pos2=comp_pos2,
        )
        if alt_choice is not None:
            tok.alt_choice = alt_choice
    else:
        # No dictionary entry, no DoMorph match -> _engtop.engtop()
        # rule-engine fallback. FrontEnd.c:1650 calls SetPOStoVal(t, kNoun)
        # right after EngToP(), then SetPOS_FromSuffix (Morph.c:1027, not
        # ported -- see module docstring) refines it. pos_choice = kNoun
        # here, confirmed against a real C oracle dump (see
        # "POS-DEFAULT-FOR-RULE-FALLBACK-WORDS").
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

    # is_content_word is set after _morph.resolve_pos() finalizes pos_choice
    # for the whole clause (see collect_fe_tokens) -- NOT here, since a
    # word's own dictionary candidates alone don't determine it.
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
    note_buf: list = field(default_factory=lambda: [0])   # phon_Buf_1-side user_Note_Buf1 equivalent (EC_slnc durations)
    rate_buf: list = field(default_factory=lambda: [0])   # phon_Buf_1-side user_Rate_Buf1 equivalent (EC_rate/EC_ratr)
    word_count: int = 0
    stress_counter: int = 0
    end_punctuation: int = 0
    last_word_index: int = 0
    last_stress_1_index: Optional[int] = None
    last_stress_2_index: Optional[int] = None
    last_vowel_index: Optional[int] = None
    is_compound_noun: bool = False
    words: list = field(default_factory=list)   # list[FEWordToken], in order


_SEP_CONTENT_POS = {kNoun, kVerb, kAdj, kAdv}


def _place_phrasing(words: list) -> list:
    """Port of `PlacePhrasing` (`Morph.c:20-280`)'s mid-clause boundary
    cascade (SEP1-6; SEP7/parenthesized-clause handling not ported --
    this port has no parenthesis tracking). Returns a list the same
    length as `words`, `mid_bnds[i]` being the resolved boundary type
    (`kBND_None` if none) to apply just before word `i`'s own phonemes.

    Mirrors the C reference's per-clause `tokBuffer` loop directly: this
    port's `words` (one clause's word tokens) line up 1:1 with
    `vv->tokBuffer[1..LastTok-1]` -- the C reference's tokBuffer holds
    exactly one trailing punctuation token PER CLAUSE, at index
    `LastTok` (since this port already splits input into clauses on
    `. , ! ?` the same way one `Fill_Tok_Buffer`/`ParseSentence` pass
    processes one such clause) -- so `next_Punct`/`next2_Punct`/
    `next3_Punct` just mean "the word at this lookahead distance IS the
    last word of the clause", not "some literal mid-clause punctuation
    token", and a flat word list is exactly the right shape; no
    architectural change was needed. `inParen` is always false (no
    parenthesized-clause tracking, a separate, smaller gap) so the C
    code's `!inParen` guard is always true here. Each rule is checked in
    order and the first match wins (mirrors the C code's
    goto-past-the-rest-of-the-checks control flow); the same-token /
    previous-token "already has a boundary" mutual-exclusion
    (`!prev_Tok->add_BND && !cur_Tok->add_BND`) is tracked via
    `word_had_bnd`.
    """
    n_words = len(words)
    mid_bnds = [kBND_None] * n_words
    short_sent = n_words <= 8  # Morph.c:60-63: vv->LastTok<=9 <=> n_words<=8
    prev_pos = kUndefPOS
    ambig1_pos = False
    det_flag = False
    initial_adv = False
    word_had_bnd = [False] * n_words
    for wi, cur_tok in enumerate(words):
        cur_pos = cur_tok.pos_choice
        c1, c2, _ = _pos_count_and_hi_rank(cur_tok.pos_code1, cur_tok.pos_code2)
        ambig_pos = (c1 + c2) > 1

        is_last = wi == n_words - 1
        next_pos = words[wi + 1].pos_choice if wi + 1 < n_words else kUndefPOS
        next_punct = is_last
        # Morph.c:88-108: confirmed via direct instrumentation of the C
        # reference (dumping word_Count/LastTok/CurTok/next2_Punct while
        # processing a genuine SEP4 hit) that `next2_Punct`/`next3_Punct`
        # are NEVER true in the real engine -- dead code. The C source
        # nests the "== LastTok-2" (or -3) check INSIDE the "< LastTok-2"
        # (or -3) guard:
        #   if (CurTok < LastTok-2) { next2_POS = ...;
        #       if (CurTok == LastTok-2) next2_Punct = true; }
        # `CurTok < X` and `CurTok == X` can never both hold, so the inner
        # assignment is unreachable and `next2_Punct`/`next3_Punct` stay
        # false always; only `next2_POS`/`next3_POS` (gated on the outer
        # `<` alone) are ever populated. Ported faithfully (bug-for-bug):
        # `next2_pos`/`next3_pos` populated iff `wi < n_words-2`/`-3`;
        # `next2_punct`/`next3_punct` always `False`.
        next2_pos = words[wi + 2].pos_choice if wi < n_words - 2 else kUndefPOS
        next2_punct = False
        next3_pos = words[wi + 3].pos_choice if wi < n_words - 3 else kUndefPOS
        next3_punct = False

        cur_bnd = kBND_None
        if not next_punct:
            got_bnd = False

            # SEP1: sentence-initial adverb (Morph.c:148-160)
            if initial_adv:
                cur_bnd = kBND_Sep1
                initial_adv = False
                got_bnd = True
            else:
                initial_adv = (
                    prev_pos == kUndefPOS and cur_pos == kAdv
                    and next_pos in (kArt, kDet)
                )

            # SEP2: coordinating conjunctions (Morph.c:165-183)
            if not got_bnd and (
                (
                    prev_pos != kUndefPOS and cur_pos == kCConj
                    and not det_flag and wi > 3
                    and next2_pos != kConj
                )
                or (cur_pos == kAdv and wi > 4 and next_pos != kAdj)
                or (prev_pos == kObjPron and wi > 2)
                or (
                    cur_pos in (kSubjPron, kContr) and wi > 3
                    and prev_pos != kRelPro and prev_pos != kConj
                )
                or (cur_pos == kInterr and wi > 4)
            ):
                cur_bnd = kBND_Sep2
                got_bnd = True

            # SEP3: subject noun phrase cued by a following aux verb
            # (Morph.c:190-213)
            if not got_bnd and (
                (
                    wi > 2 and prev_pos in (kNoun, kVerb)
                    and prev_pos not in (kVaux, kRVaux)
                    and cur_pos in (kVaux, kRVaux)
                )
                or (
                    prev_pos == kNoun
                    and next_pos not in (kRelPro, kVaux, kRVaux)
                    and next2_pos not in (kVaux, kRVaux)
                    and wi > 4 and cur_pos in (kVaux, kRVaux)
                )
                or (
                    prev_pos == kNoun and next_pos != kRelPro and ambig1_pos
                    and next_pos != kRVaux and next_pos != kConj
                    and next_pos != kCConj and wi > 3 and cur_pos == kVerb
                )
                or (
                    prev_pos == kNoun and cur_pos != kRelPro
                    and cur_pos != kRVaux and cur_pos != kInf
                    and cur_pos != kCConj and cur_pos != kConj
                    and wi > 2 and ambig1_pos
                    and (wi > 2 or short_sent) and cur_pos == kVerb
                )
            ):
                cur_bnd = kBND_Sep3
                got_bnd = True

            # SEP4: before a conjunction (Morph.c:219-236)
            if not got_bnd and (
                (
                    cur_pos == kConj and wi > 3 and cur_pos != kInf
                    and not next_punct and prev_pos != kConj
                    and prev_pos != kCConj and not next2_punct
                )
                or (
                    prev_pos == kVPart and cur_pos != kPrep
                    and cur_pos != kDet and cur_pos != kArt and wi > 2
                    and (cur_pos == kNoun or cur_pos == kAdj)
                )
                or (cur_pos == kInterr and wi > 2 and cur_pos == kSubjPron)
                or (
                    cur_pos == kInf and wi > 3 and not next_punct
                    and not next2_punct and not next3_punct
                )
            ):
                cur_bnd = kBND_Sep4
                got_bnd = True

            # SEP5: before a relative pronoun/quantifier (Morph.c:242-256)
            if not got_bnd and (
                (
                    cur_pos == kRelPro and wi >= 3 and prev_pos != kPrep
                    and next3_pos != kVaux and next3_pos != kRVaux
                    and (prev_pos == kNoun or prev_pos == kVerb)
                )
                or (
                    cur_pos == kQuant and wi > 5
                    and prev_pos != kAdj and prev_pos != kArt
                    and prev_pos != kVaux and prev_pos != kRVaux
                    and prev_pos != kDet and next2_pos != kCConj
                    and not next_punct
                )
            ):
                cur_bnd = kBND_Sep5
                got_bnd = True

            # SEP6: Silverman87-style content/function tone group boundary
            # (Morph.c:262-267)
            if not got_bnd and (
                prev_pos in _SEP_CONTENT_POS and cur_pos not in _SEP_CONTENT_POS
            ):
                cur_bnd = kBND_Sep6

        if cur_bnd != kBND_None and not (wi > 0 and word_had_bnd[wi - 1]) and not word_had_bnd[wi]:
            mid_bnds[wi] = cur_bnd
            word_had_bnd[wi] = True

        prev_pos = cur_pos
        if wi > 1:
            det_flag = False
        if cur_pos in (kArt, kDet):
            det_flag = True
        ambig1_pos = ambig_pos

    return mid_bnds


def collect_fe_tokens(
    text: str,
    emphasis_overrides: Optional[dict] = None,
    silence_overrides: Optional[dict] = None,
    pos_overrides: Optional[dict] = None,
    rate_overrides: Optional[dict] = None,
    nmbr_overrides: Optional[dict] = None,
) -> SentenceAssembly:
    """Adapted port of `Collect_FE_Tokens` (`BackEnd.c:3712-4157`).

    `rate_overrides`, if given, is a `{word_index: wpm}` dict (from
    `_embeddedcmd.scan_bracket_commands`'s `rate`/`ratr` support): the
    resolved speaking rate is recorded in `sa.rate_buf` at that word's
    START position (no extra phoneme inserted, unlike `slnc` -- mirrors
    `Parse_Embedded_Command`'s `EC_rate`/`EC_ratr` cases writing directly
    to `user_Rate_Buf1[vv->phonBuf_1_In_Index]`), consumed by
    `_moduration.mod_duration`'s rate-change check
    (`vv.user_Rate_Buf2[i]`).

    `emphasis_overrides`, if given, is a `{word_index: "emphasize"|
    "deemphasize"}` dict (from `_embeddedcmd.scan_bracket_commands`'s
    `emph` support) applied to the corresponding word's `word_emphasis`
    field right after this clause's token list is built -- mirrors
    `FrontEnd.c:343-344`/`369-370`/`460-461` copying `vv->NewEmphasis`
    straight into the next-created token's `tokEmphasis` field.

    `pos_overrides`, if given, is a `{word_index: pos_value}` dict (from
    `_embeddedcmd.scan_bracket_commands`'s `xtnd`'s `wpos` support)
    applied to the corresponding word's `pos_code1`/`comp_pos1` fields
    at the same point as `emphasis_overrides`, before `resolve_pos`
    runs -- mirrors `SetPOStoVal` (`FrontEnd.c:138-145`) setting
    `POScode1[0]`/`compPOS1`/`hiRank`/`POScount1` directly on the token.

    `nmbr_overrides`, if given, is a `{word_index: is_digit_by_digit}`
    dict (from `_embeddedcmd.scan_bracket_commands`'s `nmbr` support):
    like `char`'s mode, this is a LATCHED state (`ChangeNumberMode`
    sets `vv->Mode`'s `kDigitByDigit` bit, which stays set for every
    following numeric token until changed again), not a single-word
    override -- so it's applied by walking the tokens in order and
    updating a running mode flag at each `word_index` present in the
    dict, rather than a one-shot per-word lookup like `pos_overrides`.

    `silence_overrides`, if given, is a `{word_index: duration}` dict
    (from `_embeddedcmd.scan_bracket_commands`'s `slnc` support, `duration`
    already `>>16`-scaled to a plain integer): a real `_SIL_` phoneme is
    inserted right before that word's own phonemes, with `kSilenceDuration`
    set on its `ctrl_buf` slot and `duration` recorded in the parallel
    `note_buf` slot -- mirrors `Parse_Embedded_Command`'s `EC_slnc` case
    (`BackEnd.c`: `user_Note_Buf1[...] = embedData; phon_Ctrl_Buf_1[...]
    |= kSilenceDuration; Store_Phon_In_PhonBuf_1(_SIL_)`), consumed by
    `_moduration.mod_duration`'s existing `kSilenceDuration` branch
    (reads `vv.user_Note_Buf2[i]` for that `_SIL_`'s duration instead of
    the generic `BoundryDurTbl` lookup).

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
            sa.note_buf.append(0)
            sa.rate_buf.append(0)

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
    word_start_indices: list = []  # sa.words[i] starts at phon_buf index word_start_indices[i]

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

    # Build every clause word up front (not one-at-a-time inside the main
    # loop below): _morph.resolve_pos() needs the whole clause's tokens at
    # once (it looks at next/next2/next3 word's OWN candidate POS sets to
    # disambiguate the current word, mirroring Morph.c's ResolvePOS being a
    # separate pass over the whole token buffer before Collect_FE_Tokens
    # ever consumes it).
    from ._morph import resolve_pos
    _clause_tokens = []
    _digit_mode = False
    _dollar_indices: list = []
    for _wi, (word, punct) in enumerate(tokenize(text, _dollar_out=_dollar_indices)):
        if nmbr_overrides and _wi in nmbr_overrides:
            _digit_mode = nmbr_overrides[_wi]
        _clause_tokens.append(make_fe_word_token(
            word, punct, digit_by_digit=_digit_mode, is_dollar=_wi in _dollar_indices,
        ))
    if emphasis_overrides:
        for _wi, _emph in emphasis_overrides.items():
            if 0 <= _wi < len(_clause_tokens):
                _clause_tokens[_wi].word_emphasis = _emph
    if pos_overrides:
        for _wi, _pos_val in pos_overrides.items():
            if 0 <= _wi < len(_clause_tokens):
                _tok = _clause_tokens[_wi]
                _tok.pos_code1 = [_pos_val, kUndefPOS, kUndefPOS, kUndefPOS]
                _tok.comp_pos1 = 1 << _pos_val
    resolve_pos(_clause_tokens)
    for _tok in _clause_tokens:
        _tok.is_content_word = _tok.pos_choice in _CONTENT_POS
    _mid_bnds = _place_phrasing(_clause_tokens)

    for _wi, tok in enumerate(_clause_tokens):
        sa.words.append(tok)

        # --- _Word_ opcode case (BackEnd.c:3903-3982) ---
        if word_was_emph:
            promote_word_emphasis()
            word_was_emph = False

        # --- mid-clause phrase boundary (BackEnd.c:3814-3826): a
        # boundary type >= kBND_Paren_L and != kBND_Sep6 (i.e. SEP1-5)
        # inserts an actual _SIL_ phoneme (with the boundary/kVerb_Start
        # flags on THAT inserted phoneme, not on the word's own first
        # phoneme); kBND_Sep6 instead flags the word's own first
        # phoneme slot directly, no extra phoneme inserted.
        _mid_bnd = _mid_bnds[_wi]
        if _mid_bnd not in (kBND_None, kBND_Sep6):
            _sil_idx = store(_SIL_)
            sa.ctrl_buf[_sil_idx] |= (_mid_bnd << kSilenceTypeShift)
            sa.ctrl_buf[_sil_idx] |= kVerb_Start

        # --- EC_slnc embedded silence (BackEnd.c's Parse_Embedded_Command
        # case EC_slnc): a real _SIL_ phoneme with kSilenceDuration set and
        # the requested duration recorded in note_buf, inserted right
        # before this word's own phonemes (see silence_overrides above).
        if silence_overrides and _wi in silence_overrides:
            _slnc_idx = store(_SIL_)
            sa.ctrl_buf[_slnc_idx] |= kSilenceDuration
            sa.note_buf[_slnc_idx] = silence_overrides[_wi]

        word_start_indices.append(in_index[0])
        flag_current(kWord_Start)
        if _mid_bnd == kBND_Sep6:
            flag_current(_mid_bnd << kSilenceTypeShift)
        # --- EC_rate/EC_ratr embedded rate change (BackEnd.c:1900-1915
        # via Parse_Embedded_Command): recorded at this word's own START
        # position, no extra phoneme (see rate_overrides above).
        if rate_overrides and _wi in rate_overrides:
            ensure(in_index[0])
            sa.rate_buf[in_index[0]] = rate_overrides[_wi]
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
        punct = tok.trailing_punct
        if punct is not None and punct in _PUNCT_TO_PHON:
            phon = _PUNCT_TO_PHON[punct]
            bnd = tok.phrase_bnd
            # WH-question downgrade (Morph.c:PlacePhrasing:139-144/307-353):
            # a trailing "?" only keeps rising-question intonation
            # (_Quest_/kBND_Quest) for a genuine yes/no question. The real
            # engine tracks this via YesNo_Phrase (true by default, set
            # false when the clause-first word is kInterr -- a WH-word --
            # or when the first word is kPrep/kConj and the SECOND is
            # kInterr/kRelPro, e.g. "in what way..."). Confirmed by direct
            # instrumentation of the C reference: "how are you today?"
            # produces 3 pitch-buffer entries in the real engine, not 5 --
            # a straight _Quest_ mapping's count. Uses resolve_pos()'s real
            # POS resolution (kInterr comes from the dictionary, e.g. "how"/
            # "what"), not a fixed word list.
            yes_no_phrase = True
            if sa.words:
                if sa.words[0].pos_choice == kInterr:
                    yes_no_phrase = False
                elif sa.words[0].pos_choice in (kPrep, kConj) and len(sa.words) > 1:
                    if sa.words[1].pos_choice in (kInterr, kRelPro):
                        yes_no_phrase = False
            if phon == _Quest_ and not yes_no_phrase:
                phon = _Period_
                bnd = kBND_Decl
            written = store(_SIL_)
            sa.ctrl_buf[written] |= kTerm_Bound
            sa.ctrl_buf[written] |= (bnd << kSilenceTypeShift)
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
        flag_phon_buf_1(sa)

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


# ---------------------------------------------------------------------------
# Flag_PhonBuf_1 (BackEnd.c:3481-3519) and its helpers: MarkSyllable
# (BackEnd.c:3381-3448), MarkSyllableStart (BackEnd.c:3193-3379),
# MarkBoundry (BackEnd.c:3448-3480), If_Consonant_Cluster (BackEnd.c:3086-3167),
# Find_Next_Word_Bound (BackEnd.c:3177-3186).
#
# Called from *inside* Collect_FE_Tokens (BackEnd.c:4154, inside the
# `if (wordCount)` block) once the whole sentence's phon_Buf_1/
# phon_Ctrl_Buf_1 has been filled -- not a separate later stage. It scans
# the buffer once (calling MarkSyllable per vowel and MarkBoundry per
# phoneme to set syllable-order and word/prep/verb/term "-End" flags used
# by Fill_Phon_Buf_2/Mod_Duration/Pitch_RaiseAndFall), then makes one final
# pass (MarkSyllableStart) marking each syllable's first phoneme with
# kSyllable_Start.
#
# Place_Stress_In_Consonant (BackEnd.c:3300-3379, the consonant branch of
# the per-phoneme loop) is NOT ported: its only call site in the C
# reference is commented out (`//Place_Stress_In_Consonant (vv);`,
# `BackEnd.c:3510`), so it never runs in the compiled engine either.
# ---------------------------------------------------------------------------

def _phon_flags(phon: Optional[int]) -> int:
    """Bounds-safe PhonFlags2 lookup. phon_buf can (today) contain raw,
    not-yet-decoded placeholder opcodes from LexEntry.phon_str (e.g.
    literal _pRise_/_pFall_ standing in for compound/word markers -- see
    docs/architecture.md) that fall outside PhonFlags2's range; treat
    those the same way the existing ordinary-phoneme branch in
    collect_fe_tokens does (BackEnd.c:472's guard: `0 <= cur_phon <
    len(PhonFlags2)`)."""
    from ._data import PhonFlags2
    if phon is None or not (0 <= phon < len(PhonFlags2)):
        return 0
    return PhonFlags2[phon]

# BackEnd.c:3086-3167 -- consonant pairs that form a single cluster for
# syllable-boundary purposes (e.g. "TR" in "TRAIN" stays together).
_CONSONANT_CLUSTERS = {
    ('f', 'r'), ('f', 'l'),
    ('v', 'r'), ('v', 'l'),
    ('TH', 'r'), ('TH', 'w'),
    ('s', 'w'), ('s', 'l'), ('s', 'p'), ('s', 't'), ('s', 'k'), ('s', 'm'), ('s', 'n'), ('s', 'f'),
    ('SH', 'w'), ('SH', 'l'), ('SH', 'p'), ('SH', 't'), ('SH', 'r'), ('SH', 'm'), ('SH', 'n'),
    ('p', 'r'), ('p', 'l'),
    ('b', 'r'), ('b', 'l'),
    ('t', 'r'), ('t', 'w'),
    ('d', 'r'), ('d', 'w'),
    ('k', 'r'), ('k', 'l'), ('k', 'w'),
    ('g', 'r'), ('g', 'l'), ('g', 'w'),
}


def _consonant_cluster_ids():
    from ._phonemes import (
        _f_, _v_, _TH_, _s_, _SH_, _p_, _b_, _t_, _d_, _k_, _g_, _r_, _l_, _w_,
        _m_, _n_,
    )
    name_to_id = {
        'f': _f_, 'v': _v_, 'TH': _TH_, 's': _s_, 'SH': _SH_, 'p': _p_,
        'b': _b_, 't': _t_, 'd': _d_, 'k': _k_, 'g': _g_, 'r': _r_, 'l': _l_,
        'w': _w_, 'm': _m_, 'n': _n_,
    }
    return {(name_to_id[a], name_to_id[b]) for a, b in _CONSONANT_CLUSTERS}


_CONSONANT_CLUSTER_IDS = None


def if_consonant_cluster(consonant_1st: int, consonant_2nd: int) -> bool:
    """BackEnd.c:3086-3167 -- is (consonant_1st, consonant_2nd) a cluster
    that stays together at a syllable boundary?"""
    global _CONSONANT_CLUSTER_IDS
    if _CONSONANT_CLUSTER_IDS is None:
        _CONSONANT_CLUSTER_IDS = _consonant_cluster_ids()
    return (consonant_1st, consonant_2nd) in _CONSONANT_CLUSTER_IDS


def find_next_word_bound(sa: "SentenceAssembly", index: int) -> int:
    """BackEnd.c:3177-3186."""
    from ._consts import kBoundryTypeField, kWord_Start
    i = index + 1
    while i < len(sa.ctrl_buf):
        if sa.ctrl_buf[i] & (kBoundryTypeField | kWord_Start):
            break
        i += 1
    return i


def mark_boundry(sa: "SentenceAssembly", scan_index: int) -> None:
    """BackEnd.c:3448-3480 -- back-propagate word/prep/verb/term "-End"
    flags from the next boundary-flagged phoneme onto the consonants
    preceding it, stopping at the first vowel."""
    from ._consts import (
        kBoundryTypeField, kTerm_Bound, kTerm_End, kWord_End, kPrep_Start,
        kPrep_End, kVerb_Start, kVerb_End, kWord_Start,
    )
    from ._data import PhonFlags2
    from ._consts import kVowelF

    for index in range(scan_index + 1, len(sa.phon_buf)):
        cur_phon = sa.phon_buf[index]
        cur_flags = _phon_flags(cur_phon)
        cur_bound = sa.ctrl_buf[index] & kBoundryTypeField
        if cur_bound:
            bound_type = 0
            if cur_bound & kTerm_Bound:
                bound_type |= (kTerm_End | kWord_End)
            if cur_bound & kPrep_Start:
                bound_type |= (kPrep_End | kWord_End)
            if cur_bound & kVerb_Start:
                bound_type |= (kVerb_End | kWord_End)
            if cur_bound & kWord_Start:
                bound_type |= kWord_End
            sa.ctrl_buf[scan_index] |= bound_type

        if cur_flags & kVowelF:
            break


def mark_syllable(sa: "SentenceAssembly", scan_index: int) -> None:
    """BackEnd.c:3381-3448 -- compute this vowel's syllable order
    (first/mid/last/one-or-no syllable in its word) by scanning backward
    and forward to the nearest word boundary for other vowels."""
    from ._consts import (
        kSyllableTypeField, kWord_End, kLast_Syllable_In_Word,
        kBoundryTypeField, kMid_Syllable_In_Word, kFirst_Syllable_In_Word,
        kOneOrNo_Syllable_InWord,
    )
    from ._data import PhonFlags2
    from ._consts import kVowelF

    order = 0
    index = scan_index - 1
    while index > 0:
        cur_phon = sa.phon_buf[index]
        cur_flags = _phon_flags(cur_phon)
        cur_syllable_type = sa.ctrl_buf[index] & kSyllableTypeField
        if cur_syllable_type >= kWord_End:
            break
        if cur_flags & kVowelF:
            order = kLast_Syllable_In_Word
            break
        index -= 1

    index = scan_index + 1
    while index < len(sa.phon_buf):
        cur_phon = sa.phon_buf[index]
        cur_bound = sa.ctrl_buf[index] & kBoundryTypeField
        cur_flags = _phon_flags(cur_phon)
        if cur_bound:
            sa.ctrl_buf[scan_index] |= order
            break
        if cur_flags & kVowelF:
            if order == kLast_Syllable_In_Word:
                order = kMid_Syllable_In_Word
            elif order == 0:
                order = kFirst_Syllable_In_Word
        index += 1


def mark_syllable_start(sa: "SentenceAssembly") -> None:
    """BackEnd.c:3193-3379 -- final pass marking each syllable's first
    phoneme with kSyllable_Start, using the syllable-order bits mark_syllable
    already set on each vowel."""
    from ._consts import (
        kSyllable_Start, kSyllableOrderField, kOneOrNo_Syllable_InWord,
        kLast_Syllable_In_Word,
    )
    from ._data import PhonFlags2
    from ._consts import kVowelF
    from ._phonemes import _SIL_

    n = len(sa.phon_buf)
    syllable_index = 0
    index = 0
    while index < n:
        while sa.phon_buf[index] == _SIL_:
            syllable_index += 1
            index += 1
            if index >= n:
                return
        cur_phon = sa.phon_buf[index]
        cur_ctrl = sa.ctrl_buf[index]
        cur_flags = _phon_flags(cur_phon)
        if cur_flags & kVowelF:
            sa.ctrl_buf[syllable_index] |= kSyllable_Start
            syll_order = cur_ctrl & kSyllableOrderField
            if syll_order in (kOneOrNo_Syllable_InWord, kLast_Syllable_In_Word):
                index = find_next_word_bound(sa, index)
                syllable_index = index
            else:
                # First or mid vowel in word: scan forward for consonants.
                dist = -1
                while True:
                    index += 1
                    cur_flags = _phon_flags(sa.phon_buf[index])
                    dist += 1
                    if cur_flags & kVowelF:
                        break
                if dist == 0:
                    syllable_index = index
                elif dist == 1:
                    index -= 1
                    syllable_index = index
                elif dist == 2:
                    phon_2nd = sa.phon_buf[index - 1]
                    phon_1st = sa.phon_buf[index - 2]
                    if if_consonant_cluster(phon_1st, phon_2nd):
                        index -= 2
                    else:
                        index -= 1
                    syllable_index = index
                elif dist == 3:
                    from ._phonemes import _s_
                    phon_2nd = sa.phon_buf[index - 1]
                    phon_1st = sa.phon_buf[index - 2]
                    if if_consonant_cluster(phon_1st, phon_2nd):
                        if sa.phon_buf[index - 3] == _s_:
                            index -= 3
                        else:
                            index -= 2
                    else:
                        index -= 1
                    syllable_index = index
                else:
                    phon_2nd = sa.phon_buf[index - dist]
                    phon_1st = sa.phon_buf[index - dist + 1]
                    if if_consonant_cluster(phon_1st, phon_2nd):
                        index -= (dist - 2)
                    else:
                        index -= (dist >> 1)
                    syllable_index = index
        else:
            index += 1


def flag_phon_buf_1(sa: "SentenceAssembly") -> None:
    """BackEnd.c:3481-3519 -- final annotation pass over the whole sentence
    buffer: tracks is_Compound_Noun while scanning, calls mark_syllable per
    vowel (Place_Stress_In_Consonant, the consonant branch, is dead code in
    the C reference -- see module docstring), calls mark_boundry per
    phoneme, then mark_syllable_start once at the end."""
    from ._data import PhonFlags2
    from ._consts import kVowelF, kCompoundNoun, kBoundryTypeField

    is_compound_noun = False
    for scan_index in range(len(sa.phon_buf)):
        cur_phon = sa.phon_buf[scan_index]
        cur_flags = _phon_flags(cur_phon)
        cur_ctrl = sa.ctrl_buf[scan_index]

        if cur_ctrl & kCompoundNoun:
            is_compound_noun = True
        elif cur_ctrl & kBoundryTypeField:
            is_compound_noun = False

        if cur_flags & kVowelF:
            mark_syllable(sa, scan_index)

        mark_boundry(sa, scan_index)

    mark_syllable_start(sa)
