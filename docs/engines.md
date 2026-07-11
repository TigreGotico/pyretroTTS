# The three engines, compared

All three turn English into sound with a few hundred kilobytes of tables and
integer arithmetic. Two of them work the same way. The third does not, and the
difference is audible.

| | MacinTalk | DECtalk | SAM |
|---|---|---|---|
| Author | Tim Schaaff, Apple | Dennis Klatt et al., DEC | Don't Ask Software |
| Shipped | 1991-1995 | 1984 | 1982 |
| Synthesis | Klatt source-filter | Klatt source-filter | additive, 3 oscillators |
| Voices | 17 named | 10 named | 4 knobs, 6 presets here |
| Phonemes | 56 | 55 used here | 81 slots |
| Dictionary | 7,173 words | its own, not distributed | none |
| Markup | `[[pbas 60]]` | `[:ra 170]`, `weh<250,13>` | stress digits |
| Native output | 16-bit, 22050 Hz | 16-bit | 8-bit unsigned, 22050 Hz |
| Ported here | fully, bit-exact | phoneme→PCM bit-exact; rules+morphology front end | fully, bit-exact |

## How they make sound

### MacinTalk and DECtalk: a model of a throat

Both descend from Dennis Klatt's research at MIT, and both are **source-filter**
synthesizers. A source — a buzz for voiced sounds, a hiss for unvoiced ones —
is pushed through a bank of resonant filters. Each filter is tuned to a formant:
one of the peaks the vocal tract's shape imposes on the spectrum. Move the
formants and you move the tongue.

That architecture is why a voice is nothing but a parameter table. `Fred` and
`Zarvox` run the same code over different numbers: 72 keys for pitch, formant
frequencies and bandwidths, breathiness, nasal coupling, reverb.
`docs/creating-voices.md` walks through building one.

It is also why these engines can whisper (drop the buzz, keep the hiss) and
sing (hold the pitch flat and put a note on each phoneme). The model has a
place for those things because a throat does.

### SAM: three oscillators and a table of clicks

SAM is not a formant synthesizer, whatever its resemblance suggests. There is no
filter and no feedback. `sam/render.py:343-346` is the entire voiced source:

```python
tmp = MULTTABLE[SINUS[phase1] | self.amplitude1[y]]
tmp += MULTTABLE[SINUS[phase2] | self.amplitude2[y]]
tmp += 1 if tmp > 255 else 0          # the 6502's carry flag
tmp += MULTTABLE[RECTANGLE[phase3] | self.amplitude3[y]]
```

Two sine oscillators and a rectangle wave, summed open-loop. Each is given a
frequency and an amplitude per 10 ms frame, and the frame tables are indexed by
phoneme. Consonants that cannot be approximated that way — the fricatives, the
plosive bursts — are played back from a 1-bit compressed sample table.

This is **additive synthesis** imitating a formant synthesizer's output rather
than modelling its cause. The three oscillators sit roughly where F1, F2 and F3
would be. Nothing enforces that they behave like resonances, and they do not.

The consequences are concrete. SAM's `throat` and `mouth` knobs rewrite the F1
and F2 frequency tables directly (`sam/render.py:114-123`) rather than scaling a
vocal tract, so the voices are transformations of a curve, not of an anatomy.
Its pitch arithmetic is eight-bit and, as the singing code discovered, **not
monotonic**: some pitch values render an octave from where the arithmetic says
they should. And every sample is an unsigned byte, masked at each step, because
a 6502 had nothing wider.

## What `DECtalkEngine` is

It is a genuine port of the DECtalk synthesizer, built from the DECtalk C
source rather than layered over MacinTalk. Phoneme-to-PCM synthesis is bit-exact
against the reference for all ten voices, and the US-English text front end —
dictionary lookup, letter-to-sound rules, inflectional morphology, number and
currency expansion, sentence framing, and punctuation-driven intonation — is
ported and bit-exact over a large scope.

`DECtalkEngine.synthesize` renders natively through the DECtalk synthesizer for
the ten voices when a DECtalk dictionary is installed, and substitutes the
nearest MacinTalk voice otherwise. The DECtalk dictionary itself is not
distributed (licensing), so out of the box the front end pronounces every word
from its letter-to-sound rules and morphology rather than from dictionary
lookups. Install a DECtalk dictionary to restore dictionary pronunciations.

[dectalk.md](dectalk.md) is the authoritative reference for the DECtalk port:
every stage, its module, and its measured parity.

## How they decide what to say

Each engine has its own front end, ported from its own source.

MacinTalk's has three stages: look the word up in a 7,173-word dictionary;
failing that, strip a suffix and look up the root; failing that, sound it out
with letter-to-sound rules. It knows that `photograph` flaps its `t`, because
the word is in the book.

