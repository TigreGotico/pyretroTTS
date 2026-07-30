# Modern mode

Classic mode is what exists: bit-exact ports of MacinTalk, DECtalk markup, and
SAM, with the original voices reproduced sample-for-sample. This document plans
a **modern mode**: capabilities layered *on top* of those engines without
touching the synthesis core.

## The constraint that shapes everything

The original voices must stay bit-for-bit replicable. Two gates enforce it:

- `test/test_golden_pcm.py` hashes the PCM of 17 voices × 12 texts and fails on
  one differing byte (`test/golden.py:26-56`. The digests were captured against
  the C reference, `test/golden.py:6-13`).
- `test/test_voices.py` (the C oracle) diffs Python frames and PCM against a
  compiled `lintalker-c` build (`docs/architecture.md:140-147`).

So a proposal is **additive-safe** only if it cannot change what
`synthesize_text(voice_dict, text)` returns for the 17 built-in voice dicts.
Concretely that means it must not edit any module on the classic path
(`_frontend`, `_lexicon`, `_engtop`, `_morph`, `_assembly`, `_phonbuf2`,
`_pitchcontour`, `_moduration`, `_pitchbuf`, `_backend`, `_data`, `_phonemes`,
and `api.synthesize_text`/`build_phoneme_plan`), and must reach the engine only
through parameters that default to today's behaviour or through *new* entry
points the golden set never calls.

There is already a clean seam for this. `api.synthesize_phonemes` and
`api.synthesize_plan` (`pyretrotts/api.py:106-173`) take a phoneme plan and
render it through the identical backend, bypassing the entire text frontend.
The golden gate only ever calls `synthesize_text` (`test/golden.py:61`), never
`synthesize_phonemes`. **Any modern front end that emits a `PhonemePlan` and
feeds it to `synthesize_plan` is invisible to the golden gate by
construction**, it reuses the bit-exact backend without being able to perturb
the bit-exact frontend. This seam is the backbone of almost every recommend
below.

The engine's phoneme inventory, for reference throughout: 56 ids,
`kNumPhoneme = 56` (`pyretrotts/_phonemes.py:125`), of which 55 are speech
sounds (index 23 is `SIL`):

```
IY IH EH AE AA AH AO UH AX ER EY AY OY AW OW UW YU IR XR AR OR UR IX SIL
RX LX EL EN w y r l h m n NG f v TH DH s z SH ZH p b t d k g CH JH TX DX QX DD
```

DECtalk markup maps its mnemonics onto these same ids
(`pyretrotts/_dectalk.py:90-109`). It is one inventory, written two ways. SAM
has its own, smaller inventory and collapses several distinctions
(`pyretrotts/sam/engine.py:133-144`).

---

## 1. External phonemizer / IPA interchange

**What it is.** A canonical IPA layer with two directions: IPA → each engine's
phoneme ids (to render arbitrary IPA, or to plug `espeak-ng` / `phonemizer` /
`g2p_en` in as an alternative front end), and engine ids → IPA (to inspect what
an engine will say). The reverse direction already half-exists: `g2p.phonemize`
exposes each engine's native front end as mnemonics
(`pyretrotts/g2p.py:111-125`).

**How it stays additive.** It is a new module (`pyretrotts/ipa.py`) plus new
functions on the engines (`say_ipa`). IPA is translated to a list of phoneme
ids, packed into a `PhonemePlan`, and rendered via `synthesize_plan`. It never
imports into or edits the classic frontend. The golden set does not call it.
Nothing about `Fred_Voice`'s render through `synthesize_text` changes.

**The loss is real and must be quantified per engine.** The MacinTalk/DECtalk
inventory is ARPABET-ish and English-centric. A defensible IPA→id table looks
like this (IPA on the left, engine id mnemonic on the right. ", " = no faithful
target):

| IPA | MacinTalk id | Note |
|---|---|---|
| i, iː | IY | |
| ɪ | IH | |
| ɛ | EH | |
| æ | AE | |
| ɑ, ɒ | AA | two IPA vowels collapse to one |
| ʌ | AH | |
| ɔ | AO | |
| ʊ | UH | |
| ə | AX | |
| ɝ, ɜ | ER | |
| eɪ | EY | |
| aɪ | AY | |
| ɔɪ | OY | |
| aʊ | AW | |
| oʊ, o | OW | |
| u, uː | UW | |
| j+u | YU | engine has a dedicated /ju/ |
| ɪɚ, ɪr | IR | r-coloured. Language-specific to English |
| ɛɚ | XR | |
| ɑɚ, ɑr | AR | |
| ɔɚ, ɔr | OR | |
| ʊɚ | UR | |
| ɨ | IX | |
| p b t d k g | p b t d k g | |
| tʃ dʒ | CH JH | |
| f v θ ð s z ʃ ʒ | f v TH DH s z SH ZH | |
| m n ŋ | m n NG | |
| l | l / LX / EL | engine picks dark/syllabic itself (see below) |
| ɹ | r / RX | |
| w j h | w y h | |
| ɾ | DX | flap, engine normally inserts this itself |
| ʔ | QX | glottal stop |

