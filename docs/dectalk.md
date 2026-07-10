# DECtalk engine

This documents the Python port of the genuine DECtalk synthesizer, kept in
`pyretrotts/dectalk/`. It is a separate engine from the MacinTalk port described
in [architecture.md](architecture.md); the two share only test discipline, not
code. For the standing multi-phase plan see
[dectalk-port-plan.md](dectalk-port-plan.md).

**Licensing.** Everything under `pyretrotts/dectalk/` descends from the
Fonix/Force DECtalk C source, which FONIX Corporation declares proprietary and
confidential. That subpackage is **not** covered by this project's MIT licence;
every file in it carries the FONIX notice. See [NOTICE](../NOTICE). The shipping
DECtalk markup dialect still renders through MacinTalk
(`pyretrotts.engines.DECtalkEngine`); this port does not change what ships.

## Status

Phase 1 (the vocal tract model, `vtm/`) is **ported and bit-exact**. Phase 2
ports one layer of the text front end: `phdraw`, the `ph/` frame drawer that
interpolates per-phoneme targets into the Klatt parameter frames `vtm.py`
consumes. The rest of the front end (`cmd/`, `lts/`, and the `ph/` stages that
build `phdraw`'s input) is not ported, so there is still no text-to-speech;
`pyretrotts/dectalk/engine.py` synthesizes from Klatt parameter frames.

| Piece | Module | State |
|---|---|---|
| Fixed-point primitives, resonator coefficients, frame loop | `vtm.py` | bit-exact vs C |
| VTM fixed-point tables | `tables.py` | transcribed from C by a dumper |
| Ten voices: names, `[:n?]` codes, resolved chip parameters | `voices.py` | captured from C |
| Constants, frame-parameter layout | `consts.py` | — |
| Frame-driven synthesis + WAV writer | `engine.py` | — |
| Phoneme frame drawer (`phdraw`) | `ph.py` | bit-exact vs C (10 voices) |
| Target ROM tables (`p_us_rom_dectalk_1996m_43f.c`) | `targets.py` | read verbatim from `libtts_us.so` |
| Target lookup (`us_gettar`, `p_us_st0.c`) | `settar.py` | bit-exact vs C (10 voices) |
| Locus/burst/inherent-dur ROM, `lineartilt`, `divtab` | `targets_transitions.py` | read verbatim from `libtts_us.so` |
| `phsettar` transition setup (`ph_setar.c`, `p_us_st0.c`, `ph_sttr2.c`) | `phsettar.py` | bit-exact vs C (10 voices) |
| `phdraw` per-frame state advance + `send_pars` | `ph.py` (`advance_frame`, `finalize_av`, `send_pars`) | bit-exact vs C (10 voices) |
| `ph/` duration rules (`us_phtiming`, `p_us_tim0.c`) | `timing.py` | bit-exact vs C (10 voices) |
| `ph/` allophone selection (`phsort`/`phalloph`) | `allophones.py` | bit-exact vs C (10 voices) |
| `ph/` F0 / intonation (`phinton`, `pht0draw`) | `intonation.py` | bit-exact vs C (10 voices) |
| Phoneme+stress alphabet, `LOG_PHONEMES` renderer | `lts.py` | bit-exact vs oracle over the capture corpus |
| US main-dictionary load + lookup (`ls_dict.c`) | `dictionary.py` | payload bit-exact for unique-grapheme words |
| `[: ]` command tokenizer (voice/rate/mode) | `cmd.py` | tokenization + control state |
| `lts/` rules, numbers, abbreviations, homograph POS | — | **not ported** |

## The oracle

The reference is a C build of [`dectalk/dectalk`](https://github.com/dectalk/dectalk)
(commit `f2ef8f6`). It builds cleanly with native autotools on Linux/x86_64
(the shipped `Dockerfile` runs the same commands on `debian:bullseye`):

```sh
# Work on a copy; the build writes into the tree. Source stays read-only.
cp -r ~/AgentWorkspaces/ovos/dectalk ~/AgentWorkspaces/ovos/dectalk-c
cd ~/AgentWorkspaces/ovos/dectalk-c/src
./autogen.sh          # automake -fca; autoreconf -i
./configure
make -j               # builds into ../dist
```

The CLI `../dist/say` renders text or `[: ]` markup to WAV or raw PCM:

```sh
export DECTALK_DIR=$PWD/../dist
./dist/say -s 0 -e 1 -fo out.wav -a "hello world"        # voice 0, 16-bit WAV
./dist/say -s 3 -e 1 -fo stdout:raw -a "hello" > out.pcm # raw 16-bit PCM
./dist/say -s 0 -e 1 -fo out.wav -pre "[:phoneme on]" -a "hh ax l ow"
```

- **Output format: 11025 Hz, 16-bit signed, mono, little-endian** (`-e 1`).
- **Deterministic**: identical bytes across runs (verified by sha256).
- `-s 0..9` selects the ten built-in voices; `-r`, `-v`, `-pre "[:...]"` set
  rate, volume, and markup.

### Instrumenting the oracle for frame dumps

To validate the synthesizer in isolation, an instrumented build dumps the exact
parameter frames fed to the vocal tract model and the samples it returns. In
`src/dapi/src/vtm/vtmiont.c` (the compiled driver -- **not** `vtmio.c`, which
the Makefile does not build), gate on `getenv("DECTALK_VTM_DUMP")` and:

- right before the `OutputData(...)` call, write one line per frame:
  `F <nspf> <parambuff[1..20]> <iwave[0..nspf-1]>`;
- right after `read_speaker_definition(phTTS)`, write the resolved speaker
  state: `S rate_scale=... inv_rate_scale=... nspf=... fnscal=... avgain=...`
  through `noiseb=...` (the fields `vtm.SpeakerState` names).

Rebuild, then:

```sh
DECTALK_VTM_DUMP=/tmp/s0.txt DECTALK_DIR=$PWD/../dist \
    ./dist/say -s 0 -e 1 -fo /dev/null -a "a test one two three"
```

`test/test_dectalk_oracle.py` drives this and diffs Python against C sample for
sample; `tools/dump_dectalk_vtm.parse_vtm_dump` reads the dumps. The C patch is
temporary tuning scaffolding, kept out of the read-only checkout.

## What `vtm/` is

`vtm/vtm.c` selects a synthesizer by build macro. The US-English build defines
**`VTM1`** (verified by preprocessing `vtm.c` with the build flags
`-DENGLISH -DENGLISH_US -DACNA`), so the compiled synthesizer is
**`vtm/vtm1.c`** -- the original **integer / fixed-point Klatt cascade-parallel
formant synthesizer**, headed *"Copyright (c) 1984 by Dennis H. Klatt"* and
*"Klatt synthesizer ... J. Acoust. Soc. Am., Mar. 1980"*
(`vtm1.c:5,116-118`). The float variant (`vtm_fa.c`, `FP_VTM`) is compiled only
on ALPHA/OSF (`dectalkf_klsyn.h:161-163`), not here.

It is **fixed point, not float**: `S16`/`S32` throughout, `frac4mul(x,y) =
(x*(S32)y)>>12` and `frac1mul(x,y) = (x*(S32)y)>>15` (`vtm/viphdefs.h:408-409`).
So there are no x87/SSE rounding concerns; the port reproduces the integer
arithmetic exactly, truncating every intermediate to its C width.

`speech_waveform_generator` (`vtm1.c:264`) computes one frame of
`uiNumberOfSamplesPerFrame` samples (**71** at 11025 Hz;
`(11025*64+5000)/10000`, `vtm1.c:2044`). Per sample it:

1. runs a 16-bit LCG noise generator (`randomx = randomx*20077 + 12345`), low-pass
   filters it, and passes it through a pi-rotated antiresonator;
2. generates the glottal voicing waveform (shape `a*t^2 - b*t^3`) at 4x
   oversampling, decimated by a two-pole low-pass filter, updating pitch-synchronous
   state (period `T0`, open phase `nopen`, cascade coefficients) at glottal
   closure;
3. applies spectral tilt, breathiness, voicing gain and aspiration;
4. runs the **cascade** branch (nasal zero, nasal pole, five formants) excited by
   the glottal source;
5. sums the **parallel** branch (six formants plus a bypass path) excited by the
   frication noise, with alternating signs;
6. ramps toward silence when unvoiced, clips to +/-16383, and writes `out << 1`.

The build config that fixes the exact code path is: `VTM1`,
`PC_SAMPLE_RATE == 11025`, `SAMPLE_RATE_INCREASE` (`rate_scale = 18063`,
`inv_rate_scale = 29722`); **none** of `NEW_VTM`, `LOWCOMPUTE`, `COMPRESSION`,
`CHANGES_AFTER_V43`, `UPGRADES1999`, `LOW_COST_VERSION`, `NEW_TILT`,
`NEW_NOISE`, `LOWER_YET`, `LOWEST`, `NO_LIMIT_CYCLE_RAMPDOWN`, or `ACI_LICENSE`.
`consts.py` records this.

## The ten voices

`-s N` and `[:n?]` select the same built-in voices (`voices.py`,
`cmd/c_us_cde.h:301-315,403-415`):

| `-s` | `[:n?]` | Name |
|---|---|---|
| 0 | `np` | Perfect Paul (default) |
| 1 | `nb` | Beautiful Betty |
| 2 | `nh` | Huge Harry |
| 3 | `nf` | Frail Frank |
| 4 | `nd` | Doctor Dennis |
| 5 | `nk` | Kit the Kid |
| 6 | `nu` | Uppity Ursula |
| 7 | `nr` | Rough Rita |
| 8 | `nw` | Whispering Wendy |
| 9 | `nv` | Variable Val |

Each voice's high-level `[:dv]` Klatt parameters live in `ph/p_us_vdf*.c` (that
layer is Phase 3). `read_speaker_definition` (`vtm1.c:1469`) resolves them into
the integer coefficient set the vocal tract model consumes;
`voices.SPEAKERS[N]` holds that resolved `SpeakerState`, captured verbatim from
one speaker-definition packet per voice. Variable Val resolves to the Perfect
Paul defaults until `[:dv]` overrides it.

## Verification

The synthesizer is proven in isolation, exactly as
[dectalk-port-plan.md](dectalk-port-plan.md) Phase 1 prefers: parameter frames
are captured from the C oracle and `vtm.py` is replayed over them, so no prosody
(`ph/`) is dragged in.

- **`test/test_dectalk_oracle.py`** -- sample-for-sample diff of Python against
  the instrumented C, for all ten voices over five utterances. Skips without the
  binary. Result: **50/50 cases, every sample identical** (10 voices x 5 texts;
  ~1.1M samples). Additional ad-hoc runs (frication, nasals, numbers, `[:phoneme
  on]` input) are likewise sample-exact.
- **`test/test_dectalk_vtm.py`** -- unit tests for the fixed-point primitives and
  the resonator coefficient functions against inline values dumped from the C.
  No build needed.
- **`test/dectalk_golden.py` + `test/test_dectalk_golden.py` +
  `test/dectalk_golden.json`** -- a deterministic sha256 gate over `vtm.py` for
  the ten voices on a fixed synthetic frame vector. It runs in CI without the C.
  `--write` **refuses to regenerate** the digests unless the engine first matches
  the C oracle sample for sample on real utterances, for all ten voices. This
  synthetic vector is a weak tripwire -- it did not exercise the `ldspdef` silence
  ramp (see the vtm defect note below); the primary synthesizer gates are the
  real-capture goldens `dectalk_vtm_pcm_golden` and `dectalk_endtoend_golden`.

The tables in `tables.py` are regenerated from the C by
`tools/dump_dectalk_vtm.py`, which compiles a small program including the real
`vtm/vtmtable.h` -- the values are guaranteed identical, not retyped.


## Reproducing the oracle

The documented build produces `say` under
`src/samplosf/build/dtsamples/<uname -r>/us/release/`, not under `src/dist/`.
Running it needs both the generic and the US library on the loader path, and
`DECTALK_DIR` pointing at the directory holding `dtalk_us.dic`:

```bash
cd ~/AgentWorkspaces/ovos/dectalk-c/src && ./autogen.sh && ./configure && make -j
GEN=$(dirname $(find . -name libtts.so | head -1))
DIC=$(dirname $(find . -name dtalk_us.dic | head -1))
cd samplosf/build/dtsamples/*/us/release
LD_LIBRARY_PATH="$GEN" DECTALK_DIR="$DIC" ./say -fo out.wav -a "hello world"
```

That invocation has not yet been made to work from a clean checkout:
`TextToSpeechStartup` fails with code 1. The bit-exact result reported for the
ten voices was obtained from an instrumented build whose exact configuration is
not yet reproduced here. Until it is, the golden digests in
`test/dectalk_golden.json` are a regression gate over the ported code, not an
independent confirmation that the port matches the C reference.

The gate does bite: mutating `frac4mul`'s shift from `>> 12` to `>> 11` fails
ten of the twelve golden cases.

## What `ph/` is

`ph/` turns a phoneme + prosody stream into the per-frame Klatt parameter
vectors `vtm.py` consumes. For the US-English build (`ENGLISH_US`,
`OLD_INTONATION_AND_TIMING`; the analog of `vtm`'s `VTM1`, set at
`dectalkf_klsyn.h:248`) the orchestrator is `phclause` (`ph_claus.c:200`), which
runs the chain

    phsort -> phalloph -> us_phtiming -> phinton -> [per-frame loop]

then, once per output frame (71 samples), the loop (`ph_claus.c:362-508`):

1. advances a frame clock `tcum`; at a phoneme boundary reloads `durfon =
   allodurs[nphone]`, writes `parstochip[OUT_PH/DU/PH2]`, and calls `phsettar`
   (`ph_setar.c:561`) to reset each parameter's target and transition specs;
2. `pht0draw` (`ph_drwt01.c:277`) draws the F0/period `parstochip[OUT_T0]`;
3. **`phdraw` (`ph_draw.c:229`) draws the fifteen spectral/amplitude parameters**
   into `parstochip[]` by interpolating the `PARAMETER param[]` state;
4. `send_pars` (`ph_claus.c:694`) ships `parstochip[]` to the vocal tract model.

The interpolation is fixed point: per-frame deltas (`deldip`, `dftran`,
`dbtran`) are stored *8, and the running value is shifted back with `DIV_BY8`
(`>> 3`, `ph_defs.h:382`) to avoid roundoff propagation.

### What is ported: `phdraw`

`pyretrotts/dectalk/ph.py` ports **`phdraw`** for the compiled US path. In that
build (neither `HLSYN` nor `CHANGES_AFTER_V43` defined) `phdraw` returns at
`ph_draw.c:4307`, so every executable line is in `ph_draw.c:345-746`: the
forward/backward/diphthong smoothing of F[1,2,3], FZ, B[1,2,3]; the amplitude
smoothing of AV, AP, A[2..6], AB, TILT with the special-onset and double-burst
rules; the AV glottal-stop reduction; and the source-tilt and breathy-voice
computation. `draw_frame` is a pure per-frame function of the `PARAMETER` blocks
and the `pDph_t`/`pDphsettar` scalars `phdraw` reads.

Its input -- the interpolation state that `phsettar`, `pht0draw`, and the
upstream stages produce -- is **captured from the C oracle**, exactly as Phase 1
captured `phdraw`'s own output (`parstochip`) to validate `vtm.py`. The dumper
patch instruments `ph_draw.c` (gate on env `DECTALK_PH_DUMP`) to write, per
frame, an `E` line of `phdraw`'s entry state and an `X` line of the parameters it
drew; `tools/dump_dectalk_vtm.parse_ph_dump` reads them. Like the `vtm`
instrumentation, this C patch is kept out of the read-only checkout.

### Verification

- **`test/test_dectalk_ph.py`** -- frame-for-frame diff of Python `draw_frame`
  against the instrumented C, for all ten voices over four utterances. Skips
  without the binary. Result: **40/40 cases, every frame identical** (10 voices x
  4 texts; **12 350 frames**; every one of the sixteen drawn parameters matches).
- **`test/dectalk_ph_golden.py` + `test/test_dectalk_ph_golden.py` +
  `test/dectalk_ph_golden.json`** -- a deterministic sha256 gate over
  `draw_frame` on a hand-authored synthetic `DrawFrame` vector (no DECtalk data)
  that exercises every branch. It runs in CI without the C. `--write` **refuses
  to regenerate** the digest unless `draw_frame` first matches the C oracle frame
  for frame, for all ten voices.

## What the target ROM and `us_gettar` are

`phsettar` (`ph_setar.c:561`) resets, once per phone, each parameter's target and
transition specification -- the `PARAMETER` state `phdraw` then interpolates. Its
innermost step is `gettar`, which for the US build dispatches to **`us_gettar`
(`p_us_st0.c:67`)**: it reads the per-phoneme Klatt target ROM and applies the
context rules that pick or shift one target value (or return a negative pointer
into the diphthong ROM). The compiled US configuration is
`VOICE_ROM_DECTALK_1996M_43F` (`ph_romi.c` selects
`p_us_rom_dectalk_1996m_43f.c`) with `OLD_SETTAR` (so `ph_setar.c` includes
`p_us_st0.c`, not `p_us_st1.c`); in that build `US_TOT_ALLOPHONES == 57`.

### What is ported: the target ROM and `us_gettar`

- **`targets.py`** holds the US target ROM: `US_MALTAR`/`US_FEMTAR` (F1,F2,F3,
  B1,B2,B3,AV target blocks, 7 x 57), `US_MALDIP`/`US_FEMDIP` (diphthong target
  sequences), `US_MALAMP`/`US_FEMAMP` (parallel-formant amplitude targets),
  `US_PLACE`, `US_BEGTYP`, `US_ENDTYP`, `US_PTRAM`, `US_FEATB`, and `PARINI`/
  `PARTYP`. Several source arrays are written with feature-bit macro tokens, so
  the values are **read from the built `libtts_us.so` symbols** by
  `tools/dump_dectalk_targets.py` (a C program that links the library) rather
  than retyped -- guaranteed identical to the compiled reference. `PARTYP` is a
  C `char[]`; the dumper types it accordingly.
- **`settar.py`** ports `us_gettar` for the compiled US path (`OLD_SETTAR`,
  `SLOWTALK` off): the `partyp`-driven dispatch over the four parameter classes,
  the `-1`/`< -1` target fallback chain, diphthong-pointer resolution, and every
  context rule (fricative-after-vowel F1, /n/ B2/B3, glottal/devoiced/`hx` AV,
  aspiration AP, obstruent burst amplitudes, and the tilt targets). Its input is
  the allophone/feature stream `phsettar` reads (`allophons[]`, `allofeats[]`,
  `nallotot`, `malfem`), captured from the oracle.

### Verification

- **`test/test_dectalk_phsettar.py`** -- call-for-call diff of Python `us_gettar`
  against the instrumented C, for all ten voices over four utterances. The
  instrumented `p_us_st0.c` dumps, per call, the `(npar, nphone, return)` triple
  and, per clause, the allophone stream; the port is replayed over the identical
  stream. Result: **40/40 cases target-exact (28 700 gettar calls, 0
  mismatches)**. Skipped when the instrumented binary is absent.
- **`test/dectalk_targets_golden.py` + `test/dectalk_targets_golden.json` +
  `test/test_dectalk_targets_golden.py`** -- a deterministic sha256 gate over
  `us_gettar` on a synthetic `Allophones` vector (no captured DECtalk data). It
  runs in CI without the C. `--write` **refuses to regenerate** the digest unless
  `us_gettar` first matches the C oracle call for call, for all ten voices.

## What `phsettar` is

`phsettar` (`ph_setar.c:561`) runs once per phone. For each of the sixteen Klatt
parameters it resolves a start target (`gettar` -> `us_gettar`) and an end target,
applies coarticulation, and runs three rule blocks -- forward smoothing
(`us_forw_smooth_rules`, `p_us_st0.c:440`), backward smoothing
(`us_back_smooth_rules`, `p_us_st0.c:830`), and special rules for bursts,
aspiration and voicebar (`us_special_rules`, `p_us_st0.c:1234`) -- to produce the
per-parameter interpolation state (`ftran`/`dftran`, `btran`/`dbtran`,
`deldip`/`durlin`, `tbacktr`, `tspesh`/`pspesh`, and the diphthong line `ndip`)
that `draw_frame` interpolates each frame. It also carries the `PARAMETER` array
across phones (this phone's `tarend` is the next phone's `tarlas`). Diphthong
vowels expand into straight-line segments via `make_dip` (`ph_setar.c:1429`);
obstruent<->sonorant formant transitions read a locus ROM via `setloc`
(`ph_sttr2.c:69`); `init_variables` (`ph_setar.c:1764`) sets per-phone context and
the sonorant-shrink factors.

### What is ported: `phsettar`

`pyretrotts/dectalk/phsettar.py` ports the whole US path for the compiled build
(`ENGLISH_US`, `OLD_INTONATION_AND_TIMING`, `OLD_SETTAR`; none of `GERMAN`,
`FRENCH`, `LRULES`, `RRULES`, `HLSYN`, `NEW_VTM`), calling the Phase-3
`settar.us_gettar`. It is fixed point where the C is: `mlsh1(x,y) = (x*y) >> 14`
truncated to 16 bits, `muldv` a 32-bit `x*y/z` truncating toward zero, every
target and transition field a C `short`. `vv_coartic_across_c` (`ph_sttr2.c:357`)
has its body commented out in this source, so the F2 vowel-vowel offsets are
always zero. The locus/burst/inherent-duration ROM (`us_maleloc`, `us_femloc`,
`us_plocu`, `us_burdr`, `us_inhdr`, `divtab`) is read from `libtts_us.so` into
`targets_transitions.py` by `tools/dump_dectalk_targets.py`, like the Phase-3 ROM.

Its input -- the allophone/feature/duration stream and the per-phone `durfon`,
plus the speaker `breathysw` seed -- is captured from the oracle, exactly as the
earlier phases captured their inputs.

### Verification

- **`test/test_dectalk_phsettar_full.py`** -- phone-for-phone diff of Python
  `phsettar` against the instrumented C, for all ten voices over four utterances.
  The instrumented `ph_setar.c` dumps, per phone, the full sixteen-parameter
  `PARAMETER` state it writes; the port is replayed over the identical captured
  stream, carrying state across phones. Result: **every audio-relevant transition
  field matches the C** (135520 / 135520 fields, 10 voices). Skipped when the
  instrumented binary is absent.

The instrumentation dumps `PARAMETER.ndip[0]`/`ndip[1]` as a raw pointer peek. On
the phone where a parameter is diphthongized they match the C exactly; on a later
non-diphthong phone the C's pointer has been advanced further by `advance_frame`
during the intervening frames, which the phone-by-phone replay does not run, so
those peeks are excluded here and validated instead by the end-to-end frame loop.

Four fidelity gaps were root-caused against the oracle to reach bit-exactness:
rule 6's `tarnex` coarticulation used GERMAN-only branches (the US path is
`arg2 = N10PRCNT; tarnex += mlsh1(tarend - tarnex, arg2)`); `getbegtar` gates
`us_special_coartic` on `nfone & PFONT` where `nfone` is a phone index, so the
call is dead there (and in `make_dip` for the non-first diphthong values),
whereas `getendtar` applies it; and the backward AP boundary `PAP.tarend - 6` is
nested inside `if (np == PAV)`, unreachable dead code.

