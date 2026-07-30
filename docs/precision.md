# Arithmetic precision

The MacinTalk synthesizer computes in fixed point: `1.0` is `0x2000`, and every
scaled multiply is a right shift by 13 (`Fsynth.h:275-279`). This document
records what that costs, what a higher-precision mode changes, and, most
importantly, what has and has not been verified.

## What the integer arithmetic actually costs

Measured on the port, not inferred.

**Saturation is not a problem.** `clip14` clamps to ±8191. Over a sentence it
fires 0 times out of 30,002 calls for Fred, 0 of 30,954 for Ralph, and 5 of
82,810 for Bells. Nothing is being crushed.

**Output resolution is 14 bits, not 16.** The synthesizer produces a 14-bit
sample and writes `nSamp << 2`. The greatest common divisor of every distinct
output value is exactly 4. That gives roughly 76 dB of quantization SNR, which
sits below the voice's own noise floor. Real, and inaudible.

**The shifts carry a bias.** A right shift floors toward negative infinity, so
every scaled multiply loses a half LSB downward. The formant filters are
recursive, so that bias accumulates through the cascade on every sample. This is
the one arithmetic effect large enough to hear about.

**The dominant artifact is not arithmetic at all.** The synthesizer runs at
11 kHz internally and doubles to 22 kHz with one line of linear interpolation
(`((nSamp - lastnSamp) >> 1) + lastnSamp`). Compared against a band-limited
upsample of the identical 11 kHz core samples, the engine carries **+18.7 dB of
excess energy above the 5512 Hz internal Nyquist** for a sustained `/s/`. That is
imaging, not signal, and it is why the fricatives sound gritty. Float arithmetic
does nothing for it. Only oversampling the resonator loop or a proper polyphase
interpolator would, and both depart from the original.

## Exact mode

`exact_arithmetic(True)` keeps the same `1.0 == 2**13` scaling and replaces the
shifts with division truncated toward zero. Magnitudes are unchanged. Only the
rounding direction moves, so the downward bias no longer accumulates. Values stay
integers.

```python
from pyretrotts._backend import exact_arithmetic

exact_arithmetic(True)
pcm = synthesize_text(Fred_Voice, "hello world.")
exact_arithmetic(False)
```

It is off by default. With it off, renders are byte-identical to the integer
build, which the golden gate and the C oracle both confirm on every run.

Against the integer build, exact mode differs by 33.0 dB SNR, with a peak
deviation of 776 (LSB is 4).

## What Apple's FLOAT_SYNTH_MT3 build actually is

`Fsynth.h:268-280` carries a compile-time float variant. It is dead code.

```c
#if FLOAT_SYNTH_MT3
  #define mMul2(x,y,s) (x * y) typedef double rShort;
  #define kOnePtOh 1.0
#else
  #define mMul2(x,y,s) ((x * y) >> s) typedef short rShort;
  #define kOnePtOh 0x2000
#endif
```

It compiles. It produces a square wave: the output has exactly three distinct
magnitudes, `{0, 16382, 32764}`, while the frame control values remain normal.

The reason is `Say.c:122-125`:

```c
*Ccoeff = *(zz->CcoeffTblPtr + bwIndex); /* raw table short, 1.0 == 8192 */
*Bcoeff = mMul2(*(zz->BcoeffTblPtr + bwIndex), cosVal, kPrecision-1);
*Acoeff = kOnePtOh - *Bcoeff - *Ccoeff; /* kOnePtOh is now 1.0 */
```

Under `FLOAT_SYNTH_MT3` the coefficient tables in `Data.c` are still fixed point:
`Data.c` contains no `FLOAT_SYNTH_MT3` at all, and its 49 tables are `const
short` scaled by 8192, while `kOnePtOh` has become `1.0`. The two scales are
mixed in one expression and the filters diverge immediately.

A working float build needs a float `Data.c` that is not in this source tree.
Apple's float mode cannot be reproduced from what survives.

## Verification, and its limits

The C reference was rebuilt out of tree, twice, without modifying it:

| build | how | result |
|---|---|---|
| integer | `gcc` over the unmodified sources | reproduces the shipped `test_harness` **byte for byte** |
| `-DFLOAT_SYNTH_MT3` | the same, with the macro defined | **square wave**, unusable |
| exact | a patched copy of `Fsynth.h` shadowing the original | sane audio, 30.9 dB from integer |

The exact build is not Apple's. It is the coherent variant: same fixed-point
scale, division instead of shifts.

**The integer port is bit-exact against the C integer build.** 0 differing
samples out of 32,592 on `hello world.`, and 68/68 on the full voice sweep.

**Exact mode is not bit-exact against the exact C build.** They differ by
35.2 dB SNR, the same order as the effect being measured. Something in the
placement of the truncations differs between the two, and it has not been found.

So exact mode is:

- **deterministic**, the same input yields the same bytes, pinned by tests.
- **inert when off**, no golden digest moves, no oracle case regresses.
- **not validated against any C reference.** It is a defensible reading of what
  the original intended, not a port of something Apple shipped.

Do not treat exact mode's output as authoritative. If bit-exactness against a C
build matters to you, use the default integer mode, which has it.

## What would actually improve the voices

In descending order of audible effect:

1. **Oversample the resonator loop, or replace the linear interpolator.** Worth
  about 19 dB of imaging in the fricative band. Departs from the original.
2. **Exact arithmetic.** Removes the accumulated DC bias. Available today, off
  by default, unvalidated.
3. **16-bit output.** Worth roughly 12 dB of quantization headroom that nothing
  is currently using. Below the noise floor of everything above it.


---
[← Creating voices](creating-voices.md) · [Home](../README.md) · [DECtalk port plan →](dectalk-port-plan.md)
