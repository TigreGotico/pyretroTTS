# Constants and enums from mt4.h, Fsynth.h, SpeechEqu.h, Data.h

# Fixed-point precision
kPrecision = 13

# Format constants
kFrameTime = 5  # ms per frame
kSampFrameLen = 112  # 5.032 ms
kSampBufGroup = 1000 // kFrameTime  # 100 ms
kFrameTime_us = 5033
kGroupTime = kFrameTime_us * kSampBufGroup
kSampBufLen = (kSampBufGroup * kSampFrameLen) + kSampFrameLen
kSampleBufferSize = kSampBufGroup * kSampFrameLen

# Sample rate
SamplingRate = 22050

# Buffer sizes
kPhonBufSize = 512
kPhonBuf_Yellow_Zone = kPhonBufSize - 20
kPhonBuf_Red_Zone = kPhonBufSize - 10
kCQsize = 32
kMaxMarkers = 32
kMaxNotes = kMaxMarkers * 2
kMaxRamps = 16
kTokMax = 50

kNormal_Speech_Rate = 180  # wpm
kMinRate = 40
kNormalPitch = 323  # 120 hz
kNormalVolume = None
k100percent = 0x10000
k1pct = 655
pct = 655  # same as k1pct (C #define pct 655)
kOneHalf = 0x8000

kNoiseGain = 3200  # 3200 / 8192 = 0.4
kOnePtOh = 0x2000  # 1.0 in fixed format

kMaxBandWidth = 1225
kNoiseLen = 2048
kSizeOf1xTbl = 100
kNoValue = -1
kAmpStepRes = 16
kStepSizeRes = 3

# Phoneme types
kPhonemeType = 0x0001
kControlType = 0x0002
kStressType = 0x0004
kBoundryType = 0x0008
kWordBoundType = 0x0010
kTerminatorType = 0x0020
kPDType = 0x0040

# Flow control opcodes
EndCtrl = 0x8000
HoldCtrl = 0x8001
NopCtrl = 0x8002
WordCtrl = 0x8003
EmbedCmd = 0x8004
FirstByte = 0x8005
BE_EOF = 0x8000
BE_ECmd = 0x8004

# Phoneme flag bits
kVowelF = 1 << 0
kConsonantF = 1 << 1
kVoicedF = 1 << 2
kVowel1F = 1 << 3
kSonorantF = 1 << 4
kSonorant1F = 1 << 5
kNasalF = 1 << 6
kLiqGlideF = 1 << 7
kSonorConsonF = 1 << 8
kPlosiveF = 1 << 9
kPlosFricF = 1 << 10
kObstF = 1 << 11
kStopF = 1 << 12
kAlveolarF = 1 << 13
kVelar = 1 << 14
kLabialF = 1 << 15
kDentalF = 1 << 16
kPalatalF = 1 << 17
kYGlideStartF = 1 << 18
kYGlideEndF = 1 << 19
kGStopF = 1 << 20
kFrontF = 1 << 21
kDiphthongF = 1 << 22
kHasReleaseF = 1 << 23
kAffricateF = 1 << 24
kLiqGlide2F = 1 << 25
kVocLiq = 1 << 26
kFric = 1 << 27

kFlagMask1 = kLabialF + kDentalF + kPalatalF + kAlveolarF + kVelar + kGStopF
kFlagMask2 = kAlveolarF - 1

# SpeakPhon states
kSpeakNewPhon = 1
kSpeakPhon = 2
kSpeakLastFrame = 3
kSpeakEnd = 4
kSpeakDone = 5
kNeverHappens = -10000

# Control flags (Phon_Ctrl_Buf)
kSyllable_Start = 0x10000000
kSilenceTypeField = 0x00F00000
kSilenceTypeShift = 20
kSilenceDuration = 0x01000000
kSampleMarker = 0x02000000
kCompoundNoun = 0x8000
kBoundryTypeField = 0xF0000
kWord_Start = 0x10000
kPrep_Start = 0x20000
kVerb_Start = 0x40000
kTerm_Bound = 0x80000
kSyllableTypeField = 0x0F
kWord_End = 0x0001
kPrep_End = 0x0002
kVerb_End = 0x0004
kTerm_End = 0x0008
kSyllableOrderField = 0x0300
kOneOrNo_Syllable_InWord = 0x0000
kFirst_Syllable_In_Word = 0x0100
kMid_Syllable_In_Word = 0x0200
kLast_Syllable_In_Word = 0x0300
kMore_Than_One_Syllable_In_Word = 0x0300
kStressField = 0x1C00
kPrimaryStress = 0x0400
kSecondaryStress = 0x0800
kEmphaticStress = 0x1000
kIsStressed = 0x1C00
kPrimOrEmphStress = 0x1400
kWord_Initial_Consonant = 0x0080
kStressedWInitial = kIsStressed + kWord_Initial_Consonant
kPlosive_Release = 0x4000
kContent_Word = 0x2000
kPitchRise = 0x0020
kPitchFall = 0x0040
kPitchRise1 = 0x04000000
kPitchFall1 = 0x08000000
kLowVibrato = 0x10