## What the phdraw frame loop and `send_pars` are

`draw_frame` (Phase 2) is a pure per-frame function of the interpolation state.
The C `phdraw` also **mutates** that state each frame, and two more stages sit
between it and the vocal tract model. `ph.py` ports all three:

- **`advance_frame`** (`ph_draw.c:345-731`) applies the per-frame state changes:
  the diphthong-line step (`durlin`/`deldip`/`tarcur`/`dipcum` and the `ndip`
  pointer into the shared `dipspec[]` buffer), `ftran -= dftran`,
  `btran += dbtran`, the F2 vowel-vowel decays, and the breathy `breathyah`/
  `breathytilt` ramps -- so many frames can be driven from one `phsettar` output.
- **`finalize_av`** (`ph_draw.c:4344`, run before the compiled build's return at
  4355, i.e. after the point the Phase-2 X-dump captures) raises the voicing
  amplitude to `AV + max(0, (TILT >> 2) - 4)` for `AV > 3`.
- **`send_pars`** (`ph_claus.c:694`) assembles the vocal-tract-model frame: it
  delays every parameter except AV, TILT, and T0 by one frame, remaps TILT
  through `LINEARTILT`, and primes on the first frame without emitting (so N drawn
  frames yield N-1 synthesized frames).

### Verification: the allophone -> PCM chain composes

