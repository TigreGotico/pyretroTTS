# DECtalk engine

This documents the Python port of the genuine DECtalk synthesizer, kept in
`pyretrotts/dectalk/`. It is a separate engine from the MacinTalk port described
in [architecture.md](architecture.md); the two share only test discipline, not
code.

**Licensing.** Everything under `pyretrotts/dectalk/` descends from the
Fonix/Force DECtalk C source, which FONIX Corporation declares proprietary and
confidential. That subpackage is **not** covered by this project's MIT licence;
every file in it carries the FONIX notice. See [NOTICE](../NOTICE).
`DECtalkEngine` renders through the DECtalk synthesizer for the ten voices when a
DECtalk dictionary is installed, and substitutes the nearest MacinTalk voice
otherwise; the dictionary itself is not distributed with this package.

## Status

Phase 1 (the vocal tract model, `vtm/`) is **ported and bit-exact**. The whole
`ph/` chain above it is now ported and composed: `phclause.speak_phonemes`
(`phclause.py`) runs `phsort -> phalloph -> us_phtiming -> phinton -> per-frame
loop -> vtm` entirely in Python and reproduces the oracle WAV **sample for sample
for all ten voices** from a phoneme+stress+sentence-structure `symbols[]` stream
(the `lts/`/`cmd/` output). The `lts/` letter-to-sound rule engine that pronounces
out-of-dictionary words is now ported too (`lts_rules.py`); a lone dictionary or
rule-driven word composes text -> phonemes -> PCM sample-exact vs the oracle.

The **multi-word / multi-clause sentence front end** is now ported
(`sentence_us.py`): text is split into clauses on punctuation, each word is framed
with an inter-word boundary marker, and each clause is closed by the intonation
terminator (comma/semicolon/colon continuation-rise, period declarative fall,
question rise, exclamation). Numbers, currency, ordinals and abbreviations expand
to words first (`numbers_us.py`, the abbreviation table), and a vowelless token is
spelled letter by letter (`spell_us.py`). For sentences the C's syntactic parser
leaves at plain word boundaries -- plain statements, comma lists, and spelled
words -- this composes **whole-sentence text -> PCM sample-exact vs the oracle
across all ten voices** (see the sentence section below), and drives
`DECtalkEngine.synthesize` natively when the FONIX dictionary is present.

The **word-level syntactic marking** is now ported (`grammar_us.py`): the US
front end has **no runtime grammar/POS parser** -- the `cmd/par_*.c` files are a
character-level text preprocessor, not a syntactic parser, and none of the
phrase-marker form-class names (`PPSTART`/`VPSTART`) is referenced in the
compiled path. The phrase markers `phclause` reads come from the **word-reading
path**: a dictionary word's stored **form-class bits** (`ls_dict.c:759-763`)
promote its boundary to `VPSTART` (a verb) or `PPSTART` (a prep phrase), and the
closed-class mini-dictionary `sdic[]` (`l_us_con.c:1157`) pronounces `for`/`and`/
`to` from a fixed `PPSTART`-led list. `grammar_us.py` reproduces both, so
dictionary verbs, `for`/`and`/`to`, and prep-phrase words frame bit-exactly.

**Inflectional morphology is now ported** (`morph_us.py`): a word that misses the
main dictionary has an inflectional suffix stripped, the stem re-looked-up, and
the suffix's phonemes appended, driven by the verbatim `ls_suff.c`
`suffix_table`/`suffix_index` trie (`suffix_data.py`) -- `dogs -> dog + Z`,
`cats -> cat + S`, `boxes -> box + IX Z`.

The **in-context article reduction** and the **digit-path number/currency
reading** are now ported. The single-character word `a` reduces to the schwa
article mid-clause (`grammar_us.article_a_codes`, `ls_task.c:2632-2645`), and
integers, ordinals, currency and decimals are read by the digit path's own
phoneme lists (`numbers_us.number_token_send_codes`, `l_us_pr1.c`/`l_us_con.c`),
so `123`, `2005`, `$5`, `$5.25` and the whole number/article battery frame and
render bit-exact. The **`Dr.`/`St.` title-abbreviation disambiguation** is now
ported too (`title_abbrev_us.py`, `ls_task.c:2910`), so `dr. smith` renders
sample-exact. What remains is the **question-final content-word restress** (a
framing-only note; PCM-exact via `phsort`), the four-digit year-pairs reading
(`1100` -> "eleven hundred"), homographs, and the other languages.

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
| `ph/` clause orchestrator (`phclause`) | `phclause.py` | **phoneme -> PCM sample-exact vs C (10 voices)** |
| `lts/` letter-to-sound rules (`ls_rule*`, `ls_adju*`, `l_us_ad1`) | `lts_rules.py` | **pre-`ph/` stream exact vs oracle for out-of-dictionary alphabetic words (188/189 rule-eligible)** |
| `lts/` rule/prefix/feature tables (`acna_lswtab`, `acna_lsbtab`, `feats`, `pfeat`, `preftab`, `ls_fold`) | `lts_rules_data.py` | read verbatim from `libtts_us.so` |
| text -> phonemes -> PCM wiring (lone word) | `text_us.py` | **sample-exact vs oracle WAV (dict + rule, 10 voices)** |
| sentence front end: clause split, framing, terminators (`cmd/`, `ls_task.c`) | `sentence_us.py` | **whole-sentence text -> PCM sample-exact vs oracle (plain statements, comma lists, speller; 10 voices)** |
| digit-path number / currency / ordinal / decimal reading (`l_us_pr1.c` `ls_proc_do_number`/`ls_proc_do_digit_group`, `ls_task.c` currency, `l_us_con.c` phone lists) | `numbers_us.py` | **pre-`ph/` stream + text -> PCM bit-exact vs oracle (integers, `$`, ordinals, decimals; 10 voices); four-digit year-pairs not read** |
| vowelless-word speller + letter-name table (`ls_spel.c`, `l_us_spe.c`) | `spell_us.py` | **pre-`ph/` stream + PCM bit-exact vs oracle** |
| abbreviation table (`l_us_con.c`) | `sentence_us.py` | word sequence matches oracle; framing bit-exact where the word markers suffice |
| word-level syntactic marking: form-class phrase markers, `sdic[]` closed class (`ls_dict.c`, `l_us_con.c`) | `grammar_us.py` | **VPSTART/PPSTART bit-exact vs oracle for dict verbs, preps, and `for`/`and`/`to`** |
| inflectional-suffix morphology (`ls_suff.c` `suffix_table`/`suffix_index`) | `morph_us.py`, `suffix_data.py` | **stem + suffix codes bit-exact vs oracle for plurals / `-ed` / `-ing` / possessive; text -> PCM sample-exact across ten voices** |
| in-context article reduction (`ls_task.c:2632-2645`) | `grammar_us.py` | **schwa article bit-exact vs oracle (framing + PCM, 10 voices)** |
| question-final restress; four-digit year-pairs; abbreviation title stress | — | **not ported** |

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

