"""
Smoke test for the DoCtrl port (pylintalker._embeddedcmd.do_ctrl).

DoCtrl (BackEnd.c) drains vv.ctrlCount queued (type, data) commands from
vv.CMDQueue, applying pitch/mod/volume/reset/voice changes to vv. The queue
is normally filled by QueueCommand (BackEnd.c), itself driven by
FrontEnd.c's embedded bracket-command parser (EmbeddedCmd.c) -- see
_embeddedcmd.py's scan_bracket_commands for the ported subset (pbas/pmod/
volm) and its module docstring for the rest. That means:

  * There is no way to verify do_ctrl (or scan_bracket_commands) frame-exact
    through test_harness's plain-text CLI in this port. A PRIOR pass of this
    file claimed feeding `` `pbas +100` hello `` (backtick-delimited)
    "verified empirically" that the C reference reacts to it -- that claim
    was a misreading. Direct phoneme decoding of the C reference's output
    for that exact text proved the backtick span was never recognized as a
    command at all: "PBAS" isn't a dictionary word, so the reference spoke
    the bracketed text LITERALLY (spelled letter-by-letter, then "100" read
    as individual digits), producing a real (but irrelevant) f0 difference
    from speaking different words, not from an applied pitch change. Trying
    `[[pbas100]]hello`/`[pbas100]hello` (the delimiters `mt4.h`'s
    defaultCmdBeginDelim/defaultCmdEndDelim source constants actually
    specify) showed no such literal-reading artifact, but also no
    detectable effect on "hello" itself -- this compiled test_harness
    binary shows no evidence of implementing embedded-command recognition
    at all, for any delimiter, via its `-v <voice> <text>` CLI. This is the
    same class of reference-verification blocker documented for the
    Symbols dictionary investigation (docs/architecture.md). There is no
    committed harness invocation that fills CMDQueue directly (it requires
    text tokenization machinery this port doesn't have), so there is no
    bit-exact reference trace to pin here the way test_voices.py/
    test_engtop.py do.
  * This test therefore drives do_ctrl directly with hand-built CMDQueue
    entries and asserts against the arithmetic pinned in BackEnd.c's DoCtrl
    (lines ~272-328), not against a captured C trace.

Also verifies (regression guard) that test_voices.py's existing 68 cases
never hit this path: vv.ctrlCount stays 0 for all of them, since no shipped
voice/text data queues any embedded commands.
"""

import os
import sys

from pylintalker._assembly import collect_fe_tokens
from pylintalker._embeddedcmd import BracketCommands, scan_bracket_commands

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from pylintalker._backend import VoiceVar
from pylintalker._consts import (
    C_absMod,
    C_absPitch,
    C_absVol,
    C_relPitch,
    C_relVol,
    C_reset,
    C_voice,
    kMIDI_50HZ,
    kOneTwelfth,
    kPointFive,
)
from pylintalker._embeddedcmd import do_ctrl


def _midi_to_pitch(midi_note):
    if midi_note < kMIDI_50HZ:
        midi_note = 0
    else:
        midi_note -= kMIDI_50HZ
    return ((midi_note * kOneTwelfth) + kPointFive) >> 16


def _new_vv():
    vv = VoiceVar()
    vv.user_Volume = 128
    return vv


def _queue(vv, *entries):
    """Hand-build vv.CMDQueue/ctrlCount/cmdBufCount like QueueCommand would."""
    vv.cmdBufCount = 0
    vv.ctrlCount = len(entries)
    for i, (ctype, data) in enumerate(entries):
        vv.CMDQueue[i] = (ctype, data)


def test_abs_mod_clips_and_scales():
    vv = _new_vv()
    _queue(vv, (C_absMod, 250 << 16))  # over max -> clipped to 200<<16
    do_ctrl(vv)
    assert vv.VP_pitchRange == (200 << 16) // 100

    vv = _new_vv()
    _queue(vv, (C_absMod, -5 << 16))  # negative -> clipped to 0
    do_ctrl(vv)
    assert vv.VP_pitchRange == 0

    vv = _new_vv()
    _queue(vv, (C_absMod, 50 << 16))
    do_ctrl(vv)
    assert vv.VP_pitchRange == (50 << 16) // 100