- **`test/test_dectalk_endtoend.py`** -- drives `phsettar -> advance_frame /
  draw_frame -> finalize_av -> send_pars` over a captured allophone stream and
  diffs the result against the exact frame the C ships to its vocal tract model
  (`parambuff[1..20]`, dumped in `vtmiont.c`), for all ten voices over four
  utterances. Result: **the ported front end reproduces the synthesizer input
  bit-for-bit, 12310 / 12310 frames, 40/40 cases**. Only the F0 contour and phone
  durations (Phase 5) are borrowed from the oracle. Running those frames through
  `vtm.py` reproduces the oracle WAV **sample-for-sample for all ten voices**
  (40/40 cases).

## The allophone -> PCM chain is sample-exact

`phsettar -> advance_frame / draw_frame -> finalize_av -> send_pars -> vtm`
reproduces the oracle WAV sample-for-sample for all ten voices over four
utterances (`test/test_dectalk_endtoend.py`), borrowing only the F0 contour and
phone durations from the oracle. Two oracle-anchored CI gates lock this in from
committed real captures, needing no oracle binary:

- **`test/dectalk_vtm_pcm_golden` + `test/test_dectalk_vtm_pcm_golden.py`** --
  the real `parambuff` frames the C ships to its vocal tract model and the samples
  it returns, per voice; `vtm.py` must reproduce them.