The synthesizer is proven in isolation: parameter frames are captured from the C
oracle and `vtm.py` is replayed over them, so no prosody (`ph/`) is dragged in.

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

- **The in-context article reduction is ported** (`grammar_us.article_a_codes`,
  `ls_task.c:2632-2645`): the single-character word `a` reduces to a schwa
  mid-clause and keeps the citation `[S1 EY]` clause-finally. What remains of
  function-word reduction is the clause-final re-stress of a lone `for`/`to`/
  `and`, driven by the `ph_sort.c:1116` kludge (`allophones.py`); where the port
  feeds the correct markers this is already PCM-exact.
- **Question-final content-word restress** (`what is *that*`): the clause-final
  content word takes primary stress in a question; being ported on a sibling
  branch (`ph_sort.c` / `allophones.py`).
- **Inflectional morphology** (`dogs -> dog + s`, `-ed`/`-ing`/`-s`/possessive).
  The `ls_suff.c` suffix trie is not extracted; an inflected miss is pronounced
  by the letter-to-sound rules, which is usually right but not always bit-exact.
- **The digit-path number / currency reading is ported**
  (`numbers_us.number_token_send_codes`, `l_us_pr1.c`/`l_us_con.c`): integers,
  ordinals, currency (`$5`, `$5.25`) and decimals frame and render bit-exact via
  the reader's own phone lists. The four-digit **year-pairs** reading (`1100` ->
  "eleven hundred") and multi-word abbreviation stress (`dr. smith`) remain.
- **Homograph / duplicate-grapheme selection.** Needs the part-of-speech pass;
  a hit returns the record the search lands on.
- **`[:phoneme on]` phonetic-input decoding** (`cmd/cm_phon.c`) and `[:dv]`,
  `[:pitch]`, `[:tone]`, DTMF command *effects* — `cmd.py` tokenizes and carries
  voice/rate/mode but does not decode phonetic input or resolve these.
- **Other languages** (uk/fr/gr/sp/la). US only.

## The letter-to-sound rule engine (`lts_rules.py`)

When a word misses the main dictionary, the compiled US front end pronounces it
with the letter-to-sound rules -- the ~117k-LOC bulk of `lts/`, almost all of it
rule **data**. `lts_rules.py` ports the interpreter and post-processing for the
compiled ACNA `ENGLISH_US` path:

- **`ls_rule_rule_match` / `ls_rule_env_match`** (`ls_rule.c`, `l_us_ru1.c`): the
  grapheme alphabet build (`ls_rule_add_graph`, the `gu`/`qu` merge, the `y`/sib/
  gem/syllable feature rules), the right-to-left largest-left-block rule match
  over the compiled rule dictionary, and the recursive environment matcher
  (`GRANGE`, `GDISJ`, `GFEAT`, morpheme/word boundaries). Rule entries carry an
  ACNA language tag; ordinary words run tag 0 (the default English rules), so the
  name-language identifier (`lsa_us.c`) is not needed.
- **`ls_adju_allo1` / `ls_adju_sylables` / geminate deletion / `ls_adju_stress`
  / `ls_adju_allo2`** (`ls_adju.c`, `l_us_ad1.c`): plural/`-ed` allophony,
  syllabification, geminate-pair deletion, the suffix/prefix/best-default stress
  placement (`preftab` stress-refusing prefixes, the Nessly and camera rules),
  and the final allophonic sweep (vowel reduction, `l`/`r` velarization,
  palatalization).
- **`ls_rule_lts_out`**: assembles the phoneme+stress+boundary send stream.

The rule tables (`acna_lswtab`, `acna_lsbtab`, the grapheme feature set `feats`,
the phoneme feature set `pfeat`, the prefix table `preftab`, the case-fold
`ls_fold`) are read verbatim from the compiled `libtts_us.so` symbols by
`tools/dump_dectalk_lts_tables.py` into `lts_rules_data.py` -- guaranteed
identical to the reference, not retyped.

### Verification

The engine's output is captured at the **pre-`ph/` boundary** -- the raw `ph`
argument to `ls_util_send_phone`, instrumented in the oracle -- because the
public `LOG_PHONEMES` output folds in downstream `ph/` reductions (function-word
reduction, allophone substitution) that pollute the rule engine's own emission.
`test/dectalk_lts_rules_golden.json` is the committed real capture over 194
confirmed dictionary-miss words (nonsense words, names, technical terms), one
oracle process per word.

`test/test_dectalk_lts_rules.py` diffs `pronounce()` against that capture (runs
in CI without the oracle): **188 / 194 exact**. Five of the six differences are
vowelless or non-ASCII words (`cwm`, `cwtch`, `jwt`, `tsktsk`, ...) that the
oracle routes to its **speller** (letter-name code 111) -- a decision made in the
word-reading front end (`ls_task`), not the rule engine. Excluding those,
**188 / 189 rule-eligible words are exact**; the sole residual is `memoize`,
where the oracle splits `oi` as `o.ize` while the interpreter takes the `OY`
diphthong rule (correct for `void`, `boid`, ...).

### Full text-to-PCM (lone word)

`text_us.word_to_pcm` composes the whole US text-to-speech path for a single word
spoken with no markup: dictionary lookup or, on a miss, the rule engine, then the
`cmd/phsort` sentence framing for a lone statement word
(`[7680, 111, <font-shifted phonemes / raw prosody>, 116]`), then
`phclause.speak_phonemes` -> `vtm`. Diffed against the oracle WAV this is
**sample-exact** for both dictionary and out-of-dictionary words across all ten
voices (`test/test_dectalk_lts_rules.py`, oracle-gated:
10/10 OOD words at voice 0, 111 612/111 612 samples; verified dict+rule across
voices).

## The sentence front end (`sentence_us.py`)

`sentence_to_clauses` turns whole text into the per-clause `symbols[]` streams
the C hands to `phclause` -- the same pre-`ph/` boundary the lone-word path
targets, extended to sentences. It tokenizes text, splits it into clauses on
punctuation, frames each clause as `FONT, (WBOUND + word body)*, terminator`, and
closes each clause with the code that drives `phinton`'s clause-final intonation:

| Punctuation | Terminator | `phinton` |
|---|---|---|
| `,` `;` `:` | `COMMA` (115) | continuation rise, new clause |
| `.` or unpunctuated end | `PERIOD` (116) | declarative fall |
| `?` (yes/no) | `QUEST` (117) | question rise |
| `?` (wh-word) | `PERIOD` (116) | declarative fall |
| `!` | `EXCLAIM` (118) | exclamation |

