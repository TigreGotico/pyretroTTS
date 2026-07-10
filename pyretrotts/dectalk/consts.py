"""Constants of the DECtalk vocal tract model.

Derived from the Fonix/Force DECtalk C source (`dectalk/dectalk`). FONIX
Corporation declares that source proprietary and confidential. This file is
NOT covered by this project's MIT licence. See NOTICE.

The US-English build defines only `VTM1` (integer vocal tract model) and
`PC_SAMPLE_RATE == 11025`; none of `NEW_VTM`, `LOWCOMPUTE`, `COMPRESSION`,
`CHANGES_AFTER_V43`, `UPGRADES1999`, `LOW_COST_VERSION`, `NEW_TILT`,
`NEW_NOISE`, `LOWER_YET`, `LOWEST`, `NO_LIMIT_CYCLE_RAMPDOWN`, `ACI_LICENSE`,
or `FP_VTM` is set (confirmed by preprocessing `vtm.c` with the build flags
`-DENGLISH -DENGLISH_US -DACNA`). This port reproduces exactly that path.
"""

# Output sample format of the engine.
SAMPLE_RATE_HZ = 11025
SAMPLE_WIDTH_BITS = 16
CHANNELS = 1

# Frame parameter indices into `variabpars` (= &parambuff[1]); `ph/ph_defs.h`.
OUT_AP = 0
OUT_F1 = 1
OUT_A2 = 2
OUT_A3 = 3
OUT_A4 = 4
OUT_A5 = 5
OUT_A6 = 6
OUT_AB = 7
OUT_TLT = 8
OUT_T0 = 9
OUT_AV = 10
OUT_F2 = 11
OUT_F3 = 12
OUT_FZ = 13
OUT_B1 = 14
OUT_B2 = 15
OUT_B3 = 16
OUT_PH = 17
OUT_DU = 18
OUT_PH2 = 19

# Sample-rate mode. At PC_SAMPLE_RATE == 11025 the engine runs in
# SAMPLE_RATE_INCREASE relative to the 10 kHz design (`vtm1.c` SetSampleRate).
SAMPLES_PER_FRAME = 71  # (11025 * 64 + 5000) // 10000
RATE_SCALE = 18063  # Q2.14 of 11025/10000
INV_RATE_SCALE = 29722  # Q1.15 of 10000/11025

# Random-number generator and fixed noise filter (`vtm1.c` read_speaker_definition).
RANMUL = 20077
RANADD = 12345
NOISEC = 1499  # Q4.12, 0.365966796875; noiseb is per-speaker (SAMPLE_RATE_INCREASE = -2913)

# Parallel sixth-formant coefficients, fixed at 11025 Hz (`vtm1.c:1759`).
R6PB = -5702
R6PC = -1995

# Low-order value mask of a phoneme code (`cmd/cm_defs.h:231`, PVALUE).
PVALUE = 0x00FF