Consonants map nearly 1:1. The loss is almost entirely in the vowels and is
**structural, not tunable**:

- **English r-colouring is baked into the inventory.** IR/XR/AR/OR/UR/ER/RX are
  distinct ids (`_phonemes.py`). A language without rhotic vowels wastes them. A
  language *with* different rhotics can't get them.
- **Two IPA vowels routinely collapse to one id** (ɑ/ɒ→AA, o/oʊ→OW). Expect a
  perceptible vowel-quality error on those, ~1 of every few vowels in
  non-English text.
- **Length and nasalization are not representable.** There is no long/short vowel
  distinction and no nasal-vowel id. French /ɑ̃/ or German /yː/ have no target.
  Loss here is total, the distinction is dropped.

Quantified: for General American English the round trip IPA→id→IPA is
**near-lossless** (>95% of segments) because the inventory was built for exactly
that phoneme set. For any other language, segment-level faithful-mapping rate
falls to roughly **60-80%** depending on how many of its vowels have English
counterparts, with every dropped length/nasal/non-English-rhotic contrast
counted as a loss. SAM is worse: `DECTALK_TO_SAM`
(`pyretrotts/sam/engine.py:133-144`) already collapses yu→UW, all r-coloured
vowels→ER/AA/AO/UH, and tx→T, so its faithful-mapping ceiling is below
MacinTalk's even for English.

**Can espeak-ng/phonemizer/g2p_en be the front end?** Yes for the *segment*
stream, and this is the genuinely useful part: `espeak-ng -q --ipa` gives IPA,
`ipa.py` maps it to ids, `synthesize_plan` renders it. What breaks:

- **Stress marks.** espeak emits ˈ/ˌ. The engine does not take a per-phoneme
  stress *input* on the synthesis side. Stress enters via the frontend's opcode
  stream (`kNumPhoneme`-and-above marker ids, `g2p.py:73-82`) and prosody scaling
  in the voice dict. Feeding phonemes through `synthesize_plan` with `ctrls=0`
  (as DECtalk singing already does, `engines.py:160`) produces **flat,
  unstressed** speech. Recovering stress means synthesizing the marker/pitch
  opcodes an external phonemizer's stress marks imply, buildable, but it is new
  code, and it will not match the frontend's own POS-driven stress.
- **Syllable boundaries** are dropped the same way.
- **Allophones the engine picks itself.** `_phonbuf2.fill_phon_buf_2` does flapped
  T, dark L, R-colouring, plosive releases (`docs/architecture.md:38,73-74`). If
  you feed pre-resolved IPA allophones you either fight this stage or bypass it.
  Bypassing it (going straight to `synthesize_plan` with explicit ids) is
  cleaner and is what this proposal should do.