A `?` clause opening with a wh-word (`what`, `why`, `who`, `how`, `where`,
`when`, `which`, `whose`, `whom`) reads with the falling `PERIOD` terminator, not
the `QUEST` rise (`ls_task.c` terminator selection); only a yes/no question keeps
`QUEST`. With that, wh-questions (`what is that?`, `who are you?`,
`what time is it?`, `where is it?`, `which way?`) render text -> PCM sample-exact
across all ten voices.

Each comma/period/question/exclaim opens a separate clause, exactly as the C
flushes one `symbols[]` per clause to `phclause`; F0 and `phsettar` state carry
across those clauses (`synthesize_clauses`, already ported). Before framing, a
numeric or currency token expands to words (`numbers_us.py`), a known abbreviation
expands from the table, and a token with no vowel is spelled letter by letter
(`spell_us.py`, whose per-letter phoneme streams are captured verbatim from the
oracle). Every produced word then runs through `text_us.word_to_codes` (dictionary
or rule) like a typed word.

The boundary marker emitted here is the plain `WBOUND` (111). The C's syntactic
parser instead promotes some boundaries to phrase markers and restresses function
words; that grammar layer is not ported (see *What is stubbed*), so the framing is
faithful for clauses the parser leaves at plain word boundaries.

### Verification

`tools/dump_dectalk_sentence.py` captures the oracle's per-clause `phclause` input
over a varied set (plain statements, comma/semicolon lists, a question, numbers,
an abbreviation, and vowelless speller words) into
`test/dectalk_sentence_golden.json`, recording only the texts the port reproduces
bit-exactly (27 of the set) so the gate bites on any framing regression.
`test/test_dectalk_sentence.py`:

- **CI-safe** (no oracle, no dictionary): clause splitting + terminators, the
  speller against its golden capture (4/4 bit-exact), and the number/abbreviation
  **word sequences** (`123 -> one hundred and twenty three`, `2005 -> two thousand
  and five`, `$5 -> five dollars`, `Dr. -> doctor`). A mutation of the terminator
  no longer matches the golden (`test_golden_gate_bites`).
- **dictionary-gated**: every golden text reframes bit-exactly to the oracle
  `symbols[]`.
- **oracle-gated**: whole-sentence **text -> PCM is sample-exact vs the oracle WAV
  across all ten voices** over plain statements, a comma list, and a spelled word
  (`test_sentence_text_to_pcm_all_voices`: 60/60 renders exact, ~1.03M samples).

### Measured coverage (voice 0, oracle diff over the sentence battery)

Before/after the in-context article reduction (`grammar_us.article_a_codes`) and
the digit-path number/currency reading (`numbers_us.number_token_send_codes`),
voice 0, over the original 56-text `test/test_dectalk_grammar.py` battery. The
`before` column is the state after the inflectional-suffix morphology
(`morph_us.py`); the `after` column is what the port reproduces today; the gate
is `test/dectalk_grammar_golden.json` (whose battery is extended to 71 unique
texts -- five new number/currency/decimal and article categories -- so both
mechanisms are exercised broadly).

| Category | framing before → after | text -> PCM before → after |
|---|---|---|
| plain multi-word statements | 12/12 → 12/12 | 12/12 → 12/12 |
| comma / semicolon lists | 4/4 → 4/4 | 4/4 → 4/4 |
| vowelless speller words | 4/4 → 4/4 | 4/4 → 4/4 |
| numbers | 6/9 → **9/9** | 6/9 → **9/9** |
| questions | 1/3 → 1/3 | 2/3 → 2/3 |
| abbreviations | 3/4 → **4/4** | 3/4 → **4/4** |
| dictionary verbs (VPSTART) | 4/4 → 4/4 | 4/4 → 4/4 |
| function words | 2/4 → **3/4** | 3/4 → **4/4** |
| conjunctions / preps (`and`/`for`) | 3/4 → **4/4** | 3/4 → **4/4** |
| inflection (plurals / `-ed` / `-ing`) | 8/8 → 8/8 | 8/8 → 8/8 |
| **total** | 47/56 → **53/56** | 49/56 → **56/56** |

The article reduction makes `that is a cat` and `a dog and a cat` framing- and
PCM-exact (the article `a` reduces to a schwa mid-clause); the digit path makes
`123`, `2005`, `$5` (and the whole extended number/currency/decimal battery)
bit-exact -- `$5` is closed by porting the real currency reader (its `pdollar`
vowel), as anticipated. The clause-head be-form `S2` (below) closes `are you
there` (the last question PCM miss), and the `Dr.`-title disambiguation
(`title_abbrev_us.py`, below) closes `dr. smith` -- the battery is now **56/56
text -> PCM sample-exact** across all ten voices. The three remaining
framing-only misses (`what is that`, `are you there`, `give it to me`)
are all PCM-exact via the ported `phsort` clause-final promotion / restress: the
symbol stream carries an `S2` where the oracle records an `S1` on a pronoun, and
`phsort` reconciles the two before the VTM.

### Clause-head be-form secondary stress

The reduced be-forms `is`/`are`/`was`/`were` open the dictionary with their
primary stress stripped (`is.` cites `[S1, IH, Z]`; the in-context form is the
bare `[IH, Z]`). At the head of the **sentence's first clause** the C keeps a
residual secondary stress on them -- `is it cold.` and `are you there?` both open
`[WBOUND, S2, ...]`, while a post-comma clause head (`no, is it cold?`) and the
auxiliaries `am`/`be`/`has`/`have`/`did`/`does`/`do` do not (verified against the
oracle across ten voices). `sentence_us._HEAD_STRESS_AUX`
(`sentence_us.py`, `_with_head_stress`) inserts the `S2` (`l_com_ph.h`) before
the word's first vowel, matching the C's citation-form demotion. This closes the
`is it cold?`/`are you there?`/`was it good?`/`were you here?`/`is she home?`/
`are they ready?` yes/no battery to text->PCM sample-exact across all ten voices.
The one framing residue (`are you there` keeps the pronoun `you` at `S2` where the
oracle raises it to `S1`) is the general nuclear-stress reassignment of the
unported `cmd/par_*.c` parser; it is PCM-exact, so it is a framing-only note.

### Wh-question terminator

A `?` clause opening with a wh-word takes the falling `PERIOD` terminator, not the
`QUEST` rise (see the terminator table above). With that one selection,
`what is that?`, `who are you?`, `what time is it?`, `where is it?` and
`which way?` render text -> PCM sample-exact across all ten voices;
`test/test_dectalk_question.py` gates it (terminator selection in CI, oracle-gated
PCM across the ten voices, and a mutation gate). The yes/no questions on a
`be`-form auxiliary (`are you there?`, `is it cold?`) are now closed by the
clause-head `S2` above (`test_yesno_aux_pcm_all_voices`, mutation-gated by
`test_gate_bites_without_head_aux_stress`); `do`/`can` yes/no questions already
rendered exact.

