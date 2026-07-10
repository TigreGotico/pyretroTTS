# Two synthesizers, one ancestor

`pyretrotts` ports two engines. Both are formant synthesizers, both descend
from the same research, and they are routinely confused with each other —
including, for a while, by this repository's own documentation.

## Origins: MIT and the Klatt synthesizer

In the 1970s, MIT researcher **Dennis Klatt** built one of the first
computational models of how the human vocal tract shapes sound into speech: a
**formant synthesizer**. Rather than splicing together recordings of a real
voice, it generates speech from a physical model of resonance, energy source,
and articulation, driven entirely by numbers. Refined through the **MITalk**
text-to-speech system across the late 1970s, Klatt's synthesizer became the
technical ancestor of nearly every "classic robot voice" people associate with
computer speech.

Two commercial descendants matter here.

## DECtalk (Digital Equipment Corporation, 1984)

DEC commercialized Klatt's work as **DECtalk**, first shipping in 1984 as a
standalone hardware box — the DECtalk DTC01 — that took plain text over a
serial port and spoke it through a built-in speaker. It was remarkably
intelligible for the time, and cheap enough in CPU terms to run in real time on
1980s hardware, which is exactly why formant synthesis rather than
sample concatenation was the practical choice.

Its voices were **Perfect Paul**, **Beautiful Betty**, **Huge Harry**, **Frail
Frank**, **Doctor Dennis**, **Kit the Kid**, **Uppity Ursula**, **Rough Rita**,
**Whispering Wendy**, and **Variable Val**.

DECtalk's most famous association is with physicist **Stephen Hawking**, who
began using a DECtalk-based synthesizer — the **CallText 5010**, running the
DECtalk engine in the Perfect Paul voice — after losing his own voice to a
tracheotomy in 1985. He kept that exact voice for the rest of his life by
choice, turning down later, more natural-sounding replacements because they no
longer sounded like *him*.

DECtalk also accepts a distinctive inline markup: `[:phone on]`, `[:ra 170]`,
`[:dv ...]`, and a singing notation, `weh<250,13>`, that gives every phoneme an
explicit duration and pitch. A large amateur corpus of songs written in that
notation still circulates.

## MacinTalk (Apple Computer, 1991-1995)

Apple built its own Klatt-derived formant synthesizer for the Macintosh. The C
source this port is built from carries the banner *"Contains: Implementation of
MacInTalk2 FrontEnd. Written by: Tim Schaaff. Copyright © 1991-1992 by Apple
Computer, Inc."*, and its version string reads `1.4d7, © Apple Computer, Inc.
1994`.

Its voices are the ones Mac users know from `say -v`: **Fred**, **Kathy**,
**Princess**, **Junior**, **Ralph**, **Whisper**, plus a cast of novelty voices
showing how far one parameter set can be pushed — **Zarvox**, **Trinoids**,
**Bubbles**, **Boing**, **Bells**, **Hysterical**, **Deranged**, **Good News**,
**Bad News**, **Pipe Organ**, and **Cellos**. Several of the last few drive the
formant model from a musical note script instead of ordinary prosody, turning
speech into something closer to chanting.

MacinTalk's inline markup uses different delimiters: `[[pbas 60]]`,
`[[rate 240]]`, `[[char LTRL]]`.

Fred is not Perfect Paul. They are different engines, by different authors, at
different companies. Neither voice ever spoke for Stephen Hawking except
Perfect Paul.

## Cultural legacy

Because both engines were cheap, fast, and easy to interface with, they ended
up far beyond their original assistive-technology and telephony markets.

- Both were common **screen-reader** voices through the 1990s, long before
  natural-sounding TTS was computationally affordable.
- Both became recognizable in **music production**, sampled as vocal effects
  precisely for their unmistakably synthetic timbre. DECtalk's singing notation
  in particular spawned a whole genre of hand-transcribed songs.
- The novelty voices still serve as shorthand for "how computers used to
  sound."
- Descendants of the DECtalk engine remained in assistive-technology and
  telephony products long after formant synthesis was superseded for mainstream
  use. Intelligibility at very low computational cost, and total independence
  from any recorded corpus, remained genuinely useful properties.

## Why formant synthesis still matters

Modern TTS — concatenative unit selection, and especially neural
sequence-to-sequence and diffusion models — sounds dramatically more natural.
But formant synthesis has properties neither of those can offer:

- **No training data or corpus.** The entire "model" is a few hundred small
  parameter tables, not a multi-hour recorded voice or a network's weights.
- **Deterministic and tiny.** Rules and tables fit in a few hundred kilobytes
  and run in real time on decades-old hardware. No GPU, no inference latency,
  no model to load.
- **Every voice is a parameter set.** Building a new voice, or a deliberately
  inhuman one, means tuning formant, bandwidth, and pitch parameters — not
  recording and training on a new corpus. See
  [creating-voices.md](creating-voices.md).
- **Fully inspectable.** Every stage from text to waveform is explicit,
  deterministic arithmetic. There is no black box to probe.

See [architecture.md](architecture.md) for how the MacinTalk engine maps onto
this codebase, and [dectalk-port-plan.md](dectalk-port-plan.md) for the state
of the DECtalk port.
