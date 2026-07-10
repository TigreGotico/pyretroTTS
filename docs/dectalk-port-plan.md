# Porting the real DECtalk engine to Python

`pyretrotts` today is a bit-exact port of Apple **MacinTalk 2/3**, whose C
reference lives in `../lintalker-c` (repo `dectalk/lintalker`). Despite the
directory name, that source is *not* DECtalk. This document plans a **second,
independent engine** in the same repo: the genuine DECtalk from
[`dectalk/dectalk`](https://github.com/dectalk/dectalk), sitting beside the
MacinTalk port as a sibling class.

All C file:line references below are to a read-only checkout of `dectalk/dectalk`
at `/home/miro/AgentWorkspaces/ovos/dectalk` (commit `f2ef8f6`). Paths are given
relative to `src/dapi/src/` unless noted.

---

## 1. What DECtalk actually is here

`dectalk/dectalk` is the Fonix/Force release of DEC's DECtalk 4.x/5.x software
TTS. It is a large, multi-language, multi-platform C codebase — roughly **479 000
lines** of `.c`/`.h` across `src/` — of which the speech engine proper is
`src/dapi/src/` (~536 000 counted lines including headers and the many alternate
voice-data files). The engine is organized as a pipeline of threads communicating
over pipes, unlike MacinTalk's single call chain.

### The engine's major C subsystems

| Subsystem | Dir | Approx LOC | Role |
|---|---|---|---|
| Command / text parser | `cmd/` | 108 000 | Tokenizes text, parses `[: ]` commands and `[phoneme<...>]` phonemic input, number/abbreviation expansion, dispatches to LTS |
| Letter-to-sound | `lts/` | 130 000 | Dictionary lookup + rule-based grapheme→phoneme for US/UK/GR/SP/LA/FR |
| Phonetics / prosody / synth driver | `ph/` | 170 000 | Allophone selection, duration rules (`p_*_tim.c`), intonation/F0 (`ph_inton*.c`), the frame drawer (`ph_drwt*.c`), per-voice definitions (`p_*_vdf*.c`) |
| Vocal-tract model (the synthesizer) | `vtm/` | 26 000 | The **Klatt formant synthesizer** — cascade/parallel resonators |
| Public API | `api/` | 16 000 | `TextToSpeechStartup`, `…Speak`, `…OpenInMemory`, etc. |
| Dictionaries (source) | `dic/` | — | `Dic_us.txt` (15 537 lines) and per-year/­per-language variants, compiled to a binary trie |

### The synthesizer: KlattSyn

`vtm/vtm.c` and `vtm/vtm_f.c` carry `Copyright (c) 1984 by Dennis H. Klatt`. This
is the classic **Klatt cascade/parallel formant synthesizer** (KLSYN), driven at
frame rate. `vtm/vtm_f.c:134-175` documents its controls: F1–F3 formant
frequency/bandwidth in Hz, cascade F4/F5, parallel resonators, frication/
aspiration/voicing gains. `NSAMP_FRAME` is 64 samples/frame (`ph_task.c:1285`);
`mstofr()` (`ph_task.c:1290`) converts ms→frames as `ms*10>>6`. There is also an
optional **HLsyn** high-level articulatory front end (`hlsyn/`), off by default.

This matters because **MacinTalk 2/3 is itself a descendant of the same Klatt
lineage.** `pyretrotts/_backend.py` is a Klatt-style formant synthesizer with
fixed-point resonators. So the two engines share *heritage and math*, but not a
line of code — DECtalk's synth is float-capable (`FLTPNT_T`), frame-threaded, and
has 5 cascade formants + parallel branch + nasal pole/zero, where MacinTalk's is
the leaner fixed-point Mac variant.

### The dictionary and letter-to-sound

- **Dictionary**: `dic/Dic_us.txt` (15 537 lines) is the shipped US pronunciation
  dictionary in text form; `dic/dic_cnvt.c` + `lts/loaddict.c`/`ls_dict.c`/
  `maindict.c` compile and search it as a binary trie. MacinTalk's equivalent is
  `English.lex` → `pyretrotts/_lexicon.py`.
- **Letter-to-sound rules**: `lts/allorules.c`, `lts/l_us_*` and the `ph/p_us_*`
  rule files. MacinTalk's equivalent is `EngToP.c` → `pyretrotts/_engtop.py`.
  DECtalk's rule system is far larger and multi-language.

### Phoneme inventory vs MacinTalk

DECtalk's US phoneme set is defined in `include/l_us_ph.h:59-116` (57 codes,
`SIL`=0 … `DF`=56; `US_TOT_ALLOPHONES`=71 at line 119). MacinTalk's is
`pyretrotts/_phonemes.py` (75 enum values; 56 "core" phonemes `_IY_`.._DD_ plus
19 control/prosody markers).