- **`test/dectalk_endtoend_golden` + `test/test_dectalk_endtoend_golden.py`** --
  a real allophone stream per voice (plus F0/durations), gated end to end against
  the oracle PCM.

Both would have caught the `vtm.py` defect described next; the older synthetic
`dectalk_golden` vector did not.

### The vtm defect that hid behind an insufficient golden

`vtm.py` silenced only the first two frames after a speaker definition; the C
silences three. `ldspdef` is a C `BOOL`, which is `unsigned char` in this build
(`api/tts.h:237`), so the reference's `ldspdef = -1` wraps to 255 and the
following frame's `ldspdef >= 1` test is still true -- silencing a third frame.
The Python `int` kept `-1`, so `-1 >= 1` was false and the third frame slipped
through, latching the voicing amplitude `avlin` one frame early. That made
`vtm.py` diverge, mid-utterance and speaker-dependent, on every voice whose third
frame already carried voicing. The synthetic `dectalk_golden` vector never
reproduced that ramp, so it stayed green -- a false green. The two real-capture
goldens above are the gate that catches it.

## What the text front end is

`cmd/` and `lts/` are the top layer: they turn written text and `[: ]` markup
into the phoneme+stress stream the `ph/` allophone stage consumes. `cmd/`
(`cmd/cm_pars.c`, US command table `cmd/c_us_cde.h:390-485`) scans the input into
plain-text runs and inline commands (voice select `[:n?]`, `[:rate]`,
`[:phoneme on/off]`, `[:dv]`, ...). `lts/` looks each word up in the compiled
dictionary (`lts/ls_dict.c`, `dtalk_us.dic`) and, on a miss, runs the
letter-to-sound rules (`lts/l_us_*`, `ls_rule*.c`) plus number/abbreviation
expansion and homograph disambiguation.