### `why` and the `y`-vowel speller decision

A token whose only vowel letter is `y` (`why`, `my`, `gym`, `rhythm`) must be
pronounced by the word layer, not letter-spelled: `ls_feat.tab` marks lowercase
`y` (`0x79`) and uppercase `Y` (`0x59`) as `CFEAT_cons+CFEAT_vowel`, so the
`IS_VOWEL` macro (`ls_char.h:62`) is true for it. `spell_us.is_spelled` previously
tested only `aeiou`, so `why` (dictionary `[W, S2, AY]`) was wrongly spelled
letter by letter. Adding `y` to `spell_us._VOWELS` makes `why not?` and the
`y`-word set text->PCM sample-exact across ten voices
(`test/test_dectalk_residual.py`, mutation-gated by
`test_gate_bites_without_y_vowel`). A token with no `a/e/i/o/u/y` (`pqr`, `tv`)
is still spelled.

### `dr. smith` -- closed (`Dr.`/`St.` title-abbreviation disambiguation)

`Dr.` and `St.` are context-disambiguated by the C: before a proper name they read
as the **destressed** title `doctor`/`saint` (oracle `pdoctor` `[D, AA, K, T, RR]`
-- no `S1`, `AA` vowel -- and `psaint` `[S, EY, N, T]`), elsewhere (`the dr. is in`)
as `drive`/`street` (`pdrive` `[D, R, S1, AY, V]`, `pstreet` `[S, T, R, S2, IY, T]`).
The four fixed phone lists live in `l_us_con.c:615-629`; the selection is
`ls_task_Dr_St_process` (`ls_task.c:2910`), **not** the general `cmd/par_*.c`
parser -- it is a self-contained lookahead over the one following word. The rule
(reached only when a `.` follows the abbreviation, `ls_task.c:2931`):

- the following word is capitalized and is not itself a back-to-back `Dr`/`St`
  (`ls_task.c:2944-2955`): **title**;
- the following word is capitalized but exactly `Dr`/`St` (`ls_task.c:2947`, the
  GL 1997 back-to-back fix): **word**;
- the following word is lowercase and the abbreviation is the sentence's first
  word (`cur_word_index == 1`, `ls_task.c:2961`): **title**;
- clause-final (no following word) or otherwise: **word**.

Only `Dr` and `St` have dedicated title symbols; `Mr`/`Mrs`/`Ms` expand through
the ordinary abbreviation table. `title_abbrev_us.py` ports the four phone lists
(trailing `SIL` dropped, as with the `sdic[]` entries) and the selection rule;
`sentence_us.py` emits the resolved title/word body for a `.`-terminated `dr`/`st`
instead of the full-word `doctor`/`saint` expansion. `dr. smith`, `st. john`,
`the dr. is in`, `doctor smith` (control) and `i saw dr. smith` are all
framing- and PCM-exact across ten voices (`test/test_dectalk_title.py`,
mutation-gated by `test_gate_bites_on_swapped_title_and_word`;
`test/test_dectalk_residual.py::test_dr_title_abbreviation_is_closed`).

The 53 framing-exact and 56 voice-0 PCM-exact texts are locked by
`test/dectalk_grammar_golden.json`; `test_pcm_exact_all_voices` verifies each
PCM-exact text stays sample-exact across all ten voices, and
`test_golden_gate_bites` verifies the gate bites. `test/test_dectalk_wordclass.py`
gates the morphology mechanism; `test/test_dectalk_funcword_numbers.py` gates the
two mechanisms here: the article schwa reduction and the digit-path phone lists
in CI (mutation-gated), and -- oracle-gated -- the article and number/currency
batteries text -> PCM sample-exact across the ten voices.

### Are these two mechanisms bit-exact?

**Yes, both.** The in-context article reduction and the digit-path number /
currency / ordinal / decimal reading are pre-`ph/` stream **and** whole-sentence
text -> PCM **sample-exact vs the oracle across all ten voices** for their whole
battery scope (integers of any length that decompose through the scale/`and`
reader, `$`/`$X.YY` currency, ordinals, decimals; the schwa article). They close
the `numbers`, `funcword` and `conj` battery categories to full PCM parity. The
one number shape not read the C's way is the four-digit **year-pairs** reading
(`1100` -> "eleven hundred", `2019` -> "twenty nineteen"), whose C dispatch is an
unreached path in this build (`ls_proc_do_4_digits` has no live caller); a plain
four-digit integer instead reads through the scale reader (`2005` -> "two
thousand and five", which the oracle also does).

### Full text-to-PCM through the public engine

`DECtalkEngine.synthesize(text, voice)` now renders plain text through this native
chain for the ten voices when the FONIX `dtalk_us.dic` is present (located via
`$DECTALK_DIR` or the built oracle `dist/`), falling back to the MacinTalk
substitute voices when it is not (as in CI). For the bit-exact scope the returned
bytes equal the oracle WAV PCM exactly.

## The word-level syntactic marking (`grammar_us.py`)

The premise that a syntactic **parser** stands between text and the phoneme
stream turns out to be wrong for the compiled US path. `cmd/par_*.c` is a
character-level text preprocessor (digit ranges, ambiguous characters), not a
POS parser, and the phrase-marker names (`PPSTART`/`VPSTART`/`RELSTART`) appear
nowhere in the compiled tree. The markers `phclause` reads are produced entirely
in the **word-reading path**, one word at a time:

- **Dictionary form class** (`ls_dict.c:759-763`). A hit's stored 32-bit
  form-class field (`include/fc_def.tab`; the compiled path's `DICT_FC_ACCESS`
  is the identity) gates two markers: `PPSTART` when `(fc & PPHRASE) == PPHRASE`
  (`PPHRASE = FC_PREP|FC_CHARACTER`) and `VPSTART` when `(fc & VPHRASE) ==
  VPHRASE` or `fc == FC_VERB` (`VPHRASE = FC_VERB|FC_CHARACTER`, `ls_defs.h:658`).
  So `sing` (`0x20000`, exactly `FC_VERB`) and `went` (`0x2020000`, `VPHRASE`)
  get `VPSTART`; `walk`/`run` (`FC_VERB|FC_NOUN`) do not.
- **The closed-class mini-dictionary `sdic[]`** (`l_us_con.c:1157`, searched
  before the main dictionary by `ls_task_minidic_search`). `for`/`and`/`to` are
  pronounced from a `PPSTART`-led fixed list, carrying a prep-phrase marker and
  their reduced pronunciation.

`grammar_us.word_markers` reproduces both; `sentence_us` emits the returned
markers ahead of each word's phonemes (the verb marker replacing the plain
boundary, exactly as the `ph_task.c:870-897` collapse does). The reduced `sdic`
phonemes for `for`/`and`/`to` are the values the oracle emits, matching
`l_all_ph.h`.

