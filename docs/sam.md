# SAM, the shipped engine

SAM (Software Automatic Mouth, Don't Ask Software, 1982) is the third engine in
this repository, in `pyretrotts/sam/`. It is a bit-exact port of the C
reimplementation at `github.com/vidarh/SAM`, which is itself an
opcode-by-opcode translation of SoftVoice, Inc.'s 6502 program.

**Licensing:** SAM is not covered by this project's MIT licence and is kept in
its own subpackage. Read `NOTICE` before redistributing anything. Every file in
`pyretrotts/sam/` carries a header stating its provenance.

For the design evaluation that preceded the port. See [sam-port-plan.md](sam-port-plan.md). For why SAM sounds nothing like the other
two engines. See [history.md](history.md).

## What it is, technically

SAM is **not** a formant (Klatt) synthesizer like MacinTalk and DECtalk. Each
10 ms frame carries three oscillators, two sine waves and one rectangle wave, 
summed open-loop with no resonators and no bandwidths. Consonants that cannot be
built that way (fricatives, plosives) are played from a compressed **1-bit
sample table**. The whole synthesizer is integer-only 8-bit arithmetic emitting
**8-bit unsigned PCM at 22050 Hz mono**. `SAMEngine.synthesize` widens that to
the 16-bit signed PCM the `Engine` ABC promises, at the very edge:
`(byte - 128) << 8`.

## Module map

| C source | Python module | What it does |
|---|---|---|
| `SamTabs.h`, `RenderTabs.h`, `ReciterTabs.h` | `sam/tables.py` | Static tables, transcribed verbatim from the C |
| `SamTabs.h` phoneme flags/lengths | `sam/phonemes.py` | Phoneme ids, mnemonics, flag bits, length tables |
| `reciter.c` | `sam/reciter.py` | English text → SAM phoneme mnemonics (rule engine) |
| `sam.c` (Parser1/Parser2, stress, lengths) | `sam/prosody.py` | Tokenising, rewrite rules, and duration rules |
| `render.c`, `processframes.c`, `createtransitions.c` | `sam/render.py` | Frames, transitions, 3-oscillator + sampled output |
| `sam.c` (SAMMain/PrepareOutput) | `sam/sam.py` | Top-level driver: pipeline + clause splitting |
| - | `sam/engine.py` | `SAMEngine(Engine)` and the voice presets |

Every value is masked to eight bits exactly where the 6502/C original relied on
unsigned-byte wraparound.

## Input

Two forms, matching the C:

- **English text** (default), run through the reciter's rule engine.
- **Phoneme mnemonics** (`phonetic=True`), two-character mnemonics with stress
  digits, e.g. `/HEHLOW`, `AA5`. The notation is the `dialect` string: `/`
  diacritics (`/H`, `/X`), stress digits `1`, `8` appended to a vowel.

`sing` mode (`singmode=True` on `sam.render_pcm`) disables the automatic pitch
contour so the pitch knob holds a steady note.

## Voices, knob presets

SAM has no named voices. It has four integer knobs. `SAMEngine` exposes the
manual's six voices as `(speed, pitch, throat, mouth)` presets. Lower speed is
faster. The C defaults are speed 72, pitch 64, throat 128, mouth 128.

| Voice | speed | pitch | throat | mouth |
|---|---|---|---|---|
| Sam | 72 | 64 | 128 | 128 |
| Elf | 72 | 64 | 110 | 160 |
| Little Robot | 92 | 60 | 190 | 190 |
| Stuffy Guy | 82 | 72 | 110 | 105 |
| Little Old Lady | 82 | 32 | 145 | 145 |
| Extra-Terrestrial | 100 | 64 | 150 | 200 |

## Preserved quirks

The port reproduces upstream behaviour that shapes the output, rather than
"fixing" it:

- **`phonemeindex[255]` is set twice** (to `END`, then to 32) in the driver, as
  the C's own `FIXME` notes. Both writes are kept (`sam/sam.py`).
- **`mem66` is left uninitialised** in `ProcessFrames`. The port seeds it to 0,
  matching the reference build (`sam/render.py`).
- **Out-of-bounds `flags[]` reads.** Several parser and length rules index
  `flags[]` with the `END` sentinel (255), past the 81-entry array. The port
  extends the flag table to 256 entries with the exact bytes the reference build
  exposes there, so those rules decide as the reference does (`sam/tables.py`,
  `sam/phonemes.py`).
- **`phonemeindex[pos-1]` at `pos == 0`.** In the C this is int arithmetic, so
  the index is `-1`, not 255. The reference build reads a zero there, which the
  port reproduces (`sam/prosody.py`).

## Verification

Two layers, the same discipline as the MacinTalk engine
([architecture.md](architecture.md)).

- **The C oracle** (`test/test_sam_oracle.py`) shells out to a no-SDL build of
  the SAM C, an `oracle` binary that writes its 8-bit PCM to stdout, for a
  matrix of texts, phoneme strings, sing mode, and all six voice knobs, and
  diffs it against the Python port sample for sample. It is skipped when the
  binary is absent, so it does not run in CI. SAM has no bracket-command
  ambiguity, so every public input is oracle-checkable.
- **The golden gate** (`test/test_sam_golden.py`, `test/sam_golden.json`) hashes
  the 16-bit engine output for six voices × six texts. The digests were captured
  only after `test/sam_golden.py --write` verified every case against the C
  oracle first, so they pin the audio to that reference without needing it
  present. This runs in CI.
- **Unit tests** (`test/test_sam.py`) hold reciter strings, phoneme-table values
  and prosody-stage buffers taken from `sam -debug`, as inline literals.

At the time of writing, the port is byte-exact against the C reference across
every case tried: text and phonetic input, sing mode, punctuation, number
reading, consonant clusters, and all six voice presets.

## Limitations

- **The out-of-bounds reads are anchored to one build.** The `flags[]` tail
  (indices 81-255) and the `phonemeindex[-1]` value are properties of the
  reference binary's memory layout, not of the SAM source. They are deterministic
  for that build and the golden digests are frozen against it. A SAM C binary
  built with a different compiler or layout could in principle expose different
  out-of-bounds bytes. If that ever makes `test_sam_oracle.py` disagree, the
  oracle build has changed, not the port. The frozen golden gate is unaffected.
- **The reciter's text join.** `render_pcm` forms the reciter input as
  `text + " ["`, matching how the C CLI joins its arguments with a trailing space
  before appending the terminator. Feeding text with embedded runs of spaces or
  control characters that the CLI would have split differently is not modelled.


---
[← SAM port plan](sam-port-plan.md) · [Home](../README.md) · [Modern mode →](modern-mode.md)