### The oracle exposes the stream directly

`[:log phonemes on]` / `TextToSpeechOpenLogFile(h, path, LOG_PHONEMES)`
(`ph/phlog.c`) makes the oracle print the phoneme+stress stream as text: per
phoneme, the `us_<ARPABET>` name (`PrintLangBit` + `usa_arpa`,
`include/usa_phon.tab`) plus the stress and boundary marks. `tools/dump_dectalk_lts.py`
drives the built US library through a tiny public-API harness (no source
instrumentation) and records this text per input; `test/dectalk_lts_golden.json`
is the committed real capture. Letter-to-sound is voice-independent, so one
capture per input suffices.

### What is ported

- **`lts.py`** — the phoneme+stress alphabet: the phoneme codes (`l_us_ph.h`),
  the control/prosody codes (`l_com_ph.h`), the `usa_arpa` render table, the
  `usa_ascky` input alphabet, and `render_stream` reproducing the `LOG_PHONEMES`
  text (`phlog.c`). `phoneme_spans` decodes an oracle log back to codes.
- **`dictionary.py`** — the flat `dtalk_us.dic` loader (`loaddict.c`) and the
  `ls_dict_find_word` / `ls_dict_dlook` / `ls_dict_where_to_look` binary search
  (`ls_dict.c`), returning the raw phoneme+stress payload bytes for a hit.
- **`cmd.py`** — the `[: ]` command tokenizer and the US command table, resolving
  voice / rate / phoneme-mode control state per text run.

### Verification (`test/test_dectalk_lts.py`, 33 tests)

- **Render round-trip.** Every `us_<name>` token across all 26 committed oracle
  captures decodes through `phoneme_spans` and re-renders byte-identically
  (runs in CI without the oracle). Mutating one ARPABET render entry fails 7 of
  the captures.
- **Dictionary payload vs oracle.** For a curated set of unique-grapheme
  dictionary hits (single words and phrases), the phoneme code sequence
  `Dictionary.lookup` returns equals the phonemes the oracle emitted. Skipped
  without `dtalk_us.dic`.
- Over a 143-word common-English probe: **137 identical, 3 downstream-rule
  differences, 3 misses**. The differences are not dictionary errors — the port
  returns the exact stored payload:
  - `just` has two records; the oracle uses the `jh ah s t` variant, the search
    lands on `jh ix s t` (the duplicate-grapheme / homograph selection needs the
    part-of-speech stage);
  - `and` (`eh n d` stored, `ae n d` emitted) and `will` (`w ih ll` stored,
    `w ih lx` emitted) differ by the downstream function-word reduction and
    allophone substitution (`allorules.c`), which live in `ph/`, below this
    layer.
  - the 3 misses are words absent from the main dictionary (function words the
    engine handles elsewhere).

### What is stubbed (US)

- **Letter-to-sound rules.** Out-of-dictionary words (`ls_rule*.c`, `l_us_*`)
  are a dictionary miss here; no phonemes are produced for them.
- **Number and abbreviation expansion.** `123 -> "one hundred twenty three"`,
  `Dr. -> "doctor"` etc. (`lts/`) are not ported; the oracle captures show the
  expected expansions for the future work.
- **Homograph / duplicate-grapheme selection.** Needs the part-of-speech pass;
  a hit returns the record the search lands on.
- **`[:phoneme on]` phonetic-input decoding** (`cmd/cm_phon.c`) and `[:dv]`,
  `[:pitch]`, `[:tone]`, DTMF command *effects* — `cmd.py` tokenizes and carries
  voice/rate/mode but does not decode phonetic input or resolve these.
