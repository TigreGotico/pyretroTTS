"""Sentence assembly: words in, a flagged phoneme-opcode buffer out.

Port of `Collect_FE_Tokens` (`BackEnd.c:3712-4157`), which walks a clause word
by word, appends each word's phoneme opcodes to `phon_Buf_1`, and flags them
with the stress, syllable, word-boundary and phrase-boundary bits the rest of
the pipeline reads. `_phonbuf2.fill_phon_buf_2` consumes what this produces.

The real `Collect_FE_Tokens` pulls `OpTokRec` tokens from FrontEnd.c's
tokenizer. Here they come from `_frontend.scan_tokens` and `_lexicon.lookup`,
with `_engtop.engtop`'s letter-to-sound rules for words the dictionary misses,
and are carried in `FEWordToken`:

    C (OpTokRec / dictionary decode)   Python (`FEWordToken`)
    --------------------------------   --------------------------------------
    tok->phonStr                       phon_str      (from LexEntry)
    tok->phonHold                      phon_hold     (alternate pronunciation)
    tok->hasAlt / altChoice            has_alt / alt_choice
    tok->POScode1 / POScode2           pos_code1 / pos_code2
    tok->compPOS1 / compPOS2           comp_pos1 / comp_pos2
    tok->isAbbriv                      is_abbrev
    tok->POSchoice (Set_POS)           pos_choice    (_morph.resolve_pos)
    tok->tokEmphasis                   word_emphasis (`emph` bracket command)
    tok->add_BND / phrasingBND         phrase_bnd    (punctuation + SEP1-6)
    tok->tokType == kEOFTok            end of the token list

A word the dictionary misses is read by the letter-to-sound rules and defaults
to `kNoun`, as `FrontEnd.c:1650` does with `SetPOStoVal(t, kNoun)` straight
after `EngToP()`. `_morph.apply_pos_from_suffix` then refines it.

`Place_Stress_In_Consonant` (`BackEnd.c:3300`) is not ported: its only call
site is commented out in the C source (`BackEnd.c:3510`).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import cache

from ._consts import (
    kAdj,
    kAdv,
    kArt,
    kBND_Decl,
    kBND_Emph,
    kBND_None,
    kBND_Pause,
    kBND_Quest,
    kBND_Sep1,
    kBND_Sep2,
    kBND_Sep3,
    kBND_Sep4,
    kBND_Sep5,
    kBND_Sep6,
    kBoundryTypeField,
    kCConj,
    kCompoundNoun,
    kConj,
    kContent_Word,
    kContr,
    kDet,
    kEmphaticStress,
    kFirst_Syllable_In_Word,
    kHas_Adj,
    kHas_Noun,
    kInf,
    kInterj,
    kInterr,
    kIPron,
    kLast_Syllable_In_Word,
    kMid_Syllable_In_Word,
    kNoun,
    kObjPron,
    kOneOrNo_Syllable_InWord,
    kPrep,
    kPrep_End,
    kPrep_Start,
    kPrimaryStress,
    kQuant,
    kRelPro,
    kRPron,
    kRVaux,
    kSecondaryStress,
    kSilenceDuration,
    kSilenceTypeShift,
    kStressField,
    kSubjPron,
    kSyllable_Start,
    kSyllableOrderField,
    kSyllableTypeField,
    kTerm_Bound,
    kTerm_End,
    kUndefPOS,
    kVaux,
    kVerb,
    kVerb_End,
    kVerb_Start,
    kVowelF,
    kVPart,
    kWord_End,
    kWord_Initial_Consonant,
    kWord_Start,
)
from ._data import (
    PhonFlags2,
)
from ._embeddedcmd import BracketCommands
from ._engtop import engtop
from ._frontend import scan_tokens
from ._letters import (
    spell_word,
)
from ._lexicon import LexEntry, lookup
from ._morph import (
    _pos_count_and_hi_rank,
    apply_pos_from_suffix,
    resolve_pos,
    try_do_morph,
    try_s_morph,
)
from ._numbers import (
    cent_phonemes,
    clock_phonemes,
    digit_by_digit_phonemes,
    dollar_phonemes,
    is_year_number,
    number_to_phonemes,
    year_to_phonemes,
)
from ._phonemes import (
    _SH_,
    _SIL_,
    _TH_,
    _b_,
    _Comma_,
    _Comp_,
    _d_,
    _EmphStress_,
    _Exclam_,
    _f_,
    _g_,
    _k_,
    _l_,
    _m_,
    _n_,
    _p_,
    _Period_,
    _Prep_,
    _Quest_,
    _r_,
    _s_,
    _Stress1_,
    _Stress2_,
    _t_,
    _v_,
    _Verb_,
    _w_,
    _Word_,
)

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
    phon_hold: list | None = None
    pos_code2: list | None = None
    comp_pos2: int = 0
    pos_choice: int = kUndefPOS        # resolved by _morph.resolve_pos() (Morph.c's ResolvePOS)
    alt_choice: int = kUndefPOS        # tok->altChoice -- see _morph.py; unused downstream so far
    is_content_word: bool = False      # BackEnd.c:3971-3980
    word_emphasis: str = "none"        # documented default: no emphasis-markup source ported
    trailing_punct: str | None = None   # one of '.', ',', '!', '?', or None
    phrase_bnd: int = kBND_None        # kBND_Decl/Pause/Quest/Emph from trailing_punct, else kBND_None


def make_fe_word_token(
    word: str, punct: str | None, digit_by_digit: bool = False,
    is_dollar: bool = False, is_cent: bool = False, is_clock: bool = False,
) -> FEWordToken:
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
    `is_dollar` (set when `_frontend.scan_tokens()`'s `dollar` recorded
    this word as a `$<digits>` token) routes to `_numbers.dollar_
    phonemes` instead, appending "dollar"/"dollars" and bypassing year
    detection -- matching `SpeakTokenAsNumber`'s `kAddDollar` exclusion.
    `is_cent` (set when `_frontend.scan_tokens()`'s `cent` recorded
    this word as the cents half of a `$N.M` token) routes to
    `_numbers.cent_phonemes` instead, appending "cent"/"cents" and
    likewise bypassing year detection (`kAddCent`'s exclusion).
    `is_clock` (set when `_frontend.scan_tokens()`'s `clock` recorded
    this word as the minutes half of an `H:MM` token) routes to
    `_numbers.clock_phonemes` instead, matching `kClockSpecial`'s "oh"/
    "o'clock" insertion rules.
    """
    if word.isdigit():

        if digit_by_digit:
            _digits_phon_str = digit_by_digit_phonemes(word)
        elif is_dollar:
            _digits_phon_str = dollar_phonemes(word)
        elif is_cent:
            _digits_phon_str = cent_phonemes(word)
        elif is_clock:
            _digits_phon_str = clock_phonemes(word)
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

    entry: LexEntry | None = lookup(word)

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
        # No dictionary entry and no morphology match: read the word with the
        # letter-to-sound rules. FrontEnd.c:1650 defaults such a word to kNoun
        # (SetPOStoVal, right after EngToP).
        tok = FEWordToken(
            word=word,
            # engtop() already prefixes its output with _Word_.
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
    note_buf: list = field(default_factory=lambda: [0])   # user_Note_Buf1: EC_slnc durations
    rate_buf: list = field(default_factory=lambda: [0])   # user_Rate_Buf1: EC_rate/EC_ratr
    cmd_buf: list = field(default_factory=lambda: [0])    # user_Cmd_Buf1: commands queued at each phoneme
    #: (ctrl_type, ctrl_data) in queue order, the CMDQueue `cmd_buf` counts into
    queued_commands: list = field(default_factory=list)
    word_count: int = 0
    stress_counter: int = 0
    end_punctuation: int = 0
    last_word_index: int = 0
    last_stress_1_index: int | None = None
    last_stress_2_index: int | None = None
    last_vowel_index: int | None = None
    is_compound_noun: bool = False
    words: list = field(default_factory=list)   # list[FEWordToken], in order


_SEP_CONTENT_POS = {kNoun, kVerb, kAdj, kAdv}


@dataclass(frozen=True)
class _PhraseContext:
    """One word's view of its neighbours, as the SEP rules see it.

    `next2_punct`/`next3_punct` have no counterpart: the C source assigns them
    inside a `CurTok < LastTok-2` guard yet only under `CurTok == LastTok-2`,
    conditions that cannot both hold, so they are always false. Conjuncts that
    tested them are omitted here rather than written as `and True`.
    """

    wi: int                # index of this word within the clause
    prev_pos: int
    cur_pos: int
    next_pos: int
    next2_pos: int
    next3_pos: int
    next_punct: bool       # this word is the clause's last
    det_flag: bool         # a determiner/article was seen recently
    ambig1_pos: bool       # the previous word had an ambiguous part of speech
    short_sent: bool       # the clause is 8 words or fewer


def _is_sep2(c: _PhraseContext) -> bool:
    """Coordinating conjunctions and pronoun-led clauses (Morph.c:165-183)."""
    return (
        (
            c.prev_pos != kUndefPOS and c.cur_pos == kCConj
            and not c.det_flag and c.wi > 3
            and c.next2_pos != kConj
        )
        or (c.cur_pos == kAdv and c.wi > 4 and c.next_pos != kAdj)
        or (c.prev_pos == kObjPron and c.wi > 2)
        or (
            c.cur_pos in (kSubjPron, kContr) and c.wi > 3
            and c.prev_pos != kRelPro and c.prev_pos != kConj
        )
        or (c.cur_pos == kInterr and c.wi > 4)
    )


def _is_sep3(c: _PhraseContext) -> bool:
    """Subject noun phrase cued by a following auxiliary verb (Morph.c:190-213)."""
    return (
        (
            c.wi > 2 and c.prev_pos in (kNoun, kVerb)
            and c.prev_pos not in (kVaux, kRVaux)
            and c.cur_pos in (kVaux, kRVaux)
        )
        or (
            c.prev_pos == kNoun
            and c.next_pos not in (kRelPro, kVaux, kRVaux)
            and c.next2_pos not in (kVaux, kRVaux)
            and c.wi > 4 and c.cur_pos in (kVaux, kRVaux)
        )
        or (
            c.prev_pos == kNoun and c.next_pos != kRelPro and c.ambig1_pos
            and c.next_pos != kRVaux and c.next_pos != kConj
            and c.next_pos != kCConj and c.wi > 3 and c.cur_pos == kVerb
        )
        or (
            c.prev_pos == kNoun and c.cur_pos != kRelPro
            and c.cur_pos != kRVaux and c.cur_pos != kInf
            and c.cur_pos != kCConj and c.cur_pos != kConj
            and c.wi > 2 and c.ambig1_pos
            and (c.wi > 2 or c.short_sent) and c.cur_pos == kVerb
        )
    )


def _is_sep4(c: _PhraseContext) -> bool:
    """Before a conjunction or an infinitive (Morph.c:219-236)."""
    return (
        (
            c.cur_pos == kConj and c.wi > 3 and c.cur_pos != kInf
            and not c.next_punct and c.prev_pos != kConj
            and c.prev_pos != kCConj
        )
        or (
            c.prev_pos == kVPart and c.cur_pos != kPrep
            and c.cur_pos != kDet and c.cur_pos != kArt and c.wi > 2
            and (c.cur_pos == kNoun or c.cur_pos == kAdj)
        )
        or (c.cur_pos == kInterr and c.wi > 2 and c.cur_pos == kSubjPron)
        or (c.cur_pos == kInf and c.wi > 3 and not c.next_punct)
    )


def _is_sep5(c: _PhraseContext) -> bool:
    """Before a relative pronoun or a quantifier (Morph.c:242-256)."""
    return (
        (
            c.cur_pos == kRelPro and c.wi >= 3 and c.prev_pos != kPrep
            and c.next3_pos != kVaux and c.next3_pos != kRVaux
            and (c.prev_pos == kNoun or c.prev_pos == kVerb)
        )
        or (
            c.cur_pos == kQuant and c.wi > 5
            and c.prev_pos != kAdj and c.prev_pos != kArt
            and c.prev_pos != kVaux and c.prev_pos != kRVaux
            and c.prev_pos != kDet and c.next2_pos != kCConj
            and not c.next_punct
        )
    )


def _is_sep6(c: _PhraseContext) -> bool:
    """Content word followed by a function word (Morph.c:262-267)."""
    return c.prev_pos in _SEP_CONTENT_POS and c.cur_pos not in _SEP_CONTENT_POS


#: Checked in order; the first match wins, mirroring the C source's jump past
#: the remaining checks. SEP1 is stateful and handled separately.
_SEP_RULES = (
    (kBND_Sep2, _is_sep2),
    (kBND_Sep3, _is_sep3),
    (kBND_Sep4, _is_sep4),
    (kBND_Sep5, _is_sep5),
    (kBND_Sep6, _is_sep6),
)


def _place_phrasing(words: list) -> list:
    """Port of `PlacePhrasing` (`Morph.c:20-280`): where to break a clause
    into tone groups.

    Returns a list as long as `words`, each entry the boundary type to apply
    just before that word (`kBND_None` for most of them).

    `words` holds one clause, lining up 1:1 with the C reference's
    `tokBuffer[1..LastTok-1]`, whose trailing punctuation token sits at
    `LastTok`. So `next_punct` means "this word ends the clause" rather than
    "a punctuation token follows". SEP7 and parenthesized-clause handling are
    not ported, and `inParen` is always false, making the C source's
    `!inParen` guard always true here.

    Two boundaries never land on adjacent words, nor twice on one word
    (the C source's `!prev_Tok->add_BND && !cur_Tok->add_BND`).
    """
    n_words = len(words)
    mid_bnds = [kBND_None] * n_words
    short_sent = n_words <= 8  # Morph.c:60-63: vv->LastTok <= 9
    prev_pos = kUndefPOS
    ambig1_pos = False
    det_flag = False
    initial_adv = False
    word_had_bnd = [False] * n_words

    for wi, cur_tok in enumerate(words):
        cur_pos = cur_tok.pos_choice
        count1, count2, _ = _pos_count_and_hi_rank(cur_tok.pos_code1, cur_tok.pos_code2)
        ambig_pos = (count1 + count2) > 1

        ctx = _PhraseContext(
            wi=wi,
            prev_pos=prev_pos,
            cur_pos=cur_pos,
            next_pos=words[wi + 1].pos_choice if wi + 1 < n_words else kUndefPOS,
            next2_pos=words[wi + 2].pos_choice if wi < n_words - 2 else kUndefPOS,
            next3_pos=words[wi + 3].pos_choice if wi < n_words - 3 else kUndefPOS,
            next_punct=wi == n_words - 1,
            det_flag=det_flag,
            ambig1_pos=ambig1_pos,
            short_sent=short_sent,
        )

        cur_bnd = kBND_None
        if not ctx.next_punct:
            # SEP1: sentence-initial adverb (Morph.c:148-160). Stateful: the
            # flag is armed by one word and spent by the next.
            if initial_adv:
                cur_bnd = kBND_Sep1
                initial_adv = False
            else:
                initial_adv = (
                    prev_pos == kUndefPOS and cur_pos == kAdv
                    and ctx.next_pos in (kArt, kDet)
                )
                for bnd, matches in _SEP_RULES:
                    if matches(ctx):
                        cur_bnd = bnd
                        break

        adjacent_bnd = wi > 0 and word_had_bnd[wi - 1]
        if cur_bnd != kBND_None and not adjacent_bnd and not word_had_bnd[wi]:
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
    commands: BracketCommands | None = None,
) -> SentenceAssembly:
    """Adapted port of `Collect_FE_Tokens` (`BackEnd.c:3712-4157`).

    `char_overrides`, if given, is a `{word_index: is_spelled}` dict
    (from `_embeddedcmd.scan_bracket_commands`'s `char` support): like
    `nmbr_overrides`, a LATCHED mode tracked as a running flag while
    building this clause's tokens -- when active, an alphabetic word's
    `FEWordToken` is built with `_letters.spell_word(word)` as its
    `phon_str` instead of the normal dictionary/`EngToP` lookup
    (mirrors `kCharByChar` being checked before `GetNextToken`'s
    `tokType` switch, `FrontEnd.c:2010-2015`, i.e. it overrides
    everything else for that token).

    `raw_phon_overrides`, if given, is a `{word_index: phon_str}` dict
    (from `_embeddedcmd.scan_bracket_commands`'s `mode PHON` support):
    the word at that index is a `"RAWPHONn"` placeholder synthesized by
    `scan_bracket_commands` for one raw-phoneme opcode group -- its
    `FEWordToken` is built directly from the recorded `phon_str` here,
    bypassing `make_fe_word_token`'s dictionary/`EngToP`/digit-routing
    entirely (mirrors `CollectPhonemeToken` producing a `kRawPhonemeTok`
    whose `phonStr` is used as-is, `FrontEnd.c:334-345`, and its default
    `SetPOStoVal(tok, kNoun)` when no POS override precedes it,
    `FrontEnd.c:339-345`).

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

    commands = commands or BracketCommands()
    emphasis_overrides = commands.emphasis
    silence_overrides = commands.silences
    pos_overrides = commands.pos
    rate_overrides = commands.rates
    nmbr_overrides = commands.digit_by_digit
    raw_phon_overrides = commands.raw_phonemes
    char_overrides = commands.spelled
    note_overrides = commands.notes

    sa = SentenceAssembly()
    in_index = 1  # mirrors phonBuf_1_In_Index

    def ensure(i: int) -> None:
        while len(sa.phon_buf) <= i:
            sa.phon_buf.append(None)
            sa.ctrl_buf.append(0)
            sa.note_buf.append(0)
            sa.rate_buf.append(0)
            sa.cmd_buf.append(0)

    def queue_command(ctrl_type: int, ctrl_data: int) -> None:
        """QueueCommand (BackEnd.c:3592): park the command in the queue and
        count it against the phoneme slot it was written in front of."""
        ensure(in_index)
        sa.queued_commands.append((ctrl_type, ctrl_data))
        sa.cmd_buf[in_index] += 1

    def flag_current(flag: int) -> None:
        ensure(in_index)
        sa.ctrl_buf[in_index] |= flag

    def store(phon: int) -> int:
        """Stand-in for `Store_Phon_In_PhonBuf_1` (`BackEnd.c:3527`): writes
        `phon` at the current index and advances it, returning the index
        just written."""
        nonlocal in_index
        ensure(in_index)
        sa.phon_buf[in_index] = phon
        written = in_index
        in_index += 1
        return written

    word_initial = True
    word_stress_1_index: int | None = None
    word_stress_2_index: int | None = None
    word_vowel_index: int | None = None
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
    _clause_tokens = []
    _digit_mode = False
    _char_mode = False
    stream = scan_tokens(text)
    for _wi, (word, punct) in enumerate(stream.tokens):
        if nmbr_overrides and _wi in nmbr_overrides:
            _digit_mode = nmbr_overrides[_wi]
        if char_overrides and _wi in char_overrides:
            _char_mode = char_overrides[_wi]
        if raw_phon_overrides and _wi in raw_phon_overrides:
            _clause_tokens.append(FEWordToken(
                word=word,
                phon_str=list(raw_phon_overrides[_wi]),
                from_dictionary=True,
                pos_code1=[kNoun, kUndefPOS, kUndefPOS, kUndefPOS],
                comp_pos1=kHas_Noun,
                is_abbrev=False,
                is_compound_hint=False,
                has_alt=False,
                pos_choice=kNoun,
                trailing_punct=punct,
                phrase_bnd=_PUNCT_TO_BND.get(punct, kBND_None) if punct else kBND_None,
            ))
            continue
        if _char_mode and word.isalpha():

            _clause_tokens.append(FEWordToken(
                word=word,
                phon_str=spell_word(word),
                from_dictionary=True,
                pos_code1=[kNoun, kUndefPOS, kUndefPOS, kUndefPOS],
                comp_pos1=kHas_Noun,
                is_abbrev=False,
                is_compound_hint=False,
                has_alt=False,
                pos_choice=kNoun,
                trailing_punct=punct,
                phrase_bnd=_PUNCT_TO_BND.get(punct, kBND_None) if punct else kBND_None,
            ))
            continue
        _clause_tokens.append(make_fe_word_token(
            word, punct,
            digit_by_digit=_digit_mode or _wi in stream.decimal_frac,
            is_dollar=_wi in stream.dollar,
            is_cent=_wi in stream.cent,
            is_clock=_wi in stream.clock,
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

        word_start_indices.append(in_index)
        flag_current(kWord_Start)
        if _mid_bnd == kBND_Sep6:
            flag_current(_mid_bnd << kSilenceTypeShift)
        # --- EC_rate/EC_ratr embedded rate change (BackEnd.c:1900-1915
        # via Parse_Embedded_Command): recorded at this word's own START
        # position, no extra phoneme (see rate_overrides above).
        if rate_overrides and _wi in rate_overrides:
            ensure(in_index)
            sa.rate_buf[in_index] = rate_overrides[_wi]
        # --- EC_note (BackEnd.c:3679-3683): a packed note word on this word's
        # own start slot; vv.singing is set by build_phoneme_plan.
        if note_overrides and _wi in note_overrides:
            ensure(in_index)
            sa.note_buf[in_index] = note_overrides[_wi]
        # --- pbas/pmod/volm/rset/sync: queued against this word's own start
        # slot, exactly as QueueCommand counts them against
        # phonBuf_1_In_Index (BackEnd.c:3598).
        for _cmd_wi, _ctrl_type, _ctrl_data in commands.queued:
            if _cmd_wi == _wi:
                queue_command(_ctrl_type, _ctrl_data)
        word_initial = True
        sa.is_compound_noun = False
        sa.last_word_index = in_index
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
                    sa.last_stress_2_index = in_index
                    if word_stress_2_index is None:
                        word_stress_2_index = in_index
                else:
                    flag_current(kPrimaryStress)
                    sa.last_stress_1_index = in_index
                    if word_stress_1_index is None:
                        word_stress_1_index = in_index
                    sa.stress_counter += 1
                continue
            if _is_stress2(cur_phon):
                if not sa.is_compound_noun:
                    flag_current(kSecondaryStress)
                    if word_stress_2_index is None:
                        word_stress_2_index = in_index
                sa.last_stress_2_index = in_index
                continue
            if _is_emph_stress(cur_phon):
                flag_current(kEmphaticStress)
                sa.stress_counter += 1
                continue

            # --- ordinary phoneme (BackEnd.c:4041-4061) ---
            flags = PhonFlags2[cur_phon] if 0 <= cur_phon < len(PhonFlags2) else 0
            if flags & kVowelF:
                word_initial = False
                word_vowel_index = in_index
                sa.last_vowel_index = in_index
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
            # kInterr/kRelPro, e.g. "in what way..."). kInterr comes from
            # resolve_pos() via the dictionary, not a fixed word list.
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
                for index in range(sa.last_word_index, in_index):
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
    sa.phon_buf = sa.phon_buf[:in_index]
    sa.ctrl_buf = sa.ctrl_buf[:in_index]

    return sa


def _is_stress1(phon: int) -> bool:
    return phon == _Stress1_


def _is_stress2(phon: int) -> bool:
    return phon == _Stress2_


def _is_emph_stress(phon: int) -> bool:
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

def _phon_flags(phon: int | None) -> int:
    """Bounds-safe PhonFlags2 lookup. phon_buf can (today) contain raw,
    not-yet-decoded placeholder opcodes from LexEntry.phon_str (e.g.
    literal _pRise_/_pFall_ standing in for compound/word markers -- see
    docs/architecture.md) that fall outside PhonFlags2's range; treat
    those the same way the existing ordinary-phoneme branch in
    collect_fe_tokens does (BackEnd.c:472's guard: `0 <= cur_phon <
    len(PhonFlags2)`)."""
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


@cache
def _consonant_cluster_ids() -> frozenset[tuple[int, int]]:
    """`_CONSONANT_CLUSTERS` translated from phoneme names to phoneme ids."""
    name_to_id = {
        'f': _f_, 'v': _v_, 'TH': _TH_, 's': _s_, 'SH': _SH_, 'p': _p_,
        'b': _b_, 't': _t_, 'd': _d_, 'k': _k_, 'g': _g_, 'r': _r_, 'l': _l_,
        'w': _w_, 'm': _m_, 'n': _n_,
    }
    return frozenset((name_to_id[a], name_to_id[b]) for a, b in _CONSONANT_CLUSTERS)


def is_consonant_cluster(consonant_1st: int, consonant_2nd: int) -> bool:
    """BackEnd.c:3086-3167 -- is (consonant_1st, consonant_2nd) a cluster
    that stays together at a syllable boundary?"""
    return (consonant_1st, consonant_2nd) in _consonant_cluster_ids()


def find_next_word_bound(sa: SentenceAssembly, index: int) -> int:
    """BackEnd.c:3177-3186."""
    i = index + 1
    while i < len(sa.ctrl_buf):
        if sa.ctrl_buf[i] & (kBoundryTypeField | kWord_Start):
            break
        i += 1
    return i


def mark_boundary(sa: SentenceAssembly, scan_index: int) -> None:
    """BackEnd.c:3448-3480 -- back-propagate word/prep/verb/term "-End"
    flags from the next boundary-flagged phoneme onto the consonants
    preceding it, stopping at the first vowel."""

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


def mark_syllable(sa: SentenceAssembly, scan_index: int) -> None:
    """BackEnd.c:3381-3448 -- compute this vowel's syllable order
    (first/mid/last/one-or-no syllable in its word) by scanning backward
    and forward to the nearest word boundary for other vowels."""

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


def mark_syllable_start(sa: SentenceAssembly) -> None:
    """BackEnd.c:3193-3379 -- final pass marking each syllable's first
    phoneme with kSyllable_Start, using the syllable-order bits mark_syllable
    already set on each vowel."""

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
                    if is_consonant_cluster(phon_1st, phon_2nd):
                        index -= 2
                    else:
                        index -= 1
                    syllable_index = index
                elif dist == 3:
                    phon_2nd = sa.phon_buf[index - 1]
                    phon_1st = sa.phon_buf[index - 2]
                    if is_consonant_cluster(phon_1st, phon_2nd):
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
                    if is_consonant_cluster(phon_1st, phon_2nd):
                        index -= (dist - 2)
                    else:
                        index -= (dist >> 1)
                    syllable_index = index
        else:
            index += 1


def flag_phon_buf_1(sa: SentenceAssembly) -> None:
    """BackEnd.c:3481-3519 -- final annotation pass over the whole sentence
    buffer: tracks is_Compound_Noun while scanning, calls mark_syllable per
    vowel (Place_Stress_In_Consonant, the consonant branch, is dead code in
    the C reference -- see module docstring), calls mark_boundary per
    phoneme, then mark_syllable_start once at the end."""

    for scan_index in range(len(sa.phon_buf)):
        cur_flags = _phon_flags(sa.phon_buf[scan_index])

        if cur_flags & kVowelF:
            mark_syllable(sa, scan_index)

        mark_boundary(sa, scan_index)

    mark_syllable_start(sa)