DECtalk's has the same shape but its own rules and morphology. Its dictionary is
not distributed, so it sounds words out from its letter-to-sound rules and
inflectional morphology, and consults a dictionary only when one is installed.

SAM has no dictionary. Its reciter is rules alone. It sounds every word out,
which is why it says `photograph` as `F AA T AA G R AE F` — two flat `AA`s where
MacinTalk has `OW` and `AX`, and no flap. It is smaller, faster, and wronger.

All three front ends are exposed without synthesis, in `pyretrotts.g2p`. Each
returns its own engine's phonemes in its own notation:

```python
>>> phonemize("photograph")
['f', 'OW', 'DX', 'AX', 'g', 'r', 'AE', 'f']
>>> phonemize("photograph", engine="dectalk")
['f', 'ow', 't', 'ax', 'g', 'r', 'ae', 'f']
>>> phonemize("photograph", engine="sam")
['F', 'AA', 'T', 'AA', 'G', 'R', 'AE', 'F']
```

See [g2p.md](g2p.md) for the full API.

## How they are told what to do

Each engine has its own inline markup, and they are not compatible.

```
MacinTalk   [[rate 240]] [[pbas 60]] [[note 60.4]] [[char LTRL]]
DECtalk     [:ra 170] [:dv hs 95] [:np] weh<250,13>
SAM         /HEHLOW, stress digits: AA5
```

`pyretrotts.translate` maps between the first two. Every one of DECtalk's 55
phonemes has a MacinTalk mnemonic, so phonemes and pitch survive a round trip
exactly. Duration does not: DECtalk times each phoneme in milliseconds, while
MacinTalk gives a note one of twelve tempo-derived length codes, so 350 ms comes
back as 375.

`SAMEngine.sing` reads a DECtalk score directly. SAM's phoneme inventory is
coarser — no `yu`, no distinct r-coloured vowels, one `t` where DECtalk also has
`tx` — so `DECTALK_TO_SAM` collapses several. Notes land within a semitone.

## Which is the most intelligible

`tools/intelligibility.py` renders ten phonetically varied sentences in every
voice, runs them through the Parakeet speech recognizer, and reports word error
rate. That is a proxy, not a verdict: the recognizer was trained on human speech
and penalizes a voice for being synthetic as well as for being unclear. The
ranking is worth more than the numbers.

Only MacinTalk and SAM appear below.

| WER | voice | |
|---:|---|---|
| 14.9% | Junior | the clearest voice here |
| 19.7% | Cellos | |
| 20.9% | Ralph | |
| 21.2% | Bad News | |
| 22.7% | Whisper, Trinoids | |
| 22.8% | Kathy, Princess | |
| 24.9% | **Fred** | the default, and middling |
| 25.6% | Boing | |
| 26.3% | Zarvox | |
| 32.5% | Pipe Organ | |
| 35.6% | Good News | |
| 41.9% | Deranged | |
| 52.2% | Bells | |
| 55.3% | SAM, Little Old Lady | the best SAM manages |
| 57.0% | SAM, Sam | the default SAM voice |
| 67-70% | SAM, the other four presets | |
| 74.9% | Bubbles | |
| 87.0% | Hysterical | barely words at all |

Two things stand out. `Fred`, the voice everyone remembers, is not
MacinTalk's clearest -- `Junior` beats it by ten points, and even the singing
`Cellos` is easier to transcribe. And **the whole of SAM sits below the worst
ordinary MacinTalk voice.** Nine years and a filter bank are the difference
between 25% and 57%.

The novelty voices deserve their scores. `Bubbles` and `Hysterical` are the two
that drive the formant model from a sampled glottal source; the recognizer hears
gurgling and laughter, and so do you.

## Which one to use

Use **MacinTalk** for a Macintosh-era voice with the full English front end:
dictionary, morphology, allophone rules, real part-of-speech tagging, and
seventeen voices, ported bit-exact end to end.

Use **DECtalk** for Perfect Paul and its nine siblings, and for singing. Its
synthesizer is ported and its phoneme-to-PCM output is bit-exact for all ten
voices; its singing notation gives every phoneme an explicit duration and pitch,
which is what four decades of hand-written songs are written in. Native voices
require a DECtalk dictionary to be installed; without one, the front end
pronounces from rules and morphology, and `DECtalkEngine` substitutes the
nearest MacinTalk voice. See [dectalk.md](dectalk.md).

Use **SAM** when you want a 1982 Commodore 64 to talk. It needs no dictionary
and sounds exactly like what it is.

## History

`docs/history.md` has the long version: Klatt at MIT, DEC's 1984 machine,
Stephen Hawking's Perfect Paul, Apple's Macintosh voices, and why Fred is not
Perfect Paul.

The short version is that DECtalk and MacinTalk are cousins, born eight years
apart from the same research, and SAM is a stranger that arrived first and
sounds it.