# Pitch flow flags
kPitchStress_Flg = 0x1
kPitchRiseFall_Flg = 0x2
kPitchBoundry_Flg = 0x4
kResetDecline = 0x8
kPhraseReset = 0x10
kPitchRiseFall1_Flg = 0x20

# Rank constants (for Rank_FWD_Tbl / Rank_BKWD_Tbl)
kFrontR = 0
kMiddleR = 1
kBackR = 2
kConsonantR = 3
kRoundR = 4

# Control block types
kFreqType = 0
kBWType = 1
kFNZType = 2
kSourceAmpType = 3
kResonAmpType = 4

# Formant block indices
kF1 = 0
kF2 = 1
kF3 = 2
kBW1 = 3
kBW2 = 4
kBW3 = 5
kFNZ = 6
kAV = 7
kAF = 8
kAp2 = 9
kAp3 = 10
kAp4 = 11
kAp5 = 12
kAp6 = 13
kAB = 14
kNumOfBlocks = 15

# Noise types
kUseHarm = 0
kUseSnd = 1
kUseSyncSnd = 2

# Gender
kMaleTbls = 0
kFemaleTbls = 1

# Synth type
kFormantSynth = 0

# POS codes
kNoun = 0
kVerb = 1
kAdj = 2
kPrep = 3
kVaux = 4
kRVaux = 5
kInterj = 6
kConj = 7
kCConj = 8
kInterr = 9
kDet = 10
kAdv = 11
kInf = 12
kGen = 13
kRelPro = 14
kPPron = 15
kIPron = 16
kRPron = 17
kDPron = 18
kArt = 19
kQuant = 20
kNeg = 21
kSadv = 22
kContr = 23
kVPart = 24
kSubjPron = 25
kObjPron = 26
kMaxPOS = 32
kPOSmask = kMaxPOS - 1
kUndefPOS = -1
kAbriv = kMaxPOS + kNoun
kLastPOS = kAbriv

# Composite POS
kHas_Noun = 1 << 0
kHas_Verb = 1 << 1
kHas_Adj = 1 << 2
kHas_Prep = 1 << 3
kHas_Vaux = 1 << 4
kHas_RVaux = 1 << 5
kHas_Interj = 1 << 6
kHas_Conj = 1 << 7
kHas_CConj = 1 << 8
kHas_Interr = 1 << 9
kHas_Det = 1 << 10
kHas_Adv = 1 << 11
kHas_Inf = 1 << 12
kHas_Gen = 1 << 13
kHas_RelPro = 1 << 14
kHas_PPron = 1 << 15
kHas_IPron = 1 << 16
kHas_RPron = 1 << 17
kHas_DPron = 1 << 18
kHas_Art = 1 << 19
kHas_Quant = 1 << 20
kHas_Neg = 1 << 21
kHas_Sadv = 1 << 22
kHas_Contr = 1 << 23
kHas_VPart = 1 << 24
kHas_SubjPron = 1 << 25
kHas_ObjPron = 1 << 26

# Boundary types
kBND_Pause = 1
kBND_Decl = 2
kBND_Quest = 3
kBND_Emph = 4
kBND_Paren_L = 5
kBND_Paren_R = 6
kBND_Sep1 = 7
kBND_Sep2 = 8
kBND_Sep3 = 9
kBND_Sep4 = 10
kBND_Sep5 = 11
kBND_Sep6 = 12
kBND_Sep7 = 13
kBND_None = 0

