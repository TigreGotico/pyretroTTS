# Modern engines: generative IPA front ends

The classic engines speak IPA by mapping each symbol to the nearest of their
English phoneme presets and reading that preset's target ROM (see
[ipa.md](ipa.md) and its loss table). Any sound outside the English inventory is
rounded to an English neighbour: French `/y/` becomes `/u/`, uvular `/ʁ/` becomes
`/r/`, a nasal vowel loses its nasality.

The `pyretrotts.modern` package takes the opposite approach. It decomposes an IPA
symbol into **articulatory features** and *generates* synthesis parameters from
those features, so an arbitrary phone drives the synthesizer directly instead of
being replaced by a preset. Two front ends share the feature model:

- **ModernTalk** generates Klatt parameter frames and renders them through
  DECtalk's bit-exact vocal tract model. Klatt synthesis has high headroom, so
  this is the high-value path.
- **ModernSAM** generates three-oscillator parameters for SAM's 8-bit renderer.
  SAM's fixed sample ROM and coarse frequency codes cap its fidelity; this path
  is a lo-fi curiosity.

These are **additive, experimental** engines. They do not touch the classic
engines, their front ends, or their bit-exact goldens.

## IPA → features → parameters

### The feature model

`pyretrotts.modern.features.decompose(symbol)` returns a frozen `FeatureBundle`.
The decomposition is adapted from Distinctive Feature Theory as implemented in
[`phonematcher`](https://github.com/TigreGotico/phonematcher) (MIT licence),
which maps each IPA phone to a 21-element boolean distinctive-feature vector
(syllabic, consonantal, voice, nasal, place, height/backness/round …) and scores
segment similarity with a weighted feature distance. This package borrows the
*idea* — reason over articulatory features and feature distance rather than
symbol identity — but stores the quantities a synthesizer actually needs instead
of booleans: formant targets, place, manner, voicing, and secondary articulation.
No `phonematcher` code is imported or copied; the tables and distance are
reimplemented here.

A base symbol is split from its combining marks and modifier letters
(NFD-normalised), looked up in a vowel or consonant table, and then diacritics
are folded in: `ː` → long, combining tilde → nasal, `˞`/`ɚ`/`ɝ` → rhotic (F3
lowered), `ʲ ʷ ˠ ˤ` shift the formants, `ʰ` → aspirated, the voiceless ring →
unvoiced. Diphthongs and r-coloured multigraphs are expanded into segment pairs
so the front ends glide between them.

### Vowels

The English monophthongs are **calibrated to the shipped DECtalk US target ROM**
(`pyretrotts.dectalk.targets.US_MALTAR` / `US_MALDIP` — the steady value of each
vowel's own trajectory on *this exact synthesizer*) and cross-checked against
measured American-English formants: Hillenbrand, Getty, Clark & Wheeler (1995,
*JASA* 97(5), Table V, adult males) and Peterson & Barney (1952, *JASA* 24(2)).
The single most important correction over a naive Peterson-Barney transcription
is **F3**: DECtalk keeps English F3 in a ~2300–2800 Hz band on this synth (e.g.
`/i/` F3 2500–2779, not 3010), and an over-high F3 pushed vowels out of the
region the DECtalk cascade is tuned for. Non-English cardinals and front-rounded
vowels use Klatt (1980, *JASA* 67(3), synthesis-tuned), Catford (1988) and Vallée
(1994), with F3 held to the same synth band for consistency. The mapping is the
classic one:

- **F1 ← openness** — higher F1 for more open vowels (`/a/` ≈ 750 Hz, `/i/` ≈
  270 Hz).
- **F2 ← backness** — higher F2 for fronter vowels (`/i/` ≈ 2290 Hz, `/u/` ≈
  870 Hz); **rounding lowers F2 and F3**, which is exactly what separates `/y/`
  from `/i/` and `/u/` from `/ɯ/`.
- **length** → longer frame duration; **nasal** → the cascade nasal zero is
  dropped to ~250 Hz and B1 widened to colour the vowel; **rhotic** → F3 pulled
  down to ~1600 Hz.

### Consonants

Each consonant carries a **place** and **manner**. Place sets an F2 transition
locus and a frication/burst spectral centre. The loci follow locus theory
(Stevens 1998, *Acoustic Phonetics*; Delattre, Liberman & Cooper 1955, *JASA*
27(4)) and are pinned to the shipped DECtalk US consonant targets on this synth
(`US_MALTAR`: `/n/` F2 1540, velar `/ŋ/` 1600, `/m/` 1120, `/f/` 1100, `/ð/`
1300). The English rhotic approximants `/ɹ ɻ/` are given the defining **low F3
≈ 1400 Hz** (Espy-Wilson et al. 2000, *JASA* 108(1); DECtalk US `R` F3 1380) that
the neighbouring vowel bends toward, instead of a generic 2500 Hz. Manner picks
the source configuration:

- **stop** — a silent closure (a faint voice bar if voiced) then a one-frame
  burst at the place's spectral centre, with an aspiration tail for voiceless
  releases.
- **fricative** — parallel/bypass noise steered into a high band (sibilants), an
  upper-mid band (`/ʃ/`, palatals) or a low band (velar/uvular/pharyngeal), plus
  a voicing buzz when voiced. `/h/` is pure cascade aspiration.
- **nasal** — a voiced murmur with the nasal branch engaged and F1 low.
- **approximant / lateral** — vowel-like voiced formants at the place locus.
- **trill / tap** — approximated by amplitude-modulating a voiced approximant
  (a true trill source is future work).

### Prosody, timing and coarticulation

Bare IPA phones — even with correct formants — are barely intelligible on a Klatt
synth, because the classic *text* path runs a whole duration/stress/intonation/
coarticulation stage before the vocal-tract model that a raw phone stream skips.
`pyretrotts.modern.prosody` is that stage, generated by rule from the parsed IPA
(its per-phone stress marks, `word_breaks` and clause `terminator`). Every rule
cites its source in the module:

- **Segment durations** (Klatt 1979 "Synthesis by rule of segmental durations for
  English sentences"; Klatt 1976, *JASA* 59(5)) — each segment has an inherent
  and a minimum ("incompressible") duration, and the rules scale only the
  stretchable part: `dur = minimum + (inherent − minimum) · prcnt`. Stressed
  vowels keep their full length; unstressed/secondary are shortened; clause-final
  rimes and pre-pausal segments are lengthened; consonants in clusters and
  open-vs-closed syllables are adjusted. Same rule *set* as the DECtalk
  `us_phtiming` stage, on this package's own manner-class tables.
- **Intonation / F0** (the "hat pattern" of 't Hart, Collier & Cohen 1990;
  boundary tones after Pierrehumbert 1980) — a declining baseline (declination),
  a rise onto each accented syllable and a fall after it, and a clause-final
  boundary tone chosen by the terminator (statement fall, comma continuation
  rise, question final rise). This replaces the earlier flat per-phone F0.
- **Reduction** (Lindblom 1963 "Spectrographic study of vowel reduction") —
  unstressed vowels are shortened and *gently* centralised toward schwa (strong
  centralisation erases the vowel identity a listener and an ASR both need).
- **Coarticulation** (locus theory, Delattre, Liberman & Cooper 1955; undershoot,
  Lindblom 1963) — formants glide from a consonant locus toward the vowel target
  at a roughly fixed *rate*, so the transition width scales with segment duration
  and short/unstressed segments undershoot their target. This replaces the flat
  three-point moving average. Stop closures and bursts stay crisp (their onsets
  carry the place cue).
- **Word boundaries** (pre-boundary lengthening, Klatt 1975; Wightman et al.
  1992) — `word_breaks` drives pre-boundary lengthening plus a *short* inter-word
  transition, not a silent gap (per-word silence over-segments and costs WER).

### The frame-level seam

ModernTalk's output is a list of `pyretrotts.dectalk.consts.OUT_*` frames
(F1/F2/F3 + bandwidths, nasal zero FZ, pitch period T0, and the source
amplitudes AV/AP/AB/A2..A6), fed straight to
`pyretrotts.dectalk.engine.synthesize_frames`. That is the whole point: the
synthesizer core is the bit-exact ported Klatt vocal tract model, unchanged;
only the front end that decides *what frames to feed it* is generative. ModernSAM
fills SAM's `frequency1/2/3`, `amplitude1/2/3` and `pitches` arrays and runs
SAM's own inner synthesis loop.

## Why Klatt has headroom and additive SAM does not

A Klatt synthesizer is a source-filter model: independent formant resonators, a
nasal pole/zero, and separate voicing, aspiration and frication sources. That is
enough degrees of freedom to place any vowel and to shape most consonant noise,
so generating frames from features can, in principle, reach most of the IPA
chart. SAM is additive: three oscillators (two sine formants and a rectangle
wave) with 4-bit amplitudes and single-byte frequency codes, and its only true
noise source is a fixed 1-bit sample ROM. Front-rounded and nasal vowels are
reachable (they are just formant positions), but there is no real frication
source to steer, so ModernSAM approximates obstruents with the buzzy rectangle
oscillator. It sounds like a robot gargling. That ceiling is inherent to additive
synthesis, not a defect of the port.

## Coverage and quality (measured)

Run `python3 tools/modern_coverage.py --coverage` (no model needed) and
`--wer` (needs `onnx-asr`, `scipy`, `jiwer` and a cached Parakeet model).

### Symbol coverage

Over a set spanning English, French, German, Spanish, Portuguese, Italian,
Mandarin, Dutch and Arabic (61 distinct IPA symbols, including nasal vowels,
front-rounded `/y ø œ/`, uvular `/ʁ χ/`, palatal `/ʎ ɲ ç/`, alveolo-palatal
`/ɕ/`, velar `/x/` and pharyngeal `/ħ/`):

| metric | ModernTalk |
|---|---|
| distinct IPA symbols | 61 |
| synthesized from features | **61 (100%)** |
| nearest-target fallback | 0 |

Every symbol in the set is synthesized from its features; none collapses to an
English preset. The nearest-target fallback (an articulatory-distance search over
reachable phones, adapted from `phonematcher`'s weighted feature distance) exists
for symbols outside the tables — clicks, ejectives and other non-pulmonic sounds
that the model does not yet represent — and only then.

### English intelligibility (ASR word error rate)

Word error rate is a proxy for intelligibility, not a measure of it: Parakeet was
trained on human speech and penalises a voice for being synthetic as well as for
being unclear. The gate is the **expanded, fixed thirteen-sentence set** in
`tools/modern_coverage.py` — the ten Harvard-style sentences of
`tools/intelligibility.py` transcribed in broad GenAm, plus three
phonetically-varied lines — so it is not gameable on a handful of short phrases.
Two reference bounds are measured on the same set and ASR: the classic **text**
path (`DECtalkEngine.synthesize`, the intelligible upper reference) and the
classic **IPA nearest-preset** path (`MacInTalkEngine.say_ipa`).

| path | WER |
|---|---|
| classic **text** path (DECtalk `synthesize`) — reference upper bound | **0.400** |
| classic IPA → nearest English preset (MacInTalk `say_ipa`) | **0.611** |
| ModernTalk (generative Klatt) — **before** the prosody layer | **0.989** |
| ModernTalk (generative Klatt) — **after** the prosody layer | **0.905** |

Adding the prosody/timing/coarticulation layer moved ModernTalk from near-total
gibberish (**0.989**) down to **0.905** on this expanded set — a **0.084**
reduction, closing roughly a fifth of the gap to the classic IPA-preset path.
Component-by-component, as a leave-one-out ablation from the full 0.905 config
(toggle each component off via the `MP_*` environment gates the harness reads):

| configuration | WER | change vs full |
|---|---|---|
| **full prosody (all components)** | **0.905** | — |
| − segment durations (Klatt 1979) | 0.958 | +0.053 |
| − intonation / F0 (hat pattern) | 0.979 | +0.074 |
| − word-boundary timing | 0.979 | +0.074 |
| − vowel reduction (Lindblom) | 0.926 | +0.021 |
| − coarticulation (locus transitions) | 0.905 | +0.000 |
| bare IPA, no prosody at all (baseline) | 0.989 | +0.084 |

Every number is from an actual `tools/modern_coverage.py --wer` run (Parakeet
`istupakov/parakeet-tdt-0.6b-v2-onnx`). Read these honestly: on thirteen
seven-word sentences the ASR carries roughly ±0.03–0.04 of run-to-run noise, so
the individual leave-one-out deltas are indicative, not exact — durations, F0 and
word-boundary timing are the robust wins, and the *full* combination is at least
as good as any ablation of it (no component makes it worse). Coarticulation is
WER-neutral on this set but perceptually load-bearing (without it formants jump
at every boundary); it is kept for that reason, exactly as the earlier consonant
loci were.

**Be plain: on English, ModernTalk (0.905) is still well short of the classic
text path (0.400) and behind the nearest-preset path (0.611).** The prosody layer
makes it produce connected, word-like speech — the recognizer now returns real
English fragments and words ("dark", "the small pup … the sock", "side by side")
rather than pure filler — but it does not close the gap to a front end that was
built and tuned for English. The remaining distance is acoustic front-end
quality, not prosody.

### Which sounds remain weak (honest, per-class)

- **Overall segmental clarity.** The biggest remaining error source is not
  prosody but the per-segment acoustics on this synth: vowels and especially
  consonant noise are still coarse, so whole words are misheard even with correct
  timing and F0.
- **Word boundaries** are now timed (pre-boundary lengthening + a short
  inter-word transition, no hard silence), which helps, but the ASR still fuses
  some adjacent words in the continuous stream.
- **Liquids `/l/` and dark-`/l/`.** A single alveolar locus; no clear/dark
  allophony, no proper lateral-channel antiresonance.
- **Stops in clusters** (`/kw/`, `/st/`, `/kt/`) blur — the one-frame burst plus
  fixed VOT does not fully separate a cluster's releases.
- **Vowel reduction** is deliberately gentle: strong centralisation toward schwa
  *hurt* WER (it erased the vowel identity), so function words remain a little
  over-articulated relative to natural English — the right trade for intelligibility.

The trade is deliberate: the classic path is more polished on the English it was
built for and **cannot attempt anything else**; ModernTalk attempts every sound
in the chart and, with the prosody layer, is now connected and word-like rather
than gibberish. Closing the rest of the gap needs better per-segment acoustics —
clear/dark `/l/` allophony, cluster VOT, richer frication — beyond the prosody
front end.

## Honest limitations

- **English polish.** ModernTalk trails the mature front ends on English WER
  (0.905 vs 0.611 nearest-preset, 0.400 classic text). The prosody layer took it
  from gibberish to connected speech; the rest is per-segment acoustic quality,
  not prosody — see the per-class weaknesses above.
- **No F4/F5 per phone.** The DECtalk frame slots expose F1–F3 (F4/F5 are fixed
  per speaker), so the higher formants that add vowel naturalness cannot be set
  from features on this synth.
- **Voice quality.** One glottal source setting; no breathiness, creak or
  register control. Voices differ only by pitch floor and the DECtalk speaker's
  vocal-tract scaling.
- **Non-pulmonic sounds.** Clicks, ejectives and implosives are not modelled;
  they resolve through nearest-target fallback. A click has no formant story a
  source-filter model tells naturally.
- **Trills** are amplitude modulation, not a real oscillating source.
- **ModernSAM** is a low-ceiling demonstration: buzzy obstruents, coarse
  formants, 8-bit output. It shows the feature model driving a second, weaker
  synthesizer; it is not meant to rival ModernTalk.

## Try it

```python
from pyretrotts.modern import ModernTalkEngine, ModernSAMEngine

ModernTalkEngine().say_ipa("bɔ̃ʒuʁ", path="bonjour.wav")   # French, nasal + /ʁ/
ModernTalkEngine().say_ipa("ˈkaʎe", path="calle.wav")      # Spanish palatal /ʎ/
ModernSAMEngine().say_ipa("ħaːl", path="haal_sam.wav")     # Arabic /ħ/, lo-fi
```

`python3 tools/modern_demo.py` renders a multilingual set on both engines for
listening. `python3 tools/modern_reel.py` renders an **A/B reel** at the correct
22050 Hz: each English sentence three ways — ModernTalk, the classic **text**
path and the classic IPA-preset path, side by side — plus the multilingual set
(which the classic paths cannot attempt).
