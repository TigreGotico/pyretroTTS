"""Port of `Morph.c`'s `ResolvePOS` (`Morph.c:358-1006`): resolves each
word's final part-of-speech tag (`FEWordToken.pos_choice`) from its
dictionary candidate list (`pos_code1`/`pos_code2`, `comp_pos1`/
`comp_pos2`) using the surrounding sentence context (previous word's
resolved POS, next/next2/next3 words' candidate POS sets, sentence
position). This replaces the placeholder `pos_code1[0]` selection that
`_assembly.make_fe_word_token` used before this module existed.

Ambiguous words are common in English (the, one word can be a noun, verb,
adjective, ...) and the dictionary lists every plausible tag as a
candidate; only real context disambiguates them (a preposition needs a
different intonation/stress/phrase-boundary treatment than the same word
used as an adverb, etc.). `ResolvePOS` is a large, ordered cascade of
specific rules -- ported here rule-for-rule, in the same order, since the
C code relies on `else if` short-circuiting (multiple rules can match the
same word; only the first one in this exact order applies).

NOT ported: the `hasAlt`/`altChoice` alternate-pronunciation bookkeeping's
interaction with the dictionary's SECOND phoneme string (`phon_hold`) --
`alt_choice` is computed and stored on the token
(`FEWordToken.alt_choice`) but nothing downstream in this port switches
`phon_str` to `phon_hold` based on it yet (no caller reads `alt_choice`).
`Zap_POS`/`SetPOS_FromSuffix` and most of `DoMorph`'s ~30 suffix
functions (compound-word/suffix-stripping decomposition,
`Morph.c:2374-2373`) are separate, unported pieces of `Morph.c` -- see
docs/architecture.md. `try_s_morph` below ports the single most common
case (`Do_S_Morph`/`Store_S_or_Z`, `Morph.c:2306-2322`/`1236-1266`): a
word ending in "S" with no direct dictionary entry, whose root (minus the
"S") IS in the dictionary, gets the root's pronunciation plus a
phonetically-correct `/s/`/`/z/`/`/ɪz/` suffix (the real English
plural/3rd-person-singular allomorphy rule, based on the root's final
phoneme's voicing).
"""
from __future__ import annotations

from typing import List, Optional

from ._consts import (
    kUndefPOS, kNoun, kVerb, kAdj, kAdv, kPrep, kPPron, kRelPro, kDPron,
    kIPron, kRPron, kVaux, kRVaux, kInterj, kConj, kCConj, kInterr, kArt,
    kDet, kInf, kGen, kContr, kQuant, kVPart, kSubjPron, kObjPron,
    kPalatalF, kConsonantF, kVoicedF,
    kHas_Noun, kHas_Verb, kHas_Adj, kHas_Adv, kHas_Prep, kHas_PPron,
    kHas_RelPro, kHas_DPron, kHas_IPron, kHas_Vaux, kHas_RVaux,
    kHas_Interj, kHas_Conj, kHas_CConj, kHas_Interr, kHas_Art, kHas_Det,
    kHas_Inf, kHas_Gen, kHas_Contr, kHas_Quant, kHas_VPart,
    kHas_SubjPron, kHas_ObjPron,
    kNo_suffix, kS_suffix, kES_suffix, kIES_suffix, kED_suffix, kER_suffix,
    kERS_suffix, kEST_suffix, kIED_suffix, kIER_suffix, kIERS_suffix,
    kIEST_suffix, kING_suffix, kINGS_suffix, kMENT_suffix, kMENTS_suffix,
    kIMENT_suffix, kIMENTS_suffix, kBLY_suffix, kLY_suffix, kCALLY_suffix,
    kOR_suffix, kORS_suffix, kIZE_suffix, kIZED_suffix, kIZES_suffix,
    kIZING_suffix, kIZINGS_suffix, kIZER_suffix, kIZERS_suffix,
    kNESS_suffix, kNESSES_suffix, kINESS_suffix, kINESSES_suffix,
    kISM_suffix, kISMS_suffix, kABLE_suffix,
)
from ._phonemes import (
    _l_, _IY_, _IX_, _s_, _t_, _d_, _ER_, _NG_, _z_, _m_, _AX_, _n_, _b_, _EL_,
    _AY_, _IH_,
)


class _POSFlags:
    """One word's compPOS1|compPOS2 bits, unpacked into named booleans --
    mirrors ResolvePOS's `cur_noun`/`cur_verb`/... locals (Morph.c:432-480)."""

    __slots__ = (
        'noun', 'verb', 'adj', 'adv', 'prep', 'ppron', 'relpro', 'dpron',
        'ipron', 'vaux', 'rvaux', 'interj', 'conj', 'cconj', 'interr',
        'art', 'det', 'inf', 'gen', 'contr', 'vpart', 'quant',
        'subjpron', 'objpron',
    )

    def __init__(self, comp_pos: int):
        self.noun = bool(comp_pos & kHas_Noun)
        self.verb = bool(comp_pos & kHas_Verb)
        self.adj = bool(comp_pos & kHas_Adj)
        self.adv = bool(comp_pos & kHas_Adv)
        self.prep = bool(comp_pos & kHas_Prep)
        self.ppron = bool(comp_pos & kHas_PPron)
        self.relpro = bool(comp_pos & kHas_RelPro)
        self.dpron = bool(comp_pos & kHas_DPron)
        self.ipron = bool(comp_pos & kHas_IPron)
        self.vaux = bool(comp_pos & kHas_Vaux)
        self.rvaux = bool(comp_pos & kHas_RVaux)
        self.interj = bool(comp_pos & kHas_Interj)
        self.conj = bool(comp_pos & kHas_Conj)
        self.cconj = bool(comp_pos & kHas_CConj)
        self.interr = bool(comp_pos & kHas_Interr)
        self.art = bool(comp_pos & kHas_Art)
        self.det = bool(comp_pos & kHas_Det)
        self.inf = bool(comp_pos & kHas_Inf)
        self.gen = bool(comp_pos & kHas_Gen)
        self.contr = bool(comp_pos & kHas_Contr)
        self.vpart = bool(comp_pos & kHas_VPart)
        self.quant = bool(comp_pos & kHas_Quant)
        self.subjpron = bool(comp_pos & kHas_SubjPron)
        self.objpron = bool(comp_pos & kHas_ObjPron)