def test_abs_pitch_sets_baseline():
    vv = _new_vv()
    midi = 60 << 8  # arbitrary MIDI-ish fixed value, matches ctrlData>>8 usage
    _queue(vv, (C_absPitch, midi << 8))
    do_ctrl(vv)
    expected = _midi_to_pitch(midi)
    assert vv.voiceNaturalPitch == expected
    assert vv.VP_baselinePitch == expected


def test_rel_pitch_uses_current_baseline():
    vv = _new_vv()
    vv.VP_baselinePitch = 100
    ctrl_data = 5 << 8
    _queue(vv, (C_relPitch, ctrl_data))
    do_ctrl(vv)
    expected = _midi_to_pitch(((100 * 12) + kMIDI_50HZ) + (ctrl_data >> 8))
    assert vv.voiceNaturalPitch == expected
    assert vv.VP_baselinePitch == expected


def test_abs_vol_sets_user_volume():
    vv = _new_vv()
    _queue(vv, (C_absVol, 0x8000))  # 0.5 in xxxx.ffff -> 0x80 on 0-256 scale
    do_ctrl(vv)
    assert vv.user_Volume == 0x8000 >> 8


def test_abs_vol_clips_high_and_low():
    vv = _new_vv()
    _queue(vv, (C_absVol, 0x20000))  # > 0x10000 -> clip to 0x0100
    do_ctrl(vv)
    assert vv.user_Volume == 0x0100

    vv = _new_vv()
    _queue(vv, (C_absVol, -1))
    do_ctrl(vv)
    assert vv.user_Volume == 0


def test_rel_vol_is_relative_to_current():
    vv = _new_vv()
    vv.user_Volume = 100
    _queue(vv, (C_relVol, 10 << 8))
    do_ctrl(vv)
    assert vv.user_Volume == (100 << 8) + (10 << 8) >> 8


def test_multiple_queued_commands_drain_in_order():
    vv = _new_vv()
    _queue(vv, (C_absVol, 200 << 8), (C_absMod, 30 << 16))
    do_ctrl(vv)
    assert vv.user_Volume == 200
    assert vv.VP_pitchRange == (30 << 16) // 100
    assert vv.ctrlCount == 0
    assert vv.cmdBufCount == 2


def test_reset_raises_not_implemented():
    vv = _new_vv()
    _queue(vv, (C_reset, 0))
    try:
        do_ctrl(vv)
        raise AssertionError("expected NotImplementedError")
    except NotImplementedError:
        pass


def test_voice_is_a_noop():
    vv = _new_vv()
    _queue(vv, (C_voice, 3))
    do_ctrl(vv)  # should not raise, mirrors upstream's commented-out case body
    assert vv.ctrlCount == 0


def test_regression_voice_set_never_queues_commands():
    """Guard: current test_voices.py voice/text data never sets ctrlCount,
    so do_ctrl is never reached from say_frame today (see start_new_phon in
    _backend.py). This is *not* a claim that do_ctrl works end-to-end through
    the real pipeline -- only that wiring it in cannot regress the existing
    68 voice x text comparisons."""
    vv = _new_vv()
    assert vv.user_Cmd_Buf2 == [0] * len(vv.user_Cmd_Buf2)


def test_scan_bracket_commands_strips_and_parses_pbas():
    bc = scan_bracket_commands("[[pbas300]]hello world")
    assert bc.text == "hello world"
    assert bc.queued == ((0, C_absPitch, 300 << 16),)


def test_scan_bracket_commands_word_index_tracks_preceding_words():
    bc = scan_bracket_commands("hello [[volm50]] world")
    assert bc.text == "hello  world"
    assert bc.queued == ((1, C_absVol, 50 << 16),)


def test_scan_bracket_commands_relative_sign():
    bc = scan_bracket_commands("[[pbas+50]]hello")
    assert bc.queued == ((0, C_relPitch, 50 << 16),)

    bc = scan_bracket_commands("[[pbas-50]]hello")
    assert bc.queued == ((0, C_relPitch, -(50 << 16)),)


def test_scan_bracket_commands_unrecognized_keyword_left_untouched():
    bc = scan_bracket_commands("[[bogus123]]hello")
    assert bc.text == "[[bogus123]]hello"
    assert bc.queued == ()