- **Other languages** (uk/fr/gr/sp/la). US only.

### Full text-to-PCM

The middle layer (`ph/` allophone selection, duration, F0 above `phsettar`) is
not yet on `dev`, so `dictionary.lookup` output cannot be run end to end to PCM
inside the port. The dictionary payload is proven against the oracle phoneme
stream; the allophone -> PCM chain below it is separately proven sample-exact
(`test_dectalk_endtoend.py`). Composing text -> phonemes -> PCM awaits the
middle layer.
## What the duration stage (`us_phtiming`) is

`phclause` runs `phsort -> phalloph -> us_phtiming -> phinton` before the
per-frame loop. `us_phtiming` (`p_us_tim0.c:90`) is the third of those: it takes
the allophone stream `phalloph` produced (`allophons[]`, `allofeats[]`,
`nallotot`) and assigns each allophone a duration `allodurs[nphon]` in 6.4 ms
frames. It applies the numbered duration rules -- pause syntax, clause-final rime
lengthening, polysyllabic and consonant-cluster shortening, postvocalic-consonant
effects, cluster and function-word special cases -- to the per-phone inherent and
minimum inherent durations (`inh_timing`/`min_timing`, reading the US voice ROM),
scales them by the speaking-rate factors `init_timing` (`ph_timng.c:174`)
resolves (`sprat0`/`sprat1`/`sprat2`/`timeref`), and runs a syllable-level
time-alignment pass. All arithmetic is the reference's fixed point.

### What is ported: `us_phtiming`

`pyretrotts/dectalk/timing.py` ports `us_phtiming`, `init_timing`, `inh_timing`,
and `min_timing` for the compiled US path (`ENGLISH_US`,
`OLD_INTONATION_AND_TIMING`; none of `GERMAN`/`FRENCH`/`SPANISH`/`ENGLISH_UK`/
`HLSYN`/`CHANGES_AFTER_V43`/`SLOWTALK`/`CHANGES_FOR_V44`, and `bInTypingMode`
FALSE). The minimum inherent durations `us_mindur` are read verbatim from the
compiled voice ROM `p_us_rom_dectalk_1996m_43f.c`; the inherent durations reuse
`targets_transitions.US_INHDR`. The `[n]->[d]` postvocalic-cluster stream
mutation (Rule 9) is implemented but is not exercised by any test utterance (no
`nt` postvocalic cluster occurs). `TYPING_MODE`/`NEWTYPING_MODE` and the
`NSAMP_FRAME == 128` half-sample path are out of the compiled 11025 Hz path.

Its input -- the allophone/feature stream, `user_durs`, and the speaking rate --
is captured from the oracle at the exact `us_phtiming` boundary (the instrumented
`p_us_tim0.c` writes an `I` line of the input arrays and rate factors before the
rules run and an `O` line of `allodurs` after; `tools/dump_dectalk_aloph.py`
reads them). This boundary matters: `phinton` inserts further phones after
`us_phtiming`, so the post-`phinton` `allophons`/`allodurs` (the `phsettar`
`A`-line) has more entries than the timing stage ever saw.

### Verification

- **`test/test_dectalk_aloph.py`** -- duration-for-duration diff of Python
  `us_phtiming` against the instrumented C, for all ten voices over four
  utterances, replaying the port over the captured stage input. `init_timing` is
  checked to reproduce the speaking-rate factors the C resolved. Result: **40/40
  cases captured, 760/760 durations frame-exact, `init_timing` exact on 40/40
  clauses**. Skipped when the instrumented binary is absent.
- **`test/dectalk_aloph_golden.py` + `dectalk_aloph_golden.json` +
  `test_dectalk_aloph_golden.py`** -- a deterministic sha256 gate over
  `us_phtiming` on `dectalk_aloph_vectors.json`, twenty **real** allophone-stage
  inputs captured from the oracle across all ten voices. It runs in CI without
  the C. `--write` refuses to regenerate the digest unless the port first matches
  the oracle `allodurs` field for field for all ten voices; the gate is verified
  to bite on a rule-constant mutation. The captured vectors are
  all default-rate text, so they exercise the inherent-duration path but
  not the `durxx` user-duration-override branch (reached only by a `[:dv]`
  duration command); a mutation there passes the gate.

## What the allophone-selection stage (`phsort`/`phalloph`) is

`phclause` runs `phsort -> phalloph -> us_phtiming -> phinton` before the
per-frame loop. `phsort` and `phalloph` are the first two: they turn the
phoneme + stress + sentence-structure symbol stream the front end emits into the
allophone stream every downstream stage -- `us_phtiming` (`timing.py`),
`phsettar`, `phdraw`, `vtm` -- consumes.

- **`phsort` (`all_phsort`, `ph_sort.c:428`)** orders the input `symbols[]` into
  a phoneme stream `phonemes[]` and a parallel 32-bit `sentstruc[]`. It inserts a
  leading word boundary, resolves compound de-stress, collapses adjacent boundary
  symbols (`zap_weaker_bound`), promotes/relocates dangling stress marks
  (`move_stdangle`, `find_syll_to_stress`, `raise_last_stress`), sets the clause
  type on comma/period/question/exclamation, then emits one phone per real symbol
  (`make_phone`) and folds every control symbol -- word/phrase/clause boundaries,
  stress marks, hat commands, sentence terminators -- into `sentstruc` feature
  bits: `FSTRESS_*`, `FWINITC`, the first/medial/final syllable class
  (`init_med_final`), the next-boundary type via `bounftab` (`get_next_bound_type`),
  and the consonant-cluster stress carry (`get_stress_of_conson`, `us_phcluster`).
- **`phalloph` (`ph_aloph1.c:444`)** applies the phonological allophone-selection
  rules: it copies each phoneme to `allophons[]` unless a context/stress/boundary
  rule substitutes a different allophone -- postvocalic `/r/`+vowel coalescence
  (`ar/er/ir/or/ur/rr`) and `/l/`->`/lx/`, `/t d/` flapping (`df/dx`) and
  glottalization/dentalization (`d/tx/dz`), `/dh/` assimilation, `/t d/`->`/ch jh/`
  palatalization, and the `the/for/to/and` function-word unreductions -- and it
  writes `allofeats[]`: the `sentstruc` bits plus the hat-pattern intonation marks
  (`FHAT_BEGINS`/`FHAT_ENDS`) placed by the stressed-syllable rise/fall rules
  (`remaining_stresses_til`, `promote_last_2`). It is 1:1 phone->allophone on the
  US path (no insertion/deletion; the `/r/` coalescence rewrites the previous
  allophone in place and drops the `/r/`).

