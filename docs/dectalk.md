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

Phase 1 (the vocal tract model, `vtm/`) is **ported and bit-exact**. The text
front end (`cmd/`, `lts/`, `ph/`) is not ported, so there is no text-to-speech
yet; `pyretrotts/dectalk/engine.py` synthesizes from Klatt parameter frames.

| Piece | Module | State |
|---|---|---|
| Fixed-point primitives, resonator coefficients, frame loop | `vtm.py` | bit-exact vs C |
| VTM fixed-point tables | `tables.py` | transcribed from C by a dumper |
| Ten voices: names, `[:n?]` codes, resolved chip parameters | `voices.py` | captured from C |
| Constants, frame-parameter layout | `consts.py` | — |
| Frame-driven synthesis + WAV writer | `engine.py` | — |
| Text -> parameter frames (`ph/`) | — | **not ported** (Phase 2+) |

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

## Limitations

- **No text input.** The whole `cmd/` -> `lts/` -> `ph/` chain that turns text
  and `[: ]` markup into parameter frames is unported. `engine.py` takes frames,
  not text. Driving it therefore requires either porting `ph/` (Phase 2) or, as
  the tests do, replaying frames captured from the oracle. This is the single
  biggest obstacle to a self-contained DECtalk.
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