**Effort:** medium. The mapping table and `ipa.py` are a few days. A solid
stress/duration heuristic from external marks is the bulk of the work and never
becomes bit-exact against the native frontend (it isn't trying to be).

**Risk:** low to the constraint (new module, new entry point). Moderate to
expectations, users will expect "IPA in" to sound as good as the native
frontend and it will sound flatter unless the prosody bridge is good.

**Recommend: yes, in two tiers.** Ship the id↔IPA mapping and `say_ipa` first
(honest, bounded, immediately useful for the phoneme-plan power user and for
documentation). Treat "espeak-ng as a drop-in English/other-language front end"
as a second tier with the prosody caveat stated plainly.

---

## 2. Language support

**The blunt answer: the synthesizer is reusable. Everything in front of it is
not.**

Reusable as-is: the formant synthesizer (`_backend.say_frame`), the
source-filter model, the per-phoneme formant tables (`_data.py`), duration and
pitch machinery (`_moduration`, `_pitchcontour`, `_pitchbuf`). These are
acoustic, not linguistic, a formant is a formant in any language. The voice
dicts are language-neutral.

Not reusable, all English: the pronunciation dictionary (`_lexicon.py`,
`English.lex`), the letter-to-sound rules (`_engtop.py`, NRL-style rules keyed
A, Z, `_engtop.py:1-40`), the morphology/suffix pass (`_morph.py`), number/date
readers (`_numbers.py`), and the allophone rules (`_phonbuf2.py`, which encode
*English* flapping/dark-L/r-colouring).

Three candidate paths:

**(a) New letter-to-sound rules + dictionary per language, feeding the existing
synthesizer.** `_engtop.py`'s rule format is the NRL interpreter with tables
`Rules`, `KindTBL`, `dashruletab`, `atruletab`, `lruletab`, `mruletab`,
`zruletab`, `percentruletab`, `bruletab` in `_data.py` (`_engtop.py:33-48`),
plus a 26-slot A, Z hash. It *could* be regenerated for Portuguese or Spanish, 
Spanish especially, whose orthography is famously rule-regular, is a good NRL
fit. But two hard problems: (1) the rule tables are a binary format ported
verbatim from `Sounds.c` (`_engtop.py:36-38`). Authoring new ones means writing
a rule-compiler that does not exist. (2) The output alphabet is still the 55
English ids, you can spell Spanish words to English phonemes, but you cannot
add /r/ trill, /ɲ/, or true /o/ without new synthesizer phonemes, which means
touching `_phonemes.py`/`_data.py`, **off-limits under the constraint.** So (a)
gets you Spanish-with-an-American-accent at best.

The dictionary format (`_lexicon.py`) is a big-endian Mac binary blob with
Pascal-string keys and phoneme-byte values (`_lexicon.py` header). Regenerating
it for another language is mechanical *if* you accept the English phoneme
inventory as the target alphabet, same ceiling as (a).

**(b) IPA in from an external phonemizer** (proposal 1). This is the realistic
path. `espeak-ng` already has good Portuguese and Spanish G2P. Map its IPA to
the nearest English ids and render. Same phoneme-inventory ceiling as (a) but
*far* less bespoke code, you inherit a maintained multilingual G2P instead of
hand-authoring rule tables. Accent is unavoidable because the target inventory
is English. You cannot synthesize a phone the engine has no formant target for.

**(c) Neither.** For a language whose phonology is far from English (tonal
languages, rich vowel-length/nasal systems), both (a) and (b) produce a
caricature. Honest answer: don't ship it.

**Recommend:** path (b), and only for languages close to the English inventory
(Spanish, Portuguese, Italian, German consonants). Frame it as "these engines
speaking foreign words with an American robot accent," which is period-accurate
and honest, not "Spanish TTS." **Do not** build the `_engtop` rule-compiler
(path a): it is large, bespoke, and hits the exact same accent ceiling as the
free path (b). **Do not** add synthesizer phonemes for a language, it breaks
the constraint. Effort for (b): small (it *is* proposal 1). Effort for (a):
large, and not worth it.

---

## 3. New voices (automated design, morphing, external voice files)

**External voice-file format, recommend, easy, high value.** A voice is
already a plain dict of ~72 keys (`_voice.py`'s `Voice` TypedDict. Template at
`creating-voices.md:246-273`), read once by `init_voice`
(`api.py:42-68`). Nothing requires it to live in `_data.py`. A
`Voice.from_toml(path)` / `from_json` loader is a thin, purely additive wrapper:
the 17 built-ins stay exactly where they are (the golden gate imports them from
`_data.py`, `golden.py:32`), and new voices load from files. Zero risk to the
constraint.

```python
def load_voice(path: str) -> Voice: ... # TOML/JSON -> the same dict
def save_voice(voice: Voice, path: str) -> None: # dict -> TOML/JSON
```

**Voice interpolation / morphing, recommend, easy, genuinely fun.** Because a
voice is scalar parameters, linear interpolation between two voice dicts is
well-defined for the numeric fields. The one trap is that not every field
interpolates meaningfully: `voice` (0/1 male/female table select,
`creating-voices.md:114`) is categorical, `waveType` is categorical, and
`vWave`/`vWave1` are 48-element harmonic tables that *can* be interpolated
element-wise but only sensibly between same-`waveType` voices. A safe API
interpolates the continuous fields and snaps the categoricals:

```python
def morph(a: Voice, b: Voice, t: float) -> Voice:
  """Blend two voices. Continuous params lerp; categorical params snap at t=0.5."""
```

Additive by construction, it produces a new dict fed to the existing
`synthesize_text`. It cannot affect the built-ins.

**Automated parameter search against a target, qualified recommend, but see
proposal 4.** Optimising the ~70 scalar params against a spectral/perceptual
loss is the same machinery as voice cloning and shares its limits. As a *voice
design* tool (match a target you already like, or de-noise a hand-tune) it is
useful and low-stakes. As a *cloning* tool it is oversold, proposal 4.

**Effort:** file format + morph, small (days). Search, medium and shared with 4.
**Risk:** none to the constraint for all three (new dicts, new modules).

---

## 4. Voice cloning from a reference WAV

**Be skeptical.** A MacinTalk voice is ~72 scalar parameters
(`_voice.py`. `docs/architecture.md:28`) driving a Klatt cascade/parallel
formant model. Cloning asks: can we recover those 72 from a recording? Partly,
and the honest expectation is **it will sound like Fred wearing the speaker's
hat, not like the speaker.**

What is *estimable* from a reference recording, and which parameter it informs:

| Recoverable from audio | Parameter(s) it constrains | Confidence |
|---|---|---|
| F0 mean/range | `pitch`, `pitchRange` (`creating-voices.md:113,163`) | high |
| Overall formant scaling (vocal-tract length) | `f1_Offset`, `f2_Offset`, `f3_Offset` (`creating-voices.md:125`) | medium |
| Formant bandwidths (breathy vs tonal) | `bwGain1/2/3` (`creating-voices.md:126`) | low, medium |
| Spectral tilt / breathiness | `aGain`, `AsperW`, `vGain` (`creating-voices.md:143`) | low, medium |
| Nasality | `nasalAmt`, `nasal_*` (`creating-voices.md:133`) | low |
| Vibrato depth/rate | `vibratoDepth1/2`, `vibratoFreq` | low |

What is **not** estimable:

- **`vWave`/`vWave1`**, the 48-point glottal harmonic tables that define source
  tone quality (`creating-voices.md:140,276-285`). The doc itself says don't
  hand-guess these. Inverse-filtering a real glottal source into *these 48
  Klatt-style coefficients* is ill-posed from a mixed recording. This is the
  single biggest determinant of "who it sounds like," and it is the least
  recoverable. Clones will borrow the nearest built-in's `vWave` and move the
  cheap knobs, exactly the fallback `creating-voices.md:280-285` already
  recommends for hand-tuning.
- **Per-phoneme formant *tables*** are shared across all voices
  (`creating-voices.md:62-66`) and are *not* voice parameters, you cannot fit a
  speaker's idiosyncratic vowel space. Every voice says AA at the same target.
- The categorical `voice`/`waveType` and all prosody-*algorithm* behaviour.

**Pipeline, honestly:** (1) formant-track the reference (F1, F3, bandwidths, F0)
with an external tool. (2) fit the ~10 estimable scalars above by least-squares
on the tracks. (3) optionally refine with a search that renders a candidate
voice through `synthesize_text` and minimises a spectral distance to the
reference. Every step is additive, it *emits a voice dict*, and the result is
rendered through the existing pipeline. It cannot touch the built-ins.

**Expectation:** you recover pitch and gross vocal-tract size well, breathiness
roughly, and source timbre not at all. The output is a plausibly-male or
plausibly-female Klatt voice in the reference's pitch range, a better starting
point than Fred, but categorically a formant robot, not the speaker.

**Recommend: don't build the full "clone from WAV" feature. Do build the
estimator as a *voice-design aid*.** Ship "seed a new voice's pitch/size/
breathiness from a reference recording" (honest, ~10 parameters, clearly a
starting point for hand-tuning). Do **not** ship or market "voice cloning", 
the `vWave` and shared-formant-table limits make speaker identity
unrecoverable, and promising otherwise sets an expectation the model cannot
meet. Effort for the honest estimator: medium (needs a formant tracker
dependency). Effort for a "real clone": high and the ceiling is low, not worth
it.