### What is ported: `phsort` and `phalloph`

`pyretrotts/dectalk/allophones.py` ports both for the compiled US path
(`ENGLISH`, `ENGLISH_US`, `OLD_INTONATION_AND_TIMING`, `US_TOT_ALLOPHONES == 57`;
none of `GERMAN`, `FRENCH`, `SPANISH`, `ENGLISH_UK`, `HLSYN`, `CHANGES_AFTER_V43`,
`NWSNOAA`, `SLOWTALK`, `NEVER`, and `lang_curr == LANG_english`). It is the
reference's integer arithmetic throughout (C `short`; the US path has no
fixed-point scaling). The `bounftab` boundary-type table, the `us_phcluster`
cluster classes, and the phone-index/feature/struct-bit constants are transcribed
from the C with `file:line` citations; the per-phoneme feature bits are read
through the existing `settar._phone_feature` (`US_FEATB`, already ROM-verified).

The stage is voice-independent: `phsort`/`phalloph` do not read the speaker
definition (only `malfem`, which the US path never uses), and the captured output
is identical across all ten voices for every utterance. The output is exactly the
stream `timing.us_phtiming` consumes, captured at `phalloph`'s own boundary (the
`us_phtiming` input line), before `phinton` inserts further phones.

### Verification

- **`test/test_dectalk_phalloph.py`** -- field-for-field diff of Python `phsort`
  (`phonemes`/`sentstruc`/`nphonetot`) and `phalloph`
  (`allophons`/`allofeats`/`nallotot`) against the instrumented C, replaying the
  port over the captured stage input, for all ten voices over ten varied
  utterances (consonant clusters, phrase-final devoicing, function words,
  questions, plosive bursts, flapping, `/r l/` coalescence). Result: **100/100
  cases; `phsort` 1970/1970 phonemes and 1970/1970 `sentstruc` fields;
  `phalloph` 1960/1960 `allophons` and 1960/1960 `allofeats`; every `nphonetot`
  and `nallotot` exact**. Over a wider 36-utterance corpus the counts are
  4430/4430 and 4410/4410. Skipped when the instrumented binary is absent.
- **`test/dectalk_phalloph_golden.py` + `dectalk_phalloph_golden.json` +
  `test_dectalk_phalloph_golden.py`** -- a deterministic sha256 gate over
  `phsort` + `phalloph` on `dectalk_phalloph_vectors.json`, **130 real** captured
  vectors across all ten voices (7860 fields). It runs in CI without the C.
  `--write` refuses to regenerate the digest unless the port first matches the
  oracle field for field for all ten voices; the gate is verified to bite on a
  `bounftab` mutation and on an allophone-substitution mutation.

The dumper (`tools/dump_dectalk_phalloph.py`) reuses the two instrumentation
points already in `ph_claus.c`/`p_us_tim0.c`: `DECTALK_SORT_DUMP` writes
`phsort`'s input `symbols` and output `phonemes`/`sentstruc`, and
`DECTALK_TIM_DUMP` writes `phalloph`'s output `allophons`/`allofeats` at the
`us_phtiming` boundary; it pairs them per clause. `phsort`+`phalloph`+`us_phtiming`
compose bit-exactly (`symbols -> allodurs`, 950/950 durations, ten voices).

### What is stubbed (US)

- **Citation mode and user prosody.** `cite_it` (`(modeflag & MODE_CITATION) &&
  docitation`) defaults to 0 (connected speech) and `f0mode` to `NORMAL`; the
  citation-only unreductions (`long a -> ey`, `at -> ae`) and the
  `HAT_LOCATIONS_SPECIFIED`/`HAT_F0_SIZES_SPECIFIED` user-hat and per-phone
  `user_f0`/`user_dur` command paths are present but not exercised by any
  default-text vector. The `mode_citation` flag (raw `MODE_CITATION`, set in the
  default mode) is threaded so the "to"-flap rule matches the oracle.
- **`zap_weaker_bound` merge direction.** The compiled 43F oracle keeps the
  lower-coded (weaker) of two adjacent boundary symbols (verified field-for-field
  against `sentstruc`); a literal transcription of the C keeps the stronger one.
  The port follows the observed oracle. This is documented inline.
- **Slow-rate boundary strengthening** (`sprate <= 120`/`<= 140`) is implemented
  but the default rate (180) never reaches it, so those branches are untested.
- **`adjust_index`/`set_index_allo`** (index-mark bookkeeping for markup
  callbacks) are side effects with no bearing on the phoneme/allophone output and
  are not ported.
## What the F0/intonation stage (`phinton` + `pht0draw`) is