Both are **ARPABET-derived** and overlap heavily — vowels `IY IH EH AE AA AH AO
UH AX ER EY AY OY AW OW UW YU IX`, r-colored `IR/XR(AR)/OR/UR`, and consonants
`w y r l m n NG f v TH DH s z SH ZH p b t d k g CH JH` appear in **both** sets.
Differences:

| | MacinTalk (`_phonemes.py`) | DECtalk (`l_us_ph.h`) |
|---|---|---|
| Ordering | `IY,IH,EH,AE,AA…` (enum from `mt4.h`) | `SIL,IY,IH,EY,EH,AE,AA,AY,AW…` — **different order/codes** |
| Liquid `l`/`ll` | `l`, `LX`, `EL` | `LL`(27), `LX`(30), `EL`(34), plus `RR`(15) syllabic-r vs `R`(26) |
| `h` | `h`(32) | `HX`(28) |
| Glottal/flaps | `TX,DX,QX,DD` | `DX`(51), `TX`(52), `Q`(53 glottal stop), `DZ`(35), `DF`(56) |
| Prosody markers | in the same enum (`Stress1`, `pRise`, `Comma`…) | **separate channel** — DECtalk carries stress/boundary as `symbols[]` flags and `[/] [\] [']` hat symbols, not phoneme codes |

**Bottom line:** the two engines share the ARPABET *concept* and Klatt synthesis
*heritage*, but their phoneme codes, orderings, allophone tables, dictionaries,
rule systems, prosody representation, and synthesizer code are all independent.
Treat the phoneme id spaces as **disjoint**; do not unify them.

---

## 2. THE KEY QUESTION — `phoneme<duration,pitch>`, definitively answered

For input like `weh<250,13>` the two numbers are:

> **First number = duration in milliseconds. Second number = a musical note index
> (1–37, C2–C5) when it is ≤ 37, or an absolute fundamental frequency in Hz when
> it is > 37.**

This is proven end-to-end by four code sites.

### 2a. The parser (`cmd/cm_phon.c`)

`cm_phon_param_check()` (`cmd/cm_phon.c:268-351`) consumes the `<…>` one char at a
time after a phoneme has been matched. Using the macros
`PUSH_PHONE = params[param_index++]` and `CURR_PHONE = params[param_index-1]`
(`cmd/cm_defs.h:109-110`):

- On `'<'` (`cm_phon.c:286-294`): pushes a new slot (`params[1]=0`).
- On a digit (`cm_phon.c:339-340`): `CURR_PHONE = CURR_PHONE*10 + (c-'0')` —
  accumulates a decimal integer into the current slot.
- On `','` (`cm_phon.c:306-323`): pushes the next slot (`params[2]=0`).
- On `'>'` (`cm_phon.c:324-328`): calls `cm_phon_flush()`.

So `weh<250,13>` yields `params[0]=<weh phoneme>`, `params[1]=250`, `params[2]=13`,
with `param_index==3`. `cm_phon_flush()` (`cm_phon.c:365-489`) sees
`param_index==3` (not `>3`, so it skips the bit-packed intonation branch at
`:380`) and writes `params[0..2]` straight down the LTS pipe. (The `>3` branch is
the newer, richer `<type,value,delay,syl,length>` form; the classic songs use the
2-value form.)

### 2b. Into the prosody state (`ph/ph_task.c`)

`ph_task.c:845-854` reads those pipe values back as `buf[0..2]` and stores:

```c
pDph_t->user_durs[pDph_t->nsymbtot] = buf[1];   // first number
if (nextra == 1) pDph_t->user_f0[...] = 0;
else             pDph_t->user_f0[pDph_t->nsymbtot] = buf[2];   // second number
```

So **`buf[1]` (first number) → `user_durs` and `buf[2]` (second number) →
`user_f0`.**

### 2c. First number is milliseconds

`user_durs` is treated as milliseconds everywhere it is consumed, e.g.
`p_gr_tim.c:229` / `p_la_tim.c:191`: `durxx = mstofr(user_durs[nphon] + 4)`, and
`mstofr()` (`ph_task.c:1290-1297`) converts **milliseconds → frames**
(`ms*10 >> 6`). The mode-detection comment block confirms it:
`ph_sort.c:1065` "If duration attached to phoneme, convert to frames." → the first
number is **ms**.

### 2d. Second number: note index (≤37) OR Hz (>37) — the conversion

`set_user_target()` (`ph/ph_drwt01.c:1955-1984`, duplicated in `ph_drwt02.c:2200+`)
is the consumer that turns `user_f0` into an F0 target:

```c
if (*psF0command >= 2000)   *psF0command -= 2000;   /* strip offset flag */
if (*psF0command <= 37) {                 /* <=37: musical note, C2..C5 */
    pDphsettar->newnote = notetab[*psF0command-1];   /* F0*10 Hz from table */
    pDphsettar->vibsw = 1;                            /* vibrato ON */
}
else {                                    /* >37: literal frequency in Hz */
    *psF0command *= 10;                    /* Hz -> internal Hz*10 units */
    if (*psF0command < LOWEST_F0)  *psF0command = LOWEST_F0;   /* 500 = 50.0 Hz */
    else if (*psF0command > HIGHEST_F0) *psF0command = HIGHEST_F0; /* 5121 = 512.1 Hz */
    pDphsettar->newnote = *psF0command;
    pDphsettar->vibsw = 0;                 /* vibrato OFF */
}
```

- **≤ 37 → musical note.** `notetab[]` (`ph/p_us_rom_1997.c:1188`, also
  `ph/p_us_rom_1996.c:1116`, `ph/ph_romi.c:106`; a disabled reference copy with
  full commentary at `ph/p_us_rom_dectalk_1996m_43f.c:810-851`) is labeled
  *"Notes in F0*10 from C2 to C5"*. Index **1 = C2 (64.0 Hz), 2 = C#2 (67.8 Hz),
  …, 13 = C3 (128.0 Hz), 25 = C4 (256.0 Hz), 37 = C5 (512.0 Hz)** — one entry per
  semitone, values stored as Hz×10. Vibrato of ±1.8 Hz at 6.5 Hz is added
  (`ph_sort.c:1069`).
- **> 37 → absolute Hz.** Multiplied by 10 into the internal Hz×10 unit and
  clamped to **50.0 – 512.1 Hz** (`LOWEST_F0`=500, `HIGHEST_F0`=5121;
  `ph_drwt01.c:195-196`). No vibrato.

The clause-level mode is chosen in `ph_sort.c:1050-1075`:

> Rule 3: first f0 command attached to a phoneme with value **≤ 37 → `f0mode =
> SINGING`**. Rule 4: value **> 37 → `f0mode = PHONE_TARGETS_SPECIFIED`**.

and the two modes are otherwise identical in `set_user_target`. In SINGING mode
the target is reached linearly over ~160 ms; in PHONE_TARGETS mode over the
phoneme's duration (`ph_sort.c:1063-1075`). Both are absolute F0 with **no speaker
pitch (spdef) scaling** (`ph_sort.c:1075`).

### 2e. Why the 1211-file corpus splits the way it does

- **1144 files use only values ≤ ~40** → these are **song files**: every note is a
  semitone index in the 1–37 (C2–C5) range, triggering SINGING mode with vibrato.
  This is the normal way to write DECtalk songs.
- **52 files mix in 100–1190** → those authors dropped **absolute Hz** targets
  (`PHONE_TARGETS_SPECIFIED`) for phonemes they wanted at a precise pitch, mixed
  among note-index phonemes. (Note: DECtalk clamps anything above 512 Hz down to
  512.1 Hz, so a written `1190` is heard as 512 Hz — the high values are authors
  over-reaching, not a different unit.)