def test_scan_bracket_commands_cmnt_and_vers_are_stripped_noops():
    bc = scan_bracket_commands("[[cmnt this is ignored]]hello")
    assert bc.text == "hello"
    assert bc.queued == () and bc.emphasis == {}

    bc = scan_bracket_commands("[[vers65536]]hello")
    assert bc.text == "hello"
    assert bc.queued == () and bc.emphasis == {}


def test_scan_bracket_commands_dlim_changes_subsequent_delimiters():
    # '<'=60, '>'=62: switch delimiters mid-text, then use them for pbas.
    bc = scan_bracket_commands("[[dlim60 62]]<pbas60>hello")
    assert bc.text == "hello"
    assert bc.queued == ((0, C_absPitch, 60 << 16),)

    # Old [[ ]] delimiters no longer recognized after a dlim switch.
    bc = scan_bracket_commands("[[dlim60 62]][[pbas60]]hello")
    assert bc.text == "[[pbas60]]hello"
    assert bc.queued == ()


def test_pbas_is_queued_against_the_phoneme_it_precedes():
    """QueueCommand (BackEnd.c:3592-3599) counts a command against the phoneme
    slot it was written in front of, and DoCtrl applies it when synthesis
    reaches that phoneme -- not when the plan is built."""
    from pylintalker._data import Fred_Voice
    from pylintalker.api import build_phoneme_plan, new_voice

    vv_plain = new_voice(Fred_Voice)
    plan_plain = build_phoneme_plan(Fred_Voice, "hello world", vv_plain)

    vv_first = new_voice(Fred_Voice)
    plan_first = build_phoneme_plan(Fred_Voice, "[[pbas60]]hello world", vv_first)

    vv_second = new_voice(Fred_Voice)
    plan_second = build_phoneme_plan(Fred_Voice, "hello [[pbas60]]world", vv_second)

    # The command contributes no phonemes, wherever it sits.
    assert len(plan_first.phonemes) == len(plan_plain.phonemes)
    assert len(plan_second.phonemes) == len(plan_plain.phonemes)

    def command_slots(vv, plan):
        return [i for i in range(len(plan.phonemes)) if vv.user_Cmd_Buf2[i]]

    # Each lands on a different phoneme, and later in the buffer for the later word.
    first_slots = command_slots(vv_first, plan_first)
    second_slots = command_slots(vv_second, plan_second)
    assert len(first_slots) == 1 and len(second_slots) == 1
    assert first_slots[0] < second_slots[0]
    assert command_slots(vv_plain, plan_plain) == []

    # Building the plan queues the command; it does not apply it.
    assert vv_first.voiceNaturalPitch == vv_plain.voiceNaturalPitch


def test_pbas_position_changes_the_audio():
    """Moving a pbas command to a different word must change the output."""
    from pylintalker._data import Fred_Voice
    from pylintalker.api import synthesize_text

    at_first = synthesize_text(Fred_Voice, "[[pbas60]]hello world")
    at_second = synthesize_text(Fred_Voice, "hello [[pbas60]]world")
    plain = synthesize_text(Fred_Voice, "hello world")

    assert at_first != plain
    assert at_second != plain
    assert at_first != at_second


def test_scan_bracket_commands_emph():
    """Regression test for Parse_emph_Command (EmbeddedCmd.c:558-580):
    `[[emph+]]`/`[[emph-]]` override the word-prominence of the very
    next word, a plain per-token field copy (not a CMDQueue entry)."""

    bc = scan_bracket_commands("[[emph+]]hello world")
    assert bc.text == "hello world"
    assert bc.queued == ()
    assert bc.emphasis == {0: "emphasize"}

    bc = scan_bracket_commands("hello [[emph-]]world")
    assert bc.text == "hello world"
    assert bc.emphasis == {1: "deemphasize"}


def test_emph_override_reaches_word_emphasis_field():
    sa = collect_fe_tokens("hello world", BracketCommands(emphasis={1: "emphasize"}))
    assert sa.words[0].word_emphasis == "none"
    assert sa.words[1].word_emphasis == "emphasize"