def _pos_count_and_hi_rank(pos_code1, pos_code2):
    """FrontEnd.c:1249-1304 -- POScount1/POScount2/hiRank are derived by
    counting non-kUndefPOS entries in pos_code1/pos_code2 and tracking
    the max value seen across both."""
    count1 = 0
    count2 = 0
    hi_rank = 0
    for v in pos_code1 or ():
        if v != kUndefPOS:
            count1 += 1
            if v > hi_rank:
                hi_rank = v
    for v in pos_code2 or ():
        if v != kUndefPOS:
            count2 += 1
            if v > hi_rank:
                hi_rank = v
    return count1, count2, hi_rank


def resolve_pos(tokens: List) -> None:
    """Mutates `tok.pos_choice`/`tok.alt_choice` for every `FEWordToken`
    in `tokens`, in place, using full-sentence context -- port of
    `ResolvePOS` (`Morph.c:358-1006`). Call once per clause, after all
    tokens are built and before any of them are consumed (mirrors the
    real engine calling this as a separate pass over the whole token
    buffer before `Collect_FE_Tokens` ever runs)."""
    prev_pos = kUndefPOS
    prev2_pos = kUndefPOS
    first_aux = False
    det_count = 100

    n = len(tokens)
    for i, cur_tok in enumerate(tokens):
        pos_count1, pos_count2, hi_rank = _pos_count_and_hi_rank(
            cur_tok.pos_code1, cur_tok.pos_code2
        )
        pos_choice = kUndefPOS
        alt_choice = kUndefPOS

        # FEWordToken has no compPOS1/compPOS2 attribute of that exact
        # name -- comp_pos1/comp_pos2 (see module docstring / _assembly.py).
        if (
            (pos_count1 + pos_count2) == 1
            and not (cur_tok.comp_pos1 & kHas_Prep)
            and not (cur_tok.comp_pos1 & kHas_CConj)
            and not (cur_tok.comp_pos1 & kHas_PPron)
        ):
            pos_choice = cur_tok.pos_code1[0] if cur_tok.pos_code1 else kUndefPOS
        else:
            next_punc = (i + 1 == n)

            next_tok = tokens[i + 1] if i + 1 < n else None
            comp_pos = (cur_tok.comp_pos1 | cur_tok.comp_pos2)
            both_verbs = bool((cur_tok.comp_pos1 & kHas_Verb) and (cur_tok.comp_pos2 & kHas_Verb))

            cur = _POSFlags(comp_pos)
            next_comp = (next_tok.comp_pos1 | next_tok.comp_pos2) if next_tok else 0
            nxt = _POSFlags(next_comp)

            # --- "reed" vs "red" (Morph.c:539-556) ---
            if pos_count1 == 1 and pos_count2 == 1 and both_verbs:
                if (
                    prev_pos == kInf or first_aux or prev_pos == kUndefPOS
                    or prev_pos == kContr or prev_pos == kVaux or prev_pos == kRVaux
                ):
                    alt_choice = 1
                else:
                    alt_choice = 0

            else:
                if (prev_pos in (kVaux, kRVaux)) and cur.verb:
                    pos_choice = kVerb
                elif cur.adj and not cur.noun and prev_pos in (kArt, kDet):
                    pos_choice = kAdj
                elif cur.verb and not cur.rvaux and not cur.vaux and prev_pos in (kVaux, kRVaux) and not next_punc:
                    pos_choice = kVerb
                elif (
                    cur.relpro and cur.conj
                    and not nxt.ppron and not nxt.subjpron and not nxt.contr
                    and prev_pos != kNoun
                    and (prev_pos == kConj or next_punc or nxt.rvaux or nxt.vaux or prev_pos == kPrep)
                ):
                    pos_choice = kDPron
                    if cur_tok.pos_code1:
                        cur_tok.pos_code1[0] = pos_choice
                elif prev_pos == kDPron and cur.verb and cur.noun:
                    pos_choice = kNoun
                elif prev_pos == kRVaux and cur.verb and cur.adj:
                    pos_choice = kAdj
                elif (
                    cur.verb and cur.rvaux
                    and (
                        prev_pos in (kVaux, kRVaux, kSubjPron, kIPron, kPPron, kAdv, kInf)
                        or nxt.verb or next_punc
                    )
                    and not nxt.ppron and not nxt.subjpron and not nxt.ipron
                ):
                    pos_choice = kVerb
                elif cur.vpart and (nxt.cconj or nxt.conj or nxt.prep or nxt.inf):
                    pos_choice = kVPart
                elif cur.vpart and prev_pos == kPPron and next_punc:
                    pos_choice = kVPart
                elif cur.vpart and prev_pos == kVerb:
                    pos_choice = kVPart
                elif (
                    cur.vpart and prev2_pos == kVerb
                    and prev_pos in (kObjPron, kIPron, kDPron, kPPron)
                ):
                    pos_choice = kVPart
                elif cur.prep and not cur.inf and prev_pos == kVerb and next_punc:
                    pos_choice = kVPart
                    if cur_tok.pos_code1:
                        cur_tok.pos_code1[0] = pos_choice
                elif (
                    cur.prep and not cur.inf and prev2_pos == kVerb
                    and prev_pos in (kObjPron, kIPron, kDPron, kPPron)
                ):
                    pos_choice = kVPart
                    if cur_tok.pos_code1:
                        cur_tok.pos_code1[0] = pos_choice
                elif cur.vpart and (nxt.rvaux or nxt.vaux):
                    pos_choice = kVPart
                elif cur.vpart and cur.prep and cur.adj:
                    pos_choice = kPrep
                elif next_punc and cur.prep:
                    pos_choice = kPrep
                elif cur.cconj:
                    pos_choice = kCConj
                elif (prev_pos in (kUndefPOS, kVerb)) and cur.interr:
                    pos_choice = kInterr
                elif prev_pos != kUndefPOS and cur.interr and cur.relpro:
                    pos_choice = kRelPro
                elif cur.conj and cur.adv and (nxt.rvaux or nxt.vaux):
                    pos_choice = kAdv
                elif cur.conj and not next_punc:
                    pos_choice = kConj
                elif (
                    cur.noun and (cur.vaux or cur.rvaux)
                    and (nxt.rvaux or nxt.vaux or prev_pos in (kUndefPOS, kNoun) or nxt.verb)
                ):
                    pos_choice = kVaux if cur.vaux else kRVaux
                elif cur.prep and cur.adj and prev_pos in (kArt, kDet):
                    pos_choice = kPrep
                elif cur.prep and (nxt.art or nxt.det):
                    pos_choice = kPrep
                elif cur.verb and (nxt.det or nxt.art):
                    pos_choice = kVerb
                elif cur.noun and det_count < 2:
                    pos_choice = kNoun
                elif prev_pos == kQuant and cur.noun:
                    pos_choice = kNoun
                elif cur.adv and next_punc:
                    pos_choice = kAdv
                elif prev_pos == kSubjPron and cur.rvaux:
                    pos_choice = kRVaux
                elif prev_pos == kSubjPron and cur.vaux:
                    pos_choice = kVaux
                elif nxt.subjpron and cur.noun:
                    pos_choice = kNoun
                elif cur.noun and (nxt.rvaux or nxt.vaux):
                    pos_choice = kNoun
                elif prev_pos == kInf and cur.verb and not cur.rvaux and not cur.vaux:
                    pos_choice = kVerb
                elif cur.vaux or cur.rvaux:
                    pos_choice = kVaux if cur.vaux else kRVaux
                elif cur.inf and not nxt.det and not nxt.art and not nxt.ipron:
                    pos_choice = kInf
                elif cur.inf and cur.prep:
                    pos_choice = kPrep
                elif prev_pos == kUndefPOS and cur.adj:
                    pos_choice = kAdj
                elif prev_pos != kUndefPOS and cur.relpro:
                    pos_choice = kRelPro
                elif prev_pos == kDet and cur.adj:
                    pos_choice = kAdj
                elif prev_pos == kPrep and cur.adj:
                    pos_choice = kAdj
                elif prev_pos in (kDet, kArt) and cur.noun:
                    pos_choice = kNoun
                elif prev_pos in (kDet, kArt) and cur.adj:
                    pos_choice = kAdj
                elif prev_pos == kAdj and cur.noun:
                    pos_choice = kNoun
                elif prev_pos == kPrep and cur.noun:
                    pos_choice = kNoun
                elif cur.verb and prev_pos == kSubjPron:
                    pos_choice = kVerb
                elif prev_pos == kPPron and cur.verb:
                    pos_choice = kVerb
                elif prev_pos == kAdv and cur.verb:
                    pos_choice = kVerb
                elif prev_pos == kAdj and cur.adj and nxt.noun:
                    pos_choice = kAdj
                elif cur.verb and cur.noun and prev_pos == kConj:
                    pos_choice = kNoun
                elif cur.verb and cur.noun and nxt.verb and not nxt.noun and not nxt.adj:
                    pos_choice = kNoun
                elif cur.verb and cur.noun and prev_pos == kVerb and not next_punc:
                    pos_choice = kNoun
                elif cur.verb and cur.adj and prev_pos in (kConj, kVerb):
                    pos_choice = kAdj
                elif cur.verb and cur.noun and prev_pos == kNoun and not next_punc:
                    pos_choice = kVerb
                elif cur.verb and cur.noun and prev_pos == kNoun:
                    pos_choice = kNoun
                elif cur.verb and not cur.rvaux and not cur.vaux:
                    pos_choice = kVerb
                elif cur.noun:
                    pos_choice = kNoun
                elif cur.adj:
                    pos_choice = kAdj
                elif cur.conj:
                    pos_choice = kConj
                elif cur.prep:
                    pos_choice = kPrep
                else:
                    pos_choice = hi_rank

        det_count = 0 if pos_choice in (kDet, kArt) else det_count + 1

        if cur_tok.has_alt:
            if alt_choice == kUndefPOS:
                alt_choice = 0
                for code in (cur_tok.pos_code2 or ()):
                    if code == pos_choice:
                        alt_choice = 1
            cur_tok.alt_choice = alt_choice

        cur_tok.pos_choice = pos_choice
        # BackEnd.c:3971-3973 -- the POS set that marks a word a "content
        # word" (kContent_Word, gates primary-vs-secondary stress at
        # 3869-3877). Set here (not left to callers) so resolve_pos() is a
        # complete replacement for the old pos_code1[0] placeholder,
        # whether called directly (single-token clauses, tests) or via
        # collect_fe_tokens().
        cur_tok.is_content_word = pos_choice in (
            kNoun, kVerb, kAdj, kAdv, kInterr, kInterj, kVPart, kQuant, kIPron, kRPron,
        )

        if prev_pos == kUndefPOS and pos_choice in (kRVaux, kVaux):
            first_aux = True

        prev2_pos = prev_pos
        prev_pos = pos_choice


