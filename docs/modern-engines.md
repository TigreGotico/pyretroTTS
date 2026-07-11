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
classic nearest-English-preset path (`MacInTalkEngine.say_ipa`), over the fixed
ten-sentence set in `tools/modern_coverage.py`:

| path | WER |
|---|---|
| classic IPA → nearest English preset (MacInTalk) | **0.886** |
| ModernTalk (generative Klatt) | **0.943** |

Both numbers are poor in absolute terms, as expected for 1980s-era synthesis
scored by a modern ASR; the comparison is what matters. **The gap to the classic
path has been closed from ~0.11 to 0.057** by acoustic-data-grounded parameter
tuning:

| iteration | change | ModernTalk WER |
|---|---|---|
| 0 | prototype | 1.000 |
| 1 | English vowel formants calibrated to the DECtalk US target ROM (F3 band correction; Hillenbrand 1995 cross-check) | 0.943 |
| 2 | DECtalk-anchored consonant place loci + low-F3 English rhotic `/ɹ/` | 0.943 |

Every number above is from an actual `tools/modern_coverage.py --wer` run
(Parakeet `istupakov/parakeet-tdt-0.6b-v2-onnx`). Iteration 1 gives the whole
measurable gain; the iteration-2 consonant loci are WER-neutral on this small set
but acoustically more correct (they are pinned to the DECtalk ROM and locus
theory), and were kept for that reason.

**Be plain: on English, ModernTalk is still not quite as intelligible as the
mature nearest-preset path (0.943 vs 0.886).** After the vowel calibration it
produces connected, word-like speech — the recognizer returns real English
fragments ("please all the stellar", "small button", "we have a meal") rather
than filler — and its vowels now land in the DECtalk cascade's tuned region. WER
then **plateaus at 0.943**: a sweep of vowel/consonant duration, source
amplitudes, burst level, stop-closure length, aspiration, F0 declination and
stress, and word-boundary pausing did not beat it on this set, and forcing lower
would mean overfitting ten fixed sentences.

### Which sounds remain weak (honest, per-class)

- **Word boundaries.** `parse_ipa` drops the spaces between words, so a sentence
  is one continuous phone stream; the ASR fuses adjacent words ("She sells" →
  "He has"). Inserting per-word silence *hurt* WER (over-segmentation loses
  coarticulation), so the fix is real boundary-aware timing, not blank frames.
- **Liquids `/l/` and dark-`/l/`.** A single alveolar locus; no clear/dark
  allophony, no proper lateral-channel antiresonance.
- **Stops in clusters** (`/kw/`, `/st/`, `/kt/`) blur — the one-frame burst plus
  fixed VOT does not fully separate a cluster's releases.
- **Unstressed / reduced vowels** are not reduced or shortened enough, so
  function words are over-articulated relative to natural English.

The trade is deliberate: the classic path is more polished on the English it was
built for and **cannot attempt anything else**; ModernTalk is now within 0.06 WER
of it on English *and* attempts every sound in the chart. Closing the last of the
gap needs word-boundary-aware timing, clear/dark `/l/` allophony, cluster VOT and
vowel reduction — structural front-end work beyond steady-target tuning.

## Honest limitations

- **English polish.** ModernTalk trails the mature front end on English WER
  (0.943 vs 0.886). It needs word-boundary-aware timing and allophonics, not just
  steady targets — see the per-class weaknesses above.
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
listening. `python3 tools/modern_reel.py` renders an **A/B reel**: each English
sentence through ModernTalk *and* the classic path side by side, plus the
multilingual set (which the classic path cannot attempt).