---

## 5. Other candidates

**OVOS TTS plugin surface, recommend, high value, trivially additive.** The
README already notes the plugin lives in a separate repo
(`README.md:47-49`), and the `Engine` ABC (`engines.py:32-56`) is already the
right shape (text + voice → PCM). A plugin is a thin adapter over
`Engine.synthesize`. It adds no code to the classic path. This is the clearest
"modern mode" win with the least risk.

**CLI, recommend, easy.** `examples/` already has runnable scripts
(`synthesize_text.py`, `list_voices.py`) but no installed entry point
(`pyproject.toml` has no `console_scripts`). A `pyretrotts` CLI wrapping the
three engines is a pure wrapper. Additive, small.

**Streaming synthesis, qualified.** `synthesize_text` builds the whole
`sampleBuffer` and returns it at once (`api.py:300-302`). `say_frame` is already
a per-frame loop (`api.py:297-300`). A generator that yields frame chunks is
feasible *as a new function* (`synthesize_stream`) reusing the same loop.
`docs/architecture.md:202-205` notes `e_SpeakBuffer`'s streaming parser is
absent, so this is new territory but need not touch the batch path. Recommend as
a later, additive `synthesize_stream`, do not retrofit `synthesize_text` into a
generator (that would risk the golden path). Effort: medium.