def _store_s_or_z(phon_str: list) -> list:
    """Port of `Store_S_or_Z` (`Morph.c:1236-1266`): appends the
    phonetically-correct plural/3rd-person-singular suffix phoneme(s)
    after `phon_str`'s last phoneme, based on its voicing:
    - palatal/sibilant (`_s_`/`_z_`/`_SH_`/`_ZH_`/`_CH_`/`_JH_`-class) -> `_IX_ _z_` (/ɪz/, e.g. "wishes")
    - voiceless consonant -> `_s_` (e.g. "cats")
    - everything else (vowels, voiced consonants) -> `_z_` (e.g. "dogs")
    """
    from ._data import PhonFlags2
    from ._phonemes import _IX_, _z_, _s_

    last_phon = phon_str[-1]
    flags = PhonFlags2[last_phon] if 0 <= last_phon < len(PhonFlags2) else 0
    out = list(phon_str)
    if (flags & kPalatalF) or last_phon == _s_ or last_phon == _z_:
        out.append(_IX_)
        out.append(_z_)
    elif (flags & kConsonantF) and not (flags & kVoicedF):
        out.append(_s_)
    else:
        out.append(_z_)
    return out


def try_s_morph(word: str):
    """Port of `Do_S_Morph` (`Morph.c:2306-2322`), called when `word` (as
    typed, e.g. "DOGS") has no direct dictionary entry: if `word` ends in
    "S" and the root (word minus "S") IS a dictionary entry, returns
    `(phon_str, entry, suffix_type)` -- the root's `_Word_`-prefixed
    phoneme string with the correct `/s/`/`/z/`/`/ɪz/` suffix appended
    (`Store_S_or_Z`), the root's `LexEntry`, and `kS_suffix` (see
    `pos_select_for_suffix` -- `kS_suffix` is one of the two suffix types
    `SetPOS_FromSuffix` does NOT override the POS for, so the caller uses
    the ROOT's real POS codes as-is, matching `SearchAllDicts` populating
    `tok`'s POS fields from the root when `Do_S_Morph` looks it up --
    `WordToPhonemes` does NOT default a morphed word's POS to `kNoun` the
    way it does for a true `EngToP` rule-fallback, `FrontEnd.c:1628-1648`).
    Returns `None` if there's no root hit, so the caller falls back to
    `_engtop.engtop()` exactly as `WordToPhonemes` does when `DoMorph`
    itself fails.
    """
    from ._lexicon import lookup

    if len(word) < 2 or word[-1] != 'S':
        return None
    root = word[:-1]
    entry = lookup(root)
    if entry is None:
        return None
    return _store_s_or_z(list(entry.phon_str)), entry, kS_suffix


