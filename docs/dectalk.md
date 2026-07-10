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
| `ph/` allophone selection / duration / F0 | — | **not ported** (Phase 5+) |
| `cmd/` markup, `lts/` letter-to-sound | — | **not ported** (Phase 5+) |

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
  the C oracle sample for sample on real utterances, for all ten voices.

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
  `vtm.py` reproduces the oracle WAV sample-for-sample for the voices where the
  vocal tract model itself is exact (see the vtm limitation below).

## Limitations

- **`vtm.py` (Phase 1) diverges on some speaker configs.** With a frame-exact
  vocal-tract-model input (proven above for all ten voices), `synthesize_frames`
  reproduces the oracle WAV sample-for-sample for Perfect Paul, Beautiful Betty,
  Huge Harry, Doctor Dennis, and Rough Rita on some utterances, but diverges for
  others (e.g. Frail Frank, Kit the Kid, Uppity Ursula, Whispering Wendy, Variable
  Val). The divergence is localized (it appears mid-utterance and recovers) and
  depends on the `SpeakerState`, so it is a `vtm.py` code path the Phase-1
  utterances did not exercise -- an in-frame parameter handling the C
  `speech_waveform_generator` applies that the port does not. This is the sole
  remaining blocker to a fully sample-exact allophone->PCM chain; it is in the
  synthesizer, not the ported front end.
- **`divtab` out-of-range.** `phsettar` indexes `divtab` (50 entries) by
  transition duration; the forward/backward rules clamp that duration to
  `NF130MS` (20 frames), so the index stays in range. For any phone that reached a
  duration >= 50 the C would read runtime-mutable memory past the array
  (non-reproducible); `phsettar.py` would read zero there. No test utterance hits
  this.
- **`ph/` front end above `phsettar`.** Allophone selection (`ph_aloph1.c`),
  duration rules
  (`p_us_tim0.c`), and the F0 contour and `pht0draw` (`ph_inton0.c`,
  `ph_drwt01.c`) remain unported; `draw_frame` consumes the interpolation state
  they produce, captured from the oracle.
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