def test_scan_bracket_commands_slnc():
    """Regression test for Parse_slnc_Command (EmbeddedCmd.c:741-751):
    `[[slnc500]]` inserts a real silence, embedData>>16 giving back the
    plain millisecond value (500)."""

    bc = scan_bracket_commands("hello [[slnc500]]world")
    assert bc.text == "hello world"
    assert bc.silences == {1: 500}


def test_silence_override_inserts_real_sil_with_duration():
    """Regression test for the _assembly.collect_fe_tokens integration:
    a silence_overrides entry inserts a real _SIL_ phoneme with
    kSilenceDuration set and the duration recorded in note_buf, one
    slot ahead of the plain (no-override) phoneme count."""
    from pylintalker._consts import kSilenceDuration
    from pylintalker._phonemes import _SIL_

    sa_plain = collect_fe_tokens("hello world")
    sa_slnc = collect_fe_tokens("hello world", BracketCommands(silences={1: 500}))

    assert len(sa_slnc.phon_buf) == len(sa_plain.phon_buf) + 1

    sil_indices = [
        i for i, (p, c) in enumerate(zip(sa_slnc.phon_buf, sa_slnc.ctrl_buf, strict=True))
        if p == _SIL_ and (c & kSilenceDuration)
    ]
    assert len(sil_indices) == 1
    assert sa_slnc.note_buf[sil_indices[0]] == 500


def test_slnc_applied_end_to_end_via_build_phoneme_plan():
    """Regression test for the full pipeline: EC_slnc's duration
    (frame count = ms // kFrameTime) ends up in the final dur_Buf at
    the inserted _SIL_'s position."""
    from pylintalker._consts import kFrameTime, kSilenceDuration
    from pylintalker._data import Fred_Voice
    from pylintalker._phonemes import _SIL_
    from pylintalker.api import build_phoneme_plan, new_voice

    vv = new_voice(Fred_Voice)
    plan = build_phoneme_plan(
        Fred_Voice, "hello [[slnc500]]world", vv
    )
    hits = [
        i for i, (p, c) in enumerate(zip(plan.phonemes, plan.ctrls, strict=True))
        if p == _SIL_ and (c & kSilenceDuration)
    ]
    assert len(hits) == 1
    assert plan.durs[hits[0]] == 500 // kFrameTime


def test_scan_bracket_commands_rset():
    """Regression test for Parse_rset_Command (EmbeddedCmd.c:724-739):
    the only valid argument is 0 (queues a C_reset command, which
    do_ctrl already correctly stubs with NotImplementedError -- see
    do_ctrl's module docstring); a nonzero argument matches
    LogParseError's effect of not resetting at all."""

    bc = scan_bracket_commands("[[rset0]]hello")
    assert bc.text == "hello"
    assert bc.queued == ((0, C_reset, 0),)

    bc = scan_bracket_commands("[[rset5]]hello")
    assert bc.text == "hello"
    assert bc.queued == ()


def test_scan_bracket_commands_sync():
    """Regression test for Parse_sync_Command (EmbeddedCmd.c:753-765):
    a plain LONG argument (not Fixed-point), queued as C_sync. do_ctrl
    has no case for C_sync at all (matching the real DoCtrl switch's
    own default:break for it -- a genuine no-op in the reference too),
    so applying it must not raise or change any state."""
    from pylintalker._consts import C_sync

    bc = scan_bracket_commands("[[sync12345]]hello")
    assert bc.text == "hello"
    assert bc.queued == ((0, C_sync, 12345),)

    from pylintalker._data import Fred_Voice
    from pylintalker.api import build_phoneme_plan, new_voice

    vv = new_voice(Fred_Voice)
    build_phoneme_plan(Fred_Voice, "[[sync12345]]hello", vv)  # must not raise


def test_scan_bracket_commands_xtnd_wpos():
    """Regression test for Parse_xtnd_Command's wpos selector
    (EmbeddedCmd.c:895-921): the only selector the real dispatch
    implements, setting the next word's POS directly (SetPOStoVal)."""
    from pylintalker._consts import kVerb

    bc = scan_bracket_commands(
        "[[xtnd mtk3 wpos 1]]record it"
    )
    assert bc.text == "record it"
    assert bc.pos == {0: kVerb}