# SetPOS_FromSuffix (Morph.c:1027-1189, `!tok->hasAlt` branch only --
# `has_alt` is always False for morphed words in this port, see
# _assembly.make_fe_word_token, so the `hasAlt`-true branch, which
# instead re-Zap_POS's the token and picks between POScode1/POScode2 for
# homograph-style alternate-pronunciation entries, is not reachable and
# not ported). Suffix types with no entry here (kNo_suffix, kS_suffix,
# and the kIZING/kIZINGS/kIZER/kIZERS/kCALLY/kINESS/kINESSES fallback
# codes, which have no `case` in the real switch either) leave the
# root's own dictionary POS untouched.
_POS_FROM_SUFFIX = {
    kIES_suffix: kNoun,
    kED_suffix: kVerb,
    kER_suffix: kNoun,
    kERS_suffix: kNoun,
    kEST_suffix: kAdj,
    kIED_suffix: kVerb,
    kIERS_suffix: kNoun,
    kIEST_suffix: kAdj,
    kING_suffix: kVerb,
    kINGS_suffix: kNoun,
    kMENT_suffix: kNoun,
    kMENTS_suffix: kNoun,
    kIMENT_suffix: kNoun,
    kIMENTS_suffix: kNoun,
    kBLY_suffix: kAdv,
    kLY_suffix: kAdv,
    kOR_suffix: kNoun,
    kORS_suffix: kNoun,
    kIZE_suffix: kVerb,
    kIZED_suffix: kVerb,
    kIZES_suffix: kVerb,
    kNESS_suffix: kNoun,
    kNESSES_suffix: kNoun,
    kISM_suffix: kNoun,
    kISMS_suffix: kNoun,
    kABLE_suffix: kAdj,
}


def pos_select_for_suffix(suffix: int, pos_count1: int, comp_pos1: int):
    """Returns the POS `SetPOS_FromSuffix` forces for `suffix` (or `None`
    if that suffix doesn't override the root's own POS). Two suffixes
    have condition-dependent overrides instead of a fixed one:
    - `kES_suffix`: `kVerb` if the root has EXACTLY one dictionary POS
      candidate and it's `kVerb` (e.g. a root that's unambiguously a
      verb, like "fix" -> "fixes"), else `kNoun`.
    - `kIER_suffix`: the C source's first branch
      (`compPOS1 & kHas_Verb) && (compPOS1 & kNoun)`) is dead code --
      `kNoun == 0`, so `compPOS1 & kNoun` is always `0`/false, matching
      `Morph.c:1077`'s literal (and never-true) condition -- so this
      only ever resolves to `kNoun` (root has a verb candidate, e.g.
      "carry" -> "carrier") or `kAdj` (else, e.g. "happy" -> "happier").
    """
    if suffix == kES_suffix:
        return kVerb if (pos_count1 == 1 and (comp_pos1 & kHas_Verb)) else kNoun
    if suffix == kIER_suffix:
        return kNoun if (comp_pos1 & kHas_Verb) else kAdj
    return _POS_FROM_SUFFIX.get(suffix)