# Token types
kUnknownTok = -2
kEOFTok = -1
kNullTok = 0
kAlphaTok = 1
kNumericTok = 2
kAlphaNumericTok = 3
kWordSepTok = 4
kPeriodTok = 5
kDecimalTok = 6
kCommaTok = 7
kApostropheTok = 8
kPuncTok = 9
kLiteralTok = 10
kSmartNumberTok = 11
kRawPhonemeTok = 12
kECommandTok = 13
kAcronTok = 14

# Char attributes
kWordSep = 0x0001
kPeriod = 0x0002
kComma = 0x0004
kApostrophe = 0x0008
kPuncMark = 0x0010
kSymbol = 0x0020
kOther = 0x0040
kLetter = 0x0080
kDigit = 0x0100
kDash = 0x0200
kCap = 0x0400
kVow = 0x0800

# Speaking modes
kRawPhonemes = 0x0001
kCharByChar = 0x0002
kDigitByDigit = 0x0004
kSymbols = 0x0008
kCommand = 0x0010
kDisableCallBacks = 0x0020

# Speaking states
kNormal = 0
kPaused = 1
kStopped = 2

# Buffer indices
kBuf1 = 0
kBuf2 = 1
kFrame1 = 0
kFrame2 = 1

# Pronuncation rule strings (EngToP.c style)
VOWEL = 1
CONSON = 2
SPCHAR = 3

# Reverb constants
kTapFactor = 1
kNumOfTaps = 8
kTap1 = 404 * kTapFactor
kTap2 = 1058 * kTapFactor
kTap3 = 1362 * kTapFactor
kTap4 = 2318 * kTapFactor
kTap5 = 2909 * kTapFactor
kTap6 = 3723 * kTapFactor
kTap7 = 4030 * kTapFactor
kTap8 = 4096 * kTapFactor
kMaxTap = kTap8

# Vibrato
kVibFreq1 = 134217
kVibFreq2 = 310378

# Error codes
kNoError = 0
kNoDataTables = -1
kOutOfMemory = -2
kNoSoundHardware = -3
kNoWaveSample = -4
kParamError = -5
kUnknownEmbeddedCmd = -6
kNoFormTables = -7
synthNotReady = -8
bufTooSmall = -9
kNothingToSpeak = -107

# Text-to-phon errors
kNoPerror = 0
kPbufFull = 1
kPphonEnd = 2
kNoPhons = 3
kPbufHold = 4
kGotFullSen = 5

# Dict constants
HASH_ENTRIES = ord('Z') - ord('A') + 2  # 28
kMaxWordSize = 40
kMaxTokenLen = 32
kEngToPPad = 4
kTokenStrSize = 1 + kMaxTokenLen + kEngToPPad
kTokenPhonemeSize = 2 * kMaxTokenLen - 3
kMaxWordLen = 32
kMagicOpcodeMapSize = 64
kLookAheadChars = 2
kPOS_Slots = 128

DICT_VERSION = 0x00000001

# Dict flags
dictLocked = 0x00000001

# Dict special phonemes
kDictComp = 55  # _pRise_ = Stress1... no actually let me be precise
kDictWord = 56  # _pFall_ = Stress2...

# kPrimeStress = 0x40
kPrimeStress = 0x40
kAltFlag = 0xFF
kEndFlag = 0x80

# Dict types
kCompressDict = 2
kEncryptDict = 1
kUserDict = 0

# Embedded command selectors
EC_pbas = 0x70626173  # 'pbas'
EC_pbar = 0x70626172  # 'pbar'
EC_pmod = 0x706D6F64  # 'pmod'
EC_pmor = 0x706D6F72  # 'pmor'
EC_rate = 0x72617465  # 'rate'
EC_ratr = 0x72617472  # 'ratr'
EC_volm = 0x766F6C6D  # 'volm'
EC_volr = 0x766F6C72  # 'volr'
EC_slnc = 0x736C6E63  # 'slnc'
EC_svox = 0x73766F78  # 'svox'
EC_sync = 0x73796E63  # 'sync'
EC_word = 0x776F7264  # 'word'
EC_rset = 0x72736574  # 'rset'
EC_note = 0x6E6F7465  # 'note'
EC_tempo = 0x746D706F  # 'tmpo'
EC_marker = 0x6D61726B  # 'mark'

# Command types
C_Cmd = 0
C_absPitch = 1
C_relPitch = 2
C_absRate = 3
C_relRate = 4
C_absMod = 5
C_relMod = 6
C_absVol = 7
C_relVol = 8
C_silence = 9
C_voice = 10
C_sync = 11
C_word = 12
C_reset = 13
C_note = 14

