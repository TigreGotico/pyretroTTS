# pylintalker

A standalone Python port of **DECtalk** — the formant speech synthesizer
behind Stephen Hawking's voice, decades of screen readers, and one of
the most recognizable "robot voices" in computing history. No neural
network, no audio corpus, no GPU: just a physical model of the human
vocal tract, driven by a few hundred kilobytes of tables and rules, the
same way it worked in 1984.

```python
from pylintalker.api import synthesize_text, pcm_to_wav
from pylintalker._data import Fred_Voice

pcm = synthesize_text(Fred_Voice, "hello, this is a test.")
pcm_to_wav(pcm, "out.wav")
```

That's it — plain text in, a WAV file out, computed in real time on
whatever you're running this on right now.

This package has no OVOS/plugin dependencies and no external runtime
dependencies at all; it's a plain, standalone synthesizer library. An
OVOS TTS plugin wrapper around it lives in a separate repo.

## Why DECtalk

Read `docs/history.md` for the full story — the short version: Dennis
Klatt's formant-synthesis research at MIT became DECtalk in 1984, one of
the first computers that could read arbitrary text aloud in real time on
commodity hardware. Its "Perfect Paul" voice became world-famous as
Stephen Hawking's voice for over three decades. Its novelty voices
(Zarvox, Trinoids, Whisper...) are still a cultural shorthand for "how
computers used to sound." And because the whole engine is deterministic
arithmetic over small parameter tables — no training data, no model
weights, no corpus — it remains genuinely useful today: tiny, fully
inspectable, and endlessly re-tunable into new voices.

## How it works, in one paragraph

Text goes through a pipeline mirroring the original engine step for
step: **tokenize** into words and punctuation → look each word up in a
**pronunciation dictionary**, or strip a suffix and infer a pronunciation
from a known root (**morphology**), or fall back to **letter-to-sound
rules** for anything else → tag each word's **part of speech** and place
**phrase boundaries** and **sentence stress** → expand numbers, dates,
currency, and clock times into words → convert the resulting word list
into a stream of **phonemes** (the ~70 distinct speech sounds English
uses) with **allophone** adjustments (flapped T, dark L, R-coloring, and
so on) → assign each phoneme a **duration** and a place on the sentence's
**pitch contour** → and finally drive a **formant synthesizer** — a
cascade of resonant filters modeling the vocal tract, fed by a
buzzing/hissing source modeling the vocal cords — frame by frame into
raw PCM audio. Every one of those stages is a small, readable Python
module; see `docs/architecture.md` for exactly which C source file each
one replaces and how to verify it, and `docs/creating-voices.md` for the
formant-synthesis theory in depth and how to build an entirely new voice
from scratch.

## Install

```bash
uv pip install pylintalker
```

## Usage

```python
from pylintalker.api import synthesize_text, pcm_to_wav
from pylintalker._data import Fred_Voice

pcm = synthesize_text(Fred_Voice, "hello, this is a test.")
pcm_to_wav(pcm, "out.wav")
```

Numbers, dates, currency, and embedded commands all work out of the box:

```python
from pylintalker.api import synthesize_text, pcm_to_wav
from pylintalker._data import Fred_Voice

text = (
    "In 1984, Mr. Smith paid $5.25 for a coffee at 3:45. "
    "[[char LTRL]]DEC[[char NORM]] made this. [[rate240]]Now I'm talking fast!"
)
pcm = synthesize_text(Fred_Voice, text)
pcm_to_wav(pcm, "out.wav")
```

Or work directly with a phoneme plan, bypassing the text frontend
entirely:

```python
from pylintalker.api import synthesize_phonemes, pcm_to_wav
from pylintalker._data import Fred_Voice

# a phoneme plan for "hi" (see pylintalker/_phonemes.py for phoneme ids)
phonemes = [23, 11, 54, 3, 33, 22, 23]
ctrls = [1, 268500993, 0, 268502089, 9, 16393, 2621440]
durs = [1, 26, 10, 54, 23, 5, 135]

pcm = synthesize_phonemes(Fred_Voice, phonemes, ctrls, durs)
pcm_to_wav(pcm, "out.wav")
```

See `examples/` for runnable versions of all of the above, plus a
single-word letter-to-sound example and a voice-listing script.

## Voices

All 17 original DECtalk voices, verified bit-exact against the
reference engine:

**Fred**, **Kathy**, **Princess**, **Junior**, **Ralph**, **Whisper** —
the ordinary male/female/child/breathy registers — plus the novelty
voices **Zarvox**, **Trinoids**, **Bubbles**, **Boing**, **Bells**,
**Hysterical**, **Deranged**, **GoodNews**, **BadNews**, **PipeOrgan**,
and **Cellos**. Each is nothing more than a different parameter table
fed into the same formant model (`pylintalker/_data.py`) — see
`docs/creating-voices.md` to build your own.

## Text features

Beyond plain word-by-word synthesis, the text frontend supports:

- **Numbers**: cardinals ("123" → "one hundred and twenty three"),
  years ("1984" → "nineteen eighty-four"), currency ("$5.25" → "five
  dollars and twenty five cents"), decimals ("3.14" → "three point one
  four"), and clock times ("3:45" → "three forty five").
- **Abbreviations**: "Mr.", "Dr.", "St." and other dictionary
  abbreviations don't end a sentence at their period.
- **Morphology**: suffixes like `-ED`, `-ING`, `-S`, `-LY`, `-EST`,
  `-MENT`, `-NESS`, `-IZE` and more are stripped and reattached to a
  known root's real pronunciation, instead of falling through to
  generic letter-to-sound guessing.
- **Prosody**: sentence-level stress, phrase boundaries, and
  question/statement pitch contours driven by real part-of-speech
  tagging, not word lists.
- **Embedded bracket commands**, DECtalk's original inline control
  syntax: pitch/pitch-modulation/volume changes, word emphasis, inserted
  silence, part-of-speech overrides, speaking-rate changes, digit-by-
  digit number reading, letter-by-letter word spelling, and raw phoneme
  mnemonic input — see `docs/architecture.md` for the full command
  reference and exact positioning semantics.

`docs/architecture.md` documents this feature-by-feature against the
original C source, including the handful of narrow, deliberately
unported corners (see its "Known gaps" section).

## Testing

```bash
uv pip install -e .[test]
pytest test/
```

The test suite compares this port's output against a compiled build of
the original C reference frame-by-frame and sample-by-sample — not just
"does it sound plausible," but bit-exact numeric agreement with the
original engine's internal state, across all 17 voices and a wide range
of text. See `docs/architecture.md` for how to build the C reference
locally if you want to run that comparison yourself.

## License

Apache-2.0