The stress edits above this -- the clause-final function-word promotion
(`ph_sort.c:1116`) and the general reductions -- run inside `phclause`'s `phsort`
stage (`allophones.py`), so where the port feeds the correct pre-`phsort`
markers, the PCM is already sample-exact even when the captured (post-`phsort`)
`symbols[]` differ by that promotion (e.g. `what is that`, `are you there`,
`give it to me`, `went` are PCM-exact despite a framing diff on a function word).

## The inflectional-suffix morphology (`morph_us.py`)

When a word misses the main dictionary, `ls_dict_find_word` (`ls_dict.c:450-458`)
tries `ls_suff_suffix_find` (`ls_suff.c`) before the letter-to-sound rules, for
any word longer than two letters. That routine walks a compiled trie -- the
`suffix_index` head (one byte offset per case-folded search letter) and the
`suffix_table` of `struct suff_rule {U32 next; U32 fc; unsigned char rule[]}`
(`ls_dict.h:86`), both extracted verbatim from `libtts_us.so` into
`suffix_data.py` by `tools/dump_dectalk_suffix.py`. A rule matches the word's
trailing letters, optionally rewrites the tail (`-ies -> -y`, doubled consonant,
silent `-e`), looks the stem up in the main dictionary, and on a hit appends the
suffix's own phonemes (`ls_suff_append_pron`), choosing among the rule's
`SF_PHONES` fields by a `pfeat` feature test on the stem's last phoneme. For the
`-s` rule this yields `IX Z` after a sibilant stem, `S` after a voiceless stem,
and `Z` otherwise -- `dogs -> dog + Z`, `cats -> cat + S`, `boxes -> box + IX Z`.
`morph_us.py` ports both routines exactly; `text_us.word_to_codes` routes a
dictionary miss through it before the rule engine, as the C does. The stem lookup
re-enters the same `Dictionary`; a stem miss falls through to the rules.

### Is full US DECtalk text-to-speech parity reached?

**YES -- the general running-text battery is now 56/56 text -> PCM sample-exact
across all ten voices.** Every text is whole-sentence text -> PCM **sample-exact
vs the oracle across all ten voices**: plain statements, comma/semicolon lists,
spelled words, dictionary-verb sentences, `for`/`and`/`to` conjunction/prep
sentences, **inflected words (plurals, `-ed`, `-ing`, possessive)**, **the schwa
article `a`**, **digit-path numbers / currency / ordinals / decimals**,
**wh-questions**, **yes/no questions on a `be`-form auxiliary**, **`y`-vowel words
(`why`)**, and **the `Dr.`/`St.` title-abbreviation disambiguation (`dr. smith`)**.
This pass closed the last of the three residuals named earlier -- the `Dr.`-title
reading -- after the clause-head be-form `S2` (yes/no `is it cold?`/`are you
there?`) and the `y`-vowel speller decision (`why not?`).

`dr. smith` was closed by porting `ls_task_Dr_St_process` (`ls_task.c:2910`) and
the four `l_us_con.c:615-629` phone lists into `title_abbrev_us.py`: the
disambiguation is a self-contained one-word lookahead, **not** the general
`cmd/par_*.c` parser. Framing carries three PCM-exact-only misses (`what is that`,
`are you there`, `give it to me`) where the symbol stream holds an `S2` the
oracle records as `S1` on a pronoun and `phsort` reconciles before the VTM; those
are the unported nuclear-stress reassignment of `cmd/par_*.c`, framing-only. **Full
US DECtalk text -> speech parity for the running-text battery is reached (56/56
PCM across ten voices).**

## The in-context article reduction (`grammar_us.article_a_codes`)

The single-character word `a` has two readings (`ls_task.c:2632-2645`): the
dictionary citation spelling `['e]` = `[S1, EY]`, used when it sits against
punctuation or the input end, and the reduced article `[SPECIALWORD, US_AX]`
(form class `FC_ART`), used when the next item is whitespace -- another word
follows before any punctuation. `article_a_codes` returns the reduced schwa body
for a non-clause-final `a` and None (keep citation) otherwise; `sentence_us`
splices it. `phsort` (`ph_sort.c:1024`, `allophones.py:672`) deletes the
`SPECIALWORD`, so the post-`phsort` body the oracle emits -- and the body spliced
here -- is the bare `US_AX`. This makes `that is a cat` and `a dog and a cat`
framing- and PCM-exact; a lone `a` (or `the a`) keeps the citation `[S1, EY]`.

## The digit-path number / currency reading (`numbers_us.number_token_send_codes`)

A digit token is read by the digit path (`ls_proc_do_number`,
`ls_proc_do_digit_group`, `l_us_pr1.c`; the currency wrapper in `ls_task.c`) by
shipping fixed phoneme+marker lists (`l_us_con.c`) straight into the phone
stream, not by expanding to words and re-looking-them-up. Two of those lists
diverge from the dictionary and are why the word path could not be bit-exact: the
hundreds/scale `and` (`pand`) carries a `VPSTART` and the vowel `EH` (not the
closed-class `sdic` `and`), and currency `dollar(s)` (`pdollar`) uses the vowel
`AA` with no schwa (not the dictionary stem). `number_token_send_codes` ports the
right-justified three-digit-group integer reader (with the `VPSTART` / `pand` /
comma scale connectors), the ordinal (`pordin`), currency (`$X`, `$X.YY` ->
`... dollars and ... cents`) and decimal (`ppoint`) paths, over the phone lists
transcribed verbatim from `l_us_con.c`. `sentence_us` emits its raw code stream
for a numeric token in place of the word layer. This makes `123`, `2005`, `$5`,
`$5.25` and the number/currency/decimal battery bit-exact. The four-digit
year-pairs reading (`1100` -> "eleven hundred") is not reproduced: its C
dispatch (`ls_proc_do_4_digits`) has no live caller in this build, so a plain
four-digit integer reads through the scale reader instead.

**One mechanism remains** for the general battery, isolated to its C site: the
**question-final content-word restress** -- under a `?` terminal the final content
word is restressed `S2 -> S1` (`ph_sort.c:1316` question flag `cbsymbol`, feeding
`phinton`). It affects `what is that` (PCM-exact, framing diff) and `are you
there`, and is being ported on a sibling branch. The abbreviation title stress
(`dr. smith`) also remains.

## The phoneme -> PCM chain composes (sample-exact, 10 voices)

`phclause.speak_phonemes(voice, clauses)` (`phclause.py`, reproducing
`phclause`, `ph_claus.c:200`) runs the entire `ph/` chain in Python and returns
11025 Hz PCM:

    phsort -> phalloph -> us_phtiming -> phinton -> [pht0draw / phdraw / send_pars per frame] -> vtm

