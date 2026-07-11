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

Vowel formant targets are male-voice reference values from the acoustic-phonetics
literature: Peterson & Barney (1952) for the English monophthong cardinals, Klatt
(1980, "Software for a cascade/parallel formant synthesizer") for the
synthesis-tuned values, and Catford (1988) / Vallée (1994) for the non-English
cardinal and front-rounded vowels. The mapping is the classic one:

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
locus and a frication/burst spectral centre (locus values after Stevens 1998,
*Acoustic Phonetics*); manner picks the source configuration:

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

Formant transitions across phone boundaries — the coarticulation cue a listener
uses to hear place — come from a three-point moving average of F1/F2/F3 over
voiced frames. Stop closures and bursts are excluded so their onsets stay crisp.

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
Mandarin, Dutch and Arabic (57 distinct IPA symbols, including nasal vowels,
front-rounded `/y ø œ/`, uvular `/ʁ χ/`, palatal `/ʎ ɲ ç/`, alveolo-palatal
`/ɕ/`, velar `/x/` and pharyngeal `/ħ/`):

| metric | ModernTalk |
|---|---|
| distinct IPA symbols | 57 |
| synthesized from features | **57 (100%)** |
| nearest-target fallback | 0 |

Every symbol in the set is synthesized from its features; none collapses to an
English preset. The nearest-target fallback (an articulatory-distance search over
reachable phones, adapted from `phonematcher`'s weighted feature distance) exists
for symbols outside the tables — clicks, ejectives and other non-pulmonic sounds
that the model does not yet represent — and only then.

### English intelligibility (ASR word error rate)

Word error rate is a proxy for intelligibility, not a measure of it: Parakeet was
trained on human speech and penalises a voice for being synthetic as well as for
being unclear. Rendering the same English IPA through ModernTalk and through the
classic nearest-English-preset path (`MacInTalkEngine.say_ipa`), over ten short
sentences:

| path | WER |
|---|---|
| classic IPA → nearest English preset (MacinTalk) | **0.89** |
| ModernTalk (generative Klatt) | ~1.0 |

**Be plain about this: on English, the prototype is not yet as intelligible as
the mature nearest-preset path.** ModernTalk produces connected, word-like speech
— the recognizer returns real English phrases ("please always data", "certainly
it cannot") rather than filler — and its vowels are acoustically distinct
(measurable by the F2 split between `/i/`, `/ɑ/` and `/u/`). But its consonant
place cues and word boundaries are weaker than the classic front end's mature
allophonics, so the recognizer mishears words. Both numbers are poor in absolute
terms, as expected for 1980s-era synthesis scored by a modern ASR.

The trade is deliberate: the classic path is more polished on the English it was
built for and **cannot attempt anything else**; ModernTalk is rougher on English
but attempts every sound in the chart. Closing the English gap — better
coarticulation, allophonic rules, per-language duration and stress — is the
obvious next step.

## Honest limitations

- **English polish.** ModernTalk trails the mature front end on English WER
  (above). It needs real coarticulation and allophonics, not just steady targets.
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
listening.