def test_scan_bracket_commands_xtnd_wrong_creator_ignored():
    """A creator code other than kMacInTalkCreator ('mtk3') must be
    silently ignored -- the command isn't directed at this engine."""

    bc = scan_bracket_commands(
        "[[xtnd zzz9 wpos 1]]record it"
    )
    assert bc.text == "record it"
    assert bc.pos == {}


def test_xtnd_wpos_override_reaches_pos_choice():
    """Regression test for the _assembly.collect_fe_tokens integration:
    a pos_overrides entry resolves an otherwise-ambiguous word (e.g.
    "record", noun/verb) to the forced POS."""
    from pylintalker._consts import kVerb

    sa = collect_fe_tokens("record it", BracketCommands(pos={0: kVerb}))
    assert sa.words[0].pos_choice == kVerb


def test_init_rate_params_is_fully_portable():
    """Regression test for _backend.init_rate_params (Init_Rate_Params,
    BackEnd.c:4303-4327): pure fixed-point arithmetic, no missing
    dependency (a previous pass of several docstrings incorrectly
    claimed it needed something unported)."""
    from pylintalker._backend import VoiceVar, init_rate_params
    from pylintalker._consts import kMinRate, kNormal_Speech_Rate

    vv = VoiceVar()
    vv.speech_Rate = kNormal_Speech_Rate
    vv.stressDurTime = 25
    init_rate_params(vv)
    assert vv.rate_Ratio == (kNormal_Speech_Rate << 16) // kNormal_Speech_Rate

    vv.speech_Rate = 10  # below kMinRate
    init_rate_params(vv)
    assert vv.speech_Rate == kMinRate


def test_e_set_speech_rate_no_longer_raises():
    """Regression test: e_set_speech_rate's non-singing branch used to
    raise NotImplementedError, based on the same incorrect assumption
    about Init_Rate_Params -- it now actually changes vv.speech_Rate/
    vv.rate_Ratio."""
    from pylintalker._data import Fred_Voice
    from pylintalker._engine import e_set_speech_rate
    from pylintalker.api import new_voice

    vv = new_voice(Fred_Voice)
    before = vv.rate_Ratio
    e_set_speech_rate(vv, 240 << 16)
    assert vv.speech_Rate == 240
    assert vv.rate_Ratio != before


def test_scan_bracket_commands_rate():
    """Regression test for Parse_rate_Command/ChangeRate
    (EmbeddedCmd.c:691-720): absolute and relative rate changes,
    positioned at the exact word index (unlike pbas/pmod/volm, which
    apply at clause start)."""
    from pylintalker._consts import kMinRate, kNormal_Speech_Rate

    bc = scan_bracket_commands(
        "hello [[rate240]]world"
    )
    assert bc.text == "hello world"
    assert bc.rates == {1: 240}
    assert bc.final_rate == 240

    # Relative change accumulates from initial_rate.
    bc = scan_bracket_commands(
        "[[rate+20]]hello", initial_rate=200
    )
    assert bc.rates == {0: 220}
    assert bc.final_rate == 220

    # Clamped to kMinRate.
    bc = scan_bracket_commands(
        "[[rate-500]]hello", initial_rate=kNormal_Speech_Rate
    )
    assert bc.rates == {0: kMinRate}

    # No rate command -> bc.final_rate is None.
    bc = scan_bracket_commands("hello")
    assert bc.rates == {} and bc.final_rate is None


def test_rate_override_applied_end_to_end_via_build_phoneme_plan():
    """Regression test for the full pipeline: EC_rate's speaking-rate
    change actually produces shorter durations for a faster rate, and
    persists onto vv.speech_Rate for subsequent clauses."""
    from pylintalker._data import Fred_Voice
    from pylintalker.api import build_phoneme_plan, new_voice

    vv_plain = new_voice(Fred_Voice)
    plan_plain = build_phoneme_plan(Fred_Voice, "hello world", vv_plain)

    vv_rate = new_voice(Fred_Voice)
    plan_rate = build_phoneme_plan(Fred_Voice, "[[rate240]]hello world", vv_rate)

    assert vv_rate.speech_Rate == 240
    assert sum(plan_rate.durs) < sum(plan_plain.durs)