# Embedded command pending flags
kNewInputMode = 0x00000001
kNewCharMode = 0x00000002
kNewDigitMode = 0x00000004
kNewSymbolMode = 0x00000008
kNewDelimiters = 0x00000010
kNewEmphasis = 0x00000020
kNewPitchBase = 0x00000040
kNewPitchBaseRelative = 0x00000080
kNewPitchMod = 0x00000100
kNewPitchModRelative = 0x00000200
kNewRate = 0x00000400
kNewRateRelative = 0x00000800
kNewVolume = 0x00001000
kNewVolumeRelative = 0x00002000
kNewSilence = 0x00004000
kNewVoice = 0x00008000
kNewSync = 0x00010000
kNewReset = 0x00020000
kNewNote = 0x00040000
kNewTempo = 0x00080000
kNewMarker = 0x00100000

# Number speaking flags
kAddDollar = 1 << 0
kAddCent = 1 << 1
kAddPercent = 1 << 2
kClockSpecial = 1 << 3
kMoreThanOne = 1 << 4
kYearSpecial = 1 << 5
kHasComma = 1 << 6

# Locus transition types
C_V_type = 0
V_C_type = 1

# Pitch control constants
kAccentPitchPoints = 7
kPerPhonePitchControls = 6
kPitchBufSize = kPhonBufSize * kPerPhonePitchControls
kAbsolutePitchCeiling = 240
kAbsolutePitchFloor = 60

# Duration constants
kDur_One = 0x100
kDurStepRes = 8

# Speak control flags
kNoEndingProsody = 1
kNoSpeechInterrupt = 2
kPreflightThenPause = 4

# Stop/pause types
kImmediate = 0
kEndOfWord = 1
kEndOfSentence = 2

# Voice numbers
kMaxVoice = 9

# Dict compression tokens
kDashCh = 0
kPer = 1
kApos = 2

# Singing
kMIDI_50HZ = 0x1F59
kOneTwelfth = 0x1555
kPointFive = 0x8000

# Marker
kNoMarker = -1

# CmdElem type values
# (from EmbeddedCmd.c)
kNo_op = 0
kAllDone = 1
kResetCmd = 2
kSetRateAbs = 3
kSetRateRel = 4
kSetPitchBaseAbs = 5
kSetPitchBaseRel = 6
kSetPitchModAbs = 7
kSetPitchModRel = 8
kSetVolAbs = 9
kSetVolRel = 10
kSilence = 11
kSetVoice = 12
kSyncCmd = 13
kWordCmd = 14
kNoteCmd = 15
kSetTempo = 16
kMarkerCmd = 17

# Emphasis
kNoEmphasis = 0
kEmphasizeWord = 1
kDeemphasizeWord = 2

# Locus/envelope constants
kNoNasal_Freq = 350
kNasal_Freq = 500