Its input is one `symbols[]` (phoneme + stress + sentence-structure) stream per
clause -- the `lts/`/`cmd/` output, captured from the oracle at the `phclause`
input boundary (`DECTALK_SORT_DUMP`) for now. Every downstream stage runs in the
port; nothing is borrowed. It composes the individually bit-exact stages
(`allophones.py`, `timing.py`, `intonation.py`, `phsettar.py`, `ph.py`,
`vtm.py`) following `ph_claus.c`'s order and per-frame glue.

**Result: 130/130 cases sample-exact, 3 209 910 / 3 209 910 samples**, over all
ten voices and thirteen utterances (statements, questions, multi-clause,
fricative/plosive clusters, nasals, flapping, function words, plosive-final).
`test/test_dectalk_phoneme_pcm.py` drives it against the oracle WAV; the golden
gate `test/dectalk_phoneme_pcm_golden` + `test/test_dectalk_phoneme_pcm_golden.py`
locks it from a real capture of ten `symbols[]` vectors (2 501 330 samples, ten
voices), runs in CI without the oracle, and is verified to bite on an
`f0minimum` speaker mutation.

### The glue and the cross-stage subtleties

The chain is pure integration -- no new porting -- but three cross-stage
contracts had to be matched:

- **`phinton` lengthens the stream.** `phinton` inserts a reduced vowel after a
  clause-final plosive *after* `us_phtiming` runs, so the stream reaching
  `phsettar`/`pht0draw` is longer than the timing stage's output. The compose
  order runs `phinton` before the per-frame loop and drives the loop over its
  (longer) output.
