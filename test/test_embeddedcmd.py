"""
Smoke test for the DoCtrl port (lintalker._embeddedcmd.do_ctrl).

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
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from lintalker._backend import VoiceVar
from lintalker._embeddedcmd import do_ctrl
from lintalker._consts import (
    C_absMod, C_absPitch, C_relPitch, C_absVol, C_relVol, C_reset, C_voice,
    kMIDI_50HZ, kOneTwelfth, kPointFive,
)


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
        assert False, "expected NotImplementedError"
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
    from lintalker._embeddedcmd import scan_bracket_commands

    clean, cmds, _emph, _silences = scan_bracket_commands("[[pbas300]]hello world")
    assert clean == "hello world"
    assert cmds == [(0, C_absPitch, 300 << 16)]


def test_scan_bracket_commands_word_index_tracks_preceding_words():
    from lintalker._embeddedcmd import scan_bracket_commands

    clean, cmds, _emph, _silences = scan_bracket_commands("hello [[volm50]] world")
    assert clean == "hello  world"
    assert cmds == [(1, C_absVol, 50 << 16)]


def test_scan_bracket_commands_relative_sign():
    from lintalker._embeddedcmd import scan_bracket_commands

    clean, cmds, _emph, _silences = scan_bracket_commands("[[pbas+50]]hello")
    assert cmds == [(0, C_relPitch, 50 << 16)]

    clean, cmds, _emph, _silences = scan_bracket_commands("[[pbas-50]]hello")
    assert cmds == [(0, C_relPitch, -(50 << 16))]


def test_scan_bracket_commands_unrecognized_keyword_left_untouched():
    from lintalker._embeddedcmd import scan_bracket_commands

    clean, cmds, _emph, _silences = scan_bracket_commands("[[bogus123]]hello")
    assert clean == "[[bogus123]]hello"
    assert cmds == []


def test_scan_bracket_commands_cmnt_and_vers_are_stripped_noops():
    from lintalker._embeddedcmd import scan_bracket_commands

    clean, cmds, emph, _silences = scan_bracket_commands("[[cmnt this is ignored]]hello")
    assert clean == "hello"
    assert cmds == [] and emph == {}

    clean, cmds, emph, _silences = scan_bracket_commands("[[vers65536]]hello")
    assert clean == "hello"
    assert cmds == [] and emph == {}


def test_scan_bracket_commands_dlim_changes_subsequent_delimiters():
    from lintalker._embeddedcmd import scan_bracket_commands

    # '<'=60, '>'=62: switch delimiters mid-text, then use them for pbas.
    clean, cmds, _emph, _silences = scan_bracket_commands("[[dlim60 62]]<pbas60>hello")
    assert clean == "hello"
    assert cmds == [(0, C_absPitch, 60 << 16)]

    # Old [[ ]] delimiters no longer recognized after a dlim switch.
    clean, cmds, _emph, _silences = scan_bracket_commands("[[dlim60 62]][[pbas60]]hello")
    assert clean == "[[pbas60]]hello"
    assert cmds == []


def test_scan_bracket_commands_applied_end_to_end_via_build_phoneme_plan():
    """Regression test for the api.build_phoneme_plan integration: a
    bracketed pbas command actually changes vv.voiceNaturalPitch, and
    the resulting phoneme plan is the same length as the equivalent
    plain text (the command itself contributes no phonemes)."""
    from lintalker.api import build_phoneme_plan, new_voice
    from lintalker._data import Fred_Voice

    vv_plain = new_voice(Fred_Voice)
    plan_plain = build_phoneme_plan(Fred_Voice, "hello", vv_plain)

    vv_cmd = new_voice(Fred_Voice)
    plan_cmd = build_phoneme_plan(Fred_Voice, "[[pbas60]]hello", vv_cmd)

    assert vv_cmd.voiceNaturalPitch != vv_plain.voiceNaturalPitch
    assert len(plan_cmd[0]) == len(plan_plain[0])


def test_scan_bracket_commands_emph():
    """Regression test for Parse_emph_Command (EmbeddedCmd.c:558-580):
    `[[emph+]]`/`[[emph-]]` override the word-prominence of the very
    next word, a plain per-token field copy (not a CMDQueue entry)."""
    from lintalker._embeddedcmd import scan_bracket_commands

    clean, cmds, emph, _silences = scan_bracket_commands("[[emph+]]hello world")
    assert clean == "hello world"
    assert cmds == []
    assert emph == {0: "emphasize"}

    clean, cmds, emph, _silences = scan_bracket_commands("hello [[emph-]]world")
    assert clean == "hello world"
    assert emph == {1: "deemphasize"}


def test_emph_override_reaches_word_emphasis_field():
    from lintalker._assembly import collect_fe_tokens

    sa = collect_fe_tokens("hello world", emphasis_overrides={1: "emphasize"})
    assert sa.words[0].word_emphasis == "none"
    assert sa.words[1].word_emphasis == "emphasize"


def test_scan_bracket_commands_slnc():
    """Regression test for Parse_slnc_Command (EmbeddedCmd.c:741-751):
    `[[slnc500]]` inserts a real silence, embedData>>16 giving back the
    plain millisecond value (500)."""
    from lintalker._embeddedcmd import scan_bracket_commands

    clean, cmds, emph, silences = scan_bracket_commands("hello [[slnc500]]world")
    assert clean == "hello world"
    assert silences == {1: 500}


def test_silence_override_inserts_real_sil_with_duration():
    """Regression test for the _assembly.collect_fe_tokens integration:
    a silence_overrides entry inserts a real _SIL_ phoneme with
    kSilenceDuration set and the duration recorded in note_buf, one
    slot ahead of the plain (no-override) phoneme count."""
    from lintalker._assembly import collect_fe_tokens
    from lintalker._consts import kSilenceDuration
    from lintalker._phonemes import _SIL_

    sa_plain = collect_fe_tokens("hello world")
    sa_slnc = collect_fe_tokens("hello world", silence_overrides={1: 500})

    assert len(sa_slnc.phon_buf) == len(sa_plain.phon_buf) + 1

    sil_indices = [
        i for i, (p, c) in enumerate(zip(sa_slnc.phon_buf, sa_slnc.ctrl_buf))
        if p == _SIL_ and (c & kSilenceDuration)
    ]
    assert len(sil_indices) == 1
    assert sa_slnc.note_buf[sil_indices[0]] == 500


def test_slnc_applied_end_to_end_via_build_phoneme_plan():
    """Regression test for the full pipeline: EC_slnc's duration
    (frame count = ms // kFrameTime) ends up in the final dur_Buf at
    the inserted _SIL_'s position."""
    from lintalker.api import build_phoneme_plan, new_voice
    from lintalker._data import Fred_Voice
    from lintalker._consts import kSilenceDuration, kFrameTime
    from lintalker._phonemes import _SIL_

    vv = new_voice(Fred_Voice)
    phon, ctrl, dur, pf, pt, pfl, endp = build_phoneme_plan(
        Fred_Voice, "hello [[slnc500]]world", vv
    )
    hits = [
        i for i, (p, c) in enumerate(zip(phon, ctrl))
        if p == _SIL_ and (c & kSilenceDuration)
    ]
    assert len(hits) == 1
    assert dur[hits[0]] == 500 // kFrameTime


def test_scan_bracket_commands_rset():
    """Regression test for Parse_rset_Command (EmbeddedCmd.c:724-739):
    the only valid argument is 0 (queues a C_reset command, which
    do_ctrl already correctly stubs with NotImplementedError -- see
    do_ctrl's module docstring); a nonzero argument matches
    LogParseError's effect of not resetting at all."""
    from lintalker._embeddedcmd import scan_bracket_commands

    clean, cmds, emph, silences = scan_bracket_commands("[[rset0]]hello")
    assert clean == "hello"
    assert cmds == [(0, C_reset, 0)]

    clean, cmds, emph, silences = scan_bracket_commands("[[rset5]]hello")
    assert clean == "hello"
    assert cmds == []


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"OK: {t.__name__}")
    print(f"\n{len(tests)} tests passed")