def apply_pos_from_suffix(pos_code1, comp_pos1, pos_code2, comp_pos2, pos_count1, has_alt, suffix):
    """Full port of `SetPOS_FromSuffix` (`Morph.c:1027-1189`), INCLUDING
    the `hasAlt`-true branch that `Zap_POS`s the token and picks between
    `POScode1`/`POScode2` -- reachable in this port for any root that's
    both a DICTIONARY entry with `has_alt=True` (a homograph pair like
    "close"/"lead"/"record") AND matched by a suffix that forces a POS
    (e.g. "close" + "-er" -> "closer", forcing `kNoun`; "close" is a verb
    in `pos_code1` but has `kNoun` in its alt `pos_code2` reading, so the
    real engine picks the ALT reading and zeroes the primary one).

    Returns `(pos_code1, comp_pos1, pos_code2, comp_pos2, alt_choice)`
    -- `alt_choice` is `1` if the ALT (`pos_code2`) reading was picked,
    else `None` (meaning "leave the caller's `alt_choice` default
    alone", matching the C code only ever setting `tok->altChoice = 1`
    in that one branch, never resetting it to `0` here).
    """
    pos_select = pos_select_for_suffix(suffix, pos_count1, comp_pos1)
    if pos_select is None:
        return pos_code1, comp_pos1, pos_code2, comp_pos2, None

    if not has_alt:
        return [pos_select, kUndefPOS, kUndefPOS, kUndefPOS], 1 << pos_select, pos_code2, comp_pos2, None

    pc1 = list(pos_code1) + [kUndefPOS] * (4 - len(pos_code1))
    pc2 = (list(pos_code2) if pos_code2 is not None else [kUndefPOS] * 4)
    pc2 = pc2 + [kUndefPOS] * (4 - len(pc2))
    for j in range(4):
        if pc1[j] == pos_select and pc1[j] != pc2[j]:
            # Zap_POS (Morph.c:1010-1022): clear both POS candidate sets
            return (
                [pos_select, kUndefPOS, kUndefPOS, kUndefPOS], 1 << pos_select,
                [kUndefPOS, kUndefPOS, kUndefPOS, kUndefPOS], 0,
                None,
            )
        elif pc2[j] == pos_select:
            return (
                [kUndefPOS, kUndefPOS, kUndefPOS, kUndefPOS], 0,
                [pos_select, kUndefPOS, kUndefPOS, kUndefPOS], 1 << pos_select,
                1,
            )
    # No match in either candidate set -- the C loop completes without
    # ever calling Zap_POS, leaving the token's POS fields untouched.
    return pos_code1, comp_pos1, pos_code2, comp_pos2, None


# ---------------------------------------------------------------------------
# The rest of DoMorph's suffix functions (Morph.c:1272-2373). Each entry is
# tried longest-suffix-first (an ordering choice, not a port of the real
# engine's `SuffixTab`/`Search_Suffix` trie data, which isn't extracted --
# see module docstring); ties are rare since these suffixes mostly don't
# overlap. `Do_S_Morph` (`try_s_morph`, above) is ALWAYS tried first for any
# word ending in "S", exactly matching `DoMorph`'s own unconditional
# S-before-Search_Suffix order (`Morph.c:2384-2395`) -- the "ERS"/"IERS"/
# "MENTS"/"ORS" cases' own redundant inner S-first-try (`Morph.c:2520-2526`
# etc.) is therefore dead code from this port's perspective (by the time
# suffix detection runs, that exact check has already failed) and is not
# reproduced.
# ---------------------------------------------------------------------------

def _consonant_doubling_adjust(root: str) -> str:
    """Port of `Consonant_Doubling_Adjust` (`Morph.c:1272-1307`): undoes a
    doubled final consonant from the original spelling (`canned` -> `can`,
    `slurring` -> `slur`), except for vowels and S/L/F (which double
    without the mutation being "real", e.g. `stressing` -> `stress`,
    `calling` -> `call`, `sniffing` -> `sniff`)."""
    if not root:
        return root
    end_char = root[-1]
    if end_char in ('A', 'E', 'I', 'O', 'U', 'S', 'L', 'F'):
        return root
    if len(root) > 1 and root[-2] == end_char:
        return root[:-1]
    return root


def _decompose_e_common(stripped_root: str):
    """Port of `Decompose_E_Common` (`Morph.c:1311-1352`): the root left
    after stripping an -ED/-ER/-EST/-ING suffix may need an "E" restored
    (`timed` -> `time`) or a doubled consonant undone (`napped` -> `nap`)
    before it matches a dictionary entry. Returns the matching `LexEntry`
    or `None`."""
    from ._lexicon import lookup

    entry = lookup(stripped_root + 'E')
    if entry is not None:
        return entry
    return lookup(_consonant_doubling_adjust(stripped_root))


def _decompose_i_common(stripped_root: str):
    """Port of `Decompose_I_Common` (`Morph.c:1357-1380`): the root left
    after stripping an -IED/-IER/-IEST suffix ends in a bare "I" that was
    a "Y" in the original spelling (`happier` -> `happi` -> `happy`).
    Returns the matching `LexEntry` or `None`."""
    from ._lexicon import lookup

    return lookup(stripped_root + 'Y')


def _decompose_ness(stripped_root: str):
    """Port of `Do_INESS_Morph`'s root-recovery (`Morph.c:1567-1615`,
    identically for `Do_INESSES_Morph`): the root left after stripping
    -INESS/-INESSES ends in a bare form that was spelled with a "Y" in
    the original word (`sexiness` -> `sexi` -> `sexy`), or, failing that,
    a "-LY" adjective root with the "L" also stripped
    (`loneliness` -> `lonel` -> `lone`, reconstructed as root+"ly"+"ness").
    Returns `(entry, is_ly)` or `None`."""
    from ._lexicon import lookup

    entry = lookup(stripped_root + 'Y')
    if entry is not None:
        return entry, False
    if stripped_root.endswith('L'):
        entry = lookup(stripped_root[:-1])
        if entry is not None:
            return entry, True
    return None


def _decompose_or(stripped_root: str):
    """Port of `Do_OR_Morph`'s root-recovery (`Morph.c:1785-1820`,
    identically for `Do_ORS_Morph`): tries the root with a trailing "E"
    restored first (`senator` -> `senate`), then the bare root
    (`sailor` -> `sail`). Returns the matching `LexEntry` or `None`."""
    from ._lexicon import lookup

    entry = lookup(stripped_root + 'E')
    if entry is not None:
        return entry
    return lookup(stripped_root)