- **None are exclusively large** → a whole clause of pure-Hz targets is rare
  because the note-index form is the idiomatic and range-safe way to sing; Hz is
  only reached for occasional spot corrections.

The boundary is **exactly 37** in code (the "≤ 37" test), not 40; the empirical
"≤ 40" bucket simply includes a handful of 38–40 values that the engine actually
interprets as 380–400 Hz.

---

## 3. The `[: ]` command set

Commands are matched by **unique prefix**: `cm_cmd.c:162` fires as soon as
`total_matches == 1`, so `[:ra 200]`→`rate`, `[:phone on]`→`phoneme`,
`[:dv …]`→define_voice, `[:vo 80]`→`volume`, etc. The authoritative table is
`command_table[]` in `cmd/c_us_cde.h:393-497` (each row:
`{name, arg-format, argc, DCS_code, handler}`). Full enumeration:

| Command (table name / common form) | Args | Handler (`cm_copt.c`) | Semantics |
|---|---|---|---|
| `rate` (`ra`) | `d` | `cm_cmd_rate` | Speaking rate in words/min |
| `latin` | `d` | `cm_cmd_latin` | Latin-mode toggle |
| `name` (`n<x>`) | `d`/`a` | `cm_cmd_name` | Select built-in voice (see below) |
| `np nb nc nh nf nd nk nu nr nw nv` | 0 | `cm_cmd_name` | Direct voice-select shortcuts (DCS_NAME_*) |
| `comma` (`cp`) | `d` | `cm_cmd_comma` | Comma pause (ms) |
| `period` (`pp`) | `d` | `cm_cmd_period` | Period pause (ms) |
| `volume` (`vo`) | `add` | `cm_cmd_volume` | set/up/down loudness (+ `tone` if SW_VOLUME) |
| `vs` | `d` | `cm_cmd_vs` | Voice-style / speaking-style |
| `index` | `add` | `cm_cmd_mark` | Emit index/bookmark callback |
| `error` | `a` | `cm_cmd_error` | Error-handling mode (ignore/text/speak/tone) |
| `phoneme` (`phone`) | `aaa` | `cm_cmd_phoneme` | **Enter/leave phonemic mode**: `on`/`off`, `arpabet`/`asky`, `speak`/`silent` |
| `log` | `aa` | `cm_cmd_log` | Debug logging on/off |
| `mode` | `aa` | `cm_cmd_mode` | Sub-modes (e.g. `table on/off`, math, europe) |
| `say` | `a` | `cm_cmd_say` | Set say-granularity (clause/word/letter/line/syllable) |
| `punctuation` (`punct`) | `a` | `cm_cmd_punct` | none/some/all/pass |
| `skip` | `a` | `cm_cmd_skip` | Skip modes |
| `pause` | `d` | `cm_cmd_pause` | Insert a pause of N ms |
| `play` | `a` | `cm_cmd_play` | Play a wave/tone resource |
| `resume` | 0 | `cm_cmd_resume` | Resume after pause |
| `sync` | 0 | `cm_cmd_sync` | Synchronization barrier |
| `flush` | `ad` | `cm_cmd_flush` | Flush the pipeline |
| `enable` | — | `cm_cmd_enable` | Enable callbacks/features |
| `mtone` | `dddd` | `cm_cmd_mtone` | Multi-parameter tone |
| `dial` | `a` | `cm_cmd_dial` | Dial a phone number (DTMF) |
| `tone` | `dd` | `cm_cmd_tone` | Emit a tone (freq,dur) |
| `timeout` | `d` | `cm_cmd_timeout` | Set timeout |
| `pronounce` (`pron`) | `aa` | `cm_cmd_pronounce` | Homograph/pronunciation flags |
| `digitized` | 0 | `cm_cmd_digitized` | Digitized-speech mode |
| `language` (`lang`) | `a` | `cm_cmd_language` | english/british/french/german/spanish/latin_american + us/uk/fr/gr/sp/la |
| `remove` | — | `cm_cmd_remove` | Remove a user dictionary entry |
| `pitch` (`pi`) | `d` | `cm_cmd_stress` | Baseline pitch / stress (DCS_STRESS) |
| `define_voice` / **`dv`** | `ad*` | `cm_cmd_define` | **Designer Voice**: set any of ~40 Klatt params |
| `debug` | `h` | `cm_cmd_debug` | Debug hooks |
| `setv` | `d` | `cm_cmd_setv` | Select a stored voice slot |
| `loadv` | `d` | `cm_cmd_loadv` | Load a voice definition |
| `gender` | `a` | `cm_cmd_gender` | Set gender |
| `preamble` | `d` | `cm_cmd_preamble` | Preamble handling |
| `dbgv` | up to 10×`d` | `cm_cmd_dbgv` | Pass debug variables |
| `version` | `a` | `cm_cmd_version` | Report version |
| `spf` | `d` | `cm_cmd_samples_per_frame` | Samples per frame |
| `clk_rate` | `d` | `cm_cmd_cpu_rate` | Clock/CPU rate |
| `code_page` | `d` | `cm_cmd_code_page` | Character code page |
| `plang` | `d` | `cm_cmd_plang` | Phoneme language |
| `break` | `a` | `cm_cmd_break` | Insert a break |
| `power` | `ad` | `cm_cmd_power` | Battery/power (embedded) |
| `tsr` | `a` | `cm_cmd_tsr` | TSR control (DOS) |

