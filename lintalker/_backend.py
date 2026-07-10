"""
Backend synthesizer: phonemes → 16-bit PCM audio.

Bit-exact port of Say.c + formantSynth.c synthesis pipeline.
Fixed-point arithmetic (kPrecision=13, kOnePtOh=0x2000).
"""
from __future__ import annotations
from typing import Optional
from ._consts import *
from ._phonemes import *
from ._data import *

# ---------------------------------------------------------------------------
# Fixed-point math helpers (mirrors C macros)
# ---------------------------------------------------------------------------

def mMul2(x: int, y: int, s: int = kPrecision) -> int:
    return (x * y) >> s

def mDiv(x: int, y: int, s: int = kPrecision) -> int:
    # C's mDiv(x, y, s) reduces to `x >> s` in the non-float build (Fsynth.h);
    # `y` is unused there. Callers rely on this for scaled averaging, e.g.
    # mDiv(a + b, 2, 1) == (a + b) >> 1.
    return x >> s

def mScale(x: int, s: int = kPrecision) -> int:
    return x << s

def s16(x: int) -> int:
    """Truncate to a signed 16-bit (C `short`) value, matching C wraparound."""
    x &= 0xFFFF
    return x - 0x10000 if x >= 0x8000 else x

def mUnScale(x: int, s: int = kPrecision) -> int:
    return x >> s

def mRatio(x: int, y: int, s: int = kPrecision) -> int:
    return (x << s) // y

