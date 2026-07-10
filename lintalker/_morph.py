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
`Zap_POS`/`SetPOS_FromSuffix`/`DoMorph` (compound-word/suffix-stripping
decomposition) are separate, unported pieces of `Morph.c` -- see
docs/architecture.md.
"""
from __future__ import annotations

from typing import List

from ._consts import (
    kUndefPOS, kNoun, kVerb, kAdj, kAdv, kPrep, kPPron, kRelPro, kDPron,
    kIPron, kRPron, kVaux, kRVaux, kInterj, kConj, kCConj, kInterr, kArt,
    kDet, kInf, kGen, kContr, kQuant, kVPart, kSubjPron, kObjPron,
    kHas_Noun, kHas_Verb, kHas_Adj, kHas_Adv, kHas_Prep, kHas_PPron,
    kHas_RelPro, kHas_DPron, kHas_IPron, kHas_Vaux, kHas_RVaux,
    kHas_Interj, kHas_Conj, kHas_CConj, kHas_Interr, kHas_Art, kHas_Det,
    kHas_Inf, kHas_Gen, kHas_Contr, kHas_Quant, kHas_VPart,
    kHas_SubjPron, kHas_ObjPron,
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