- **F0 and `phsettar` state persist across clauses.** A multi-clause utterance is
  driven through **one** `Pht0draw` (the F0 `beginfall`/filter/glottalization
  state carries; first clause seeds `nf0ev = -2`, the rest `-1`) and **one**
  `PhsettarState` and `send_pars` delay buffer. The `PARAMETER` array
  (this phone's `tarend` -> next phone's `tarlas`), the `breathysw` flag, and the
  previous frame's drawn TILT all carry across the clause boundary exactly as the
  C `pDph_t` does; resetting any of them per clause diverges at the next clause's
  GEN_SIL onset (whose forward TILT rule reads the prior frame's tilt).
- **`parstochip[OUT_PH]` tracks the F0 segment pointer, not the audio phone.**
  The only vtm use of the phone code is the limit-cycle silence rampdown
  (`vtm.py:425`, `PH & PVALUE == 0` for GEN_SIL). The phone code the vtm reads is
  drawn from `pht0draw`'s segment pointer `np_drawt0` -- which advances with its
  own `extrad` plosive/voiceless offsets -- not from the main-loop audio phone
  index; the two differ by a few frames around each boundary. Feeding the audio
  phone index instead mis-times the GEN_SIL rampdown by a frame and cascades
  hundreds of PCM samples.

The speaker-definition scalars the chain reads (`malfem`; the `phdraw` offsets
`spdefb1off`/`f0_dep_tilt`/`spdeftltoff`/`spdeflaxprcnt`; the F0 scalars
`f0basefall`/`f0_lp_filter`/`f0minimum`/`f0scalefac`/`size_hat_rise`/
`scale_str_rise`/`assertiveness`) are resolved by the unported Phase-3
`ph/p_us_vdf*.c` (setspdef) layer. They are constant per voice; `PH_SPEAKERS`
holds them captured verbatim from one oracle run per voice, exactly as
`voices.SPEAKERS` holds the resolved `vtm` speaker state. Variable Val (9)
resolves to Perfect Paul (0). The intonation question flag `cbsymbol` is the one
per-clause input beyond the stream: it is 1 for a question clause
(`phsort` clausetype `QUESTION`), 0 otherwise.

No new latent cross-stage bug surfaced during composition (the `ldspdef`
BOOL-is-`unsigned char` defect was already found and fixed on an earlier compose
test); the `np_drawt0`/audio-phone split above is a documented data contract, not
a bug.

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
  (`timing.py`, `allophones.py`, `intonation.py`), and `phclause.py` composes
  them with `phsettar`/`ph`/`vtm` into a **sample-exact phoneme -> PCM chain**
  (see above). What remains for a self-contained DECtalk is only the text front
  layer (`lts/` letter-to-sound rules, numbers, homographs, `cmd/` markup
  effects), which turns text into the `symbols[]` phoneme stream `phclause`
  consumes.
- **Speaker-definition scalars are captured, not resolved.** `phclause.PH_SPEAKERS`
  holds the per-voice `ph/`-layer speaker scalars (`malfem`, the `phdraw` offsets,
  the F0 scalars) captured from the oracle, because the `ph/p_us_vdf*.c`
  (setspdef) resolution of the high-level `[:dv]` voice definitions is Phase 3 and
  unported. A new `[:dv]` custom voice would need those scalars resolved, not
  looked up.
- **No text input.** The `cmd/` -> `lts/` chain that turns text and `[: ]` markup
  into the `symbols[]` phoneme stream is unported (LTS rules, numbers,
  homographs). `phclause` takes that stream; `engine.py` takes frames. Driving
  either from text still requires the front layer (Phase 6) or, as the tests do,
  replaying the `symbols[]` stream captured from the oracle. This is the single
  biggest remaining obstacle to a self-contained DECtalk.
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

## Multilingual (UK / gr / fr / sp / la)

DECtalk ships six front ends. The US port above is complete; the other five
(British English `uk`, German `gr`, Castilian Spanish `sp`, Latin-American
Spanish `la`, French `fr`) reuse the *shared* lower layers and diverge only in
the language-specific data. This section records the parameterization seam and
the measured UK delta; UK is Phase 1 of the five-language program.

### What is shared vs per-language (from the C)

The compiled multilanguage build (`dtalkml/src/dtalk_ml.c:379`) dlopens
`libtts_<lang>.so` and, inside it, tags every phoneme with a per-language *font
byte* (`include/l_all_ph.h`: `PFUSA 0x1E`, `PFUK 0x1D`, `PFGR 0x1C`,
`PFSP 0x1B`, `PFLA 0x1A`, `PFFR 0x19`) so a phoneme code is `(font << 8) | index`.

- **Shared, must not regress** (one code path, language macros only): the `vtm/`
  synthesizer (`VTM1`), the `phdraw` frame loop (`ph_draw.c`), the clause
  orchestrator (`ph_claus.c`), and `send_pars`. The port keeps these in the
  language-agnostic modules (`vtm.py`, `ph.py`, `phclause.py`, ...).
- **Per-language**: the phoneme render/parse alphabet (`<lang>_arpa[]`,
  `<lang>_phon.tab`), the dictionary (`dtalk_<lang>.dic`), the LTS rules
  (`lts/l_<lang>_*`), and the whole `ph/` target layer -- ROM (`p_<lang>_rom.c`),
  gettar (`p_uk_st1.c` `uk_gettar` vs `p_us_st0.c` `us_gettar`), locus/transitions
  (`p_<lang>_sr1.c`), syllabification (`p_<lang>_sy1.c`), timing (`p_<lang>_tim.c`),
  and the voice-definition / intonation tunes (`p_<lang>_vdf*.c`).

### The language-parameterization seam

`pyretrotts/dectalk/language.py` is the selector: a `Language` enum keys a
frozen `LanguageProfile` naming the font byte, the phoneme inventory
(`phoneme_names`/`phoneme_codes`), the ARPABET render table (`arpa_pairs`), and
the `LOG_PHONEMES` language tag. US is registered from the existing `lts` module
tables verbatim, so the US path is byte-identical (its goldens do not move); UK
is registered from `pyretrotts/dectalk/uk_phonemes.py`. Heavier per-language
data (dictionary, LTS rules, `ph/` ROM) attaches to the profile as it is ported.

### UK status (measured)

The UK oracle is driven by `tools/uksay.c` + `tools/dump_dectalk_uk.py`: the
stock `say` refuses `-l uk` (its `MultiLang` guard, `say.c:491`, is false on
Linux), so the harness calls `TextToSpeechStartLang("uk")` directly to dlopen
`libtts_uk.so`, renders to WAV, and captures the raw pre-`ph/` phoneme+stress
stream from the `DECTALK_LTS_DUMP` instrumentation of `ls_util_send_phone`
(`lts/ls_util.c`) -- the same instrumentation-boundary the US LTS port used.

- **Phoneme alphabet -- ported, bit-exact, gated** (`uk_phonemes.py`,
  `test/test_dectalk_uk_phonemes.py`, 8 tests). The UK inventory is 57 allophones
  (`UK_TOT_ALLOPHONES`), position-for-position identical to US 1..56 **except**
  index 29 (`UK_OH`, the RP LOT/CLOTH vowel, vs `US_RX`) and index 51
  (`UK_YR`/`UK_DX` alias vs `US_DX`); US also has 57..60 (`TZ/CZ/LY/RE`) with no
  UK counterpart. The `uk_arpa[]` render table differs from `usa_arpa[]` only at
  indices 25 (`y ` vs `yx`), 27 (`l ` vs `ll`), 29 (`oh` vs `rx`), 51 (`yr` vs
  `dx`). A committed real capture of 37 UK words
  (`test/dectalk_uk_lts_golden.json`) decodes 100% through the ported inventory;
  the render round-trip and an arpa-mutation gate bite.
- **UK non-rhoticity is realized downstream, not in the inventory.** The centring
  vowels `IR/ER/AR/OR/UR` (19..23) and the NURSE vowel `RR` (15) share their US
  codes; the post-vocalic `R` (26) the UK dictionary/LTS still emit
  (`water` -> `w ao t ax r`, raw) is dropped by the shared `ph/` reduction, so
  `car` reaches `phclause` as `k aa` (49, S1, 6) with no `r`. Verified against the
  oracle.
- **UK intonation/timing differ.** The oracle's per-clause `T` line for UK voice 0
  is `200 160 19114 17749 ...` vs US `180 180 18245 17314 ...` -- the UK
  `p_uk_vdf_tune*.c` / `p_uk_tim.c` layer, distinct from US.
- **UK `ph/` target ROM -- extracted verbatim, gated** (`targets_uk.py`,
  `targets_transitions_uk.py`, `tools/dump_dectalk_uk_targets.py`). The per-phoneme
  Klatt target ROM of `p_uk_rom.c` (`uk_maltar`/`uk_femtar` 7x57, `uk_maldip` 432,
  `uk_femdip` 366, `uk_malamp`/`uk_femamp` 542, `uk_place`/`uk_begtyp`/`uk_endtyp`/
  `uk_ptram` 57, `uk_featb` 101 shorts, and the transition ROM `uk_maleloc`/
  `uk_femloc` 866, `uk_plocu` 228, `uk_inhdr`/`uk_burdr` 57) is read from the built
  `libtts_uk.so` symbols at their resolved addresses -- guaranteed identical to the
  compiled reference, cross-checked against the ELF symbol sizes. `parini`,
  `partyp`, `divtab`, `lineartilt` are language-shared and reused from
  `targets.py`/`targets_transitions.py`.
- **UK `uk_gettar` -- ported under the language seam** (`settar_uk.py`,
  `test/test_dectalk_uk_targets_golden.py`, 7 tests). `uk_gettar` (`p_uk_st1.c:76`)
  is a faithful line-by-line port of the UK target-lookup, indexing `targets_uk.py`,
  differing from `us_gettar` exactly where the C does: no `-1` fallback chain for
  the formant params (`p_uk_st1.c:100-108`); the unstressed `-4` reduction applies
  to both AV and AP (`:198-204`); `[h]` aspiration 50/52 not 53/60 (`:184-192`);
  TILT `+10` for `[ow]` (`:296`). `language.LanguageProfile.gettar` selects it by
  language: US routes through `settar.us_gettar` unchanged (its goldens do not
  move), UK through `settar_uk.uk_gettar`, mirroring the C `all_gettar[font]`
  dispatch (`ph_setar.c:351`, `all_gettar[0x1D] == uk_gettar`). The UK oracle
  carries no isolated `gettar`/target dump (`DECTALK_TAR_DUMP` exists only in
  `libtts_us.so`), so `uk_gettar` is guarded by a deterministic regression digest
  over synthetic streams (mutation-biting) over the byte-exact ROM; the
  call-for-call oracle proof arrives with the UK `phsettar` port below, gated via
  `DECTALK_PHS_DUMP` (compiled into `libtts_uk.so`, verified present).

### What remains for full UK (and what gr/fr/sp/la will each need)

UK **phoneme -> PCM is not yet bit-exact**: it cannot route through the US `ph/`
chain, because UK has its own target ROM (`p_uk_rom.c`), its own `uk_gettar`
(`p_uk_st1.c`), its own locus/syllable/timing (`p_uk_sr1.c`, `p_uk_sy1.c`,
`p_uk_tim.c`), and its own voice/intonation tunes (`p_uk_vdf*.c`). Porting UK to
the US 56/56 standard therefore requires, in order:

1. extract the UK `ph/` ROMs from `libtts_uk.so` (a dumper like the US
   `tools/dump_dectalk_targets.py`), then port `uk_gettar` + the UK `phsettar`
   path and UK timing/intonation, gating phoneme -> PCM against the UK oracle.
   **Done so far:** the ROM extraction (`targets_uk.py`, `targets_transitions_uk.py`),
   `uk_gettar` (`settar_uk.py`), and the UK `phsettar` smooth/coartic rules
   (`phsettar_uk.py`) under the language seam. The UK `phsettar` port
   (`uk_forw_smooth_rules` `p_uk_st1.c:446`, `uk_back_smooth_rules` `:834`,
   `uk_special_rules` `:1240`, `UKP_special_coartic` `:305`) is gated against the
   live `libtts_uk.so` `DECTALK_PHS_DUMP` over 8 voices x 6 utterances
   (`test/test_dectalk_uk_phsettar.py`): **all 166144 interior (non-`GEN_SIL`)
   audio-relevant `PARAMETER` fields are bit-exact.** Font-dispatch findings that
   were load-bearing: the shared `ph/` accessors and the smooth-rule/gettar
   dispatch select tables/rules by the phone's font byte, so the boundary
   `GEN_SIL` (US font `0x1E00`) runs the *US* smooth rules and `us_gettar`; and the
   current build's `make_dip`/`getendtar` special_coartic dispatch has no `PFUK`
   branch, so `UKP_special_coartic` is compiled-in-but-never-invoked for UK
   (ported for fidelity, documented inert). The `GEN_SIL` boundary TILT target/
   transition depends on `parstochip[OUT_TLT]` (the previous drawn frame) and is
   validated at the end-to-end PCM stage, not the phone-by-phone `phsettar` gate.
   **Progress toward phoneme -> PCM:**
   - **UK timing -- ported, bit-exact, gated** (`timing_uk.uk_phtiming`,
     `p_uk_tim.c:107`; `test/test_dectalk_uk_timing.py`). It is the UK-parameterized
     analogue of `timing.us_phtiming` (the US path is unchanged and its goldens do
     not move). Every delta vs US was verified against `p_uk_tim.c`: the
     `LANG_british` `init_timing` (+20 rate, `sprat0 -= 40` floor 65, so `-r 180`
     runs at effective 200 with `sprat0 = 160`, `timeref 80`, `sprat1 19114`,
     `sprat2 17749`), `GEN_SIL` pause `4/5` with floor 2 and the
     `feanex & (FVOICD | FOBST)` gate, Rule 2 `number_words >= 4` with `[LX]` only,
     the nasal-lengthening rules, the Rule 7 `durmin < 6` floor, Rule 6
     `>= FWBNEXT`, the Rule 9 nasal `N70PRCNT` and `arg1 < 500 -> 4196` clamp, the
     Rule 13 plosive-plosive guard and `N120PRCNT` nasal, the voiced/voiceless
     plosive rule, Rule 18 (`FSONCON`), Rule 17 `prcnt += 10`, dropped Rule 20, Rule
     23 gated `prcnt > 50` with `N40PRCNT`, the `[RR]` `durmin` floor 13, Rule 25
     (`N130PRCNT`), the word-initial `[HX]` Rule 26, the absolute stop-`durmin`
     floors 6/6/14, and the stressed-syllabic sonorant time-alignment pass. `nfcomma`
     14 / `nfperiod` 94 (`ph_claus.c:229`) and `uk_mindur` (`p_uk_rom.c:142`) are UK.
     Gating caveat solved: `DECTALK_TIM_DUMP` is `p_us_tim0.c`-only, so a UK timing
     dump (`DECTALK_UKTIM_DUMP`) was added to `p_uk_tim.c` in the instrumented build
     copy and `libtts_uk.so` rebuilt (`ph_timng.o` -> relink). It dumps the entry
     `allophons`/`allofeats`/rate factors/`number_words` and the exit `allodurs`.
     Result: **72 clauses / 1360 durations bit-exact across the 8 UK voices**; a
     committed real-capture golden (`dectalk_uk_timing_vectors.json`) re-checks it in
     CI without the oracle, mutation-verified to bite. `LanguageProfile` gains
     `phtiming`/`nfcomma`/`nfperiod`, selecting `uk_phtiming` by language.
   - **UK per-voice scalars -- measured** (`phclause.PH_SPEAKERS_UK`,
     `test/test_dectalk_uk_speakers.py`). UK ships **8** voices. The five `phdraw`
     scalars (`malfem`, `spdefb1off`, `f0_dep_tilt`, `spdeftltoff`, `spdeflaxprcnt`)
     are captured from the oracle (`DECTALK_PH_DUMP` E-line + `PHS_DUMP` A-line
     `malfem`) and are **byte-identical to US voices 0..7** -- the `[:dv]` speaker
     definitions are language-independent. The seven F0 scalars come from that same
     shared speaker-def resolution.
   - **UK intonation -- NOT language-shared (scope correction).** The earlier note
     that `phinton`/`pht0draw` are shared is **wrong** per the C: `ph_inton0.c` and
     `ph_drwt01.c` each carry a **separate `#ifdef ENGLISH_UK` function body**
     (`phinton` at `ph_inton0.c:154` under `#if defined NWSNOAA || defined
     ENGLISH_UK`, vs the US `phinton` at `:1327` in the `#else`; likewise `pht0draw`
     at `ph_drwt01.c:277` vs `:2383`), and `ph_draw.c` has further `ENGLISH_UK`
     conditionals. So UK **phinton + pht0draw are a separate rule port** (~1000 and
     ~2000 lines), not a reuse of `intonation.py`. This is the remaining blocker for
     end-to-end UK phoneme -> PCM. `phalloph` also has UK deltas
     (`ph_aloph1.c`/`ph_aloph2.c`, `ENGLISH_UK`), though `phsort` has none.
   Until the UK `phinton`/`pht0draw` rule bodies are ported and the end-to-end
   `DECTALK_VTM_DUMP` gate closes, UK **phoneme -> PCM is not yet bit-exact**;
   `phclause` is deliberately left US-only (wiring `phsettar_uk` + `uk_phtiming`
   alone still lacks the UK F0 contour);
2. load `dtalk_uk.dic` (the loader is shared) and port the UK LTS rules
   (`lts/l_uk_ru1.c`/`l_uk_rta.c`/`l_uk_suf*.c`/`l_uk_ad1.c`), gating the pre-`ph/`
   stream against the `DECTALK_LTS_DUMP` capture;
3. UK number/abbreviation reading (`l_uk_pr1.c`/`l_uk_con.c`) and the UK sentence
   front end, then text -> PCM across the UK voices.

Each of **gr/fr/sp/la** needs the identical five-part port against its own font
byte, `libtts_<lang>.so`, and `dtalk_<lang>.dic`: (a) the phoneme alphabet
(`<lang>_phon.tab`, one `<lang>_phonemes.py` + profile registration -- cheap,
like UK here), (b) the `ph/` ROM + gettar + timing + intonation
(`p_<lang>_*` -- the expensive part, structurally like the US `settar`/`phsettar`
port), (c) the dictionary, (d) the LTS rules, (e) numbers/abbreviations and the
sentence front end. The shared `vtm`/`phdraw`/`phclause` and the `tools/uksay.c`
capture harness (which already takes any `-l <lang>`) are reused unchanged.