def cDiv(x: int, y: int) -> int:
    """C-style integer division: truncates toward zero (unlike Python //)."""
    if y < 0:
        x, y = -x, -y
    if x >= 0:
        return x // y
    return -(-x // y)


def rshort(x: int) -> int:
    """Truncate to signed 16-bit (rShort in C)."""
    x &= 0xFFFF
    if x >= 0x8000:
        x -= 0x10000
    return x


def clip14(x: int) -> int:
    if x > 8191: return 8191
    if x < -8191: return -8191
    return x

# ---------------------------------------------------------------------------
# Frame — per-frame synthesis parameters
# ---------------------------------------------------------------------------

class Frame:
    __slots__ = (
        'Av', 'Af', 'f0',
        'f1', 'f2', 'f3',
        'bw1', 'bw2', 'bw3',
        'FNZ', 'AB',
        'a2', 'a3', 'a4', 'a5', 'a6',
        'phon_Edge', 'marker',
    )

    def __init__(self):
        self.Av = 0
        self.Af = 0
        self.f0 = 0
        self.f1 = 0
        self.f2 = 0
        self.f3 = 0
        self.bw1 = 0
        self.bw2 = 0
        self.bw3 = 0
        self.FNZ = 0
        self.AB = 0
        self.a2 = 0
        self.a3 = 0
        self.a4 = 0
        self.a5 = 0
        self.a6 = 0
        self.phon_Edge = 0
        self.marker = kNoMarker

# ---------------------------------------------------------------------------
# ControlBlock — per-block interpolator state
# ---------------------------------------------------------------------------

class ControlBlock:
    __slots__ = (
        'curP_START_Targ', 'curTarget_TIME', 'curTarget_STEP', 'curTarget_OFFS',
        'HEAD_offs', 'HEAD_step',
        'TAIL_offs', 'TAIL_step', 'TAIL_START_time',
        'onset_END_TIME', 'onset_VAL',
        'nextP_START_Targ', 'prevP_END_Targ', 'curP_END_Targ',
        'ptrToTargetList', 'lastVal',
    )
    def __init__(self):
        self.curP_START_Targ = 0
        self.curTarget_TIME = 0
        self.curTarget_STEP = 0
        self.curTarget_OFFS = 0
        self.HEAD_offs = 0
        self.HEAD_step = 0
        self.TAIL_offs = 0
        self.TAIL_step = 0
        self.TAIL_START_time = 0
        self.onset_END_TIME = 0
        self.onset_VAL = 0
        self.nextP_START_Targ = 0
        self.prevP_END_Targ = 0
        self.curP_END_Targ = 0
        self.ptrToTargetList = None  # type: ignore
        self.lastVal = 0

# ---------------------------------------------------------------------------
# FormantVar — synthesis engine state (per voice instance)
# ---------------------------------------------------------------------------

class FormantVar:
    """Analogous to formantVar struct in Fsynth.h."""

    def __init__(self):
        # Table pointers (set from _data)
        self.EnvelopeListTbl = None
        self.f1FreqTblM = f1FreqTblM
        self.f2FreqTblM = f2FreqTblM
        self.f3FreqTblM = f3FreqTblM
        self.b1FreqTblM = b1FreqTblM
        self.b2FreqTblM = b2FreqTblM
        self.b3FreqTblM = b3FreqTblM
        self.avVolTblM = avVolTblM
        self.f1FreqTblF = f1FreqTblF
        self.f2FreqTblF = f2FreqTblF
        self.f3FreqTblF = f3FreqTblF
        self.b1FreqTblF = b1FreqTblF
        self.b2FreqTblF = b2FreqTblF
        self.b3FreqTblF = b3FreqTblF
        self.avVolTblF = avVolTblF
        self.CtrlBlockTypeTbl = CtrlBlockTypeTbl
        self.DefaultTargTbl = DefaultTargTbl
        self.Rank_FWD_Tbl = Rank_FWD_Tbl
        self.Rank_BKWD_Tbl = Rank_BKWD_Tbl
        self.NoiseIndexTbl = NoiseIndexTbl
        self.Front_Loci_Tbl = Front_Loci_Tbl
        self.Mid_Loci_Tbl = Mid_Loci_Tbl
        self.Back_Loci_Tbl = Back_Loci_Tbl
        self.Male_NoiseAmpTbl = Male_NoiseAmpTbl
        self.Female_NoiseAmpTbl = Female_NoiseAmpTbl
        self.Male_Loci_Tbl = Male_Loci_Tbl
        self.Female_Loci_Tbl = Female_Loci_Tbl
        self.BurstDurTbl = BurstDurTbl
        self.One_Over_X_Tbl = One_Over_X_Tbl
        self.MaleEnvelopeListTbl = MaleEnvTbl
        self.FemaleEnvelopeListTbl = FemaleEnvTbl
        self.a_EnvelopeListTbl = None
        self.a_f1FreqTblM = f1FreqTblM
        self.a_f2FreqTblM = f2FreqTblM
        self.a_f3FreqTblM = f3FreqTblM
        self.a_b1FreqTblM = b1FreqTblM
        self.a_b2FreqTblM = b2FreqTblM
        self.a_b3FreqTblM = b3FreqTblM
        self.a_avVolTblM = avVolTblM

        # Voice-specific table pointers
        self.voice_Formants: list = [None] * 6
        self.voice_av_Tbl = None
        self.voice_NoiseAmp_Tbl = None
        self.voice_Locus_Tbl = None
        self.locusOffset = 0

        # Duration state
        self.cur_Phon_MaxDur_CF = 0
        self.cur_Phon_PctOfMaxDur_CF = 0
        self.cur_Phon_PctOfMaxDur1_CF = 0
        self.cur_Phon_PctOfMaxDur2_CF = 0

        # Transition temps
        self.trans_TIME = 0
        self.trans_LEVEL = 0
        self.trans_TIME_f2 = 0
        self.trans_LEVEL_f2 = 0
        self.f2_HEAD_offset = 0
        self.f2_HEAD_step = 0
        self.f2_TAIL_START_time = 0
        self.f2_TAIL_offset = 0
        self.f2_TAIL_step = 0

        self.big_Bang = False
        self.cur_ControlBlk_Index = 0
        self.controlBlockArray: list[ControlBlock] = [ControlBlock() for _ in range(kNumOfBlocks)]
        self.controlData: list[int] = [0] * kNumOfBlocks
        self.diphEntryArray: list[int] = [0] * 100
        self.next_DiphEntry: int = 0

        # Frame buffers
        self.frameBuf1 = Frame()
        self.frameBuf2 = Frame()
        self.curFrameBuf = kFrame1

        # Glottal source
        self.glotType = kUseHarm
        self.voiceWaveform: list[int] = [0] * 256
        self.voiceWaveform1: list[int] = [0] * 256
        self.SineWave15Ptr = SineWave15

        # Pitch / phase
        self.glotInc = 0
        self.glotInc1 = 0
        self.glotIndex = 0
        self.glotIndex1 = 0

        # Noise
        self.noiseIndex = 0
        self.setNoiseGain = 0

        # Wavesample
        self.SampleWave = None
        self.sampleLength = 0
        self.sampleInc = 0
        self.sampleInc1 = 0
        self.sndIndex = 0
        self.sndIndex1 = 0
        self.loopPoint = 0
        self.sync_On_Vowel = 0
        self.VP_offsetPitch = 0

        # Av interpolator
        self.ampStep = 0
        self.lastAmp = 0
        self.curAmp_Full = 0
        self.curAmp = 0

        # Gains
        self.Af = 0
        self.Av = 0
        self.wavesampleGain = 0

        # Breath
        self.breathGain = 0
        self.breathCycle = 0
        self.breathWave = SineWave  # overwritten in init_voice for breath
        self.SineWavePtr = SineWave  # always SineWave, for vibrato (matches C Engine.c)

        # Voice formant offsets
        self.voiceF1Gain = 0
        self.voiceF2Gain = 0
        self.voiceF3Gain = 0
        self.voiceBWgain1 = 0
        self.voiceBWgain2 = 0
        self.voiceBWgain3 = 0
        self.voiceMinBW = 0
        self.voice_F4_Freq = 0
        self.voice_F4_BW = 0
        self.voiceChorus = 0
        self.voiceNoiseGain = 0
        self.f4_Par = 0
        self.bw4_Par = 0
        self.f5_Par = 0
        self.bw5_Par = 0
        self.f6_Par = 0
        self.bw6_Par = 0
        self.fNP = 0
        self.bNP = 0
        self.nasalBaseFreq = 0
        self.nasalTargFreq = 0
        self.nasalAmt = 0
        self.hfEmph = 1
        self.voice_Num = kMaleTbls
        self.FormTables = None

        # Table pointers for filter computation
        self.CosTblPtr = CosTbl
        self.BcoeffTblPtr = BcoeffTbl
        self.CcoeffTblPtr = CcoeffTbl
        self.TOPtr = TopOctave
        self.NoiseWavePtr = NoiseWave
        self.BandNoisePtr = BandNoise
        self.HPNoisePtr = HPNoise

        # Filter coefficients (per-frame)
        self.Acoeff1 = self.Bcoeff1 = self.Ccoeff1 = 0
        self.Acoeff2 = self.Bcoeff2 = self.Ccoeff2 = 0
        self.Acoeff3 = self.Bcoeff3 = self.Ccoeff3 = 0
        self.Acoeff4 = self.Bcoeff4 = self.Ccoeff4 = 0
        self.Acoeff4p = self.Bcoeff4p = self.Ccoeff4p = 0
        self.Acoeff5 = self.Bcoeff5 = self.Ccoeff5 = 0
        self.Acoeff6 = self.Bcoeff6 = self.Ccoeff6 = 0
        self.AcoeffNZ = self.BcoeffNZ = self.CcoeffNZ = 0
        self.AcoeffNP = self.BcoeffNP = self.CcoeffNP = 0

        # IIR delay taps
        self.Na1 = self.Nb1 = 0
        self.Na2 = self.Nb2 = 0
        self.Na3 = self.Nb3 = 0
        self.Na4 = self.Nb4 = 0
        self.Na5 = self.Nb5 = 0
        self.Na6 = self.Nb6 = 0
        self.Na2a = self.Nb2a = 0
        self.Na3a = self.Nb3a = 0
        self.Na4a = self.Nb4a = 0
        self.NaNZ = self.NbNZ = 0
        self.NaNP = self.NbNP = 0

        # Parallel amp gains
        self.amp2 = self.amp3 = self.amp4 = self.amp5 = self.amp6 = 0
        self.ab = 0

        # Reverb
        self.delayBuffer: list[int] = [0] * kMaxTap
        self.maxRvbDelay = 0
        self.delay_Index = 0
        self.reverbDepth = 0
        self.reverbDelay = 0
        self.addReverb = 0
        self.tapBuffer: list[int] = [0] * kNumOfTaps

        # Misc
        self.lastSample = 0
        self.lastRevbSample = 0
        self.lastnSamp = 0
        self.Is16BitSound = 1
        self.speechVolume = 256  # 1.0 in fixed

# ---------------------------------------------------------------------------
# VoiceVar — top-level TTS engine state
# ---------------------------------------------------------------------------

class VoiceVar:
    """Analogous to voiceVar struct in mt4.h (simplified for synthesis)."""

    def __init__(self):
        self.synthVars = FormantVar()
        self.synthTech = kFormantSynth
        self.bit16_Sound = 1  # 16-bit output

        # Sample buffers
        self.waveBuffers = bytearray()
        self.sampleBuffer1 = bytearray()
        self.sampleBuffer2 = bytearray()
        self.sampleBuffer = self.sampleBuffer1
        self.nextSampBuf = kBuf1
        self.waveIndex = 0
        self.sync_On_Marker = 0

        # Pitch/voice state
        self.VP_pitchRange = 0
        self.voiceNaturalPitch = 0
        self.VP_baselinePitch = 0
        self.last_baseline = 0
        self.portamento = 1
        self.VP_stressGain = 0
        self.VP_assertiveness = 0
        self.VP_baselineFall = 0
        self.VP_quickness = 0
        self.VP_intonation = 0
        self.VP_riseAmt = 0
        self.VP_fallAmt = 0
        self.VP_riseAmt1 = 0
        self.VP_fallAmt1 = 0

        # Phoneme processing state
        self.cur_PhonFlags_CF = 0
        self.prev_PhonFlags_CF = 0
        self.next_PhonFlags_CF = 0
        self.dur_Done_in_Phon_CF = 0
        self.cur_Phon_CF = 0
        self.prev_Phon_CF = 0
        self.prev2_Phon_CF = 0
        self.next_Phon_CF = 0
        self.cur_PhonCtrl_CF = 0
        self.prev_PhonCtrl_CF = 0
        self.prev2_PhonCtrl_CF = 0
        self.next_PhonCtrl_CF = 0
        self.cur_Phon_Dur_CF = 0
        self.cur_PhonBuf_Index_CF = 0
        self.speakState = kSpeakDone
        self.speech_Rate = kNormal_Speech_Rate
        self.rate_Ratio = 0
        self.rate_Ratio_LowGain = 0
        self.phonBuf_1_In_Index = 0
        self.phonBuf_2_In_Index = 0
        self.phonBuf_1_Out_Index = 0
        self.cpuIsFast = 1

        # Table pointers (set from _data)
        self.phonFlags2 = PhonFlags2
        self.maxDurTbl = MaxDurTbl
        self.minDurTbl = MinDurTbl
        self.BoundryDurTbl = BoundryDur
        self.logOf2Tbl = logOf2Tbl
        self.OctFreqTbl = OctFreqTbl
        self.ExpOf2Tbl = ExpOf2Tbl
        self.logToLinPtr = LogToLin
        self.phonPitchTbl = phonPitchTbl

        # Phoneme buffers
        self.phon_Buf_2: list[int] = [0] * kPhonBufSize
        self.phon_Ctrl_Buf_2: list[int] = [0] * kPhonBufSize
        self.dur_Buf: list[int] = [0] * kPhonBufSize
        self.user_Cmd_Buf2: list[int] = [0] * kPhonBufSize
        # CMDQueue (mt4.h CmdElem[kCQsize]): ring buffer of (type, data)
        # embedded-control commands; user_Cmd_Buf2[phonIndex] is a count of
        # how many of these apply at that phoneme, drained by DoCtrl.
        self.CMDQueue: list[tuple[int, int]] = [(0, 0)] * kCQsize
        self.user_Pitch_Buf2: list[int] = [0] * kPhonBufSize
        self.pitch_Buf_Freq: list[int] = [0] * kPhonBufSize
        self.pitch_Buf_Time: list[int] = [0] * kPhonBufSize
        self.pitch_Buf_Flags: list[int] = [0] * kPhonBufSize
        self.pitchBuf_In_Index = 0
        self.pitchBuf_Out_Index = 0
        self.cur_PitchBuf_Time = 0
        self.next_PitchBuf_Time = 0
        self.cur_PitchBuf_Pitch = 0
        self.cur_PitchBuf_Flags = 0
        self.user_Dur_Buf2: list[int] = [0] * kPhonBufSize
        self.user_Note_Buf2: list[int] = [0] * kPhonBufSize
        self.user_Rate_Buf2: list[int] = [0] * kPhonBufSize

        # Pitch state
        self.controlF0 = 0
        self.starting_New_Phon = False
        self.newSentence = False
        self.singing = False
        self.basePitch_Offset = 0
        self.phon_Pitch_Offset = 0
        self.phon_Pitch_Offset_1 = 0
        self.uvPhon_Pitch_Targ = 0
        self.pitch_Clause_StartTime = 10 // kFrameTime
        self.phon_Dur_Delay = 0
        self.baselineFall_START = 0
        self.baselineFall_END = 0
        self.baseline_Start_Offset = 0
        self.baseline_End_Offset = 0
        self.baseLine_Offset = 0
        self.down_Ramp_Step = 0
        self.curRamp = 0
        self.rampSteps: list[int] = [0] * kMaxRamps
        self.pbHold = 0
        self.pbLowGain = 0
        self.low_Gain_CP = 0
        self.pitch_Boundry = 0
        self.stress_Active_Time = 0
        self.stress_Duration = 0
        self.vibrato_Phase1 = 0
        self.vibrato_Phase2 = 0
        self.vibratoFreq = 0
        self.vibratoDepth1 = 0
        self.vibratoDepth2 = 0
        self.pFilter_In_Gain = 0
        self.pFilter_FB_Gain = 0
        self.portamentoAccum = 0
        self.portamentoStep = 0
        self.newPortaTarget = False
        self.start_of_Paragraph_Flag = False
        self.end_Punctuation = 0
        self.FEinputDone = False
        self.user_Volume = 0
        self.ctrlCount = 0
        self.sync_On_Marker = 0
        self.frameMarker = kNoMarker
        self.markerBuf: list[int] = [0] * kMaxMarkers
        self.markerIndex = 0
        self.lastMarkerIndex = 0
        self.singScript = False
        self.nLastWordStart = 0
        self.lastWordStart = 0
        self.numOfNotes = 0
        self.notesBuf: list[int] = [0] * kMaxNotes
        self.lastSongIndex = 0
        self.songIndex = 0
        self.cmdBufCount = 0
        self.pFilter_Out1 = 0
        self.pFilter_Out2 = 0
        self.down_Ramp_Offset = 0
        self.fallRise_Offset = 0
        self.fallRise1_Offset = 0
        self.stress_Target = 0
        self.punct_Offset = 0
        self.next_PitchBuf_Time = 0
        self.phon_Index_Targ = 0
        self.phon_Index_CP = 0
        self.pitchBuf_Out_Index = 0
        self.time_IntoPhon_CP = 0
        self.cur_Phon_Dur_CC = 0
        self.cur_PhonDur_CP = 0
        self.time_IntoPhon_Targ = 0
        self.cur_PitchBuf_Time = 0
        # Save1
        self.pFilter_Out1_Save1 = 0
        self.pFilter_Out2_Save1 = 0
        self.down_Ramp_Offset_Save1 = 0
        self.fallRise_Offset_Save1 = 0
        self.fallRise1_Offset_Save1 = 0
        self.stress_Target_Save1 = 0
        self.punct_Offset_Save1 = 0
        self.next_PitchBuf_Time_Save1 = 0
        self.phon_Index_Targ_Save1 = 0
        self.phon_Index_CP_Save1 = 0
        self.pitchBuf_Out_Index_Save1 = 0
        self.time_IntoPhon_CP_Save1 = 0
        self.cur_Phon_Dur_CC_Save1 = 0
        self.cur_PhonDur_CP_Save1 = 0
        self.time_IntoPhon_Targ_Save1 = 0
        self.cur_PitchBuf_Time_Save1 = 0
        self.cmdBufCount_Save1 = 0
        self.songIndex_Save1 = 0
        self.VP_baselinePitch_Save1 = 0
        # Save2
        self.pFilter_Out1_Save2 = 0
        self.pFilter_Out2_Save2 = 0
        self.down_Ramp_Offset_Save2 = 0
        self.fallRise_Offset_Save2 = 0
        self.fallRise1_Offset_Save2 = 0
        self.stress_Target_Save2 = 0
        self.punct_Offset_Save2 = 0
        self.next_PitchBuf_Time_Save2 = 0
        self.phon_Index_Targ_Save2 = 0
        self.phon_Index_CP_Save2 = 0
        self.pitchBuf_Out_Index_Save2 = 0
        self.time_IntoPhon_CP_Save2 = 0
        self.cur_Phon_Dur_CC_Save2 = 0
        self.cur_PhonDur_CP_Save2 = 0
        self.time_IntoPhon_Targ_Save2 = 0
        self.cur_PitchBuf_Time_Save2 = 0
        self.cmdBufCount_Save2 = 0
        self.songIndex_Save2 = 0
        self.VP_baselinePitch_Save2 = 0

        # Synthesizer function table (used for callbacks)
        self.e_Fill_Next_Frame = None  # type: ignore
        self._i_Last_Snd_Buffer = None  # type: ignore
        self._i_Cur_Sample_Buffer = None  # type: ignore
        self._i_First_Sample_Buffer = None  # type: ignore


# ---------------------------------------------------------------------------
# Coefficient computation (bit-exact)
# ---------------------------------------------------------------------------

def calc_pole_coefficients(zz: FormantVar, pitch: int, bw: int):
    """Compute A/B/C coefficients for a pole (resonator)."""
    if bw > kMaxBandWidth:
        bw = kMaxBandWidth
    if bw < zz.voiceMinBW:
        bw = zz.voiceMinBW
    if pitch < 256:
        pitch = 256
    bw_index = (bw - 50) // 5
    Cc = zz.CcoeffTblPtr[bw_index]
    cos_val = zz.CosTblPtr[pitch - 256]
    Bc = mMul2(zz.BcoeffTblPtr[bw_index], cos_val, kPrecision - 1)
    Ac = kOnePtOh - Bc - Cc
    return Ac, Bc, Cc


def calc_zero_coefficients(zz: FormantVar, pitch: int, bw: int):
    """Compute A/B/C coefficients for a zero (anti-resonator)."""
    if bw > kMaxBandWidth:
        bw = kMaxBandWidth
    bw_index = (bw - 50) // 5
    Cc = zz.CcoeffTblPtr[bw_index]
    cos_val = zz.CosTblPtr[pitch - 256]
    Bc = mMul2(zz.BcoeffTblPtr[bw_index], cos_val, kPrecision - 1)
    # Negate for zero
    Cc = -Cc
    Bc = -Bc
    Ac = kOnePtOh + Bc + Cc
    return Ac, Bc, Cc


def init_fixed_formants(zz: FormantVar):
    """Pre-compute fixed-format coefficients (F4, parallel, nasal pole)."""
    zz.Acoeff4, zz.Bcoeff4, zz.Ccoeff4 = calc_pole_coefficients(
        zz, zz.voice_F4_Freq, zz.voice_F4_BW)

    zz.Acoeff4p, zz.Bcoeff4p, zz.Ccoeff4p = calc_pole_coefficients(
        zz, zz.f4_Par, zz.bw4_Par)
    zz.Acoeff4p = mMul2(zz.Acoeff4p, kNoiseGain, kPrecision)

    zz.Acoeff5, zz.Bcoeff5, zz.Ccoeff5 = calc_pole_coefficients(
        zz, zz.f5_Par, zz.bw5_Par)
    zz.Acoeff5 = mMul2(zz.Acoeff5, kNoiseGain, kPrecision)

    zz.Acoeff6, zz.Bcoeff6, zz.Ccoeff6 = calc_pole_coefficients(
        zz, zz.f6_Par, zz.bw6_Par)
    zz.Acoeff6 = mMul2(zz.Acoeff6, kNoiseGain, kPrecision)

    zz.AcoeffNP, zz.BcoeffNP, zz.CcoeffNP = calc_pole_coefficients(
        zz, zz.fNP, zz.bNP)


# ---------------------------------------------------------------------------
# InitSay — reset synthesizer state
# ---------------------------------------------------------------------------

def init_say(vv: VoiceVar):
    """Reset all synthesis state (mirrors C InitSay)."""
    zz: FormantVar = vv.synthVars
    vv.nextSampBuf = kBuf1
    vv.sampleBuffer = vv.sampleBuffer1
    vv.waveIndex = 0

    vv.e_Fill_Next_Frame = e_fill_next_frame

    zz.glotIndex = 0
    zz.glotIndex1 = 0
    zz.sndIndex = 0
    zz.sndIndex1 = 0
    zz.noiseIndex = 0

    init_fixed_formants(zz)

    zz.Na1 = zz.Nb1 = 0
    zz.Na2 = zz.Nb2 = 0
    zz.Na3 = zz.Nb3 = 0
    zz.Na4 = zz.Nb4 = 0
    zz.Na5 = zz.Nb5 = 0
    zz.Na6 = zz.Nb6 = 0
    zz.Na2a = zz.Nb2a = 0
    zz.Na3a = zz.Nb3a = 0
    zz.Na4a = zz.Nb4a = 0
    zz.NaNZ = zz.NbNZ = 0
    zz.NaNP = zz.NbNP = 0
    zz.lastnSamp = 0
    zz.lastAmp = 0
    zz.lastSample = 0
    zz.lastRevbSample = 0

    # Init reverb
    scale = zz.reverbDelay
    zz.tapBuffer[0] = (kTap4 * zz.reverbDelay) >> 16
    zz.tapBuffer[1] = (kTap5 * zz.reverbDelay) >> 16
    zz.tapBuffer[2] = (kTap6 * zz.reverbDelay) >> 16
    zz.tapBuffer[3] = (kTap8 * zz.reverbDelay) >> 16
    zz.maxRvbDelay = (kMaxTap * zz.reverbDelay) >> 16
    zz.delay_Index = 0
    for i in range(kMaxTap):
        zz.delayBuffer[i] = 0

    zz.addReverb = 1 if (zz.reverbDepth > 0 and vv.cpuIsFast) else 0


# ---------------------------------------------------------------------------
# SayFrame — per-frame sample generation (bit-exact port)
# ---------------------------------------------------------------------------

def say_frame(vv: VoiceVar) -> int:
    """Generate kSampFrameLen samples into the sample buffer.

    Returns the number of sample frames produced (kSampFrameLen).
    """
    zz: FormantVar = vv.synthVars

    # Local copies (mirrors C for speed + bit-exactness)
    local_bit16 = vv.bit16_Sound
    local_sync_marker = vv.sync_On_Marker
    local_VP_pitchRange = vv.VP_pitchRange
    local_VP_baselinePitch = vv.VP_baselinePitch
    local_cur_PhonFlags_CF = vv.cur_PhonFlags_CF

    # Use previous frame (double-buffered)
    if zz.curFrameBuf == kFrame1:
        frame = zz.frameBuf2
    else:
        frame = zz.frameBuf1

    # Reset if output is silent
    if zz.curAmp == 0 and zz.Af == 0:
        zz.glotIndex = 0
        zz.glotIndex1 = 0
        zz.Na1 = zz.Nb1 = 0
        zz.Na2 = zz.Nb2 = 0
        zz.Na3 = zz.Nb3 = 0
        zz.Na4 = zz.Nb4 = 0
        zz.NaNP = zz.NbNP = 0
        zz.NaNZ = zz.NbNZ = 0
        zz.lastAmp = 0

    # Calculate new filter coefficients (F1-F3 cascade)
    zz.Acoeff1, zz.Bcoeff1, zz.Ccoeff1 = calc_pole_coefficients(
        zz, frame.f1 + zz.voiceF1Gain, frame.bw1)
    zz.Acoeff2, zz.Bcoeff2, zz.Ccoeff2 = calc_pole_coefficients(
        zz, frame.f2 + zz.voiceF2Gain, frame.bw2)
    zz.Acoeff3, zz.Bcoeff3, zz.Ccoeff3 = calc_pole_coefficients(
        zz, frame.f3 + zz.voiceF3Gain, frame.bw3)

    # Nasal pole/zero
    if frame.FNZ != zz.fNP:
        no_nasal = False
        zz.AcoeffNZ, zz.BcoeffNZ, zz.CcoeffNZ = calc_zero_coefficients(
            zz, frame.FNZ + zz.nasalAmt, zz.bNP)
        nGain = mRatio(zz.AcoeffNP, zz.AcoeffNZ, 16)
    else:
        no_nasal = True

    # Scale Av, Af, ab
    zz.Av = frame.Av * zz.speechVolume
    zz.Af = (frame.Af * zz.speechVolume) << 2
    zz.ab = frame.AB * zz.speechVolume

    ampBank = (zz.Af > 0) or (zz.ab > 0)

    # Scale a2-a6
    if frame.a2:
        zz.amp2 = frame.a2 << (kPrecision - 5)
        Acoeff2q = mMul2(zz.Acoeff2, zz.amp2, kPrecision)
        ampBank = True
    else:
        zz.amp2 = 0
        zz.Nb2a = zz.Na2a = 0
        Acoeff2q = 0

    if frame.a3:
        zz.amp3 = frame.a3 << (kPrecision - 5)
        Acoeff3q = mMul2(zz.Acoeff3, zz.amp3, kPrecision)
        ampBank = True
    else:
        zz.amp3 = 0
        zz.Nb3a = zz.Na3a = 0
        Acoeff3q = 0

    if frame.a4:
        zz.amp4 = frame.a4 << (kPrecision - 5)
        Acoeff4q = mMul2(zz.Acoeff4p, zz.amp4, kPrecision)
        ampBank = True
    else:
        zz.amp4 = 0
        zz.Nb4a = zz.Na4a = 0
        Acoeff4q = 0

    if frame.a5:
        zz.amp5 = frame.a5 << (kPrecision - 5)
        Acoeff5q = mMul2(zz.Acoeff5, zz.amp5, kPrecision)
        ampBank = True
    else:
        zz.amp5 = 0
        zz.Nb5 = zz.Na5 = 0
        Acoeff5q = 0

    if frame.a6:
        zz.amp6 = frame.a6 << (kPrecision - 5)
        Acoeff6q = mMul2(zz.Acoeff6, zz.amp6, kPrecision)
        ampBank = True
    else:
        zz.amp6 = 0
        zz.Nb6 = zz.Na6 = 0
        Acoeff6q = 0

    # Parallel accumulators
    SampAB = Samp2 = Samp3 = Samp4 = Samp5 = Samp6 = 0

    # Pitch / glottal source
    curF0Pitch = frame.f0

    if zz.glotType == kUseSnd:
        # Wavesample source
        zz.glotInc = (zz.TOPtr[(curF0Pitch + zz.VP_offsetPitch) & 0xFF]
                      >> (3 - ((curF0Pitch + zz.VP_offsetPitch) >> 8)))
        if local_sync_marker:
            zz.sampleInc = 1 << 14
            if zz.voiceChorus:
                tempP = 0x1CD + zz.voiceChorus
                zz.sampleInc1 = (zz.TOPtr[tempP & 0xFF]) >> (5 - (tempP >> 8))
                zz.sampleInc1 >>= 2
            if frame.marker != kNoMarker:
                zz.sndIndex = frame.marker << 14
                zz.sndIndex1 = zz.sndIndex
        else:
            if local_VP_pitchRange == 0:
                curF0Pitch = local_VP_baselinePitch
            zz.sampleInc = (zz.TOPtr[curF0Pitch & 0xFF]) >> (5 - (curF0Pitch >> 8))
            zz.sampleInc >>= 2
            if zz.voiceChorus:
                curF0Pitch += zz.voiceChorus
                if curF0Pitch < 0:
                    curF0Pitch = 0
                zz.sampleInc1 = (zz.TOPtr[curF0Pitch & 0xFF]) >> (5 - (curF0Pitch >> 8))
                zz.sampleInc1 >>= 2
    else:
        # Buzz source
        zz.glotInc = (zz.TOPtr[curF0Pitch & 0xFF]) >> (3 - (curF0Pitch >> 8))
        if zz.voiceChorus:
            curF0Pitch += zz.voiceChorus
            if curF0Pitch < 0:
                curF0Pitch = 0
            zz.glotInc1 = (zz.TOPtr[curF0Pitch & 0xFF]) >> (3 - (curF0Pitch >> 8))

    totalBreathGain = mMul2(zz.breathGain, zz.Av, kPrecision)

    if frame.phon_Edge and (local_cur_PhonFlags_CF & kSonorantF):
        vowel = True
    else:
        vowel = False

    # 3ms Av ramp (32 steps)
    zz.ampStep = ((zz.Av << kAmpStepRes) - zz.lastAmp) >> 3
    zz.curAmp_Full = zz.lastAmp
    zz.lastAmp = mScale(zz.Av, kAmpStepRes)
    ampCtr = 0

    local_waveIndex = vv.waveIndex
    sample_count = kSampFrameLen // 2

    # Pre-size output buffer (16-bit)
    needed = local_waveIndex + sample_count * 4  # 2 samples * 2 bytes
    if len(vv.sampleBuffer) < needed:
        vv.sampleBuffer.extend(b'\x00' * (needed - len(vv.sampleBuffer)))

    for _ in range(sample_count):
        # Av ramp
        if ampCtr < 8:
            zz.curAmp_Full += zz.ampStep
            zz.curAmp = zz.curAmp_Full >> kAmpStepRes
            ampCtr += 1
        else:
            zz.curAmp = zz.Av

        if zz.curAmp > 0 or ampBank:
            # Noise index
            zz.noiseIndex = (zz.noiseIndex + 1) & (kNoiseLen - 1)

            # Glottal excitation
            if zz.curAmp > 0:
                if zz.glotType == kUseSnd and zz.SampleWave is not None:
                    # Wavesample
                    zz.sndIndex = zz.sampleInc + zz.sndIndex
                    sampleIndex = zz.sndIndex >> 14
                    if zz.sync_On_Vowel and vowel:
                        zz.sndIndex = 0
                        sampleIndex = 0
                        vowel = False
                    elif sampleIndex >= zz.sampleLength:
                        sampleIndex = (sampleIndex - zz.sampleLength) + zz.loopPoint
                        zz.sndIndex = sampleIndex << 14
                    vPulse = zz.SampleWave[sampleIndex] - 128
                    sourceC = (vPulse - (vPulse >> 2)) << 4

                    # Chorus
                    if zz.voiceChorus:
                        zz.sndIndex1 = zz.sampleInc1 + zz.sndIndex1
                        sampleIndex = zz.sndIndex1 >> 14
                        if zz.sync_On_Vowel and vowel:
                            zz.sndIndex1 = 0
                            sampleIndex = 0
                            vowel = False
                        elif sampleIndex >= zz.sampleLength:
                            sampleIndex = (sampleIndex - zz.sampleLength) + zz.loopPoint
                            zz.sndIndex1 = sampleIndex << 14
                        vPulse = zz.SampleWave[sampleIndex] - 128
                        vPulse = (vPulse - (vPulse >> 2)) << 4
                        sourceC = mDiv(sourceC + vPulse, 2, 1)

                    sourceC = mMul2(sourceC, zz.wavesampleGain, kPrecision)
                    sourceC = mMul2(sourceC, zz.curAmp, kPrecision)
                else:
                    sourceC = 0

                # Buzz oscillator
                zz.glotIndex = (zz.glotInc + zz.glotIndex) & 0xFFFFFF
                cycleIndex = zz.glotIndex >> 16
                vPulse = zz.voiceWaveform[cycleIndex]

                if zz.voiceChorus and zz.glotType != kUseSnd:
                    zz.glotIndex1 = (zz.glotInc1 + zz.glotIndex1) & 0xFFFFFF
                    cycleIndex = zz.glotIndex1 >> 16
                    vPulse1 = zz.voiceWaveform1[cycleIndex]
                    vPulse = mDiv(vPulse + vPulse1, 2, 1)

                sourceC = mMul2(vPulse, zz.curAmp, kPrecision) + sourceC
            else:
                # No glottal
                sourceC = 0
                zz.lastnSamp = 0
                zz.glotIndex = 0
                zz.glotIndex1 = 0
                zz.lastAmp = 0
                vPulse = 0

            # Cascade filter branch
            if zz.curAmp > 0 or zz.Af > 0:
                # Aspiration
                asperation = zz.BandNoisePtr[zz.noiseIndex] - 128
                sourceC += mMul2(asperation, zz.Af, kPrecision)

                # Breath
                if totalBreathGain > 0 and cycleIndex > zz.breathCycle:
                    breath = zz.breathWave[zz.noiseIndex] - 128
                    sourceC += mMul2(breath, totalBreathGain, kPrecision - 2)

                if no_nasal:
                    SampV = sourceC
                else:
                    # Nasal zero
                    SampV = sourceC + mUnScale(
                        zz.BcoeffNZ * zz.NaNZ + zz.CcoeffNZ * zz.NbNZ, kPrecision)
                    zz.NbNZ = zz.NaNZ
                    zz.NaNZ = sourceC
                    SampV = mMul2(nGain, SampV, 16)

                    # Nasal pole
                    SampV = SampV + mUnScale(
                        zz.BcoeffNP * zz.NaNP + zz.CcoeffNP * zz.NbNP, kPrecision)
                    zz.NbNP = zz.NaNP
                    zz.NaNP = SampV

                # F1
                _f1_raw = zz.Acoeff1 * SampV + zz.Bcoeff1 * zz.Na1 + zz.Ccoeff1 * zz.Nb1
                _after_f1 = mUnScale(_f1_raw, kPrecision)
                zz.Nb1 = zz.Na1
                zz.Na1 = SampV = _after_f1

                # F2
                _f2_raw = zz.Acoeff2 * SampV + zz.Bcoeff2 * zz.Na2 + zz.Ccoeff2 * zz.Nb2
                _after_f2 = mUnScale(_f2_raw, kPrecision)
                zz.Nb2 = zz.Na2
                zz.Na2 = SampV = _after_f2

                # F3
                _f3_raw = zz.Acoeff3 * SampV + zz.Bcoeff3 * zz.Na3 + zz.Ccoeff3 * zz.Nb3
                _after_f3 = mUnScale(_f3_raw, kPrecision)
                zz.Nb3 = zz.Na3
                zz.Na3 = SampV = _after_f3

                # F4 cascade
                _f4_raw = zz.Acoeff4 * SampV + zz.Bcoeff4 * zz.Na4 + zz.Ccoeff4 * zz.Nb4
                _after_f4 = mUnScale(_f4_raw, kPrecision)
                zz.Nb4 = zz.Na4
                zz.Na4 = SampV = _after_f4

                pass
            else:
                SampV = 0


            # Parallel filter branch
            nPulse = zz.NoiseWavePtr[zz.noiseIndex] - 128
            sourceP = mMul2(nPulse, zz.voiceNoiseGain, kPrecision)

            if zz.ab > 0:
                SampAB = mMul2(sourceP, zz.ab, kPrecision - 1)

            if zz.amp2 > 0:
                Samp2 = mUnScale(
                    Acoeff2q * sourceP + zz.Bcoeff2 * zz.Na2a + zz.Ccoeff2 * zz.Nb2a,
                    kPrecision)
                zz.Nb2a = zz.Na2a
                zz.Na2a = Samp2

            if zz.amp3 > 0:
                Samp3 = mUnScale(
                    Acoeff3q * sourceP + zz.Bcoeff3 * zz.Na3a + zz.Ccoeff3 * zz.Nb3a,
                    kPrecision)
                zz.Nb3a = zz.Na3a
                zz.Na3a = Samp3

            if zz.amp4 > 0:
                Samp4 = mUnScale(
                    Acoeff4q * sourceP + zz.Bcoeff4p * zz.Na4a + zz.Ccoeff4p * zz.Nb4a,
                    kPrecision)
                zz.Nb4a = zz.Na4a
                zz.Na4a = Samp4

            if zz.amp5 > 0:
                Samp5 = mUnScale(
                    Acoeff5q * sourceP + zz.Bcoeff5 * zz.Na5 + zz.Ccoeff5 * zz.Nb5,
                    kPrecision)
                zz.Nb5 = zz.Na5
                zz.Na5 = Samp5

            if zz.amp6 > 0:
                Samp6 = mUnScale(
                    Acoeff6q * sourceP + zz.Bcoeff6 * zz.Na6 + zz.Ccoeff6 * zz.Nb6,
                    kPrecision)
                zz.Nb6 = zz.Na6
                zz.Na6 = Samp6

            # Sum parallel branches
            Samp = SampAB - Samp3 + Samp4 - Samp5 + Samp6 - Samp2

            # Combine cascade + parallel
            nSamp = SampV + Samp

            # Emphasis (radiation impedance)
            if zz.hfEmph:
                nSamp += nSamp >> 2
                tSamp = nSamp - (zz.lastSample - (zz.lastSample >> 2))
                zz.lastSample = nSamp
                nSamp = tSamp + (nSamp >> 1)

            # Reverb
            if zz.addReverb:
                zz.delayBuffer[zz.delay_Index] = nSamp
                accumL = 0
                for tCntr in range(4):
                    reflect_Index = zz.delay_Index - zz.tapBuffer[tCntr]
                    if reflect_Index < 0:
                        reflect_Index += zz.maxRvbDelay
                    accumL += zz.delayBuffer[reflect_Index]

                nSamp += ((accumL + zz.lastRevbSample) >> 3) * zz.reverbDepth >> kPrecision
                zz.lastRevbSample = accumL

                zz.delay_Index += 1
                if zz.delay_Index >= zz.maxRvbDelay:
                    zz.delay_Index = 0

            # Clip
            nSamp = clip14(nSamp)

            # Output interpolation (11kHz → 22kHz)
            wByte = (((nSamp - zz.lastnSamp) >> 1) + zz.lastnSamp) << 2
            # 16-bit output
            offset = local_waveIndex * 2
            vv.sampleBuffer[offset:offset + 2] = wByte.to_bytes(2, 'little', signed=True)
            local_waveIndex += 1

            wByte = nSamp << 2
            offset = local_waveIndex * 2
            vv.sampleBuffer[offset:offset + 2] = wByte.to_bytes(2, 'little', signed=True)
            local_waveIndex += 1

            zz.lastnSamp = nSamp

        else:
            # Silence
            zz.lastnSamp = 0
            zz.glotIndex = 0
            zz.glotIndex1 = 0
            zz.lastAmp = 0

            # Write 2 silent 16-bit samples
            for _ in range(2):
                offset = local_waveIndex * 2
                vv.sampleBuffer[offset:offset + 2] = b'\x00\x00'
                local_waveIndex += 1

    vv.waveIndex = local_waveIndex
    return sample_count * 2  # 112 samples produced


# ---------------------------------------------------------------------------
# FillSampBuf — fill the sample buffer (kSampBufGroup frames)
# ---------------------------------------------------------------------------

def fill_samp_buf(vv: VoiceVar):
    """Fill one buffer of samples (20 frames = 100ms)."""
    vv.waveIndex = 0
    for _ in range(kSampBufGroup):
        if vv.speakState == kSpeakLastFrame:
            say_frame(vv)
            break
        say_frame(vv)
        if vv.e_Fill_Next_Frame:
            vv.e_Fill_Next_Frame(vv)


def synth_fill_next_samp_buffer(vv: VoiceVar):
    """Top-level entry: fill next buffer and invoke callback."""
    fill_samp_buf(vv)
    if vv._i_Cur_Sample_Buffer:
        vv._i_Cur_Sample_Buffer(vv, vv.sampleBuffer, vv.waveIndex)


# ---------------------------------------------------------------------------
# Init voice from voiceData dict
# ---------------------------------------------------------------------------

def init_voice(vv: VoiceVar, vd: dict):
    """Configure synthesizer from a voice data dict (from _data.py)."""
    zz: FormantVar = vv.synthVars

    zz.Is16BitSound = vv.bit16_Sound

    # Voice type (must be set early, used below)
    zz.voice_Num = vd.get('voice', kMaleTbls)

    # Glottal source type (matches C Say.c InitVoice)
    zz.glotType = vd.get('waveType', kUseHarm)
    vv.sync_On_Marker = False

    # Pitch / rate
    zz.vd_pitch = vd['pitch']
    vv.voiceNaturalPitch = e_hz_to_pitch(vv, vd['pitch'])

    # sPitch / sGain override for waveType 1/2 (kUseSnd / kUseSyncSnd)
    wt = vd.get('waveType', kUseHarm)
    if wt == kUseSnd or wt == 2:  # kUseSnd (1) or kUseSyncSnd (2)
        temp_pitch = vv.voiceNaturalPitch  # save hz-based pitch
        vv.voiceNaturalPitch = e_midi_to_pitch(vd.get('sPitch', 0) << 8)
        zz.VP_offsetPitch = temp_pitch - vv.voiceNaturalPitch
        if wt == 2:  # kUseSyncSnd
            vv.sync_On_Marker = True
            zz.glotType = kUseSnd
        else:
            vv.sync_On_Marker = False
        zz.wavesampleGain = mRatio(vd.get('sGain', 0), 100, kPrecision)

        # InsertSample (Say.c:1471-1499): the embedded sample data (in
        # _data.py, header already stripped -- see that file) drives the
        # actual glottal-source waveform for these voices; sampleLength
        # comes from the header itself, which extraction already parsed
        # into the byte count of vd['sample']. Without this, zz.SampleWave
        # stays None and say_frame's kUseSnd branch (line ~836) silently
        # falls through to sourceC=0 (no wavesample contribution at all),
        # which happened to leave every frame-level CONTROL value
        # (f0/formants/amplitude) matching the C reference exactly while
        # the actual synthesized PCM samples were completely wrong --
        # confirmed by a genuine sample-value comparison (not just frame
        # count), which no test in this port had performed until this bug
        # was found.
        zz.SampleWave = vd.get('sample')
        zz.sampleLength = len(zz.SampleWave) if zz.SampleWave else 0
        zz.loopPoint = vd.get('loopPoint', 0)
        zz.sync_On_Vowel = vd.get('vowelSync', 0)
    else:
        zz.VP_offsetPitch = 0
        zz.wavesampleGain = 0
        zz.SampleWave = None
        zz.sampleLength = 0
        zz.loopPoint = 0
        zz.sync_On_Vowel = 0

    # C sets VP_baselinePitch in Init_Pitch_Params/Talk(), which run *after*
    # InitVoice — so it picks up the final voiceNaturalPitch (post sPitch
    # override for kUseSnd/kUseSyncSnd voices), not the pre-override hz value.
    vv.VP_baselinePitch = vv.voiceNaturalPitch

    zz.voiceNoiseGain = 0  # will be set by setVolume

    # Breath gain (matches C Say.c InitVoice)
    temp_long = mRatio(vd['aGain'], 100, kPrecision)
    zz.breathGain = mMul2(temp_long, kNoiseGain, kPrecision)
    zz.breathCycle = vd.get('aCycle', 0)
    aw = vd.get('AsperW', 0)
    if aw == 0:
        zz.breathWave = BandNoise
    elif aw == 1:
        zz.breathWave = NoiseWave
    else:
        zz.breathWave = HPNoise
    zz.voiceChorus = vd.get('chorus', 0)
    zz.voiceF1Gain = vd.get('f1_Offset', 0)
    zz.voiceF2Gain = vd.get('f2_Offset', 0)
    zz.voiceF3Gain = vd.get('f3_Offset', 0)

    zz.voice_F4_BW = vd.get('f4_BW', 250)
    f4_freq = vd.get('f4_Freq', 780)
    if f4_freq > 800:
        zz.voice_F4_Freq = e_hz_to_pitch(vv, f4_freq)
    else:
        zz.voice_F4_Freq = f4_freq

    bg1 = vd.get('bwGain1', 0)
    zz.voiceBWgain1 = (bg1 << 16) // 100 if bg1 else 0
    bg2 = vd.get('bwGain2', 0)
    zz.voiceBWgain2 = (bg2 << 16) // 100 if bg2 else 0
    bg3 = vd.get('bwGain3', 0)
    zz.voiceBWgain3 = (bg3 << 16) // 100 if bg3 else 0
    zz.voiceMinBW = 200

    # Parallel formants (always convert Hz → pitch units)
    zz.f4_Par = e_hz_to_pitch(vv, vd.get('f4p_Freq', 780))
    zz.bw4_Par = vd.get('f4p_BW', 250)
    zz.f5_Par = e_hz_to_pitch(vv, vd.get('f5p_Freq', 900))
    zz.bw5_Par = vd.get('f5p_BW', 250)
    zz.f6_Par = e_hz_to_pitch(vv, 4700)  # C code hardcodes 4700 Hz!
    zz.bw6_Par = vd.get('f6p_BW', 250)

    # Nasal (Hz → pitch)
    zz.bNP = vd.get('nasal_BW', vd.get('bNP', 60))
    zz.nasalAmt = vd.get('nasalAmt', 0)
    zz.nasalBaseFreq = vd.get('nasal_Base', 350)
    zz.nasalTargFreq = vd.get('nasal_targ', 500)
    zz.fNP = e_hz_to_pitch(vv, zz.nasalBaseFreq)
    zz.nasalAmt = 0

    # Gains
    zz.setNoiseGain = vd.get('nGain', 0)
    # Compute voiceNoiseGain from setNoiseGain (matches C Say.c init)
    zz.voiceNoiseGain = mRatio(zz.setNoiseGain, 100, kPrecision)
    if vv.bit16_Sound:
        zz.voiceNoiseGain = mMul2(zz.voiceNoiseGain, 0xCCCC, 16)
    vv.VP_stressGain = (vd.get('stressGain', 0) << 16) // 100

    # Voice type
    zz.voice_Num = vd.get('voice', kMaleTbls)

    # Set up formant tables
    if zz.voice_Num == kMaleTbls:
        zz.a_f1FreqTblM = f1FreqTblM
        zz.a_f2FreqTblM = f2FreqTblM
        zz.a_f3FreqTblM = f3FreqTblM
        zz.a_b1FreqTblM = b1FreqTblM
        zz.a_b2FreqTblM = b2FreqTblM
        zz.a_b3FreqTblM = b3FreqTblM
        zz.a_avVolTblM = avVolTblM
        zz.avVolTblM = avVolTblM
        zz.f1FreqTblM = f1FreqTblM
        zz.f2FreqTblM = f2FreqTblM
        zz.f3FreqTblM = f3FreqTblM
        zz.b1FreqTblM = b1FreqTblM
        zz.b2FreqTblM = b2FreqTblM
        zz.b3FreqTblM = b3FreqTblM
        zz.MaleEnvelopeListTbl = MaleEnvTbl
        zz.voice_Locus_Tbl = Male_Loci_Tbl
        zz.voice_NoiseAmp_Tbl = Male_NoiseAmpTbl
        zz.voiceMinBW = 50
    else:
        zz.a_f1FreqTblM = f1FreqTblF
        zz.a_f2FreqTblM = f2FreqTblF
        zz.a_f3FreqTblM = f3FreqTblF
        zz.a_b1FreqTblM = b1FreqTblF
        zz.a_b2FreqTblM = b2FreqTblF
        zz.a_b3FreqTblM = b3FreqTblF
        zz.a_avVolTblM = avVolTblF
        zz.avVolTblM = avVolTblF
        zz.f1FreqTblM = f1FreqTblF
        zz.f2FreqTblM = f2FreqTblF
        zz.f3FreqTblM = f3FreqTblF
        zz.b1FreqTblM = b1FreqTblF
        zz.b2FreqTblM = b2FreqTblF
        zz.b3FreqTblM = b3FreqTblF
        zz.MaleEnvelopeListTbl = FemaleEnvTbl
        zz.voice_Locus_Tbl = Female_Loci_Tbl
        zz.voice_NoiseAmp_Tbl = Female_NoiseAmpTbl
        zz.voiceMinBW = 50

    # Populate voice_Formants table (used by get_target)
    customForm = vd.get('customForm', 0)
    if customForm:
        zz.voice_Formants[kF1] = zz.a_f1FreqTblM
        zz.voice_Formants[kF2] = zz.a_f2FreqTblM
        zz.voice_Formants[kF3] = zz.a_f3FreqTblM
        zz.voice_Formants[kBW1] = zz.a_b1FreqTblM
        zz.voice_Formants[kBW2] = zz.a_b2FreqTblM
        zz.voice_Formants[kBW3] = zz.a_b3FreqTblM
        zz.voice_av_Tbl = zz.a_avVolTblM
        zz.EnvelopeListTbl = zz.a_EnvelopeListTbl
    elif zz.voice_Num == kMaleTbls:
        zz.voice_Formants[kF1] = zz.f1FreqTblM
        zz.voice_Formants[kF2] = zz.f2FreqTblM
        zz.voice_Formants[kF3] = zz.f3FreqTblM
        zz.voice_Formants[kBW1] = zz.b1FreqTblM
        zz.voice_Formants[kBW2] = zz.b2FreqTblM
        zz.voice_Formants[kBW3] = zz.b3FreqTblM
        zz.voice_av_Tbl = zz.avVolTblM
        zz.EnvelopeListTbl = zz.MaleEnvelopeListTbl
    else:
        zz.voice_Formants[kF1] = zz.f1FreqTblM
        zz.voice_Formants[kF2] = zz.f2FreqTblM
        zz.voice_Formants[kF3] = zz.f3FreqTblM
        zz.voice_Formants[kBW1] = zz.b1FreqTblM
        zz.voice_Formants[kBW2] = zz.b2FreqTblM
        zz.voice_Formants[kBW3] = zz.b3FreqTblM
        zz.voice_av_Tbl = zz.avVolTblM
        zz.EnvelopeListTbl = zz.FemaleEnvelopeListTbl

    # Reverb (Say.c:1450-1458): reverbDepth is a 16.16 ratio (mRatio(x,100,
    # kPrecision)), and reverbDelay is clipped to [10,100]% before its own
    # 16.16 conversion ((x<<16)/100) -- both were previously raw percentage
    # copies with no scaling/clipping at all, wildly overstating the reverb
    # echo contribution to nSamp for every voice with reverb enabled.
    zz.reverbDepth = mRatio(vd.get('rvbDepth', 0), 100, kPrecision)
    _reverb_delay_pct = vd.get('rvbDelay', 0)
    if _reverb_delay_pct > 100:
        _reverb_delay_pct = 100
    if _reverb_delay_pct < 10:
        _reverb_delay_pct = 10
    zz.reverbDelay = (_reverb_delay_pct << 16) // 100
    zz.voiceChorus = vd.get('chorus', 0)

    # Emphasis (Say.c:1455-1458): a real per-voice flag, not always-on --
    # voices with emphVoice==0 (Cellos, PipeOrgan, Bells, Hysterical, ...)
    # must NOT get the high-frequency radiation-loss emphasis applied in
    # say_frame's nSamp computation. This was hardcoded to 1 unconditionally
    # before, which happened to match ordinary voices (emphVoice=1, e.g.
    # Fred) by coincidence but silently corrupted every sample of output
    # for every voice with emphVoice=0 -- confirmed by a genuine sample-level
    # PCM comparison against the C reference (frame-level control values
    # matched exactly throughout, masking this completely).
    zz.hfEmph = 1 if vd.get('emphVoice', 0) > 0 else 0

    # Pitch dynamics
    vv.VP_riseAmt = vd.get('riseAmt', 0)
    vv.VP_fallAmt = vd.get('fallAmt', 0)
    vv.VP_riseAmt1 = vd.get('riseAmt1', 0)
    vv.VP_fallAmt1 = vd.get('fallAmt1', 0)
    vv.VP_assertiveness = vd.get('assertiveness', 0)
    vv.VP_baselineFall = vd.get('baselineFall', 0)
    vv.VP_quickness = vd.get('quickness', 0)
    vv.VP_intonation = (vd.get('intonation', 0) << 16) // 100
    vv.VP_pitchRange = (vd.get('pitchRange', 0) << 16) // 100

    # Custom waveform (vWave/vWave1) — synthesize buzz waveforms (C InvDFT)
    vw = vd.get('vWave', None)
    if vw:
        voice_wave_gain = mRatio(vd.get('vGain', 100), 200, 16)
        _inv_dft(zz, vw, vd.get('vWave1', None), voice_wave_gain)

    # Volume
    vv.VP_stressGain = (vd.get('stressGain', 0) << 16) // 100

    # Locus offset (Say.c:1425)
    zz.locusOffset = vd.get('locus', 0)

    # Pitch baseline fall and filter gains (BackEnd.c:4337-4351)
    vv.baselineFall_START = kHZ_7 + vv.VP_baselineFall
    vv.baselineFall_END = kHZ_7 - vv.VP_baselineFall
    vv.pFilter_Out1 = vv.baselineFall_START << kStepSizeRes
    vv.pFilter_Out2 = vv.pFilter_Out1
    vv.pFilter_In_Gain = vv.VP_quickness
    vv.pFilter_FB_Gain = k100percent - vv.pFilter_In_Gain

    # Init fixed formants
    init_fixed_formants(zz)

    # Rate/speaking params (Say.c:1258, 1423 + Init_Rate_Params)
    vv.speech_Rate = vd.get('rate', kNormal_Speech_Rate)
    vv.stressDurTime = vd.get('stressDurTime', 50) >> 1
    if vv.speech_Rate < kMinRate:
        vv.speech_Rate = kMinRate
    vv.rate_Ratio = (kNormal_Speech_Rate << 16) // vv.speech_Rate
    vv.rate_Ratio_LowGain = (kNormal_Speech_Rate << 16) // (
        (((vv.speech_Rate - kNormal_Speech_Rate) * (655 * 60)) >> 16) + kNormal_Speech_Rate
    )
    vv.stress_Duration = (vv.rate_Ratio * vv.stressDurTime) >> 16

    # Vibrato params (Say.c:1428-1436)
    vib_freq = vd.get('vibratoFreq', 0)
    vv.vibratoFreq = (((vib_freq << 16) // 10) * 256) // 200
    vv.vibratoDepth1 = (vd.get('vibratoDepth1', 0) << 16) // 1000
    vv.vibratoDepth2 = (vd.get('vibratoDepth2', 0) << 16) // 1000

    # Portamento step divisor (Say.c:1465-1467)
    vv.portamento = vd.get('portamento', 0) // kFrameTime
    if vv.portamento == 0:
        vv.portamento = 1

    # Notes / singing (embedded note script; ResetVoice numOfNotes check)
    notes = vd.get('notes', None)
    if notes:
        vv.numOfNotes = notes[0]
        if vv.numOfNotes >= kMaxNotes:
            vv.numOfNotes = 1  # too many notes, don't sing
        for i in range(vv.numOfNotes):
            vv.notesBuf[i] = notes[i + 1]
    else:
        vv.numOfNotes = 0
    vv.songIndex = 0
    if vv.numOfNotes > 1:
        vv.singScript = True
        vv.singing = True
    else:
        vv.singScript = False
        vv.singing = False
    # ResetVoice also calls e_SetTempo(vv, vv->tempo) when numOfNotes > 1
    # (BackEnd.c:4364-4368) to populate Note_Times[], which Mod_Duration's
    # singScript/singing branches need. tempo itself comes from voice data
    # (e.g. PipeOrgan_Voice['tempo'] == 85); e_set_tempo() is called from
    # api.new_voice() once vv.tempo is set here.
    vv.tempo = vd.get('tempo', 120)


def _inv_dft(zz: FormantVar, vWave: list, vWave1: Optional[list] = None,
             voice_wave_gain: int = 0x8000):
    """Synthesize voice waveform from harmonic coefficients (C InvDFT port)."""
    SINE = zz.SineWave15Ptr
    wf = zz.voiceWaveform
    wf1 = zz.voiceWaveform1

    # Clear waveforms
    for j in range(256):
        wf[j] = 0
        wf1[j] = 0

    if vWave1 is None:
        vWave1 = [0] * 48

    # Accumulate harmonics 0-47 into 256-sample waveforms
    for i in range(48):
        amp = mMul2(vWave[i], voice_wave_gain, 16)
        amp1 = mMul2(vWave1[i], voice_wave_gain, 16)
        sIndex = 0
        sIndex1 = 0
        for j in range(256):
            if amp:
                wf[j] += mMul2(amp, SINE[sIndex], 16)
            if amp1:
                wf1[j] += mMul2(amp1, SINE[sIndex1], 16)
            sIndex += i
            if sIndex > 255:
                sIndex -= 256
            sIndex1 += i
            if sIndex1 > 255:
                sIndex1 -= 256

    # Scale buzz #2 to match buzz #1 peak
    max0 = 0
    max1 = 0
    for j in range(256):
        hold = wf[j]
        if hold < 0:
            hold = -hold
        if hold > max0:
            max0 = hold
        hold = wf1[j]
        if hold < 0:
            hold = -hold
        if hold > max1:
            max1 = hold

    if max1 > 0:
        max2 = mRatio(max0, max1, 16)
        for j in range(256):
            wf1[j] = mMul2(wf1[j], max2, 16)

    # Normalize vWave1 to match vWave peak
    peak = max(abs(x) for x in wf)
    peak1 = max(abs(x) for x in wf1)
    if peak1 > 0 and peak > 0:
        scale = peak * 8192 // peak1
        for i in range(256):
            wf1[i] = (wf1[i] * scale) >> 13


# ---------------------------------------------------------------------------
# synth_SetVolume
# ---------------------------------------------------------------------------

def synth_set_volume(vv: VoiceVar, vol: int):
    """Set speech volume (0-256 scale)."""
    zz: FormantVar = vv.synthVars
    zz.speechVolume = vol
    zz.voiceNoiseGain = mMul2(zz.setNoiseGain, zz.speechVolume, 8)


def set_volume(vv: VoiceVar, vol: int):
    """SetVolume (BackEnd.c). Clips a fixed-point (xxxx.ffff) volume value
    to 0-256, latches it into vv.user_Volume, and dispatches to
    synth_set_volume (the synth_SetVolume_FUNC slot)."""
    if vol > 0x10000:
        vv.user_Volume = 0x0100
    elif vol < 0:
        vv.user_Volume = 0
    else:
        vv.user_Volume = vol >> 8
    synth_set_volume(vv, vv.user_Volume)


# ---------------------------------------------------------------------------
# Helper: e_GetPhon / e_GetPhonCtrl (mirrors BackEnd.c)
# ---------------------------------------------------------------------------

def e_get_phon(vv: VoiceVar, index: int) -> int:
    if 0 <= index < vv.phonBuf_2_In_Index:
        return vv.phon_Buf_2[index]
    return _SIL_


def e_get_phon_ctrl(vv: VoiceVar, index: int) -> int:
    if 0 <= index < vv.phonBuf_2_In_Index:
        return vv.phon_Ctrl_Buf_2[index]
    return 0


def e_midi_to_pitch(midi_note: int) -> int:
    """Convert MIDI note (fixed-point sPitch << 8) to internal pitch units."""
    if midi_note < kMIDI_50HZ:
        midi_note = 0
    else:
        midi_note -= kMIDI_50HZ
    return ((midi_note * kOneTwelfth) + kPointFive) >> 16


def e_hz_to_pitch(vv: VoiceVar, hz: int) -> int:
    ratioK = 2621
    note = 0
    if hz > 0:
        if hz < 100:
            freq = hz << 3
            fk = 0x0
        elif hz < 200:
            freq = hz << 2
            fk = 0x100
        elif hz < 400:
            freq = hz << 1
            fk = 0x200
        elif hz < 800:
            freq = hz
            fk = 0x300
        elif hz < 1600:
            freq = hz >> 1
            fk = 0x400
        elif hz < 3200:
            freq = hz >> 2
            fk = 0x500
        else:
            freq = hz >> 3
            fk = 0x600
        ratio = ((freq - 400) * ratioK) >> 11
        if ratio < 0:
            ratio = 0
        elif ratio >= len(vv.logOf2Tbl):
            ratio = len(vv.logOf2Tbl) - 1
        note = vv.logOf2Tbl[ratio] + fk
    return note


def e_log_to_lin(vv: VoiceVar, logVal: int) -> int:
    idx = (logVal >> 1) if logVal >= 0 else 0
    if idx > 31:
        idx = 31
    return vv.logToLinPtr[idx]


def pitch_to_hz(vv: VoiceVar, pitch: int) -> int:
    return (vv.OctFreqTbl[(pitch & 0xF00) >> 8] * vv.ExpOf2Tbl[pitch & 0xFF]) >> 15


# ---------------------------------------------------------------------------
# Init_ControlBlocks (formantSynth.c)
# ---------------------------------------------------------------------------

def init_control_blocks(zz: FormantVar):
    zz.big_Bang = True
    for i in range(kNumOfBlocks):
        cb = zz.controlBlockArray[i]
        cb.curP_START_Targ = 0
        cb.curTarget_TIME = 0
        cb.curTarget_STEP = 0
        cb.curTarget_OFFS = 0
        cb.HEAD_offs = 0
        cb.HEAD_step = 0
        cb.TAIL_offs = 0
        cb.TAIL_step = 0
        cb.TAIL_START_time = 0
        cb.onset_END_TIME = 0
        cb.onset_VAL = 0
        cb.nextP_START_Targ = 0
        cb.prevP_END_Targ = 0
        cb.curP_END_Targ = 0
        cb.ptrToTargetList = None
        cb.lastVal = 0


# ---------------------------------------------------------------------------
# Scale_Prcnt_to_PhonDur (formantSynth.c:1923)
# ---------------------------------------------------------------------------

def scale_prcnt_to_phondur(zz: FormantVar, percent: int) -> int:
    tempL = (percent * zz.cur_Phon_PctOfMaxDur_CF) >> 8
    tempL = ((zz.cur_Phon_MaxDur_CF * tempL) // 100) >> 8
    if tempL <= 0:
        tempL = 1
    return tempL


# ---------------------------------------------------------------------------
# Adjust_Colored_Target (formantSynth.c:578)
# ---------------------------------------------------------------------------

def adjust_colored_target(vv: VoiceVar, index: int, entryCount: int) -> int:
    zz: FormantVar = vv.synthVars
    cur_Phon = e_get_phon(vv, index)
    next_Phon = e_get_phon(vv, index + 1)
    prev_Phon = e_get_phon(vv, index - 1)
    cur_Flags = vv.phonFlags2[cur_Phon]
    next_Flags = vv.phonFlags2[next_Phon]
    prev_Flags = vv.phonFlags2[prev_Phon]
    adjust = 0

    if zz.cur_ControlBlk_Index == kF3:
        if (cur_Flags & kVowel1F) and (cur_Phon != _ER_) and \
           ((prev_Flags & kLiqGlide2F) or (next_Flags & kLiqGlide2F)):
            adjust = -150

    elif zz.cur_ControlBlk_Index == kF2:
        cur_PhonCtrl = vv.phon_Ctrl_Buf_2[index]

        # L-colored vowels
        if next_Phon == _LX_:
            if cur_Flags & kFrontF:
                adjust = -150
            elif ((cur_Phon == _AY_) or (cur_Phon == _OY_)) and (entryCount > 0):
                adjust = -250

        if ((prev_Phon == _LX_) or (prev_Phon == _l_) or (prev_Phon == _w_)) and (cur_Flags & kFrontF):
            adjust = -150

        if (cur_Phon == _UW_) and (prev_Flags & kAlveolarF):
            adjust = 200

        if (entryCount > 0) and ((cur_Phon == _UW_) or (cur_Phon == _YU_)) and (next_Flags & kAlveolarF):
            adjust += 200

        # Stress scaling
        if cur_PhonCtrl & kStressField:
            adjust = adjust >> 1
        else:
            adjust += adjust >> 1
            if (entryCount > 0) and (cur_Phon == _YU_):
                adjust = 400

        if adjust > 400:
            adjust = 400
        elif adjust < -400:
            adjust = -400

    return adjust


# ---------------------------------------------------------------------------
# GetTarget (formantSynth.c:695)
# ---------------------------------------------------------------------------

def get_target(vv: VoiceVar, index: int) -> int:
    zz: FormantVar = vv.synthVars
    cb = zz.controlBlockArray[zz.cur_ControlBlk_Index]
    cur_ControlBlk_Type = zz.CtrlBlockTypeTbl[zz.cur_ControlBlk_Index]

    cur_phon = e_get_phon(vv, index)
    cur_Flags = vv.phonFlags2[cur_phon]
    cur_PhonCtrl = vv.phon_Ctrl_Buf_2[index]
    next_phon = e_get_phon(vv, index + 1)
    next_Flags = vv.phonFlags2[next_phon]
    prev_phon = e_get_phon(vv, index - 1)
    prev_Flags = vv.phonFlags2[prev_phon]

    target_Val = -1

    if (cur_ControlBlk_Type == kFreqType) or (cur_ControlBlk_Type == kBWType):
        targetPtr = zz.voice_Formants[zz.cur_ControlBlk_Index]
        target_Val = targetPtr[cur_phon]
        if target_Val < kNoValue:
            return target_Val  # raw envelope reference
        if target_Val < 0:
            if target_Val == kNoValue:
                target_Val = targetPtr[next_phon]
                if target_Val == kNoValue:
                    target_Val = targetPtr[e_get_phon(vv, index + 2)]
                    if target_Val == kNoValue:
                        target_Val = targetPtr[prev_phon]
                        if target_Val < kNoValue:
                            target_Val = zz.EnvelopeListTbl[(target_Val & 0x7FFF) + 2]
                        if target_Val == kNoValue:
                            target_Val = zz.DefaultTargTbl[zz.cur_ControlBlk_Index]
            if target_Val < kNoValue:
                target_Val &= 0x7FFF
                target_Val = zz.EnvelopeListTbl[target_Val]

    elif cur_ControlBlk_Type == kFNZType:
        if cur_Flags & kNasalF:
            target_Val = zz.nasalTargFreq
        else:
            target_Val = zz.nasalBaseFreq

    elif cur_ControlBlk_Type == kSourceAmpType:
        if zz.cur_ControlBlk_Index == kAV:
            target_Val = zz.voice_av_Tbl[cur_phon]
            if cur_PhonCtrl & kPlosive_Release:
                if prev_Flags & kNasalF:
                    target_Val -= 6
                else:
                    target_Val -= 20
            if (cur_Flags & kStopF) and not (prev_Flags & kVoicedF):
                target_Val = 0
            if (cur_phon == _h_) and (prev_Flags & kVoicedF) and not (cur_PhonCtrl & kPrimOrEmphStress):
                target_Val = 54
        elif cur_phon == _h_:
            if zz.Rank_FWD_Tbl[next_phon] == kFrontR:
                target_Val = 58
            else:
                target_Val = 62
            if not (cur_PhonCtrl & kStressField):
                target_Val -= 1
        else:
            target_Val = 0

    elif cur_ControlBlk_Type == kResonAmpType:
        target_Val = zz.NoiseIndexTbl[cur_phon]
        if target_Val == kNoValue:
            target_Val = 0
        else:
            if next_phon == _SIL_:
                rank = zz.Rank_BKWD_Tbl[prev_phon]
            else:
                rank = zz.Rank_FWD_Tbl[next_phon]
            if rank == kRoundR:
                rank = kBackR
            target_Val += (zz.cur_ControlBlk_Index - kAp2) + (rank * 6)
            target_Val = zz.voice_NoiseAmp_Tbl[target_Val]
            if (vv.phon_Ctrl_Buf_2[index + 1] & kPlosive_Release) and (target_Val >= 4):
                target_Val -= 4

    return target_Val


def get_first_target(vv: VoiceVar, index: int) -> int:
    zz: FormantVar = vv.synthVars
    targ = get_target(vv, index)
    if targ < kNoValue:
        targ &= 0x7FFF
        targ = zz.EnvelopeListTbl[targ]
        if zz.CtrlBlockTypeTbl[zz.cur_ControlBlk_Index] == kFreqType:
            targ += adjust_colored_target(vv, index, 0)
    return targ


def get_last_target(vv: VoiceVar, index: int) -> int:
    zz: FormantVar = vv.synthVars
    targ = get_target(vv, index)
    if targ < kNoValue:
        targ = zz.EnvelopeListTbl[(targ & 0x7FFF) + 2]
        if zz.CtrlBlockTypeTbl[zz.cur_ControlBlk_Index] == kFreqType:
            targ += adjust_colored_target(vv, index, 1)
    return targ


# ---------------------------------------------------------------------------
# Get_Diphthongs (formantSynth.c:1951)
# ---------------------------------------------------------------------------

def get_diphthongs(vv: VoiceVar, index: int):
    zz: FormantVar = vv.synthVars
    cb = zz.controlBlockArray[zz.cur_ControlBlk_Index]
    cur_ControlBlk_Type = zz.CtrlBlockTypeTbl[zz.cur_ControlBlk_Index]

    artic_Factor = k1pct * 10
    cb.ptrToTargetList = zz.next_DiphEntry

    p1_Val = zz.EnvelopeListTbl[index]
    index += 1
    t1_Val = zz.EnvelopeListTbl[index]
    index += 1
    p2_Val = zz.EnvelopeListTbl[index]
    index += 1
    t2_Val = zz.EnvelopeListTbl[index]

    t1_Val = scale_prcnt_to_phondur(zz, t1_Val)
    t2_Val = scale_prcnt_to_phondur(zz, t2_Val)

    if cur_ControlBlk_Type == kFreqType:
        if cb.prevP_END_Targ > 0:
            p1_Val += ((cb.prevP_END_Targ - p1_Val) * artic_Factor) >> 16
        p1_Val += adjust_colored_target(vv, vv.cur_PhonBuf_Index_CF, 0)
        if cb.nextP_START_Targ > 0:
            p2_Val += ((cb.nextP_START_Targ - p2_Val) * artic_Factor) >> 16
        p2_Val += adjust_colored_target(vv, vv.cur_PhonBuf_Index_CF, 1)

    rampTime = t2_Val - t1_Val
    tempL = (p2_Val - p1_Val) << kStepSizeRes
    if rampTime < kSizeOf1xTbl:
        step_Size = (zz.One_Over_X_Tbl[rampTime] * tempL) >> 16
    else:
        step_Size = cDiv(tempL, rampTime)

    cb.curP_START_Targ = p1_Val
    cb.curTarget_TIME = t1_Val
    cb.curTarget_STEP = 0

    zz.diphEntryArray[zz.next_DiphEntry] = t2_Val
    zz.next_DiphEntry += 1
    zz.diphEntryArray[zz.next_DiphEntry] = step_Size
    zz.next_DiphEntry += 1
    zz.diphEntryArray[zz.next_DiphEntry] = vv.cur_Phon_Dur_CF
    zz.next_DiphEntry += 1
    zz.diphEntryArray[zz.next_DiphEntry] = 0
    zz.next_DiphEntry += 1

    cb.curP_END_Targ = p2_Val


# ---------------------------------------------------------------------------
# Fill_Phon_Targets (formantSynth.c:2041)
# ---------------------------------------------------------------------------

def fill_phon_targets(vv: VoiceVar):
    zz: FormantVar = vv.synthVars
    if vv.cur_PhonBuf_Index_CF == 0:
        if zz.big_Bang:
            zz.big_Bang = False
            for i in range(kNumOfBlocks):
                cb = zz.controlBlockArray[i]
                zz.cur_ControlBlk_Index = i
                cb.curP_END_Targ = get_first_target(vv, vv.cur_PhonBuf_Index_CF)
    zz.cur_Phon_MaxDur_CF = vv.maxDurTbl[vv.cur_Phon_CF] // kFrameTime
    if not (vv.cur_PhonFlags_CF & kPlosFricF) and (vv.cur_Phon_CF != _SIL_):
        zz.cur_Phon_PctOfMaxDur_CF = (vv.cur_Phon_Dur_CF << 16) // zz.cur_Phon_MaxDur_CF
        zz.cur_Phon_PctOfMaxDur1_CF = (zz.cur_Phon_PctOfMaxDur_CF >> 1) + kOneHalf
        zz.cur_Phon_PctOfMaxDur2_CF = zz.cur_Phon_PctOfMaxDur1_CF - (10 * 655)
    zz.next_DiphEntry = 0
    for i in range(kF1, kNumOfBlocks):
        zz.controlBlockArray[i].onset_END_TIME = 0


# ---------------------------------------------------------------------------
# Get_Locus (formantSynth.c:955)
# ---------------------------------------------------------------------------

def get_locus(vv: VoiceVar, i_Consonant: int, i_Vowel: int, bType: int):
    zz: FormantVar = vv.synthVars
    if (zz.cur_ControlBlk_Index >= kF1) and (zz.cur_ControlBlk_Index <= kF3):
        consonant_Phon = e_get_phon(vv, i_Consonant)
        vowel1_Phon = e_get_phon(vv, i_Vowel)

        if bType == C_V_type:
            vowel_Rank = zz.Rank_FWD_Tbl[vowel1_Phon]
            consonant_Rank = zz.Rank_BKWD_Tbl[consonant_Phon]
        else:
            vowel_Rank = zz.Rank_BKWD_Tbl[vowel1_Phon]
            consonant_Rank = zz.Rank_FWD_Tbl[consonant_Phon]

        if (consonant_Rank == kConsonantR) and (vowel_Rank != kConsonantR):
            v1_Flags = vv.phonFlags2[vowel1_Phon]
            con_Flags = vv.phonFlags2[consonant_Phon]

            f2_y_Colored = bool(v1_Flags & kYGlideStartF)

            if bType == C_V_type:
                v1_Target = get_first_target(vv, i_Vowel)
            else:
                v1_Target = get_last_target(vv, i_Vowel)

            if vowel_Rank == kFrontR:
                loci_Tbl_Index = zz.Front_Loci_Tbl[consonant_Phon]
            elif vowel_Rank == kMiddleR:
                loci_Tbl_Index = zz.Mid_Loci_Tbl[consonant_Phon]
            else:
                loci_Tbl_Index = zz.Back_Loci_Tbl[consonant_Phon]

            if loci_Tbl_Index != kNoValue:
                loci_Tbl_Index = loci_Tbl_Index >> 1
                loci_Tbl_Index += (zz.cur_ControlBlk_Index - kF1) * 3

                locus_Freq = zz.voice_Locus_Tbl[loci_Tbl_Index]
                loci_Tbl_Index += 1
                locus_Pcnt = zz.voice_Locus_Tbl[loci_Tbl_Index]
                loci_Tbl_Index += 1
                locus_Freq += zz.locusOffset
                zz.trans_TIME = zz.voice_Locus_Tbl[loci_Tbl_Index] // kFrameTime

                if not (con_Flags & kNasalF) and not f2_y_Colored:
                    zz.trans_TIME = zz.trans_TIME - (zz.trans_TIME >> 2)

                if (vowel_Rank == kRoundR) and (zz.cur_ControlBlk_Index != kF1) and (con_Flags & (kDentalF + kPalatalF)):
                    locus_Pcnt = (locus_Pcnt >> 1) + 50

                if f2_y_Colored and (zz.cur_ControlBlk_Index == kF2):
                    locus_Pcnt = (25 - (locus_Pcnt >> 2)) + locus_Pcnt

                target_Offset = cDiv(locus_Pcnt * (v1_Target - locus_Freq), 100)
                zz.trans_LEVEL = locus_Freq + target_Offset


# ---------------------------------------------------------------------------
# Head_Rules (formantSynth.c:1068)
# ---------------------------------------------------------------------------

def head_rules(vv: VoiceVar):
    zz: FormantVar = vv.synthVars
    cb = zz.controlBlockArray[zz.cur_ControlBlk_Index]
    cur_ControlBlk_Type = zz.CtrlBlockTypeTbl[zz.cur_ControlBlk_Index]

    if cur_ControlBlk_Type == kFreqType:
        if vv.cur_PhonFlags_CF & kSonorant1F:
            if not (vv.cur_PhonFlags_CF & kLiqGlideF):
                zz.trans_TIME = 45 // kFrameTime
                if vv.prev_PhonFlags_CF & kLiqGlideF:
                    zz.trans_LEVEL = (cb.prevP_END_Targ + zz.trans_LEVEL) >> 1
                    if (vv.prev_Phon_CF == _l_) and (zz.cur_ControlBlk_Index == kF1):
                        zz.trans_LEVEL += 80
                    elif (vv.prev_Phon_CF == _r_) and (zz.cur_ControlBlk_Index != kF1):
                        zz.trans_TIME = 70 // kFrameTime
                else:
                    if vv.cur_Phon_CF == _h_:
                        zz.trans_LEVEL = (cb.prevP_END_Targ + zz.trans_LEVEL) >> 1
            else:
                if not (vv.prev_PhonFlags_CF & kLiqGlideF):
                    zz.trans_LEVEL = (cb.prevP_END_Targ + zz.trans_LEVEL) >> 1
                else:
                    zz.trans_LEVEL = (cb.prevP_END_Targ + zz.trans_LEVEL) >> 1
                zz.trans_TIME = 32 // kFrameTime

        if vv.cur_Phon_CF == _SIL_:
            zz.trans_LEVEL = cb.prevP_END_Targ
            zz.trans_TIME = vv.cur_Phon_Dur_CF
        else:
            get_locus(vv, vv.cur_PhonBuf_Index_CF - 1, vv.cur_PhonBuf_Index_CF, C_V_type)
            get_locus(vv, vv.cur_PhonBuf_Index_CF, vv.cur_PhonBuf_Index_CF - 1, V_C_type)
            if (vv.prev_PhonFlags_CF & kStopF) and not (vv.prev_PhonFlags_CF & kVoicedF) and (zz.cur_ControlBlk_Index == kF1):
                zz.trans_LEVEL += 100
            if vv.cur_PhonFlags_CF & kPlosFricF:
                if zz.cur_ControlBlk_Index == kF1:
                    zz.trans_TIME = 20 // kFrameTime
                else:
                    zz.trans_TIME = 30 // kFrameTime
                if vv.cur_PhonFlags_CF & kStopF:
                    zz.trans_TIME = vv.cur_Phon_Dur_CF
            if vv.cur_PhonFlags_CF & kNasalF:
                if zz.cur_ControlBlk_Index == kF1:
                    zz.trans_TIME = 0
                else:
                    zz.trans_TIME = vv.cur_Phon_Dur_CF
                if ((vv.cur_Phon_CF == _n_) or (vv.cur_Phon_CF == _EN_)) and (zz.Rank_BKWD_Tbl[vv.prev_Phon_CF] == kFrontR):
                    if zz.cur_ControlBlk_Index == kF2:
                        if vv.prev_PhonFlags_CF & kYGlideEndF:
                            zz.trans_LEVEL -= 200
                        else:
                            zz.trans_LEVEL -= 100
                    elif zz.cur_ControlBlk_Index == kF3:
                        zz.trans_LEVEL -= 100
                elif (vv.cur_Phon_CF == _m_) and (zz.cur_ControlBlk_Index == kF2) and (vv.prev_PhonFlags_CF & kYGlideEndF):
                    zz.trans_LEVEL -= 150

        if not (vv.cur_PhonFlags_CF & kPlosFricF) and (zz.Rank_BKWD_Tbl[vv.prev_Phon_CF] != kConsonantR) and (zz.trans_TIME > 0):
            zz.trans_TIME = 1 + ((zz.cur_Phon_PctOfMaxDur1_CF * zz.trans_TIME) >> 16)

    elif cur_ControlBlk_Type == kFNZType:
        if (vv.prev_PhonFlags_CF & kNasalF) and not (vv.cur_PhonFlags_CF & kNasalF):
            zz.trans_LEVEL = zz.nasalBaseFreq + ((zz.nasalTargFreq - zz.nasalBaseFreq) >> 1)
            zz.trans_TIME = 80 // kFrameTime
        if vv.cur_PhonFlags_CF & kNasalF:
            zz.trans_LEVEL = zz.nasalTargFreq

    elif cur_ControlBlk_Type == kBWType:
        if vv.cur_PhonFlags_CF & kVoicedF:
            if not (vv.prev_PhonFlags_CF & kVoicedF) and (zz.cur_ControlBlk_Index == kBW1):
                zz.trans_TIME = 50 // kFrameTime
                zz.trans_LEVEL = ((zz.controlBlockArray[kF1].curP_START_Targ) >> 3) + cb.curP_START_Targ
            else:
                zz.trans_TIME = 40 // kFrameTime
        else:
            zz.trans_TIME = 20 // kFrameTime
        if vv.prev_Phon_CF == _SIL_:
            zz.trans_LEVEL = ((kBW3 - cur_ControlBlk_Type) * 50) + cb.curP_START_Targ
            zz.trans_TIME = 50 // kFrameTime
        elif vv.cur_Phon_CF == _SIL_:
            zz.trans_LEVEL = ((kBW3 - cur_ControlBlk_Type) * 50) + cb.prevP_END_Targ
            if not (vv.phonFlags2[vv.prev2_Phon_CF] & kVoicedF) and (vv.prev_PhonCtrl_CF & kPlosive_Release) and (zz.cur_ControlBlk_Index == kBW1):
                zz.trans_LEVEL = 250
            zz.trans_TIME = 50 // kFrameTime
        if vv.prev_PhonFlags_CF & kNasalF:
            zz.trans_LEVEL = cb.curP_START_Targ
            if zz.cur_ControlBlk_Index == kBW2:
                if ((vv.prev_Phon_CF == _n_) or (vv.prev_Phon_CF == _EN_)) and (zz.Rank_FWD_Tbl[vv.cur_Phon_CF] != kFrontR):
                    zz.trans_LEVEL += 60
                    zz.trans_TIME = 60 // kFrameTime
            elif zz.cur_ControlBlk_Index == kBW1:
                zz.trans_LEVEL += 70
                zz.trans_TIME = 100 // kFrameTime
        if vv.cur_PhonFlags_CF & kNasalF:
            zz.trans_TIME = 0

    elif (cur_ControlBlk_Type == kResonAmpType) or (cur_ControlBlk_Type == kSourceAmpType):
        ampT = cb.curP_START_Targ - 10
        if (zz.trans_LEVEL < ampT) or (vv.prev_PhonFlags_CF & kStopF) or (vv.prev_Phon_CF == _JH_):
            zz.trans_LEVEL = ampT
            if not (vv.cur_PhonFlags_CF & kPlosFricF):
                zz.trans_TIME = 20 // kFrameTime
            if zz.cur_ControlBlk_Index == kAV:
                if (vv.prev_Phon_CF == _SIL_) and (vv.cur_PhonFlags_CF & kVoicedF):
                    zz.trans_LEVEL -= 8
                    zz.trans_TIME = 45 // kFrameTime
                if vv.prev_PhonFlags_CF & kPlosFricF:
                    zz.trans_LEVEL = ampT + 6
                if vv.prev_PhonFlags_CF & kStopF:
                    zz.trans_LEVEL = cb.curP_START_Targ - 5
        if (vv.cur_PhonFlags_CF & kVoicedF) and (vv.prev_PhonFlags_CF & kNasalF):
            zz.trans_TIME = 0
        if (vv.prev_PhonFlags_CF & kVoicedF) and (vv.cur_PhonFlags_CF & kNasalF) and (zz.cur_ControlBlk_Index == kAV):
            zz.trans_TIME = 0
        ampT = cb.prevP_END_Targ - 10
        if zz.trans_LEVEL < ampT:
            zz.trans_LEVEL = ampT - 3
            if vv.cur_Phon_CF == _SIL_:
                zz.trans_TIME = 70 // kFrameTime
        if (zz.cur_ControlBlk_Index == kAp3) and (vv.cur_PhonFlags_CF & kAffricateF):
            zz.trans_TIME = vv.cur_Phon_Dur_CF - 2
            zz.trans_LEVEL = cb.curP_START_Targ - 30
        if (zz.cur_ControlBlk_Index == kAV) and (vv.cur_PhonFlags_CF & kPlosiveF):
            zz.trans_TIME = 10 // kFrameTime
        if zz.cur_ControlBlk_Index == kAF:
            if (vv.cur_Phon_CF == _SIL_) or (vv.cur_Phon_CF == _f_) or (vv.cur_Phon_CF == _TH_) or (vv.cur_Phon_CF == _s_) or (vv.cur_Phon_CF == _SH_):
                if (vv.prev_PhonFlags_CF & kVoicedF) and not (vv.prev_PhonFlags_CF & kPlosFricF):
                    if vv.cur_Phon_CF == _SIL_:
                        zz.trans_TIME = 80 // kFrameTime
                        zz.trans_LEVEL = 52
                    else:
                        zz.trans_TIME = 45 // kFrameTime
                        zz.trans_LEVEL = 48

    if zz.trans_TIME > vv.cur_Phon_Dur_CF:
        zz.trans_TIME = vv.cur_Phon_Dur_CF
    if zz.trans_TIME > 130 // kFrameTime:
        zz.trans_TIME = 130 // kFrameTime
    if zz.trans_TIME < 0:
        zz.trans_TIME = 0


# ---------------------------------------------------------------------------
# Tail_Rules (formantSynth.c:1499)
# ---------------------------------------------------------------------------

def tail_rules(vv: VoiceVar):
    zz: FormantVar = vv.synthVars
    cb = zz.controlBlockArray[zz.cur_ControlBlk_Index]
    cur_ControlBlk_Type = zz.CtrlBlockTypeTbl[zz.cur_ControlBlk_Index]

    if cur_ControlBlk_Type == kFreqType:
        if vv.cur_PhonFlags_CF & kSonorant1F:
            zz.trans_TIME = 45 // kFrameTime
            if not (vv.cur_PhonFlags_CF & kLiqGlideF):
                if vv.next_PhonFlags_CF & kLiqGlideF:
                    if zz.cur_ControlBlk_Index == kF3:
                        zz.trans_TIME = 60 // kFrameTime
                    if (vv.next_Phon_CF == _l_) and (zz.cur_ControlBlk_Index == kF1):
                        zz.trans_LEVEL += 80
                else:
                    if vv.next_Phon_CF == _h_:
                        zz.trans_LEVEL = (cb.curP_END_Targ + zz.trans_LEVEL) >> 1
            else:
                if not (vv.next_PhonFlags_CF & kLiqGlideF):
                    zz.trans_LEVEL = (cb.curP_END_Targ + zz.trans_LEVEL) >> 1
                    zz.trans_TIME = 20 // kFrameTime
                else:
                    zz.trans_LEVEL = (cb.curP_END_Targ + zz.trans_LEVEL) >> 1
                    zz.trans_TIME = 40 // kFrameTime

        if vv.next_Phon_CF == _SIL_:
            zz.trans_TIME = 0
        else:
            get_locus(vv, vv.cur_PhonBuf_Index_CF + 1, vv.cur_PhonBuf_Index_CF, V_C_type)
            get_locus(vv, vv.cur_PhonBuf_Index_CF, vv.cur_PhonBuf_Index_CF + 1, C_V_type)
            if vv.cur_PhonFlags_CF & kPlosFricF:
                if zz.cur_ControlBlk_Index == kF1:
                    zz.trans_TIME = 20 // kFrameTime
                else:
                    zz.trans_TIME = 30 // kFrameTime
                if vv.cur_PhonFlags_CF & kStopF:
                    zz.trans_TIME = vv.cur_Phon_Dur_CF
                    if not (vv.cur_PhonFlags_CF & kVoicedF) and (zz.cur_ControlBlk_Index == kF1):
                        zz.trans_LEVEL += 100
            if vv.cur_PhonFlags_CF & kNasalF:
                if zz.cur_ControlBlk_Index == kF1:
                    zz.trans_TIME = 0
                else:
                    zz.trans_TIME = vv.cur_Phon_Dur_CF
                if ((vv.cur_Phon_CF == _n_) or (vv.cur_Phon_CF == _EN_)) and (zz.Rank_FWD_Tbl[vv.next_Phon_CF] == kFrontR):
                    if zz.cur_ControlBlk_Index == kF2:
                        zz.trans_LEVEL -= 100
                        if vv.next_PhonFlags_CF & kYGlideStartF:
                            zz.trans_LEVEL -= 100
                    elif zz.cur_ControlBlk_Index == kF3:
                        zz.trans_LEVEL -= 100
                elif (vv.cur_Phon_CF == _m_) and (zz.cur_ControlBlk_Index == kF2) and (vv.next_PhonFlags_CF & kYGlideStartF):
                    zz.trans_LEVEL -= 150

        if not (vv.cur_PhonFlags_CF & kPlosFricF) and (zz.Rank_FWD_Tbl[vv.next_Phon_CF] != kConsonantR) and (zz.trans_TIME > 0):
            zz.trans_TIME = 1 + ((zz.cur_Phon_PctOfMaxDur2_CF * zz.trans_TIME) >> 16)

    elif cur_ControlBlk_Type == kFNZType:
        if (vv.next_PhonFlags_CF & kNasalF) and not (vv.cur_PhonFlags_CF & kNasalF):
            zz.trans_LEVEL = zz.nasalTargFreq
            zz.trans_TIME = 80 // kFrameTime

    elif cur_ControlBlk_Type == kBWType:
        if vv.cur_PhonFlags_CF & kVoicedF:
            zz.trans_TIME = 40 // kFrameTime
            if not (vv.next_PhonFlags_CF & kVoicedF) and (zz.cur_ControlBlk_Index == kBW1):
                zz.trans_TIME = 50 // kFrameTime
                zz.trans_LEVEL = ((zz.controlBlockArray[kF1].curP_START_Targ) >> 3) + cb.curP_END_Targ
        else:
            zz.trans_TIME = 20 // kFrameTime
        if vv.next_Phon_CF == _SIL_:
            zz.trans_LEVEL = ((kBW3 - cur_ControlBlk_Type) * 50) + cb.curP_END_Targ
            zz.trans_TIME = 50 // kFrameTime
        elif vv.cur_Phon_CF == _SIL_:
            zz.trans_LEVEL = ((kBW3 - cur_ControlBlk_Type) * 50) + cb.nextP_START_Targ
            zz.trans_TIME = 50 // kFrameTime
        if vv.next_PhonFlags_CF & kNasalF:
            zz.trans_LEVEL = cb.curP_END_Targ
            if zz.cur_ControlBlk_Index == kBW2:
                if ((vv.next_Phon_CF == _n_) or (vv.next_Phon_CF == _EN_)) and (zz.Rank_FWD_Tbl[vv.cur_Phon_CF] != kFrontR):
                    zz.trans_LEVEL += 60
                    zz.trans_TIME = 60 // kFrameTime
            elif zz.cur_ControlBlk_Index == kBW1:
                zz.trans_LEVEL += 100
                zz.trans_TIME = 100 // kFrameTime
        if vv.cur_PhonFlags_CF & kNasalF:
            zz.trans_TIME = 0

    elif (cur_ControlBlk_Type == kResonAmpType) or (cur_ControlBlk_Type == kSourceAmpType):
        ampT = cb.nextP_START_Targ - 10
        if zz.trans_LEVEL < ampT:
            zz.trans_LEVEL = ampT
            if vv.cur_Phon_CF == _SIL_:
                zz.trans_TIME = 70 // kFrameTime
        if (zz.cur_ControlBlk_Index == kAV) and (zz.trans_LEVEL < cb.nextP_START_Targ):
            if (vv.cur_Phon_CF != _v_) and (vv.cur_Phon_CF != _DH_) and (vv.cur_Phon_CF != _JH_) and (vv.cur_Phon_CF != _ZH_) and (vv.cur_Phon_CF != _z_):
                zz.trans_TIME = 0
                if vv.cur_PhonFlags_CF & (kStopF + kAffricateF):
                    if vv.cur_PhonFlags_CF & kVoicedF:
                        zz.trans_LEVEL = cb.curP_END_Targ - 3
                        zz.trans_TIME = 45 // kFrameTime
                    else:
                        zz.trans_TIME = 0
                    # goto Done
                    if zz.trans_TIME > vv.cur_Phon_Dur_CF:
                        zz.trans_TIME = vv.cur_Phon_Dur_CF
                    if zz.trans_TIME > 130 // kFrameTime:
                        zz.trans_TIME = 130 // kFrameTime
                    cb.TAIL_START_time = vv.cur_Phon_Dur_CF - zz.trans_TIME
                    if zz.trans_TIME < 0:
                        zz.trans_TIME = 0
                    return
        if (vv.cur_PhonFlags_CF & kVoicedF) and (vv.next_PhonFlags_CF & kNasalF):
            zz.trans_TIME = 0
        if vv.cur_PhonFlags_CF & kNasalF:
            if (vv.next_PhonFlags_CF & kVoicedF) and not (vv.cur_PhonFlags_CF & kPlosFricF) and not (vv.next_PhonCtrl_CF & kPlosive_Release):
                zz.trans_TIME = 0
            else:
                zz.trans_TIME = 40 // kFrameTime
        ampT = cb.curP_END_Targ - 10
        if vv.cur_PhonFlags_CF & kPlosiveF:
            zz.trans_TIME = 15 // kFrameTime
            if (vv.cur_PhonFlags_CF & kStopF) or (vv.cur_Phon_CF == _DX_) or (vv.cur_Phon_CF == _QX_) or (vv.cur_Phon_CF == _DD_):
                ampT = cb.curP_END_Targ
        if zz.trans_LEVEL < ampT:
            zz.trans_LEVEL = ampT - 3
            zz.trans_TIME = 20 // kFrameTime
        if zz.cur_ControlBlk_Index == kAV:
            if (zz.trans_LEVEL < ampT) or ((ampT > 0) and (vv.next_PhonCtrl_CF & kPlosive_Release)):
                zz.trans_LEVEL = ampT + 3
                if (vv.next_Phon_CF == _SIL_) or (vv.next_PhonCtrl_CF & kPlosive_Release):
                    zz.trans_TIME = 75 // kFrameTime
        if vv.next_Phon_CF >= _p_:
            if not (vv.cur_PhonFlags_CF & kNasalF) or (zz.cur_ControlBlk_Index != kAV):
                zz.trans_TIME = 0
        if zz.cur_ControlBlk_Index == kAF:
            if (vv.cur_Phon_CF == _f_) or (vv.cur_Phon_CF == _TH_) or (vv.cur_Phon_CF == _s_) or (vv.cur_Phon_CF == _SH_):
                if (vv.next_PhonFlags_CF & kVoicedF) and not (vv.next_PhonFlags_CF & kPlosFricF):
                    zz.trans_TIME = 40 // kFrameTime
                    zz.trans_LEVEL = 52
            if (vv.cur_PhonFlags_CF & kVowelF) and (vv.next_Phon_CF == _SIL_):
                zz.trans_TIME = 130 // kFrameTime
                zz.trans_LEVEL = 52

    if zz.trans_TIME > vv.cur_Phon_Dur_CF:
        zz.trans_TIME = vv.cur_Phon_Dur_CF
    if zz.trans_TIME > 130 // kFrameTime:
        zz.trans_TIME = 130 // kFrameTime
    cb.TAIL_START_time = vv.cur_Phon_Dur_CF - zz.trans_TIME
    if zz.trans_TIME < 0:
        zz.trans_TIME = 0


# ---------------------------------------------------------------------------
# Insert_Burst (formantSynth.c:402)
# ---------------------------------------------------------------------------

def insert_burst(vv: VoiceVar):
    zz: FormantVar = vv.synthVars
    if vv.cur_PhonFlags_CF & kPlosiveF:
        burstDur = zz.BurstDurTbl[vv.cur_Phon_CF] // kFrameTime
        if (vv.cur_PhonFlags_CF & kStopF) and not (vv.cur_PhonFlags_CF & kVoicedF):
            if vv.next_PhonFlags_CF & (kStopF + kNasalF):
                if vv.next_PhonCtrl_CF & kPrimOrEmphStress:
                    burstDur = 0
                else:
                    burstDur >>= 1
        if burstDur > 1:
            if ((vv.cur_PhonFlags_CF & kStopF) and (vv.next_PhonFlags_CF & kPlosFricF)) or (vv.cur_Phon_Dur_CF < 50 // kFrameTime):
                pass
        burstClosureDur = vv.cur_Phon_Dur_CF - burstDur
        if (vv.cur_PhonFlags_CF & kAffricateF) and (burstClosureDur > 80 // kFrameTime):
            burstClosureDur = 80 // kFrameTime
        for i in range(kAp2, kAB + 1):
            zz.controlBlockArray[i].onset_END_TIME = burstClosureDur
            zz.controlBlockArray[i].onset_VAL = 0

    burstReleaseDur = 0
    if (vv.prev_PhonFlags_CF & kStopF) and not (vv.prev_PhonFlags_CF & kVoicedF) and (vv.cur_PhonFlags_CF & kSonorant1F):
        burstReleaseDur = 40 // kFrameTime
        zz.controlBlockArray[kAV].onset_VAL = 0
        if zz.Rank_FWD_Tbl[vv.next_Phon_CF] == kFrontR:
            zz.controlBlockArray[kAF].onset_VAL = 48
        else:
            zz.controlBlockArray[kAF].onset_VAL = 54
        if not (vv.cur_PhonCtrl_CF & kVowelF):
            burstReleaseDur = 25 // kFrameTime
            zz.controlBlockArray[kAF].onset_VAL -= 3
        if (vv.cur_PhonCtrl_CF & kLiqGlideF) or (vv.cur_Phon_CF == _ER_):
            zz.controlBlockArray[kAF].onset_VAL += 3
        if vv.prev2_Phon_CF == _s_:
            if not (vv.prev2_PhonCtrl_CF & kSyllableTypeField):
                burstReleaseDur = 10 // kFrameTime
        else:
            if not (vv.cur_PhonCtrl_CF & kVowelF):
                burstReleaseDur += 20 // kFrameTime
        if burstReleaseDur >= vv.cur_Phon_Dur_CF:
            burstReleaseDur = vv.cur_Phon_Dur_CF - 1
        if burstReleaseDur > (vv.cur_Phon_Dur_CF >> 1):
            if (vv.cur_PhonFlags_CF & kVowelF) and (vv.cur_PhonCtrl_CF & kPrimOrEmphStress):
                burstReleaseDur = vv.cur_Phon_Dur_CF >> 1
        if vv.cur_PhonCtrl_CF & kPlosive_Release:
            burstReleaseDur = vv.cur_Phon_Dur_CF
            zz.controlBlockArray[kAF].onset_VAL = 0
        zz.controlBlockArray[kAV].onset_END_TIME = burstReleaseDur
        zz.controlBlockArray[kAF].onset_END_TIME = burstReleaseDur
        zz.controlBlockArray[kBW1].onset_END_TIME = burstReleaseDur
        zz.controlBlockArray[kBW2].onset_END_TIME = burstReleaseDur
        zz.controlBlockArray[kBW1].onset_VAL = zz.controlBlockArray[kBW1].curP_START_Targ + 250
        zz.controlBlockArray[kBW2].onset_VAL = zz.controlBlockArray[kBW2].curP_START_Targ + 70

    if (vv.cur_PhonFlags_CF & kStopF) and (vv.cur_PhonFlags_CF & kVoicedF) and (vv.prev_PhonFlags_CF & kVoicedF) and not (vv.next_PhonFlags_CF & kVoicedF) and (vv.cur_Phon_CF != _TX_):
        zz.controlBlockArray[kAV].onset_END_TIME = vv.cur_Phon_Dur_CF - (10 // kFrameTime)
        zz.controlBlockArray[kBW1].onset_END_TIME = vv.cur_Phon_Dur_CF
        zz.controlBlockArray[kBW2].onset_END_TIME = vv.cur_Phon_Dur_CF
        zz.controlBlockArray[kBW3].onset_END_TIME = vv.cur_Phon_Dur_CF
        zz.controlBlockArray[kAV].onset_VAL = 53
        zz.controlBlockArray[kBW1].onset_VAL = 1000
        zz.controlBlockArray[kBW2].onset_VAL = 1000
        zz.controlBlockArray[kBW3].onset_VAL = 1200


# ---------------------------------------------------------------------------
# Init_Ctrls_for_New_Phon (formantSynth.c:2089)
# ---------------------------------------------------------------------------

def init_ctrls_for_new_phon(vv: VoiceVar):
    zz: FormantVar = vv.synthVars
    fill_phon_targets(vv)
    for zz.cur_ControlBlk_Index in range(kF1, kNumOfBlocks):
        cb = zz.controlBlockArray[zz.cur_ControlBlk_Index]
        cur_ControlBlk_Type = zz.CtrlBlockTypeTbl[zz.cur_ControlBlk_Index]
        cb.prevP_END_Targ = cb.curP_END_Targ
        cb.nextP_START_Targ = get_first_target(vv, vv.cur_PhonBuf_Index_CF + 1)
        cb.curTarget_OFFS = 0
        cb.curP_START_Targ = get_target(vv, vv.cur_PhonBuf_Index_CF)

        if cb.curP_START_Targ < kNoValue:
            get_diphthongs(vv, cb.curP_START_Targ & 0x7FFF)
        else:
            cb.curTarget_STEP = 0
            cb.curTarget_TIME = vv.cur_Phon_Dur_CF
            if cur_ControlBlk_Type == kFreqType:
                tempL = k1pct * 10
                if vv.phon_Ctrl_Buf_2[vv.cur_PhonBuf_Index_CF] & kIsStressed:
                    if zz.cur_ControlBlk_Index == kF2:
                        tempL = k1pct * 25
                    else:
                        tempL = k1pct * 15
                cb.curP_START_Targ += ((((cb.prevP_END_Targ + cb.nextP_START_Targ) >> 1) - cb.curP_START_Targ) * tempL) >> 16
            cb.curP_END_Targ = cb.curP_START_Targ

        if cur_ControlBlk_Type == kFreqType:
            tempL = k1pct * 10
            cb.nextP_START_Targ += ((cb.curP_END_Targ - cb.nextP_START_Targ) * tempL) >> 16

        zz.trans_LEVEL = (cb.prevP_END_Targ + cb.curP_START_Targ) >> 1
        zz.trans_TIME = 32 // kFrameTime
        head_rules(vv)
        cb.HEAD_offs = 0
        if zz.trans_TIME > 0:
            cb.HEAD_offs = (zz.trans_LEVEL - cb.curP_START_Targ) << kStepSizeRes
            if cb.HEAD_offs != 0:
                tempL = (zz.One_Over_X_Tbl[zz.trans_TIME] * cb.HEAD_offs) >> 16
                cb.HEAD_step = tempL
                cb.HEAD_offs = tempL * zz.trans_TIME

        zz.trans_LEVEL = (cb.curP_END_Targ + cb.nextP_START_Targ) >> 1
        zz.trans_TIME = 25 // kFrameTime
        tail_rules(vv)
        cb.TAIL_offs = 0
        cb.TAIL_step = 0
        if zz.trans_TIME > 0:
            tempS = (zz.trans_LEVEL - cb.curP_END_Targ) << kStepSizeRes
            if tempS != 0:
                cb.TAIL_step = (zz.One_Over_X_Tbl[zz.trans_TIME] * tempS) >> 16

    insert_burst(vv)


# ---------------------------------------------------------------------------
# Phon_Boundry_Pitch (BackEnd.c:870)
# ---------------------------------------------------------------------------

def phon_boundry_pitch(vv: VoiceVar):
    if vv.time_IntoPhon_CP >= vv.cur_PhonDur_CP:
        vv.time_IntoPhon_CP -= vv.cur_PhonDur_CP
        vv.phon_Index_CP += 1
        vv.cur_PhonDur_CP = vv.dur_Buf[vv.phon_Index_CP]

        cur_Phon = e_get_phon(vv, vv.phon_Index_CP)
        cur_Flags = vv.phonFlags2[cur_Phon]
        cur_Ctrl = e_get_phon_ctrl(vv, vv.phon_Index_CP + 1)

        next_Phon = e_get_phon(vv, vv.phon_Index_CP + 1)
        next_Flags = vv.phonFlags2[next_Phon]
        next_Ctrl = e_get_phon_ctrl(vv, vv.phon_Index_CP + 1)

        if vv.pitch_Boundry == 0:
            vv.pitch_Boundry = kNeverHappens

        if vv.pitch_Boundry > 0:
            vv.pitch_Boundry = 0

        vv.pbHold = kNeverHappens
        vv.pbLowGain = False

        if (cur_Flags & kVowel1F) and \
           not (next_Ctrl & kMid_Syllable_In_Word) and \
           ((cur_Ctrl & kSyllableTypeField) >= kWord_End) and \
           (next_Phon != _YU_):
            if cur_Flags & kVowelF:
                if (cur_Phon == next_Phon) and (next_Ctrl & kPrimOrEmphStress):
                    vv.pbHold = vv.cur_PhonDur_CP
                elif (cur_Ctrl & kSyllableTypeField) >= kPrep_End:
                    vv.pbHold = vv.cur_PhonDur_CP
                    vv.pbLowGain = True
            else:
                if not (cur_Flags & kStopF) and (cur_Phon != _DX_) and (next_Ctrl & kPrimOrEmphStress):
                    vv.pbHold = vv.cur_PhonDur_CP

        if next_Flags & kGStopF:
            vv.pbHold = vv.cur_PhonDur_CP

        if cur_Flags & kGStopF:
            vv.pbHold = vv.cur_PhonDur_CP
            return

    if (vv.time_IntoPhon_CP == 50 // kFrameTime) or (vv.time_IntoPhon_CP == vv.cur_PhonDur_CP - 1):
        vv.pitch_Boundry = vv.pbHold
        vv.low_Gain_CP = vv.pbLowGain


# ---------------------------------------------------------------------------
# Calc_Ramp_Steps (BackEnd.c:678)
# ---------------------------------------------------------------------------

kRampMode = 0
kSusMode = 1


def calc_ramp_steps(vv: VoiceVar):
    rampIndex = 0
    mode = kRampMode
    accum = 1

    for i in range(vv.phonBuf_2_In_Index):
        cur_Ctrl = e_get_phon_ctrl(vv, i)
        cur_SyllableType = cur_Ctrl & kSyllableTypeField
        cur_Dur = vv.dur_Buf[i]

        if mode == kRampMode:
            if (cur_Ctrl & kSilenceTypeField) or (cur_SyllableType & kTerm_End):
                vv.rampSteps[rampIndex] = ((vv.baselineFall_START - vv.baselineFall_END) << 16) // accum
                if cur_Ctrl & kSilenceTypeField:
                    pass
                else:
                    if (vv.end_Punctuation == _Comma_) or (vv.end_Punctuation == _Quest_):
                        vv.rampSteps[rampIndex] >>= 1
                if rampIndex < kMaxRamps:
                    rampIndex += 1
                accum = 1
            else:
                accum += cur_Dur
        else:
            if cur_Ctrl & kSilenceTypeField:
                mode = kRampMode
                accum = 1
                i += 1

    vv.curRamp = 0
    vv.down_Ramp_Step = vv.rampSteps[0]


# ---------------------------------------------------------------------------
# StartNew_PitchClause (BackEnd.c:1284)
# ---------------------------------------------------------------------------

def start_new_pitch_clause(vv: VoiceVar):
    vv.baseline_Start_Offset = vv.baselineFall_START
    vv.baseline_End_Offset = vv.baselineFall_END

    vv.down_Ramp_Offset = 0
    vv.down_Ramp_Offset_Save1 = 0
    vv.down_Ramp_Offset_Save2 = 0

    if vv.start_of_Paragraph_Flag:
        vv.baseline_Start_Offset += kHZ_12
        vv.baseline_End_Offset += kHZ_7
        vv.start_of_Paragraph_Flag = False

    vv.next_PitchBuf_Time = vv.pitch_Buf_Time[0]
    vv.phon_Index_Targ = -1
    vv.phon_Index_CP = -1
    vv.pitchBuf_Out_Index = 0
    vv.time_IntoPhon_CP = 0
    vv.cur_Phon_Dur_CC = 0
    vv.cur_PhonDur_CP = 0

    vv.next_PitchBuf_Time_Save1 = vv.next_PitchBuf_Time
    vv.phon_Index_Targ_Save1 = vv.phon_Index_Targ
    vv.phon_Index_CP_Save1 = vv.phon_Index_CP
    vv.pitchBuf_Out_Index_Save1 = 0
    vv.time_IntoPhon_CP_Save1 = 0
    vv.cur_Phon_Dur_CC_Save1 = 0
    vv.cur_PhonDur_CP_Save1 = 0

    vv.next_PitchBuf_Time_Save2 = vv.next_PitchBuf_Time_Save1
    vv.phon_Index_Targ_Save2 = vv.phon_Index_Targ_Save1
    vv.phon_Index_CP_Save2 = vv.phon_Index_CP_Save1
    vv.pitchBuf_Out_Index_Save2 = 0
    vv.time_IntoPhon_CP_Save2 = 0
    vv.cur_Phon_Dur_CC_Save2 = 0
    vv.cur_PhonDur_CP_Save2 = 0

    vv.phon_Dur_Delay = 0
    vv.uvPhon_Pitch_Targ = 0
    vv.phon_Pitch_Offset_1 = 0

    vv.fallRise_Offset = 0
    vv.fallRise1_Offset = 0
    vv.fallRise_Offset_Save1 = 0
    vv.fallRise_Offset_Save2 = 0
    vv.fallRise1_Offset_Save1 = 0
    vv.fallRise1_Offset_Save2 = 0
    vv.stress_Target = 0
    vv.stress_Target_Save1 = 0
    vv.stress_Target_Save2 = 0
    vv.punct_Offset = 0
    vv.punct_Offset_Save1 = 0
    vv.punct_Offset_Save2 = 0

    vv.VP_baselinePitch_Save1 = vv.VP_baselinePitch
    vv.VP_baselinePitch_Save2 = vv.VP_baselinePitch

    vv.time_IntoPhon_Targ = vv.pitch_Clause_StartTime
    vv.cur_PitchBuf_Time = vv.time_IntoPhon_Targ >> 1

    vv.time_IntoPhon_Targ_Save1 = vv.time_IntoPhon_Targ
    vv.cur_PitchBuf_Time_Save1 = vv.cur_PitchBuf_Time

    vv.time_IntoPhon_Targ_Save2 = vv.time_IntoPhon_Targ_Save1
    vv.cur_PitchBuf_Time_Save2 = vv.cur_PitchBuf_Time_Save1


# ---------------------------------------------------------------------------
# Interpolate_Pitch (BackEnd.c:969)
# ---------------------------------------------------------------------------

def interpolate_pitch(vv: VoiceVar):
    collect = True
    while collect:
        if (vv.cur_PitchBuf_Time >= vv.next_PitchBuf_Time) and \
           (vv.pitchBuf_Out_Index < vv.pitchBuf_In_Index):
            vv.cur_PitchBuf_Pitch = vv.pitch_Buf_Freq[vv.pitchBuf_Out_Index]
            vv.cur_PitchBuf_Flags = vv.pitch_Buf_Flags[vv.pitchBuf_Out_Index]

            vv.cur_PitchBuf_Time -= vv.next_PitchBuf_Time
            vv.pitchBuf_Out_Index += 1

            vv.next_PitchBuf_Time = vv.pitch_Buf_Time[vv.pitchBuf_Out_Index]

            if vv.cur_PitchBuf_Flags & kResetDecline:
                vv.down_Ramp_Offset = 0

            elif vv.cur_PitchBuf_Flags & kPhraseReset:
                vv.down_Ramp_Offset = (vv.baselineFall_START - vv.baselineFall_END) << 14
                if vv.curRamp < kMaxRamps:
                    vv.curRamp += 1
                vv.down_Ramp_Step = vv.rampSteps[vv.curRamp]

            elif vv.cur_PitchBuf_Flags & kPitchRiseFall_Flg:
                vv.fallRise_Offset += vv.cur_PitchBuf_Pitch
                if vv.cur_PitchBuf_Pitch < 0:
                    if vv.stress_Target > 0:
                        vv.stress_Target = 0
                else:
                    if vv.stress_Target < 0:
                        vv.stress_Target = 0

            elif vv.cur_PitchBuf_Flags & kPitchRiseFall1_Flg:
                vv.fallRise1_Offset += vv.cur_PitchBuf_Pitch

            elif vv.cur_PitchBuf_Flags & kPitchStress_Flg:
                vv.stress_Target = vv.cur_PitchBuf_Pitch
                vv.stress_Active_Time = vv.stress_Duration

            else:
                vv.punct_Offset = vv.cur_PitchBuf_Pitch << 1
        else:
            collect = False

    if not vv.singing:
        vv.baseLine_Offset = vv.baseline_Start_Offset - (vv.down_Ramp_Offset >> 16) + \
                             (vv.user_Pitch_Buf2[vv.phon_Index_Targ] if vv.phon_Index_Targ >= 0 else 0)

        if vv.baseLine_Offset > vv.baseline_End_Offset:
            vv.down_Ramp_Offset += vv.down_Ramp_Step

        vv.stress_Active_Time -= 1
        if vv.stress_Active_Time < 0:
            vv.stress_Target = 0

        if (vv.time_IntoPhon_Targ > (vv.cur_Phon_Dur_CC + vv.phon_Dur_Delay)) and \
           (vv.phon_Index_Targ < vv.phonBuf_2_In_Index):
            vv.time_IntoPhon_Targ -= vv.cur_Phon_Dur_CC

            vv.phon_Index_Targ += 1
            vv.cur_Phon_Dur_CC = vv.dur_Buf[vv.phon_Index_Targ]
            vv.phon_Dur_Delay = 0

            cur_Phon = e_get_phon(vv, vv.phon_Index_Targ)
            cur_Ctrl = e_get_phon_ctrl(vv, vv.phon_Index_Targ)
            cur_Flags = vv.phonFlags2[cur_Phon]
            next_Phon = e_get_phon(vv, vv.phon_Index_Targ + 1)
            next_Flags = vv.phonFlags2[next_Phon]

            vv.phon_Pitch_Offset = vv.phonPitchTbl[cur_Phon]
            vv.phon_Pitch_Offset >>= 1

            if not (next_Flags & kVoicedF):
                vv.phon_Dur_Delay = 25 // kFrameTime

            if cur_Flags & kVoicedF:
                vv.phon_Pitch_Offset_1 = vv.phon_Pitch_Offset << 1
                vv.uvPhon_Pitch_Targ = 0
            else:
                vv.uvPhon_Pitch_Targ = vv.phon_Pitch_Offset << kStepSizeRes
                vv.phon_Pitch_Offset_1 = 0
                if cur_Flags & kStopF:
                    vv.phon_Dur_Delay = 30 // kFrameTime
                else:
                    vv.phon_Dur_Delay = 0

        phon_boundry_pitch(vv)

        stress = vv.stress_Target if vv.stress_Target is not None else 0
        fr = vv.fallRise_Offset if vv.fallRise_Offset is not None else 0
        po = vv.punct_Offset if vv.punct_Offset is not None else 0
        bl = vv.baseLine_Offset if vv.baseLine_Offset is not None else 0
        ppo1 = vv.phon_Pitch_Offset_1 if vv.phon_Pitch_Offset_1 is not None else 0

        phon_Pitch_Target = ((stress + fr + po + bl) * vv.VP_intonation) >> 16
        phon_Pitch_Target = (phon_Pitch_Target + ppo1) << kStepSizeRes

        if vv.newSentence:
            vv.pFilter_Out1 = vv.pFilter_Out2 = vv.VP_baselinePitch
            vv.newSentence = False

        vv.pFilter_Out1 = ((vv.pFilter_In_Gain * phon_Pitch_Target) +
                           (vv.pFilter_FB_Gain * vv.pFilter_Out1)) >> 16

        vv.pFilter_Out2 = ((vv.pFilter_In_Gain * (vv.pFilter_Out1 + vv.uvPhon_Pitch_Targ)) +
                           (vv.pFilter_FB_Gain * vv.pFilter_Out2)) >> 16

        vv.basePitch_Offset = vv.pFilter_Out2 >> kStepSizeRes

        vv.phon_Pitch_Offset_1 = (vv.phon_Pitch_Offset_1 * 98 * pct) >> 16

        pbIndex = vv.time_IntoPhon_CP - vv.pitch_Boundry
        if pbIndex < 0:
            pbIndex = -pbIndex

        if pbIndex <= (45 // kFrameTime):
            if vv.low_Gain_CP:
                vv.basePitch_Offset += (pbIndex * (10 // (45 // kFrameTime))) - 10
            else:
                vv.basePitch_Offset += (pbIndex * (80 // (45 // kFrameTime))) - 80

        vv.controlF0 = ((vv.basePitch_Offset * vv.VP_pitchRange) >> 16) + vv.VP_baselinePitch

        vv.vibrato_Phase1 = (vv.vibratoFreq + vv.vibrato_Phase1) & 0xFFFFFF
        sine_idx = vv.vibrato_Phase1 >> 16
        vibrato = (vv.synthVars.SineWavePtr[sine_idx] if hasattr(vv.synthVars, 'SineWavePtr') else 0) - 128
        if vv.speech_Rate >= 100:
            vv.controlF0 += (vibrato * vv.vibratoDepth1) >> 16
        else:
            vv.controlF0 += (vibrato * vv.vibratoDepth2) >> 16
    else:
        if vv.newSentence:
            vv.portamentoAccum = vv.VP_baselinePitch << 16
            vv.newSentence = False
            vv.newPortaTarget = False

        elif vv.newPortaTarget:
            if vv.portamentoStep > 0:
                vv.portamentoAccum += vv.portamentoStep
                if (vv.portamentoAccum >> 16) >= vv.VP_baselinePitch:
                    vv.portamentoAccum = vv.VP_baselinePitch << 16
                    vv.newPortaTarget = False
            elif vv.portamentoStep < 0:
                vv.portamentoAccum += vv.portamentoStep
                if (vv.portamentoAccum >> 16) < vv.VP_baselinePitch:
                    vv.portamentoAccum = vv.VP_baselinePitch << 16
                    vv.newPortaTarget = False
            else:
                vv.portamentoAccum = vv.VP_baselinePitch << 16
                vv.newPortaTarget = False

        vv.controlF0 = vv.portamentoAccum >> 16

        vv.vibrato_Phase1 = (vv.vibratoFreq + vv.vibrato_Phase1) & 0xFFFFFF
        sine_idx = vv.vibrato_Phase1 >> 16
        vibrato = (vv.synthVars.SineWavePtr[sine_idx] if hasattr(vv.synthVars, 'SineWavePtr') else 0) - 128
        if vv.cur_PhonCtrl_CF & kLowVibrato:
            vv.controlF0 += (vibrato * vv.vibratoDepth2) >> 16
        else:
            vv.controlF0 += (vibrato * vv.vibratoDepth1) >> 16

    if vv.controlF0 < 0:
        vv.controlF0 = 0

    vv.cur_PitchBuf_Time += 1
    vv.time_IntoPhon_Targ += 1
    vv.time_IntoPhon_CP += 1


# ---------------------------------------------------------------------------
# Interpolate_Formants (formantSynth.c:2229)
# ---------------------------------------------------------------------------

def interpolate_formants(vv: VoiceVar):
    zz: FormantVar = vv.synthVars
    for i in range(kF1, kFNZ + 1):
        cb = zz.controlBlockArray[i]
        if vv.dur_Done_in_Phon_CF > cb.curTarget_TIME:
            start = cb.ptrToTargetList
            cb.curTarget_TIME = zz.diphEntryArray[start]
            cb.curTarget_STEP = zz.diphEntryArray[start + 1]
            cb.ptrToTargetList = start + 2
            cb.curP_START_Targ += (cb.curTarget_OFFS >> kStepSizeRes)
            cb.curTarget_OFFS = 0
        cb.curTarget_OFFS += cb.curTarget_STEP
        offset = cb.curTarget_OFFS + cb.HEAD_offs
        if cb.HEAD_offs != 0:
            cb.HEAD_offs -= cb.HEAD_step
        if vv.dur_Done_in_Phon_CF >= cb.TAIL_START_time:
            offset += cb.TAIL_offs
            cb.TAIL_offs += cb.TAIL_step
        val = cb.curP_START_Targ + (offset >> kStepSizeRes)
        zz.controlData[i] = val
        if cb.onset_END_TIME > 0:
            if vv.dur_Done_in_Phon_CF < cb.onset_END_TIME:
                zz.controlData[i] = cb.onset_VAL

    for i in range(kAV, kAB + 1):
        cb = zz.controlBlockArray[i]
        offset = cb.curP_START_Targ + (cb.HEAD_offs >> kStepSizeRes)
        if cb.HEAD_offs != 0:
            cb.HEAD_offs -= cb.HEAD_step
        if vv.dur_Done_in_Phon_CF >= cb.TAIL_START_time:
            offset += (cb.TAIL_offs >> kStepSizeRes)
            cb.TAIL_offs += cb.TAIL_step
        zz.controlData[i] = offset
        if cb.onset_END_TIME > 0:
            if vv.dur_Done_in_Phon_CF < cb.onset_END_TIME:
                zz.controlData[i] = cb.onset_VAL
            elif (i >= kAp2) and (vv.dur_Done_in_Phon_CF == (cb.onset_END_TIME + 1)) and (zz.controlData[i] > 10):
                zz.controlData[i] -= 10


# ---------------------------------------------------------------------------
# SaveFrame (Say.c:1055)
# ---------------------------------------------------------------------------

def save_frame(vv: VoiceVar):
    zz: FormantVar = vv.synthVars
    if zz.curFrameBuf == kFrame1:
        frameBuf = zz.frameBuf1
    else:
        frameBuf = zz.frameBuf2

    curF1 = zz.controlData[kF1]
    curF2 = zz.controlData[kF2]
    curF3 = zz.controlData[kF3]

    while (curF2 - curF1) < 200:
        curF1 -= 10
    while (curF3 - curF2) < 600:
        curF3 += 10

    frameBuf.f1 = e_hz_to_pitch(vv, curF1)
    frameBuf.f2 = e_hz_to_pitch(vv, curF2)
    frameBuf.f3 = e_hz_to_pitch(vv, curF3)

    frameBuf.bw1 = (zz.controlData[kBW1] * zz.voiceBWgain1) >> 16
    frameBuf.bw2 = (zz.controlData[kBW2] * zz.voiceBWgain2) >> 16
    frameBuf.bw3 = (zz.controlData[kBW3] * zz.voiceBWgain3) >> 16

    frameBuf.FNZ = e_hz_to_pitch(vv, zz.controlData[kFNZ])

    if zz.controlData[kAp2] < 0: zz.controlData[kAp2] = 0
    if zz.controlData[kAp3] < 0: zz.controlData[kAp3] = 0
    if zz.controlData[kAp4] < 0: zz.controlData[kAp4] = 0
    if zz.controlData[kAp5] < 0: zz.controlData[kAp5] = 0
    if zz.controlData[kAp6] < 0: zz.controlData[kAp6] = 0
    if zz.controlData[kAB] < 0: zz.controlData[kAB] = 0
    if zz.controlData[kAV] < 0: zz.controlData[kAV] = 0
    if zz.controlData[kAF] < 0: zz.controlData[kAF] = 0

    frameBuf.Av = e_log_to_lin(vv, zz.controlData[kAV])
    frameBuf.Af = e_log_to_lin(vv, zz.controlData[kAF])
    frameBuf.a2 = e_log_to_lin(vv, zz.controlData[kAp2])
    frameBuf.a3 = e_log_to_lin(vv, zz.controlData[kAp3])
    frameBuf.a4 = e_log_to_lin(vv, zz.controlData[kAp4])
    frameBuf.a5 = e_log_to_lin(vv, zz.controlData[kAp5])
    frameBuf.a6 = e_log_to_lin(vv, zz.controlData[kAp6])
    frameBuf.AB = e_log_to_lin(vv, zz.controlData[kAB])

    frameBuf.f0 = vv.controlF0
    frameBuf.phon_Edge = 1 if vv.starting_New_Phon else 0
    frameBuf.marker = vv.frameMarker
    vv.frameMarker = kNoMarker


# ---------------------------------------------------------------------------
# synth_SpeakPhon / synth_StartNewPhon (formantSynth.c)
# ---------------------------------------------------------------------------

# Hook for test harness (intercepts after save_frame, before buffer toggle)
post_frame_hook = None

def synth_speak_phon(vv: VoiceVar):
    zz: FormantVar = vv.synthVars
    interpolate_formants(vv)
    save_frame(vv)
    if zz.curFrameBuf == kFrame1:
        zz.curFrameBuf = kFrame2
    else:
        zz.curFrameBuf = kFrame1
    vv.dur_Done_in_Phon_CF += 1
    if post_frame_hook:
        post_frame_hook(vv)


def synth_start_new_phon(vv: VoiceVar):
    init_ctrls_for_new_phon(vv)


def synth_start_talk(vv: VoiceVar):
    zz: FormantVar = vv.synthVars
    init_control_blocks(zz)
    zz.curFrameBuf = kFrame1
    e_fill_next_frame(vv)
    init_say(vv)


# ---------------------------------------------------------------------------
# StartNewPhon (BackEnd.c:747)
# ---------------------------------------------------------------------------

def do_note(vv: VoiceVar):
    """BackEnd.c DoNote — embedded pitch (non-scripted note) handling."""
    note = vv.user_Note_Buf2[vv.cur_PhonBuf_Index_CF] if hasattr(vv, 'user_Note_Buf2') else 0
    if note != 0 and not (vv.phon_Ctrl_Buf_2[vv.cur_PhonBuf_Index_CF] & kSilenceDuration):
        note = s16((note & 0xFF) << 8)
        if note != 0x7F00:
            vv.VP_baselinePitch = vv.voiceNaturalPitch + ((note * 0x1555) >> 16)
            if vv.VP_baselinePitch < 0:
                vv.VP_baselinePitch = 0


def do_note_script(vv: VoiceVar):
    """BackEnd.c DoNoteScript — advances the embedded note/song script."""
    if (e_get_phon_ctrl(vv, vv.cur_PhonBuf_Index_CF) & kSyllable_Start) and \
       not (vv.phon_Ctrl_Buf_2[vv.cur_PhonBuf_Index_CF] & kSilenceDuration):
        note = s16((vv.notesBuf[vv.songIndex] & 0xFF) << 8)
        vv.songIndex += 1
        if vv.songIndex >= vv.numOfNotes:
            vv.songIndex = 0
        if note != 0x7F00:
            vv.last_baseline = vv.VP_baselinePitch
            vv.VP_baselinePitch = vv.voiceNaturalPitch + ((note * 0x1555) >> 16)
            if vv.VP_baselinePitch < 0:
                vv.VP_baselinePitch = 0
            level = (vv.VP_baselinePitch - vv.last_baseline) << 16
            # C integer division truncates toward zero
            vv.portamentoStep = int(level / vv.portamento)
            vv.newPortaTarget = True


def start_new_phon(vv: VoiceVar):
    if e_get_phon_ctrl(vv, vv.cur_PhonBuf_Index_CF) & kWord_Start:
        vv.nLastWordStart = vv.lastWordStart
        vv.lastWordStart = vv.cur_PhonBuf_Index_CF
        vv.pFilter_Out1_Save2 = vv.pFilter_Out1_Save1
        vv.pFilter_Out2_Save2 = vv.pFilter_Out2_Save1
        vv.down_Ramp_Offset_Save2 = vv.down_Ramp_Offset_Save1
        vv.fallRise_Offset_Save2 = vv.fallRise_Offset_Save1
        vv.fallRise1_Offset_Save2 = vv.fallRise1_Offset_Save1
        vv.stress_Target_Save2 = vv.stress_Target_Save1
        vv.punct_Offset_Save2 = vv.punct_Offset_Save1
        vv.next_PitchBuf_Time_Save2 = vv.next_PitchBuf_Time_Save1
        vv.phon_Index_Targ_Save2 = vv.phon_Index_Targ_Save1
        vv.phon_Index_CP_Save2 = vv.phon_Index_CP_Save1
        vv.pitchBuf_Out_Index_Save2 = vv.pitchBuf_Out_Index_Save1
        vv.time_IntoPhon_CP_Save2 = vv.time_IntoPhon_CP_Save1
        vv.cur_Phon_Dur_CC_Save2 = vv.cur_Phon_Dur_CC_Save1
        vv.cur_PhonDur_CP_Save2 = vv.cur_PhonDur_CP_Save1
        vv.time_IntoPhon_Targ_Save2 = vv.time_IntoPhon_Targ_Save1
        vv.cur_PitchBuf_Time_Save2 = vv.cur_PitchBuf_Time_Save1
        vv.cmdBufCount_Save2 = vv.cmdBufCount_Save1
        vv.songIndex_Save2 = vv.songIndex_Save1
        vv.next_PitchBuf_Time_Save1 = vv.next_PitchBuf_Time
        vv.phon_Index_Targ_Save1 = vv.phon_Index_Targ
        vv.phon_Index_CP_Save1 = vv.phon_Index_CP
        vv.pitchBuf_Out_Index_Save1 = vv.pitchBuf_Out_Index
        vv.time_IntoPhon_CP_Save1 = vv.time_IntoPhon_CP
        vv.cur_Phon_Dur_CC_Save1 = vv.cur_Phon_Dur_CC
        vv.cur_PhonDur_CP_Save1 = vv.cur_PhonDur_CP
        vv.time_IntoPhon_Targ_Save1 = vv.time_IntoPhon_Targ
        vv.cur_PitchBuf_Time_Save1 = vv.cur_PitchBuf_Time
        vv.pFilter_Out1_Save1 = vv.pFilter_Out1
        vv.pFilter_Out2_Save1 = vv.pFilter_Out2
        vv.down_Ramp_Offset_Save1 = vv.down_Ramp_Offset
        vv.fallRise_Offset_Save1 = vv.fallRise_Offset
        vv.fallRise1_Offset_Save1 = vv.fallRise1_Offset
        vv.stress_Target_Save1 = vv.stress_Target
        vv.punct_Offset_Save1 = vv.punct_Offset
        vv.cmdBufCount_Save1 = vv.cmdBufCount
        vv.songIndex_Save1 = vv.songIndex
        vv.VP_baselinePitch_Save1 = vv.VP_baselinePitch

    # DoCtrl — embedded control commands (ported in _embeddedcmd.py; not
    # exercised by current voice set since no shipped voice/text data queues
    # any commands into vv.CMDQueue, so ctrlCount stays 0 here today)
    vv.ctrlCount = vv.user_Cmd_Buf2[vv.cur_PhonBuf_Index_CF]

    if vv.ctrlCount:
        from ._embeddedcmd import do_ctrl  # local import: avoids a module
        # cycle since _embeddedcmd.py imports helpers from this module
        do_ctrl(vv)

    if vv.sync_On_Marker:
        if vv.phon_Ctrl_Buf_2[vv.cur_PhonBuf_Index_CF] & kSampleMarker:
            vv.frameMarker = vv.markerBuf[vv.markerIndex]
            vv.markerIndex += 1
            if vv.markerIndex == vv.lastMarkerIndex:
                vv.markerIndex = 0
    elif vv.singScript:
        do_note_script(vv)
    else:
        do_note(vv)

    vv.dur_Done_in_Phon_CF = 0
    vv.cur_Phon_Dur_CF = vv.dur_Buf[vv.cur_PhonBuf_Index_CF]

    if vv.cur_PhonBuf_Index_CF == 0:
        vv.prev_Phon_CF = _SIL_
        vv.prev_PhonCtrl_CF = 0
        vv.prev2_Phon_CF = _SIL_
        vv.prev2_PhonCtrl_CF = 0
    else:
        vv.prev2_Phon_CF = vv.prev_Phon_CF
        vv.prev2_PhonCtrl_CF = vv.prev_PhonCtrl_CF
        vv.prev_Phon_CF = vv.cur_Phon_CF
        vv.prev_PhonCtrl_CF = vv.cur_PhonCtrl_CF

    vv.prev_PhonFlags_CF = vv.phonFlags2[vv.prev_Phon_CF]
    vv.cur_Phon_CF = e_get_phon(vv, vv.cur_PhonBuf_Index_CF)
    vv.cur_PhonCtrl_CF = e_get_phon_ctrl(vv, vv.cur_PhonBuf_Index_CF)
    vv.cur_PhonFlags_CF = vv.phonFlags2[vv.cur_Phon_CF]
    vv.next_Phon_CF = e_get_phon(vv, vv.cur_PhonBuf_Index_CF + 1)
    vv.next_PhonCtrl_CF = e_get_phon_ctrl(vv, vv.cur_PhonBuf_Index_CF + 1)
    vv.next_PhonFlags_CF = vv.phonFlags2[vv.next_Phon_CF]


# ---------------------------------------------------------------------------
# e_Fill_Next_Frame (BackEnd.c:4198)
# ---------------------------------------------------------------------------

def e_fill_next_frame(vv: VoiceVar):
    if vv.speakState == kSpeakNewPhon:
        start_new_phon(vv)
        synth_start_new_phon(vv)
        vv.speakState = kSpeakPhon
        vv.starting_New_Phon = True
    if vv.speakState == kSpeakPhon:
        interpolate_pitch(vv)
        synth_speak_phon(vv)
        vv.starting_New_Phon = False
        if vv.dur_Done_in_Phon_CF >= vv.cur_Phon_Dur_CF:
            vv.cur_PhonBuf_Index_CF += 1
            if vv.cur_PhonBuf_Index_CF < vv.phonBuf_2_In_Index:
                vv.speakState = kSpeakNewPhon
            else:
                vv.speakState = kSpeakLastFrame


# ---------------------------------------------------------------------------
# Start_Talk (BackEnd.c:4247)
# ---------------------------------------------------------------------------

def start_talk(vv: VoiceVar):
    vv.speakState = kSpeakNewPhon
    vv.dur_Done_in_Phon_CF = 0
    vv.cur_Phon_Dur_CF = 0
    synth_start_talk(vv)