### `[:n?]` voice selects → canonical names

Rows `cmd/c_us_cde.h:403-415`, names `cmd/c_us_cde.h:301-315`:

| Command | `DCS_NAME_*` | Canonical voice |
|---|---|---|
| `[:np]` | PAUL | **Perfect Paul** (default) |
| `[:nb]` | BETTY | **Beautiful Betty** |
| `[:nh]` | HARRY | **Huge Harry** |
| `[:nf]` | FRANK | **Frail Frank** |
| `[:nd]` | DENNIS | **Doctor Dennis** |
| `[:nk]` | THE_KID | **Kit the Kid** |
| `[:nu]` | URSULA | **Uppity Ursula** |
| `[:nr]` | RITA | **Rough Rita** |
| `[:nw]` | WILLY | **Whispering Wendy** (table code `WILLY`/`wendy`) |
| `[:nv]` | VAL | **Variable Val** |
| `[:nc]` | CHRIS | Chris (HLsyn-only, post-4.3) |

### `[:dv]` Designer Voice parameters

`cm_cmd_define`/`cm_cmd_setv` accept the ~40 two-letter Klatt parameters listed at
`cmd/c_us_cde.h:340-392`: `sx sm as ap pr br ri nf la hs f4 b4 f5 b5 f7 f8 gf gh
gv gn g1 g2 g3 g4 g5 ft bf lx qu hr sr ago agvo aguo chink oq` — e.g. `ap`=average
pitch (Hz), `pr`=pitch range (% of Paul's), `hs`=head size, `f4`/`b4`=4th-formant
freq/bw, `gv`=voicing gain. **This is DECtalk's analogue of MacinTalk's 72-key
voice dict** (`pyretrotts/_voice.py`), and is what makes the 10 named voices.

---

## 4. Port plan (phased, testable)

The MacinTalk port's discipline is the template (`docs/architecture.md`):
per-stage unit tests anchored to a C oracle, then a **golden PCM sha256 gate** that
pins audio without needing the C build. Reproduce that exactly.

### The oracle exists — build it first (Phase 0)

`dectalk/dectalk` builds with `autogen.sh`/`configure.ac`/`Makefile.in` (and ships
a `Dockerfile`/`docker-compose.yml`). The sample CLI `src/samples/SAY/say.c`
(also `ports/emscripten/src/say.c`) renders text or phonemic strings to
WAV/PCM — this is the bit-exact reference. Deliverable: a `dectalk-c` sibling
checkout that builds `say`, plus a `test/test_dectalk_voices.py` harness that
shells out to it (mirroring `test/test_voices.py`). **Instrument points** to dump
intermediate state: the LTS pipe values in `cm_phon_flush`, the `symbols[]`/
`user_durs`/`user_f0` arrays after `ph_task`, the F0 command list from
`set_user_target`, and the per-frame Klatt controls in `ph_drwt*.c`. Effort:
**1–2 weeks** (build system is old; the Docker path de-risks it).

### Phase 1 — Klatt synthesizer core (`vtm/` → `pyretrotts/dectalk/vtm.py`) — DONE

**Landed and bit-exact.** The oracle builds with native autotools (see
[dectalk.md](dectalk.md)) and renders 11025 Hz, 16-bit mono PCM deterministically
for all ten voices. The compiled synthesizer is **`vtm/vtm1.c`, the integer
(fixed-point) Klatt cascade/parallel model** — *not* the float `vtm_f.c`, which
builds only on ALPHA/OSF. `vtm.py` reproduces `speech_waveform_generator` for the
US-English path (`VTM1`, `PC_SAMPLE_RATE == 11025`, `SAMPLE_RATE_INCREASE`),
driven by Klatt parameter frames captured from an instrumented oracle. Verified
**sample-for-sample identical** to the C for all ten voices over multiple
utterances (`test/test_dectalk_oracle.py`, 50/50 cases). Tables are transcribed
from the C by a dumper (`tools/dump_dectalk_vtm.py`); the golden gate
(`test/dectalk_golden.py`) refuses to write unless the oracle match passes first.

Note on the earlier estimate: the synthesizer is fixed-point, so there is no
float/x87/SSE risk; the risk was the preprocessor config, now pinned exactly.

### Phase 2 — Phonemic / singing path (`cmd/cm_phon.c` + `ph/` prosody)

Port the phonemic-mode parser (`cm_phon.c`), the `user_durs`/`user_f0` plumbing
(`ph_task.c`), `set_user_target` + `notetab` (`ph_drwt01.c`), and enough of
`ph_inton0.c`/`ph_sort.c`/`p_us_tim.c` to realize `[:phone on]` songs. **This is
the deliverable that makes DECtalk songs play**, and it is testable in isolation
because phonemic input bypasses the dictionary and LTS. Golden gate: PCM of a set
of real `.EN` songs. Effort: **4–6 weeks**.

### Phase 3 — Command layer (`[: ]`)

Port `command_table` dispatch (`cm_cmd.c`, `cm_copt.c`) with prefix-matching,
plus the handlers that affect audio: `name`/`n?`, `dv`/`setv`, `rate`, `volume`,
`pitch`, `comma`/`period`, `pause`, `tone`. Extract the 10 voice definitions from
`ph/p_us_vdf*.c` and the `dv` parameter semantics. Effort: **3–4 weeks**.

### Phase 4 — Text front end (dictionary + LTS)

The largest surface: compile/port `dic/Dic_us.txt` search (`lts/ls_dict.c`,
`maindict.c`) and the US letter-to-sound rules (`lts/l_us_*`, `ph/p_us_rom*.c`,
`allorules.c`), number/abbreviation expansion (`cmd/par_*`). Port US-English only;
defer UK/GR/SP/LA/FR. Effort: **8–12 weeks** (rule-heavy, many small tables).

### Data tables to extract

- `notetab[]` (37 note freqs) — `ph/p_us_rom_1997.c:1188`.
- The 10 voice definitions (`dv` params) — `ph/p_us_vdf*.c`.
- Klatt formant/coefficient tables — `vtm/vtmtable.h`, `vtm/fvtmtabl.h`.
- Duration rule tables — `ph/p_us_tim.c`.
- Allophone/phoneme tables — `include/l_us_ph.h`, `ph/p_us_rom*.c`.
- Compiled dictionary trie + LTS rule tables (Phase 4).

Write an `tools/extract_dectalk_data.py` that emits `_dectalk_data.generated.py`
for review, exactly as `tools/extract_data.py` does for MacinTalk.

---

## 5. Shared architecture for two engines in one repo

### Proposed surface

Two engine classes with a thin common protocol; **no shared internal pipeline.**

```
pyretrotts/
  api.py                     # dispatches to either engine; today's MacinTalk entry points
  _phonemes.py … _backend.py # MacinTalk internals (unchanged)
  dectalk/
    _consts.py _phonemes.py _vtm.py _cmd.py _phon.py _inton.py _lts.py _data.py
    engine.py                # DECtalkEngine
  engines.py                 # MacInTalkEngine wrapper + DECtalkEngine, common ABC
```

Common surface (an ABC, not shared implementation):

```python
class SpeechEngine(Protocol):
    voices: list[str]
    markup_dialect: str                         # "macintalk-[[..]]" | "dectalk-[:..]"
    def synthesize_text(voice, text) -> bytes    # 16-bit mono PCM
    def build_plan(voice, text) -> Plan          # engine-specific plan type
    def synthesize_plan(plan) -> bytes
```

### What is genuinely shareable

- **Nothing in the phoneme id space, prosody model, dictionary, LTS, or voice
  definitions.** DECtalk's `l_us_ph.h` codes, `symbols[]`+`user_f0`/`user_durs`
  prosody channel, `dv` Klatt params, and `[: ]` markup are all structurally
  different from MacinTalk's. Forcing a shared abstraction here would make one
  engine diverge from its C reference — reject it.
- **Small, generic numeric helpers only, and only if bit-identical.** MacinTalk's
  fixed-point helpers (`mMul2`, `mScale`, `rshort`, `clip14`; kPrecision=13) are
  candidates *if and only if* DECtalk's ported synth also computes in the same
  fixed-point regime. But `vtm/` uses `FLTPNT_T` (float-capable), so **the two
  synthesizers will most likely not share arithmetic.** Keep the helpers in
  MacinTalk's namespace; copy, do not couple, if DECtalk needs a fixed-point path.
- **Infrastructure, not DSP**: the WAV writer, the PCM sha256 golden-gate
  framework (`test/golden.py`), the C-oracle harness pattern, and the
  `tools/extract_*.py` scaffolding are worth sharing verbatim.

### What must stay separate

The Klatt synthesizer core (5-formant cascade+parallel vs MacinTalk's leaner
fixed-point synth), phoneme ids, allophone selection, duration rules, intonation,
dictionary, LTS, voice tables, and markup parsers. Two `_data.py`, two
`_phonemes.py`, two backends. The only place they meet is `api.py`/`engines.py`
dispatch and the test/tooling infrastructure.

### Skeptical note on "shared formant core"

It is tempting to factor a single formant synthesizer both engines call. **Do
not** — MacinTalk's synth is already verified bit-exact against its own C
reference; DECtalk's must be verified bit-exact against *its* C reference
(`vtm/`), which differs in formant count, source model, and numeric type. A shared
core would force at least one of them off its oracle. Share the *test harness*,
not the *synthesizer*.

---

## Appendix — key file:line index

- Phonemic `<dur,pitch>` parse: `cmd/cm_phon.c:268-351`, flush `:365-489`;
  slot macros `cmd/cm_defs.h:109-110`.
- `dur`/`pitch` → prosody arrays: `ph/ph_task.c:845-854`; `mstofr` `:1290-1297`.
- Note-vs-Hz conversion: `ph/ph_drwt01.c:1955-1984` (`set_user_target`),
  `LOWEST_F0/HIGHEST_F0` `:195-196`.
- `notetab[]` (C2–C5, F0×10): `ph/p_us_rom_1997.c:1188`; commented ref
  `ph/p_us_rom_dectalk_1996m_43f.c:810-851`.
- f0mode selection + full semantics comment: `ph/ph_sort.c:1050-1108`.
- User-target application in inton: `ph/ph_inton0.c:298-309`.
- Command table: `cmd/c_us_cde.h:393-497`; voice names `:301-315`; `dv` params
  `:340-392`; `n?` rows `:403-415`.
- Prefix command match: `cmd/cm_cmd.c:141-260`.
- Klatt synth: `vtm/vtm_f.c` (`Copyright 1984 Dennis H. Klatt`), controls
  `:134-175`.
- US phoneme codes: `include/l_us_ph.h:59-116`; `US_TOT_ALLOPHONES` `:119`.
- Dictionary source: `dic/Dic_us.txt` (15 537 lines); loader `lts/ls_dict.c`,
  `lts/maindict.c`.
- Oracle CLI: `src/samples/SAY/say.c`; build `src/autogen.sh` + `Dockerfile`.