def test_scan_bracket_commands_mode_phon_parses_raw_phonemes():
    from pylintalker._rawphon import parse_raw_phonemes, split_into_word_groups

    bc = scan_bracket_commands(
        "hello [[mode PHON]]_1AAt[[mode TEXT]] world"
    )
    assert bc.text == "hello RAWPHON1 world"
    groups = split_into_word_groups(parse_raw_phonemes("_1AAt"))
    assert bc.raw_phonemes == {1: groups[0]}


def test_scan_bracket_commands_mode_phon_multiple_word_groups():
    from pylintalker._rawphon import parse_raw_phonemes, split_into_word_groups

    # Two _Word_-delimited groups inside one PHON span -> two placeholders.
    bc = scan_bracket_commands(
        "[[mode PHON]]_1AAt_2t1IY[[mode TEXT]]"
    )
    groups = split_into_word_groups(parse_raw_phonemes("_1AAt_2t1IY"))
    assert len(groups) == 2
    assert bc.text == "RAWPHON0 RAWPHON1"
    assert bc.raw_phonemes == {0: groups[0], 1: groups[1]}


def test_scan_bracket_commands_mode_phon_unterminated_runs_to_end():
    from pylintalker._rawphon import parse_raw_phonemes, split_into_word_groups

    bc = scan_bracket_commands(
        "hello [[mode PHON]]_1AAt"
    )
    groups = split_into_word_groups(parse_raw_phonemes("_1AAt"))
    assert bc.raw_phonemes == {1: groups[0]}


def test_mode_phon_reaches_word_token_end_to_end():
    bc = scan_bracket_commands(
        "hello [[mode PHON]]_1AAt[[mode TEXT]] world"
    )
    sa = collect_fe_tokens(bc.text, BracketCommands(raw_phonemes=bc.raw_phonemes))
    # tokenize()'s alpha-only fallback filter strips the trailing digit
    # from "RAWPHON1" -> "RAWPHON" (harmless -- the placeholder's WORD
    # STRING is never inspected downstream, only its position/phon_str).
    assert sa.words[1].word == "RAWPHON"
    assert sa.words[1].phon_str == bc.raw_phonemes[1]


def test_mode_phon_applied_end_to_end_via_build_phoneme_plan_does_not_crash():
    from pylintalker._data import Fred_Voice
    from pylintalker.api import build_phoneme_plan, new_voice

    vv = new_voice(Fred_Voice)
    plan = build_phoneme_plan(Fred_Voice, "hello [[mode PHON]]_1AAt[[mode TEXT]] world", vv)
    assert len(plan.phonemes) > 0


def test_scan_bracket_commands_char_toggles_spelling_mode():
    bc = scan_bracket_commands(
        "[[char LTRL]]cab[[char NORM]] home"
    )
    assert bc.text == "cab home"
    assert bc.spelled == {0: True, 1: False}


def test_char_spelling_reaches_word_token_end_to_end():
    from pylintalker._letters import spell_word

    sa = collect_fe_tokens("cab home", BracketCommands(spelled={0: True, 1: False}))
    assert sa.words[0].word == "CAB"
    assert sa.words[0].phon_str == spell_word("CAB")
    assert sa.words[1].word == "HOME"
    assert sa.words[1].phon_str != spell_word("HOME")  # char mode off again


def test_char_mode_latches_until_switched_back():
    from pylintalker._letters import spell_word

    bc = scan_bracket_commands(
        "[[char LTRL]]ab cd[[char NORM]] ef"
    )
    sa = collect_fe_tokens(bc.text, BracketCommands(spelled=bc.spelled))
    assert sa.words[0].phon_str == spell_word("AB")
    assert sa.words[1].phon_str == spell_word("CD")
    assert sa.words[2].phon_str != spell_word("EF")


def test_char_mode_applied_end_to_end_via_build_phoneme_plan_does_not_crash():
    from pylintalker._data import Fred_Voice
    from pylintalker.api import build_phoneme_plan, new_voice

    vv = new_voice(Fred_Voice)
    plan = build_phoneme_plan(Fred_Voice, "[[char LTRL]]cab[[char NORM]] home", vv)
    assert len(plan.phonemes) > 0


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"OK: {t.__name__}")
    print(f"\n{len(tests)} tests passed")
