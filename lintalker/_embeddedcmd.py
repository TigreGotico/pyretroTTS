"""
Port of the per-frame embedded-control-command dispatcher: DoCtrl (BackEnd.c).

DoCtrl is *not* the FrontEnd.c/EmbeddedCmd.c bracket-delimited text-escape
parser (that parser -- ProcessEmbeddedCommands and friends in
EmbeddedCmd.c -- lives one level up, turning `[[pbas200]]`-style text
escapes -- `[[`/`]]` are the real engine's default command delimiters,
`mt4.h`'s `defaultCmdBeginDelim`/`defaultCmdEndDelim`, changeable at
runtime via the `dlim` command itself -- into vv->PendingCommands bits;
none of FrontEnd.c is ported here). DoCtrl is the *consumer* at the
bottom of the pipeline: once a phoneme plan is built, some phonemes may carry
a count in `user_Cmd_Buf2[phonIndex]` of queued (type, data) control words
sitting in the `CMDQueue` ring buffer, and `say_frame` (BackEnd.c Talk())
calls DoCtrl once per frame to drain and apply that phoneme's share of them.

This is invoked from ``_backend.py``'s ``start_new_phon`` (the ported
Talk()/start-new-phon frame-boundary block) exactly where BackEnd.c calls
``DoCtrl (vv)``.

What's real here (faithfully ported, same shape as DoCtrl):
    C_absMod, C_absPitch, C_relPitch, C_absVol, C_relVol -- all pure
    arithmetic over already-ported state (VP_pitchRange, voiceNaturalPitch,
    VP_baselinePitch, user_Volume via _backend.set_volume/e_midi_to_pitch).

What's stubbed (raises NotImplementedError if actually hit), and why:
    * C_reset -- real DoCtrl calls e_ResetFE_FUNC (FrontEnd.c, not ported)
      then ResetVoice (fsynth.c, not ported in _backend.py under any name --
      see _engine.py's e_reinit_voice/e_reset_params for the same gap).
    * C_voice -- real DoCtrl's case is itself commented out in BackEnd.c
      (`//NewVoice (vv, &vv->zz->IntervalVoices[ctrlData-1]);`) and NewVoice
      is not ported either; this mirrors upstream's own no-op plus a marker
      so a caller that actually relies on voice-switching notices instead of
      silently doing nothing.

No currently-shipped voice/text data in this port emits queued embedded
commands (ctrlCount stays 0 for every test case in test/test_voices.py), so
do_ctrl's body never runs during the existing regression suite -- exercising
it requires hand-populating vv.CMDQueue/vv.user_Cmd_Buf2.
"""
from __future__ import annotations

from ._consts import *
from ._backend import VoiceVar, e_midi_to_pitch, set_volume

__all__ = ["do_ctrl"]


def do_ctrl(vv: VoiceVar) -> None:
    """DoCtrl (BackEnd.c). Drains vv.ctrlCount queued commands from
    vv.CMDQueue starting at vv.cmdBufCount, applying each to vv."""
    while vv.ctrlCount:
        ctrlType, ctrlData = vv.CMDQueue[vv.cmdBufCount]
        vv.cmdBufCount += 1
        vv.ctrlCount -= 1

        if ctrlType == C_absMod:
            if ctrlData < 0:
                ctrlData = 0
            elif ctrlData > (200 << 16):
                ctrlData = 200 << 16
            vv.VP_pitchRange = ctrlData // 100

        elif ctrlType == C_absPitch:
            ctrlData >>= 8
            vv.voiceNaturalPitch = e_midi_to_pitch(ctrlData)
            vv.VP_baselinePitch = vv.voiceNaturalPitch

        elif ctrlType == C_relPitch:
            vv.voiceNaturalPitch = e_midi_to_pitch(
                ((vv.VP_baselinePitch * 12) + kMIDI_50HZ) + (ctrlData >> 8)
            )
            vv.VP_baselinePitch = vv.voiceNaturalPitch

        elif ctrlType == C_absVol:
            set_volume(vv, ctrlData)

        elif ctrlType == C_relVol:
            set_volume(vv, (vv.user_Volume << 8) + ctrlData)

        elif ctrlType == C_reset:
            raise NotImplementedError(
                "do_ctrl: C_reset requires e_ResetFE (FrontEnd.c) and "
                "ResetVoice (fsynth.c), neither of which is ported."
            )

        elif ctrlType == C_voice:
            pass  # upstream DoCtrl's C_voice case body is itself commented out

        # else: unknown/unhandled type -- upstream falls through to `default: break;`