def try_do_morph(word: str):
    """Port of the rest of `DoMorph`'s dispatch (`Morph.c:2396-2373`,
    minus the `Do_S_Morph` special-case already handled by `try_s_morph`)
    for the highest-frequency suffixes. Tried longest-suffix-first (see
    module note above for why this doesn't need the real `SuffixTab`
    data). Returns `(phon_str, entry, suffix_type)` like `try_s_morph`
    (`suffix_type` for `pos_select_for_suffix` -- chosen to match exactly
    which suffix-dispatch branch the real engine's `sufType` variable
    would hold at that point, INCLUDING the cases where a fallback path
    does NOT get its own suffix-table entry and `sufType` stays at the
    outer, more-specific code that has no `SetPOS_FromSuffix` case --
    e.g. the `-IZER`/`-IZERS`/`-IZING`/`-IZINGS`/`-IZED`/`-CALLY`(both
    branches) fallbacks below all keep their OWN suffix code rather than
    "becoming" the plain suffix they resemble, so none of them override
    the root's POS), or `None` if no suffix matched and had a dictionary
    hit for its decomposed root -- the caller falls back to
    `_engtop.engtop()`.

    Ported: -CALLY, -BLY, -LY (`Do_CALLY_Morph`/`Do_BLY_Morph`/
    `Do_LY_Morph`, adds /li/), -IEST/-EST (adds /ɪst/), -IER/-ERS/-ER
    (adds /ɚ/, `_ER_`, optionally + /z/), -IED/-ED (adds /d/, /t/, or
    /ɪd/ by the root's final phoneme's voicing, same rule as
    `Store_S_or_Z`), -INGS/-ING (adds /ɪŋ/, optionally + /z/), -IES/-ES
    (adds the `Store_S_or_Z` suffix after a "Y"->"IE" or "E"/direct-match
    root mutation), -MENT(S)/-IMENT(S) (adds /mənt/, optionally + /s/),
    -ABLE (adds /əbl/), -NESS(ES)/-INESS(ES) (adds /nəs/, optionally +
    /ɪz/, with the same "-Y"/"-LY" root recovery as -IEST), -ISM(S) (adds
    /ɪzəm/, optionally + /z/), -OR(S) (adds /ɚ/ via an "-E"-terminated or
    direct root match, optionally + /z/).

    Also ported: -IZE/-IZED/-IZES/-IZING/-IZINGS/-IZER/-IZERS (adds
    /aɪz/ and the relevant suffix; tried only as a fallback after the
    corresponding plain -ED/-ING/-INGS/-ER/-ERS/-S decompose, matching
    `DoMorph`'s own priority of trying "root+IZE is itself a dict entry"
    first, e.g. "materialize", before falling back to "root minus IZE",
    e.g. "organize" -> "organ").

    NOT ported: true compound-noun decomposition -- see module
    docstring.
    """
    from ._lexicon import lookup

    w = word

    # --- -CALLY / -BLY / -LY (Morph.c:1880-1955, dispatch 2653-2678) ---
    if w.endswith('CALLY') and len(w) > 6:
        # Do_CALLY_Morph: the suffix table entry is "CALLY" (5 chars), but
        # the word's own root already ends in that "C" (magic -> magically
        # splits as "magic" + "ally", not "magi" + "cally") -- stripping
        # only "ALLY" (4 chars) keeps it: magically -> magic.
        entry = lookup(w[:-4])
        if entry is not None:
            return _append(entry.phon_str, [_l_, _IY_]), entry, kCALLY_suffix
        # else fall through to plain -LY (Morph.c:2669-2672: "orig word
        # minus LY" -- e.g. "musically" -> "musical", if that's an entry).
        # sufType stays kCALLY_suffix even on this fallback (Morph.c never
        # reassigns it to kLY_suffix here) -- no case for kCALLY_suffix in
        # SetPOS_FromSuffix, so neither branch overrides the root's POS.
        entry = lookup(w[:-2])
        if entry is not None:
            return _append(entry.phon_str, [_l_, _IY_]), entry, kCALLY_suffix
    if w.endswith('BLY') and len(w) > 3:
        # Do_BLY_Morph: "possibly" -> root + "ble" (possible)
        entry = lookup(w[:-1] + 'E')
        if entry is not None:
            return _append(entry.phon_str, [_l_, _IY_]), entry, kBLY_suffix
        # else "superbly" -> "superb" + LY
        entry = lookup(w[:-2])
        if entry is not None:
            return _append(entry.phon_str, [_l_, _IY_]), entry, kBLY_suffix
    if w.endswith('LY') and len(w) > 2:
        entry = lookup(w[:-2])
        if entry is not None:
            return _append(entry.phon_str, [_l_, _IY_]), entry, kLY_suffix

    # --- -IEST / -EST (Morph.c:2006-2070, dispatch 2538-2585) ---
    if w.endswith('IEST') and len(w) > 4:
        entry = _decompose_i_common(w[:-4])
        if entry is not None:
            return _append(entry.phon_str, [_IX_, _s_, _t_]), entry, kIEST_suffix
        stripped = w[:-4]
        # Root + LY + EST: "loneliest" -> strip "IEST" -> "lonel" -> strip
        # the trailing "L" -> "lone" (Morph.c:2047-2064).
        if stripped.endswith('L'):
            entry = lookup(stripped[:-1])
            if entry is not None:
                return _append(entry.phon_str, [_l_, _IY_, _IX_, _s_, _t_]), entry, kIEST_suffix
    if w.endswith('EST') and len(w) > 3:
        entry = _decompose_e_common(w[:-3])
        if entry is not None:
            return _append(entry.phon_str, [_IX_, _s_, _t_]), entry, kEST_suffix

    # --- -IERS / -IER / -ERS / -ER (Morph.c:1995-2027, dispatch 2512-2578) ---
    if w.endswith('IERS') and len(w) > 4:
        entry = _decompose_i_common(w[:-4])
        if entry is not None:
            return _append(entry.phon_str, [_ER_, _z_]), entry, kIERS_suffix
    if w.endswith('IER') and len(w) > 3:
        entry = _decompose_i_common(w[:-3])
        if entry is not None:
            return _append(entry.phon_str, [_ER_]), entry, kIER_suffix
    if w.endswith('ERS') and len(w) > 3:
        entry = _decompose_e_common(w[:-3])
        if entry is not None:
            return _append(entry.phon_str, [_ER_, _z_]), entry, kERS_suffix
        # Do_IZERS_Morph fallback (Morph.c:1462-1489, dispatch
        # 2568-2578): "organizers" -> "organ" (no root+"IZE" hit).
        # sufType stays kIZERS_suffix (no case in SetPOS_FromSuffix, so
        # no POS override -- only the kERS_suffix success path above
        # gets reassigned to kERS_suffix/kNoun).
        if w.endswith('IZERS') and len(w) > 5:
            entry = lookup(w[:-5])
            if entry is not None:
                return _append(entry.phon_str, [_AY_, _z_, _ER_, _z_]), entry, kIZERS_suffix
    if w.endswith('ER') and len(w) > 2:
        entry = _decompose_e_common(w[:-2])
        if entry is not None:
            return _append(entry.phon_str, [_ER_]), entry, kER_suffix
        # Do_IZER_Morph fallback (Morph.c:1437-1461, dispatch 2555-2566):
        # "organizer" -> "organ". sufType stays kIZER_suffix (no case, no
        # override).
        if w.endswith('IZER') and len(w) > 4:
            entry = lookup(w[:-4])
            if entry is not None:
                return _append(entry.phon_str, [_AY_, _z_, _ER_]), entry, kIZER_suffix

    # --- -IED / -ED (Morph.c:1960-1990, dispatch 2504-2552) ---
    if w.endswith('IED') and len(w) > 3:
        entry = _decompose_i_common(w[:-3])
        if entry is not None:
            return _append(entry.phon_str, [_d_]), entry, kIED_suffix
    if w.endswith('ED') and len(w) > 2:
        entry = _decompose_e_common(w[:-2])
        if entry is not None:
            return _store_ed(list(entry.phon_str)), entry, kED_suffix
        # Do_IZED_Morph fallback (Morph.c:1515-1539, dispatch 2705-2718):
        # "organized" -> "organ". sufType stays kIZED_suffix (no case, no
        # override).
        if w.endswith('IZED') and len(w) > 4:
            entry = lookup(w[:-4])
            if entry is not None:
                return _append(entry.phon_str, [_AY_, _z_, _d_]), entry, kIZED_suffix

    # --- -INGS / -ING (Morph.c:2073-2084, dispatch 2587-2601) ---
    if w.endswith('INGS') and len(w) > 4:
        entry = _decompose_e_common(w[:-4])
        if entry is not None:
            return _append(entry.phon_str, [_IX_, _NG_, _z_]), entry, kINGS_suffix
        # Do_IZINGS_Morph fallback (Morph.c:1410-1436, dispatch
        # 2418-2432): "organizings" -> "organ". sufType stays
        # kIZINGS_suffix (no case, no override).
        if w.endswith('IZINGS') and len(w) > 6:
            entry = lookup(w[:-6])
            if entry is not None:
                return _append(entry.phon_str, [_AY_, _z_, _IH_, _NG_, _z_]), entry, kIZINGS_suffix
    if w.endswith('ING') and len(w) > 3:
        entry = _decompose_e_common(w[:-3])
        if entry is not None:
            return _append(entry.phon_str, [_IX_, _NG_]), entry, kING_suffix
        # Do_IZING_Morph fallback (Morph.c:1384-1409, dispatch 2401-2416):
        # "organizing" -> "organ". sufType stays kIZING_suffix (no case,
        # no override).
        if w.endswith('IZING') and len(w) > 5:
            entry = lookup(w[:-5])
            if entry is not None:
                return _append(entry.phon_str, [_AY_, _z_, _IH_, _NG_]), entry, kIZING_suffix

    # --- -IES / -ES (Morph.c:2178-2302, dispatch 2489-2501/2474-2487) ---
    if w.endswith('IES') and len(w) > 3:
        entry = lookup(w[:-3] + 'Y')  # candies -> candy
        if entry is not None:
            return _store_s_or_z(list(entry.phon_str)), entry, kIES_suffix
        entry = lookup(w[:-2] + 'E')  # calories -> calorie (keep the "I", add E)
        if entry is not None:
            return _store_s_or_z(list(entry.phon_str)), entry, kIES_suffix
    if w.endswith('ES') and len(w) > 2:
        # Do_ES_Morph (Morph.c:2221-2302) checks the STRIPPED ROOT's own
        # ending (word minus "ES"), not the full word's.
        root = w[:-2]
        if root.endswith('SH') or root.endswith('CH'):
            # fish -> fishES ; scratch -> scratchES
            entry = lookup(root)
            if entry is not None:
                return _store_s_or_z(list(entry.phon_str)), entry, kES_suffix
        elif root.endswith('SS'):
            # stress -> stressES
            entry = lookup(root)
            if entry is not None:
                return _store_s_or_z(list(entry.phon_str)), entry, kES_suffix
        elif root.endswith('X'):
            # box -> boxES
            entry = lookup(root)
            if entry is not None:
                return _store_s_or_z(list(entry.phon_str)), entry, kES_suffix
        else:
            entry = lookup(w[:-1])  # keep the "E": house -> houses, name -> names
            if entry is not None:
                return _store_s_or_z(list(entry.phon_str)), entry, kES_suffix
            root = w[:-2]
            if root and root[-1] in ('S', 'Z'):  # bus -> buses, waltz -> waltzes
                entry = lookup(root)
                if entry is not None:
                    return _store_s_or_z(list(entry.phon_str)), entry, kES_suffix

    # --- -IZES / -IZE (Morph.c:1490-1566, dispatch 2700-2703/2720-2732) ---
    # -IZES: Do_S_Morph (via try_s_morph, already tried before this
    # function) covers the "root+IZE is itself a dict entry" case
    # ("materializes" -> "materialize"); this is the Do_IZES_Morph
    # fallback for when it isn't ("organizes" -> "organ").
    if w.endswith('IZES') and len(w) > 4:
        entry = lookup(w[:-4])
        if entry is not None:
            return _append(entry.phon_str, [_AY_, _z_, _IX_, _z_]), entry, kIZES_suffix
    if w.endswith('IZE') and len(w) > 3:
        entry = lookup(w[:-3])
        if entry is not None:
            return _append(entry.phon_str, [_AY_, _z_]), entry, kIZE_suffix

    # --- -IMENTS / -IMENT / -MENTS / -MENT (Morph.c:2086-2177, dispatch
    # 2664-2717) ---
    if w.endswith('IMENTS') and len(w) > 6:
        entry = _decompose_i_common(w[:-6])
        if entry is not None:
            return _append(entry.phon_str, [_m_, _AX_, _n_, _t_, _s_]), entry, kIMENTS_suffix
    if w.endswith('IMENT') and len(w) > 5:
        entry = _decompose_i_common(w[:-5])
        if entry is not None:
            return _append(entry.phon_str, [_m_, _AX_, _n_, _t_]), entry, kIMENT_suffix
    if w.endswith('MENTS') and len(w) > 5:
        entry = lookup(w[:-5])
        if entry is not None:
            return _append(entry.phon_str, [_m_, _AX_, _n_, _t_, _s_]), entry, kMENTS_suffix
    if w.endswith('MENT') and len(w) > 4:
        entry = lookup(w[:-4])
        if entry is not None:
            return _append(entry.phon_str, [_m_, _AX_, _n_, _t_]), entry, kMENT_suffix

    # --- -ABLE (Morph.c:2104-2112, dispatch 2790-2795) ---
    if w.endswith('ABLE') and len(w) > 4:
        entry = _decompose_e_common(w[:-4])
        if entry is not None:
            return _append(entry.phon_str, [_AX_, _b_, _EL_]), entry, kABLE_suffix

    # --- -INESSES / -NESSES / -INESS / -NESS (Morph.c:1567-1728, dispatch
    # 2733-2769) ---
    if w.endswith('INESSES') and len(w) > 7:
        entry = _decompose_ness(w[:-7])
        if entry is not None:
            root_entry, is_ly = entry
            extra = [_l_, _IY_, _n_, _IX_, _s_, _IX_, _z_] if is_ly else [_n_, _IX_, _s_, _IX_, _z_]
            return _append(root_entry.phon_str, extra), root_entry, kINESSES_suffix
    if w.endswith('NESSES') and len(w) > 6:
        entry = lookup(w[:-6])
        if entry is not None:
            return _append(entry.phon_str, [_n_, _IX_, _s_, _IX_, _z_]), entry, kNESSES_suffix
    if w.endswith('INESS') and len(w) > 5:
        entry = _decompose_ness(w[:-5])
        if entry is not None:
            root_entry, is_ly = entry
            extra = [_l_, _IY_, _n_, _IX_, _s_] if is_ly else [_n_, _IX_, _s_]
            return _append(root_entry.phon_str, extra), root_entry, kINESS_suffix
    if w.endswith('NESS') and len(w) > 4:
        entry = lookup(w[:-4])
        if entry is not None:
            return _append(entry.phon_str, [_n_, _IX_, _s_]), entry, kNESS_suffix

    # --- -ISMS / -ISM (Morph.c:1729-1783, dispatch 2779-2789) ---
    if w.endswith('ISMS') and len(w) > 4:
        entry = lookup(w[:-4])
        if entry is not None:
            return _append(entry.phon_str, [_IX_, _z_, _AX_, _m_, _z_]), entry, kISMS_suffix
    if w.endswith('ISM') and len(w) > 3:
        entry = lookup(w[:-3])
        if entry is not None:
            return _append(entry.phon_str, [_IX_, _z_, _AX_, _m_]), entry, kISM_suffix

    # --- -ORS / -OR (Morph.c:1785-1878, dispatch 2680-2692) ---
    if w.endswith('ORS') and len(w) > 3:
        entry = _decompose_or(w[:-3])
        if entry is not None:
            return _append(entry.phon_str, [_ER_, _z_]), entry, kORS_suffix
    if w.endswith('OR') and len(w) > 2:
        entry = _decompose_or(w[:-2])
        if entry is not None:
            return _append(entry.phon_str, [_ER_]), entry, kOR_suffix

    return None


def _append(phon_str, extra):
    return list(phon_str) + list(extra)


def _store_ed(phon_str: list) -> list:
    """Port of `Do_ED_Morph` (`Morph.c:1960-1990`): appends the
    phonetically-correct past-tense suffix after `phon_str`'s last
    phoneme, based on its voicing:
    - the root already ends in `_t_`/`_d_` -> `_IX_ _d_` (/ɪd/, e.g. "wanted")
    - voiceless consonant -> `_t_` (e.g. "walked")
    - everything else (vowels, voiced consonants) -> `_d_` (e.g. "jogged")
    """
    from ._data import PhonFlags2
    from ._phonemes import _IX_, _t_, _d_

    last_phon = phon_str[-1]
    flags = PhonFlags2[last_phon] if 0 <= last_phon < len(PhonFlags2) else 0
    out = list(phon_str)
    if last_phon == _t_ or last_phon == _d_:
        out.append(_IX_)
        out.append(_d_)
    elif (flags & kConsonantF) and not (flags & kVoicedF):
        out.append(_t_)
    else:
        out.append(_d_)
    return out

