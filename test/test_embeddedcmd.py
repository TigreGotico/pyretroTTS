"""
Smoke test for the DoCtrl port (lintalker._embeddedcmd.do_ctrl).

DoCtrl (BackEnd.c) drains vv.ctrlCount queued (type, data) commands from
vv.CMDQueue, applying pitch/mod/volume/reset/voice changes to vv. The queue
is normally filled by QueueCommand (BackEnd.c), itself driven by
FrontEnd.c's embedded backtick-command parser (EmbeddedCmd.c) -- neither of
which is ported here (see _embeddedcmd.py's module docstring). That means:

  * There is no way to reach do_ctrl through test_harness's plain-text CLI
    in this port: feeding `` `pbas +100` hello `` (verified empirically
    against ./lintalker-c/bin/Debug/test_harness -- the C reference *does*
    react to it, shifting f1/f2/f3 on frame 0 relative to plain "hello")
    only exercises FrontEnd.c's PendingCommands path, which is a different,
    unported mechanism from CMDQueue/DoCtrl. There is no committed harness
    invocation that fills CMDQueue directly (it requires text tokenization
    machinery this port doesn't have), so there is no bit-exact reference
    trace to pin here the way test_voices.py/test_engtop.py do.
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


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"OK: {t.__name__}")
    print(f"\n{len(tests)} tests passed")