`phclause` runs `phsort -> phalloph -> us_phtiming -> phinton` before the
per-frame loop; `phinton` is the fourth stage and `pht0draw` runs inside the
loop. For the compiled US path (`ENGLISH_US`, `OLD_INTONATION_AND_TIMING`; the
`phinton` at `ph_inton0.c:1325`, reached through `ph_inton.c`, and the `pht0draw`
at `ph_drwt01.c:2381` -- **not** the malfem-branching one at `ph_drwt01.c:277`,
which that build's `#if` excludes).

- **`phinton`** (`ph_inton0.c:1325`) runs once per clause. It walks the
  post-`us_phtiming` allophone/structure/duration stream and, at each syllabic
  phone and clause boundary, emits F0 commands into `f0tar[]` (target, Hz*10 with
  rule-encoded flags) and `f0tim[]` (frames since the previous command) via
  `make_f0_command`: the hat rise at a hat-begin, the stress+phrase-position rise
  at each stressed syllable (`us_f0_stress_level`/`us_f0_phrase_position`,
  scaled by `scale_str_rise`), the hat fall at a hat-end (assertiveness-scaled,
  boundary-dependent, with a forward scan for the next syllable), the
  continuation-rise/fall pairs at clause and sentence boundaries, and the return
  to baseline at silence. It also **inserts a reduced vowel** (`AX`/`IX`) after a
  clause-final plosive, so its output stream is longer than its input.
- **`pht0draw`** (`ph_drwt01.c:2381`) runs once per output frame. It consumes the
  F0 command stream and the post-`phinton` allophone/duration stream to draw the
  per-frame fundamental: a declining baseline (`beginfall`/`endfall`), the summed
  hat/impulse/segment targets (`us_f0segtars`), a two-pole low-pass
  (`filter_commands`), a glottalization dip (`set_tglst`/`dtglst`), the speaker
  range scaling (`f0minimum`/`f0scalefac`), and a `getcosine` pseudo-jitter --
  then writes the period `parstochip[OUT_T0] = 400000 / f0prime` the vocal tract
  model uses. The user-markup modes (singing / per-phone / hat-size,
  `f0mode >= 3`) and their `linear_interp`/`set_user_target`/`notetab` paths are
  reproduced but not exercised by plain text (`f0mode == NORMAL`).

### What is ported: `intonation.py`

`pyretrotts/dectalk/intonation.py` ports `phinton` + `make_f0_command` and
`pht0draw` + `set_user_target`/`set_tglst`/`filter_commands`/`linear_interp` for
that build. It is fixed point where the C is: every intermediate is a C `short`
(`s16`), the target/assertiveness products use `muldv` and the filter taps
`mlsh1` (shared with `phsettar.py`). The F0 ROM tables (`us_f0_stress_level`,
`us_f0_phrase_position`, `us_f0segtars`, `notetab`, `getcosine`) are transcribed
from `p_us_rom_dectalk_1996m_43f.c` with citations; `us_place`/feature bits reuse
`targets.US_PLACE`/`US_FEATB`. Its input -- the post-`us_phtiming` stream, the
speaker F0 scalars, and (for `pht0draw`) the `phinton` output plus the `nf0ev`
seed -- is captured from the oracle. The `pDphsettarF0` state persists across a
clause boundary, so a multi-clause utterance is driven through one `Pht0draw`
whose carried `f0`/`timecos*`/fall state feeds the next clause's `nf0ev == -1`
soft init.

### Verification

- **`test/test_dectalk_phinton.py`** -- field-for-field diff of Python `phinton`
  (its `f0tar`/`f0tim`/`nf0tot` and the reduced-vowel-inserted stream) and
  frame-for-frame diff of `pht0draw` (its `parstochip[OUT_T0]` and drawn
  `f0prime`) against the instrumented C, for all ten voices over ten utterances
  (statements, questions, multi-clause, emphasis, function-word runs). The
  instrumented `phinton`/`pht0draw` (`DECTALK_INT_DUMP`) dump the stage input,
  output, per-clause scalars, and per-frame T0. Result: **phinton 900/900 output
  fields exact, pht0draw 37500/37500 per-frame T0/f0prime exact (100/100 cases,
  10 voices)**. Skipped without the instrumented binary.
- **`test/dectalk_intonation_golden.py` + `dectalk_intonation_vectors.json` +
  `test_dectalk_intonation_golden.py`** -- a deterministic sha256 gate over
  `phinton`/`pht0draw` on the real captured clause corpus (37800 F0 values, ten
  voices, oracle-anchored at write time). Runs in CI without the C; verified to
  bite on a `us_f0_stress_level` and a `getcosine` mutation.

### The F0-included chain composes bit-exact

`test/test_dectalk_endtoend.py` proves `phsettar -> phdraw loop -> send_pars ->
vtm` reproduces the oracle PCM sample-for-sample while borrowing the per-frame
`parstochip[OUT_T0]` from the oracle. `pht0draw` here draws that exact
`parstochip[OUT_T0]` field bit-for-bit (37500/37500 frames), so substituting the
ported F0 for the borrowed one yields identical vocal-tract-model input and
therefore identical PCM; the borrow in `test_dectalk_endtoend` is now a ported
stage, not an oracle dependency.

### What is stubbed (F0)

- **User-markup F0 modes.** `f0mode` 3/4/5 (`[/]`/`[\\]` hat sizes, sung notes,
  per-phone targets) and their `mstofr` millisecond-to-frame conversion are
  reproduced in structure but not exercised; `mstofr` (defined outside the ported
  translation units) raises, and no `[:...]` prosody markup reaches this stage in
  the corpus. Plain text is always `f0mode == NORMAL`.
- **`cbsymbol`** (French interrogative halving) is always 0 in the US build; those
  branches are present but dead.

## Limitations

- **`divtab` out-of-range.** `phsettar` indexes `divtab` (50 entries) by
  transition duration; the forward/backward rules clamp that duration to
  `NF130MS` (20 frames), so the index stays in range. For any phone that reached a
  duration >= 50 the C would read runtime-mutable memory past the array
  (non-reproducible); `phsettar.py` would read zero there. No test utterance hits
  this.
- **`ph/` front end above `phsettar`.** The duration rules (`us_phtiming`,
  `p_us_tim0.c`), allophone selection (`phsort`/`phalloph`, `ph_sort.c`/
  `ph_aloph1.c`), and the F0 contour (`phinton`/`pht0draw`, `ph_inton0.c`/
  `ph_drwt01.c`) are all ported and bit-exact against the C across ten voices
  (`timing.py`, `allophones.py`, `intonation.py`). With these merged the whole
  `ph/` chain from a phoneme+stress stream down to PCM is ported; what remains
  above it is the text front end (`lts/` letter-to-sound rules and `cmd/`), which
  turns text into that phoneme stream.
- **No text input.** The whole `cmd/` -> `lts/` -> `ph/` chain that turns text
  and `[: ]` markup into parameter frames is unported. `engine.py` takes frames,
  not text. Driving it therefore requires porting the rest of the front end
  (Phase 3+) or, as the tests do, replaying frames captured from the oracle. This
  is the single biggest obstacle to a self-contained DECtalk.
- **US English, 11025 Hz only.** The port hard-codes the `VTM1`,
  `PC_SAMPLE_RATE == 11025`, `SAMPLE_RATE_INCREASE` path. The 8 kHz / mu-law
  path (`SAMPLE_RATE_DECREASE`) and the float `FP_VTM` variant are not ported;
  the sample-rate-scaling branches in the coefficient functions are present but
  exercised only in the `INCREASE` direction.
- **HLsyn, tones, DTMF, compression** (`hlsyn/`, `playtone.c`, `COMPRESSION`)
  are out of scope; none is in the US-English default path.
- **The oracle instrumentation is not vendored.** The frame dump depends on a
  temporary C patch to `vtmiont.c` (documented above); the read-only checkout
  stays clean, so the oracle test skips unless you build an instrumented copy.
