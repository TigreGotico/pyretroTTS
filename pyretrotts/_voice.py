"""The voice parameter set: the only thing that separates one voice from another."""
from __future__ import annotations

from typing import TypedDict


class Voice(TypedDict, total=False):
    """A DECtalk voice definition.

    Every key is optional; `_backend.init_voice` supplies a default for any
    the voice omits. See docs/creating-voices.md for what each one does.
    """

    AsperW: int
    aCycle: int
    aGain: int
    assertiveness: int
    baselineFall: int
    bwGain1: int
    bwGain2: int
    bwGain3: int
    chorus: int
    customForm: int
    down_Ramp_Step: int
    durCmdStep: int
    emphVoice: int
    f1_Offset: int
    f2_Offset: int
    f3_Offset: int
    f4_BW: int
    f4_Freq: int
    f4p_BW: int
    f4p_Freq: int
    f5p_BW: int
    f5p_Freq: int
    f6p_BW: int
    f6p_Freq: int
    fallAmt: int
    fallAmt1: int
    free1: int
    free2: int
    free3: int
    free4: int
    free5: int
    free6: int
    free7: int
    free8: int
    intonation: int
    locus: int
    loopPoint: int
    markers: list[int]
    nGain: int
    nasalAmt: int
    nasal_BW: int
    nasal_Base: int
    nasal_targ: int
    notes: list[int]
    pitch: int
    pitchCmdStep: int
    pitchRange: int
    portamento: int
    quickness: int
    rate: int
    riseAmt: int
    riseAmt1: int
    rvbDelay: int
    rvbDepth: int
    rvbWetDry: int
    sGain: int
    sPitch: int
    sample: bytes
    sndID: int
    stressDurTime: int
    stressGain: int
    tempo: int
    vGain: int
    vWave: list[int]
    vWave1: list[int]
    vibratoDepth1: int
    vibratoDepth2: int
    vibratoFreq: int
    voice: int
    voiceVers: int
    vowelSync: int
    waveType: int