**SSML, qualified, prefer mapping to existing markup.** MacinTalk already has a
rich inline command language (`[[rate]]`, `[[pbas]]`, `[[note]]`, `[[slnc]]`,
`[[char]]`, …, `_embeddedcmd.py`) and DECtalk its `[: ]` dialect, with a working
translator between them (`translate.py`). An SSML front end that *compiles to
`[[...]]`* is additive (new module, emits text the existing frontend already
parses) and reuses proven machinery. Recommend this over a native SSML parser.
Only `<prosody rate/pitch>`, `<break>`, `<say-as>`, `<phoneme>` map cleanly.
Document the unsupported tags. Effort: small, medium.

**Prosody control API.** Partly redundant with SSML/embedded commands. The voice
dict already exposes prosody scaling (`stressGain`, `riseAmt`, `pitchRange`, …,
`creating-voices.md:155-167`) and it is "safe to tune without touching Python"
(`creating-voices.md:150-153`). A convenience API over these + `[[...]]` is
additive but low novelty. Recommend folding into the SSML/CLI work rather than a
standalone feature.

**`.wav` round-trip test corpus, recommend as *infrastructure* for everything
above.** The golden gate protects the 17 classic voices. Modern-mode outputs
(IPA renders, morphed voices, SSML) need their *own* regression corpus so they
don't silently drift, but kept in a **separate** test module with its **own**
digests, never added to `test/golden.py`'s `VOICES`/`TEXTS` (which are anchored
to the C reference, `golden.py:6-13`). This keeps the two regimes from
contaminating each other.

---

## Ranking

1. **OVOS TTS plugin surface** (§5), highest value, lowest risk, ABC is ready.
2. **External voice-file format + morph** (§3), easy, additive, unlocks §4.
3. **IPA interchange, tier 1: id↔IPA mapping + `say_ipa`** (§1), bounded,
  honest, enables §2.
4. **CLI** (§5), easy, expected, pure wrapper.
5. **SSML → `[[...]]` compiler** (§5), reuses proven markup machinery.
6. **IPA tier 2: espeak-ng as a front end + close-language support** (§1, §2b)
, useful with the prosody/accent caveats stated.
7. **Voice-design estimator from a reference WAV** (§4, honest ~10-param
  version), medium effort, clearly a *seed*, not a clone.
8. **Streaming `synthesize_stream`** (§5), later, additive.

**Do not build:** full "voice cloning" marketed as speaker identity (§4, 
`vWave` and shared formant tables make it unrecoverable). A bespoke `_engtop`
rule-compiler for new languages (§2a, same accent ceiling as free espeak, far
more code). New synthesizer phonemes for non-English languages (breaks the
constraint outright). Retrofitting `synthesize_text` into a streaming generator
(risks the golden path, add a new function instead).

## Why each stays additive, in one line

Every recommend either (a) adds a new module/entry point that emits a
`PhonemePlan` or a voice dict and renders through the existing
`synthesize_plan`/`synthesize_text` (`api.py:106-173`), or (b) wraps the
`Engine` ABC (`engines.py:32-56`) from outside. None edits a classic-path module
or `api.synthesize_text`, and none is called by `test/golden.py`. The 17 × 12
digests cannot move.

## Phased roadmap

**Phase 0, infrastructure.** Separate modern-mode test corpus with its own
digests (§5), kept out of `test/golden.py`. Establishes the safety net before
anything ships.

**Phase 1, surfaces (no new synthesis).** OVOS plugin (§5), CLI (§5), external
voice-file loader + `morph` (§3). All thin wrappers. Immediate user value. Zero
constraint risk.

**Phase 2, phoneme-level modern input.** `ipa.py` id↔IPA mapping and `say_ipa`
(§1 tier 1) with the per-engine loss table documented. Then espeak-ng as an
optional front end and close-language rendering (§1 tier 2, §2b), accent caveat
stated.

**Phase 3, expressive input.** SSML→`[[...]]` compiler (§5) and streaming
`synthesize_stream` (§5).

**Phase 4, voice design.** Reference-WAV parameter *estimator* as a voice-design
seed (§4), explicitly not marketed as cloning. Optional parameter search (§3)
built on the same machinery.

Everything through all four phases renders through the untouched classic
backend. Classic mode is the ground truth. Modern mode only ever adds new ways
to reach it.


---
[← SAM engine](sam.md) · [Home](../README.md)
