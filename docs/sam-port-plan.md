# Adding SAM (Software Automatic Mouth) as a third engine

> **Status: shipped.** The port landed in `pyretrotts/sam/` and is byte-exact
> against the C reference. For the engine as built, modules, voices, quirks,
> verification and limitations. See [sam.md](sam.md). The evaluation below is
> the analysis that preceded it. The licensing position it reaches still holds,
> and the repo owner accepted that risk knowingly (see `NOTICE`).

`pylintalker` (renaming to `pyretroTTS`) hosts two engines behind the `Engine`
ABC in `pylintalker/engines.py`: `MacInTalkEngine` (a bit-exact port of Apple
MacinTalk 2/3) and `DECtalkEngine` (DECtalk markup voiced through the MacinTalk
synthesizer, with a native port planned in `docs/dectalk-port-plan.md`). This
document evaluates a third engine, **SAM**, the 1982 Commodore 64 / Apple II
speech synthesizer by Don't Ask Software, and plans its implementation.

The target is the C reimplementation at `https://github.com/vidarh/SAM`
(a fork of Sebastian Macke's `s-macke/SAM`), read-only checkout inspected at
commit `c86ea39`. All C `file:line` references below are to that checkout's
`src/` directory unless noted.

**The licence is a gating problem and it blocks shipping the code. Read §1
first.**

---

## 1. What SAM actually is

### Provenance and licence, the gating question

SAM is a **reverse-engineered** version of a 1982 commercial product. The
`README.md` "License" section states this without ambiguity:

> "The software is a reverse-engineered version of a commercial software
> published more than 30 years ago. The current copyright holder is SoftVoice,
> Inc. … As long this is the case I cannot put my code under any specific open
> source software license. Use it at your own risk."

The "Adaption To C" section confirms the provenance: the C was produced by
**semi-automatically converting the original 6502 assembler opcode-by-opcode**
(`lda 56` → `A = mem[56];`, `jmp 38018` → `goto pos38018;`) and then rewriting
it. It is therefore a derivative work of SoftVoice's copyrighted C64 program,
not a clean-room implementation.

There is **no LICENSE/COPYING file** in the repository, the only licence text is
the README paragraph above. `README.md` describes the status as "Abandonware".

**Verdict: incompatible with this repository's Apache-2.0 licence.** Abandonware
is a description of enforcement likelihood, not a licence grant. The upstream
author explicitly declined to apply any open-source licence because he cannot, 
he does not hold the copyright. Vendoring this C, or a Python translation of it
(a translation is a derivative work), into an Apache-2.0 package would place
Apache-2.0 headers on code the project has no right to relicense, and would ship
SoftVoice's tables and algorithm without permission. This is a materially
different situation from MacinTalk and DECtalk:

- MacinTalk: ported from `../lintalker-c`, whose provenance the repo already
  relies on for its shipped tables.
- DECtalk: `dectalk/dectalk` is the **Fonix/Force source release** of DECtalk, 
  an actual source drop with its own terms, per `docs/dectalk-port-plan.md`.

SAM has neither a source release nor a licence grant. **Do not vendor SAM code,
SAM tables, or a line-by-line Python translation of them into this repo without
a licence resolution** (an explicit grant from SoftVoice, Inc., or a legal
determination that the specific tables/algorithm are not protectable). Every
technical section below is written on the assumption that this blocker is
understood. The effort estimates are moot until it is cleared.

*Unverified:* whether SoftVoice, Inc. would grant permission, and whether any
prior OVOS/TigreGotico contact exists. `README.md` says contact attempts failed.

### Size and file layout

SAM is tiny, **3,441 lines of C total** across `src/` (`wc -l src/*`):

| File | Lines | Role |
|---|---|---|
| `sam.c` | 729 | Phoneme-list pipeline: Parser1/Parser2, stress, lengths, insertions |
| `render.c` | 389 | Frame creation, formant/amplitude tables, sampled-consonant playback |
| `reciter.c` | 303 | English text → phoneme mnemonics (rule engine) |
| `main.c` | 278 | CLI arg parsing, WAV writer, SDL audio |
| `createtransitions.c` | 206 | Linear interpolation of frames between phonemes |
| `processframes.c` | 112 | The inner synthesis loop (glottal pulse + formant combine) |
| `debug.c` | 74 | Debug dumps |
| Headers (`ReciterTabs.h` 546, `RenderTabs.h` 509, `SamTabs.h` 215, `sam.h`, `render.h`, `reciter.h`, `debug.h`) | ~1,300 | Static tables: reciter rules, sine/rectangle/multiply tables, phoneme flags/lengths |

Roughly 2,100 lines of code + 1,300 lines of tables. The whole engine is smaller
than any single stage of the MacinTalk port.

### Synthesis model, NOT a formant/Klatt synthesizer

This is the most important technical distinction from the existing two engines.
MacinTalk and DECtalk are **Klatt cascade/parallel formant synthesizers**, 
resonant filters (`_backend.py`. `docs/dectalk-port-plan.md` §"KlattSyn"). SAM
is **not a filter-based synthesizer at all.** It generates the waveform by
**direct additive synthesis of three fixed oscillators**, per the README and
`processframes.c:22-34` (`CombineGlottalAndFormants`):

```
A = A1*sin(f1*t) + A2*sin(f2*t) + A3*rect(f3*t)
```

Concretely, each 10 ms frame carries three "formant" oscillators, 
`frequency1/2/3[]` and `amplitude1/2/3[]` (`render.c:25-31`). The inner loop
(`processframes.c:26-33`) advances three phase accumulators (`phase1/2/3`,
`unsigned char`, so they wrap mod 256) by the formant frequencies each sample,
looks up two **sine tables** and one **rectangle table** (`sinus[]`,
`rectangle[]` in `RenderTabs.h`), ORs each with the 4-bit amplitude nibble,
indexes a **multiply table** (`multtable[]`), sums the three, adds 136, and
shifts right by 4. There are **no resonators, no cascade, no bandwidths**, the
"formants" are just three oscillators summed open-loop. The comment at
`processframes.c:36-44` is explicit: "SAM generates these formants directly with
sin and rectangular waves."

Consonants that cannot be made this way (fricatives, plosives, `S`, `SH`, `F`,
`CH`, `P`, `T`, `K`, …) are played from a **compressed 1-bit sample table**
(`sampleTable[]` in `RenderTabs.h`), `render.c:75-185`
(`RenderVoicedSample`/`RenderUnvoicedSample`/`RenderSample`). Each bit expands to
one of a few fixed output levels (README "Final Output". `render.c:139-156`).
This is a wavetable/noise mechanism, again unlike Klatt frication.

Output is **8-bit unsigned PCM at 22,050 Hz mono** (`main.c:35-37`,
`WriteWav`). Internally the C64 SID had a 4-bit volume register, so each sample
is quantized to 4 bits then scaled to a byte (`Output`, `render.c:63-72`.
`CombineGlottalAndFormants` masks `& 0xf`). Voice character is shaped by four
integer knobs, **speed, pitch, throat, mouth** (`sam.c:20-23`), where
throat/mouth rescale the F2/F1 formant frequency tables (`SetMouthThroat`,
`render.c:337-389`).

**Bottom line:** SAM shares the *ARPABET-derived phoneme concept* with the other
two engines but **none of the synthesis math**. It is a table-driven additive +
1-bit-sample synth, not a formant filter. There is nothing in the DSP core to
share with the Klatt engines.

---

## 2. Phoneme inventory and markup

### SAM's phoneme set

SAM's phonemes are 2-character mnemonics with indices 0-80, assembled from
`signInputTable1[]` + `signInputTable2[]` (`SamTabs.h:11-39`) and documented in
the flag table comment (`SamTabs.h:108-213`) and the CLI help (`main.c:81-109`).
The speakable set:

- **Vowels (5-17):** `IY IH EH AE AA AH AO OH UH UX ER AX IX`
- **Diphthongs (48-53):** `EY AY OY AW OW UW`
- **Semivowels / r-coloured (18-26):** `RX WX LX YX WH R* L* W* Y*`
- **Nasals (27-29):** `M* N* NX`
- **Voiced stops/affricate (54,57,60,44):** `B* D* G* J*`
- **Voiced fricatives (38-41):** `Z* ZH V* DH`
- **Unvoiced fricatives (32-37):** `S* SH F* TH /H /X`
- **Unvoiced stops/affricate (66,69,72,42):** `P* T* K* CH`
- **Specials (78-80,31):** `UL UM UN` (= AXL/AXM/AXN) and `Q` (glottal stop)
- **Punctuation/pause markers (0-4):** `* . ? , -`

Stress is written by **appending a digit 1-8** to a vowel in phonetic input
(`stressInputTable[]`, `SamTabs.h:5-8`, e.g. `AA5`). Stress is a separate
`stress[]` array, not a phoneme code (`sam.c:28`).

### Comparison to MacinTalk and DECtalk

| | MacinTalk (`_phonemes.py`) | DECtalk (`l_us_ph.h`) | SAM (`SamTabs.h`) |
|---|---|---|---|
| Count | 56 core + 19 markers | 57 codes, 71 allophones | ~49 speakable, indices 0-80 |
| Ordering / codes | `mt4.h` enum | its own | **its own, disjoint** (`IY`=5, gaps to 80) |
| Stress | phoneme-stream markers (`Stress1`, `EmphStress`) | `symbols[]` channel + hat symbols | appended digit → `stress[]` |
| r-coloured | `ER IR XR AR OR UR` | `RR/RX/…` | `ER RX` + `R*` only |
| Extra vowels | - |, | `OH UX` distinct from `AO UW`. `WX YX WH` glides |
| Synth target | Klatt formants | Klatt formants | 3-oscillator additive |

All three are ARPABET-derived and overlap on the obvious vowels/consonants, but
the code spaces are **disjoint**, exactly the conclusion `docs/dectalk-port-plan.md`
§1 reaches for MacinTalk vs DECtalk, and it holds a third time for SAM. Treat
SAM's ids as a fourth independent namespace.

### Markup / text input

SAM has **no bracket-command markup**, no `[[...]]` (MacinTalk), no `[: ]`
(DECtalk). Its only inputs are:

1. **Plain English text** → the **reciter** rule engine (`reciter.c`,
  `ReciterTabs.h`). Rules look like `" ANT(I)" → "AY"` with context classes
  `# & @ ^ + : %` (README "Reciter"). This is SAM's analogue of MacinTalk's
  `_engtop.py` letter-to-sound, but rule-format-incompatible.
2. **Phonetic mode** (`-phonetic`, `main.c:202`): the mnemonics above plus stress
  digits, terminated by `\x9b` (`main.c:254`).
3. **Voice knobs** as CLI flags (`-pitch -speed -throat -mouth -sing`), not
  in-band markup.
4. **`-sing` mode** (`main.c:198`, `EnableSingmode`): disables the automatic
  pitch contour (`render.c:293`, `AssignPitchContour` is skipped) so the pitch
  knob holds a steady note, the mechanism by which the bundled `sing` script
  makes SAM sing.

### Can a score be translated between engines?

**Partially, with loss.**

- **MacinTalk/DECtalk `[[...]]`/`[: ]` markup → SAM:** the *phoneme sequence* can
  be transliterated (both are ARPABET), and duration/pitch can be approximated
  through SAM's per-frame lengths and the pitch knob. But SAM has **no in-band
  per-phoneme pitch** like DECtalk's `weh<250,13>`. SAM sings only by holding one
  global pitch in `-sing` mode. A DECtalk *melody* (a note per phoneme) therefore
  **cannot** be reproduced on SAM without re-driving the pitch knob frame group
  by frame group, which the engine's public interface does not expose. Timbre
  is unrecoverable: SAM's oscillator voice sounds nothing like a Klatt formant
  voice.
- **SAM phonetic input → MacinTalk/DECtalk:** mnemonics map to their ARPABET
  equivalents, but SAM's `OH/UX/WX/YX/WH` distinctions and its stress-digit
  granularity are lossy in either direction.

Conclusion: cross-engine score translation is a nice-to-have, not free, and is
**not** a reason to unify the phoneme spaces. Keep them disjoint, as the DECtalk
plan already mandates.

---

## 3. Portability to pure Python

SAM is **exceptionally portable**, far more so than either Klatt engine:

- **Integer-only, no floating point.** The entire synth is `unsigned char` /
  `unsigned int` arithmetic over small static tables. `grep` finds no `float`
  or `double` in the synthesis path. Contrast MacinTalk's fixed-point regime
  (`kPrecision=13`, `docs/architecture.md` §"Fixed-point") and DECtalk's
  `FLTPNT_T`.
- **Small tables.** Sine/rectangle/multiply/sample tables and phoneme
  flag/length/formant tables total ~1,300 lines of header data, trivially
  transcribed into a `_sam_data.py` (licence permitting).
- **No self-modifying code.** The README says the assembler was rewritten to
  "remove most of the jumps and register variables". The surviving code is
  ordinary structured C. No runtime code mutation remains.
- **No timing hacks in the audio path.** The old cycle-accurate SID timing is
  reduced to a static `timetable[5][5]` that accumulates `bufferpos`
  (`render.c:54-72`, `Output`). The buffer is written 50× oversampled and
  divided by 50 on output (`main.c:273`, `WriteWav(..., GetBufferLength()/50)`).
  This oversample-then-decimate byte-timing is the **one genuinely fiddly detail**
  to reproduce bit-exactly, but it is deterministic integer arithmetic.

**6502-isms that need care (all mechanical):**

- **Deliberate unsigned-byte wraparound as loop control.** `while(++phase1 != 0)`
  (`render.c:86`), `while(++off != 0)` (`render.c:100`), `while(++X != 0)`
  (`sam.c:111`), phase accumulators wrapping mod 256 (`processframes.c:90-92`).
  Python ints do not wrap, every `unsigned char` operation must be masked
  `& 0xFF`, and every 256-entry index buffer must stay `& 0xFF`. This is the
  same class of hazard `docs/architecture.md` §"Fixed-point" flags for MacinTalk
  (`rshort()`/`s16()`), applied to 8-bit.
- **Global `A, X` pseudo-registers** in the reciter (`reciter.c:7`), mutated as
  side effects across `match()`/`Code37055()`/`handle_ch()`
  (`reciter.c:13-59`). Portable but must be modelled as explicit state, not
  Python locals.
- **Memory-address-named variables** (`mem38`, `mem48`, `mem66`, `Var56`) and
  "magic" fall-through like the overflow-carry fudge `tmp += tmp > 255 ? 1 : 0`
  (`processframes.c:28`), must be copied verbatim, not "cleaned up", or the
  output diverges.
- **Fixed off-by-one / sentinel quirks** the C carries as bug-compatible
  behaviour: `phonemeindex[255]` set twice to different values
  (`sam.c:90` vs `sam.c:97`, with a `FIXME` noting the conflict), `mem66` "was
  not initialized" (`processframes.c:51`). A bit-exact port must preserve these,
  not fix them.

**Estimated Python port size: ~1,500-2,000 LOC + ~1,300 lines of transcribed
tables.** Comparable to two or three MacinTalk stage modules, i.e. a small
fraction of the existing package.

---

## 4. Verification, bit-exact oracle

**Yes, a bit-exact oracle is straightforward, and SAM is fully deterministic.**

- **Determinism:** no RNG at runtime, the "noise" for fricatives is the fixed
  `sampleTable[]`, not a random source (README "Final Output" speculates about
  randomness but the code uses a static table, `render.c:79`,`render.c:94`).
  Same input + knobs ⇒ identical bytes, every run. This is exactly the property
  the golden gate needs (`docs/architecture.md` §"Correctness").
- **The repo builds a CLI that emits WAV.** `make` produces `./sam`. With SDL
  removed (README "Compile") or via `-wav out.wav` (`main.c:193-196`,`main.c:272`)
  it writes an 8-bit/22050/mono WAV (`WriteWav`, `main.c:29-64`). No SDL needed
  for the oracle, build the no-SDL variant (`Makefile` lines 8-9 commented
  block) to avoid a libsdl dependency in CI.
- **Diffing, mirroring `test/test_voices.py`:** shell out to a sibling `sam-c`
  build for a given (knob-set, phonetic-or-text input), capture the WAV, and diff
  the Python engine's PCM byte-for-byte. Because SAM has no bracket-command
  ambiguity (the limitation that blocks MacinTalk's frame-exact bracket
  verification, `docs/architecture.md` §"Limitations"), **every public input is
  oracle-checkable**, an advantage over the existing two engines.
- **Stage oracles** (anallogous to `test_assembly.py` etc.): SAM's `-debug` flag
  already dumps the intermediate `phonemeindex/stress/phonemeLength` tables
  (`sam.c:100`,`sam.c:114`, `PrintPhonemes`) and the per-frame
  `frequency*/amplitude*/pitches` arrays (`render.c:296-298`, `PrintOutput`).
  These give ready-made per-stage fixtures with **no C source instrumentation
  required**, again easier than MacinTalk's `phon_Buf_1` re-capture.
- **Golden gate:** add SAM's `voices × inputs` PCM sha256 to `test/golden.py` /
  `test/golden_pcm.json`, exactly as the two existing engines do.

Caveat: reproduce the `Output` oversample/decimate byte-timing
(`render.c:63-72`. `main.c:273` divides length by 50) precisely, or the golden
hash will differ even when every frame control matches, the SAM analogue of the
"matched every control but emitted silence" trap in `docs/architecture.md`.

---

## 5. Integration, `SAMEngine(Engine)`

### Shape

SAM fits the `Engine` ABC (`engines.py:32-56`) with one honest wrinkle: the ABC
assumes **16-bit** little-endian PCM (`pcm_to_wav` sets `sampwidth=2`,
`api.py:180`. `scale_to_headroom`/`pcm_peak` unpack `<h`), while SAM is natively
**8-bit unsigned**. The sample *rate* already matches, the repo's `SamplingRate`
is 22050 (`_consts.py:16`), which is SAM's native rate (`main.c:35`). So
`SAMEngine.synthesize` must **up-convert 8-bit unsigned → 16-bit signed** at the
boundary (`(byte - 128) << 8`) and return 16-bit PCM like the others. The
`sample_rate` property needs no override. Do the widening at the very edge so the
core stays a bit-exact mirror of the C.

```python
class SAMEngine(Engine):
  name = "SAM"
  dialect = "phonetic" # mnemonics + stress digits; no bracket markup

  # SAM has no named voices — it has speed/pitch/throat/mouth knobs. Expose the
  # six presets from the original manual (README "Usage") as named voices.
  VOICE_KNOBS = { # (speed, pitch, throat, mouth)
  "SAM": (72, 64, 128, 128),
  "Elf": (72, 64, 110, 160),
  "LittleRobot": (92, 60, 190, 190),
  "StuffyGuy": (82, 72, 110, 105),
  "LittleOldLady": (82, 32, 145, 145),
  "ExtraTerrestrial": (100, 64, 150, 200),
  }

  @property
  def voices(self) -> dict[str, Voice]:
  # NB: a SAM "voice" is a 4-knob preset, not a MacinTalk 72-key Voice dict.
  # Either a distinct SamVoice type or a thin adapter — do NOT force it into
  # the MacinTalk Voice schema.
  ...

  def synthesize(self, source: str, voice: str = "SAM") -> bytes:
  speed, pitch, throat, mouth = self.VOICE_KNOBS[voice]
  pcm8 = _sam.render(source, speed, pitch, throat, mouth, phonetic=...)
  return _u8_to_s16(pcm8) # widen at the edge
```

`voices` returning a knob preset rather than a formant dict is the same pattern
DECtalk already uses to return substitute Voices (`engines.py:115-119`), the ABC
only requires "a dict by name", and SAM honours that without pretending its knobs
are MacinTalk coefficients.

Text vs phonetic input: default `synthesize` runs the reciter (like
`MacInTalkEngine`'s text path). Expose a `phonetic=True`/`-sing` path the way
`DECtalkEngine` exposes `sing()`.

### What can genuinely be shared

- **Infrastructure, not DSP** (identical to the DECtalk plan's conclusion,
  `docs/dectalk-port-plan.md` §5): the `Engine` ABC, `pcm_to_wav` (SAM reuses it
  after widening to 16-bit), the `test/golden.py` sha256 gate framework, the
  C-oracle harness pattern from `test/test_voices.py`, and the
  `tools/extract_*.py` scaffolding.
- **Nothing in the DSP, phoneme ids, reciter rules, or voice knobs.** Forcing a
  shared synthesizer or a shared phoneme namespace would drag SAM off its own
  reference, and SAM's reference is not even a formant synth, so the abstraction
  would be actively wrong.

### What genuinely cannot be shared, and must not be forced

- **The synthesizer.** SAM is 3-oscillator additive + 1-bit samples. MacinTalk/
  DECtalk are Klatt filters. There is no common "formant core", the DECtalk plan
  already warns against a shared formant core between two *Klatt* engines
  (`docs/dectalk-port-plan.md` §"Skeptical note"). SAM makes the case stronger,
  because it is not a formant synth at all.
- **Phoneme ids / stress model / reciter rules / voice knobs.** All disjoint from
  both existing engines.
- **The 8-bit/16-bit boundary.** Keep the native SAM core 8-bit (bit-exact vs the
  C) and widen only at `synthesize`'s return. Do not "promote" the whole core to
  16-bit to match the ABC, that would break the oracle diff.

Two `_sam*.py` modules (a `_sam.py` core + `_sam_data.py` tables), one engine
class, meeting the others only at `engines.py`/`api.py` dispatch and the test
harness. Exactly the "sibling class, no shared internal pipeline" structure the
DECtalk plan prescribes.

---

## 6. Recommendation

**Technically: clearly feasible, and the easiest of the three engines to port**, 
tiny, integer-only, deterministic, with a build-and-diff oracle and ready-made
`-debug` stage dumps. If licence were not an issue this would be a 2-3 week job,
not the multi-month DECtalk effort.

**But do not proceed on the current licence footing.** SAM is reverse-engineered,
copyright SoftVoice Inc., with the upstream author explicitly stating he cannot
license it. Vendoring it (or a Python translation, which is a derivative work)
into an Apache-2.0 package is a licence violation, regardless of the code's
technical elegance. This is categorically different from the MacinTalk and
DECtalk sources the repo already builds on.

### Recommended sequence

- **Phase 0, licence resolution (blocking, do first).** Get an explicit grant
  from SoftVoice, Inc., or a legal determination on whether the specific tables/
  algorithm are protectable, or a decision to keep SAM support as an **optional,
  separately-licensed plugin** that shells out to a user-supplied `sam` binary
  rather than vendoring code. **Until this closes, all phases below are on hold.**
  Effort: unknown. Owner is legal/maintainer, not engineering.
- **Phase 1: oracle and golden scaffold (approximately 2-3 days, post-Phase 0).** Build the
  no-SDL `sam-c` sibling, wire `test/test_sam_voices.py` shelling out to it, and
  capture `-debug` stage fixtures.
- **Phase 2, synth core `_sam.py` (≈1 week).** Port `render.c` +
  `processframes.c` + `createtransitions.c` + `SetMouthThroat`, transcribe the
  `RenderTabs.h`/`SamTabs.h` tables into `_sam_data.py`, mask every byte op,
  reproduce the `Output` oversample/decimate timing. Golden-gate the six voice
  presets on fixed phonetic input.
- **Phase 3, phoneme pipeline `sam.c` (≈1 week).** Parser1/Parser2, stress,
  lengths, insertions, bit-compatible with the quirks (`phonemeindex[255]`
  double-set, `mem66`). Diff `phonemeindex/stress/phonemeLength` against `-debug`.
- **Phase 4, reciter `reciter.c` (≈3-5 days).** The English rule engine +
  `ReciterTabs.h`. Optional if only phonetic input is targeted first.
- **Phase 5, `SAMEngine` wiring (≈1-2 days).** The ABC class, six named-knob
  voices, 8→16-bit boundary, `sing()`-style path, `engines.py`/`api.py` dispatch.

Engineering total (Phases 1-5): **≈3-4 weeks**, dwarfed by the licence question.

### Risks

- **Biggest risk, licence (§1).** It is a hard blocker, not a caveat. Everything
  else is easy. This is the only thing that matters. Recommended mitigation if no
  grant is obtainable: ship SAM as a **separate, clearly-labelled optional
  component** that invokes a user-provided binary, keeping SoftVoice-derived code
  out of the Apache-2.0 tree entirely.
- **Byte-timing bit-exactness** (`Output` oversample/decimate), deterministic
  but the one place a golden hash can silently diverge. Anchor with the audio
  oracle, not just stage dumps.
- **Bug-compatibility**, SAM ships with `FIXME`s and uninitialised-variable
  quirks that shape the output. A well-meaning cleanup breaks the golden gate.
- **8/16-bit and knob-vs-Voice impedance** at the ABC boundary, low risk if
  contained at the edges as described in §5. Real risk if someone "unifies" it.
```


---
[← DECtalk engine](dectalk.md) · [Home](../README.md) · [SAM engine →](sam.md)