# Pitch values (kHZ_1..kHZ_60 from mt4.h)
kHZ_1 = 326 - kNormalPitch  # 3
kHZ_2 = 329 - kNormalPitch  # 6
kHZ_3 = 332 - kNormalPitch  # 9
kHZ_4 = 335 - kNormalPitch  # 12
kHZ_5 = 338 - kNormalPitch  # 15
kHZ_6 = 341 - kNormalPitch  # 18
kHZ_7 = 344 - kNormalPitch  # 21
kHZ_8 = 347 - kNormalPitch  # 24
kHZ_9 = 350 - kNormalPitch  # 27
kHZ_10 = 352 - kNormalPitch  # 29
kHZ_11 = 355 - kNormalPitch  # 32
kHZ_12 = 358 - kNormalPitch  # 35
kHZ_13 = 361 - kNormalPitch  # 38
kHZ_14 = 364 - kNormalPitch  # 41
kHZ_15 = 366 - kNormalPitch  # 43
kHZ_16 = 369 - kNormalPitch  # 46
kHZ_17 = 372 - kNormalPitch  # 49
kHZ_18 = 374 - kNormalPitch  # 51
kHZ_19 = 377 - kNormalPitch  # 54
kHZ_20 = 380 - kNormalPitch  # 57
kHZ_21 = 382 - kNormalPitch  # 59
kHZ_22 = 385 - kNormalPitch  # 62
kHZ_23 = 388 - kNormalPitch  # 65
kHZ_24 = 390 - kNormalPitch  # 67
kHZ_25 = 393 - kNormalPitch  # 70
kHZ_26 = 395 - kNormalPitch  # 72
kHZ_27 = 398 - kNormalPitch  # 75
kHZ_28 = 400 - kNormalPitch  # 77
kHZ_29 = 403 - kNormalPitch  # 80
kHZ_30 = 405 - kNormalPitch  # 82
kHZ_31 = 408 - kNormalPitch  # 85
kHZ_32 = 410 - kNormalPitch  # 87
kHZ_33 = 413 - kNormalPitch  # 90
kHZ_34 = 415 - kNormalPitch  # 92
kHZ_35 = 417 - kNormalPitch  # 94
kHZ_36 = 420 - kNormalPitch  # 97
kHZ_37 = 422 - kNormalPitch  # 99
kHZ_38 = 424 - kNormalPitch  # 101
kHZ_39 = 427 - kNormalPitch  # 104
kHZ_40 = 429 - kNormalPitch  # 106
kHZ_41 = 431 - kNormalPitch  # 108
kHZ_42 = 434 - kNormalPitch  # 111
kHZ_43 = 436 - kNormalPitch  # 113
kHZ_44 = 438 - kNormalPitch  # 115
kHZ_45 = 440 - kNormalPitch  # 117
kHZ_46 = 443 - kNormalPitch  # 120
kHZ_47 = 445 - kNormalPitch  # 122
kHZ_48 = 447 - kNormalPitch  # 124
kHZ_49 = 449 - kNormalPitch  # 126
kHZ_50 = 451 - kNormalPitch  # 128
kHZ_51 = 454 - kNormalPitch  # 131
kHZ_52 = 456 - kNormalPitch  # 133
kHZ_53 = 458 - kNormalPitch  # 135
kHZ_54 = 460 - kNormalPitch  # 137
kHZ_55 = 462 - kNormalPitch  # 139
kHZ_56 = 464 - kNormalPitch  # 141
kHZ_57 = 466 - kNormalPitch  # 143
kHZ_58 = 468 - kNormalPitch  # 145
kHZ_59 = 471 - kNormalPitch  # 148
kHZ_60 = 473 - kNormalPitch  # 150

# kDownRampStep
# kDownRampStep = 15360

# Morph suffix types
kIZING_suffix = 1
kIZINGS_suffix = 2
kIZES_suffix = 3
kIZER_suffix = 4
kIZERS_suffix = 5
kIES_suffix = 6
kIERS_suffix = 7
kIER_suffix = 8
kIED_suffix = 9
kIEST_suffix = 10
kERS_suffix = 11
kER_suffix = 12
kEST_suffix = 13
kINGS_suffix = 14
kING_suffix = 15
kABLE_suffix = 16
kBLY_suffix = 17
kCALLY_suffix = 18
kLY_suffix = 19
kIMENTS_suffix = 20
kIMENT_suffix = 21
kMENTS_suffix = 22
kMENT_suffix = 23
kORS_suffix = 24
kOR_suffix = 25
kINESS_suffix = 26
kINESSES_suffix = 27
kNESS_suffix = 28
kNESSES_suffix = 29
kIZED_suffix = 30
kIZE_suffix = 31
kISMS_suffix = 32
kISM_suffix = 33
kED_suffix = 34
kES_suffix = 35
kS_suffix = 36
kNo_suffix = -1

# Fixed-point math helpers
def mMul2(x, y, s=kPrecision):
    return (x * y) >> s

def mRatio(x, y, s=kPrecision):
    return (x << s) // y

def mScale(x, s=kPrecision):
    return x << s

def mUnScale(x, s=kPrecision):
    return x >> s

def mDiv(x, y, s=kPrecision):
    # C's mDiv(x, y, s) reduces to `x >> s` in the non-float build (Fsynth.h);
    # `y` is unused there. Callers rely on this for scaled averaging, e.g.
    # mDiv(a + b, 2, 1) == (a + b) >> 1.
    return x >> s

def clamp(val, lo, hi):
    if val < lo:
        return lo
    if val > hi:
        return hi
    return val

# Synthesizer types
kTextToSpeechSynthType = 0x74747363  # 'ttsc'
kTextToSpeechVoiceType = 0x74747664  # 'ttvd'
kTextToSpeechVoiceFileType = 0x747666  # 'ttvf'
kTextToSpeechVoiceBundleType = 0x747662  # 'ttvb'
