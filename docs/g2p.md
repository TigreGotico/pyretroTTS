# Grapheme-to-phoneme: `pyretrotts.g2p`

Every engine has to know how to pronounce a word before it can synthesize one,
so each carries a complete grapheme-to-phoneme (G2P) front end. This module
exposes those front ends on their own, turning written English into the phonemes
an engine would say, with no audio produced. It is the tool for inspecting what
an engine will pronounce, for feeding another synthesizer, or for studying how
the three engines disagree.

## The three front ends

Each engine returns its own phonemes in its own notation, ported from its own
source. They are not meant to agree.

| Engine | Front end | Notation |
|---|---|---|
| `macintalk` (default) | 7,173-word dictionary → suffix-stripping morphology → letter-to-sound rules | MacinTalk mnemonics (`IY`, `p`, `AA`) |
| `dectalk` | DECtalk's own letter-to-sound rules and inflectional morphology, with number and punctuation expansion; dictionary lookup when one is installed | DECtalk mnemonics (`iy`, `p`, `aa`) |
| `sam` | SAM's reciter, a single rule engine with no dictionary | SAM mnemonics (`IY`, `P`, `AA`) |

```python
>>> from pyretrotts.g2p import phonemize
>>> phonemize("photograph")
['f', 'OW', 'DX', 'AX', 'g', 'r', 'AE', 'f']
>>> phonemize("photograph", engine="dectalk")
['f', 'ow', 't', 'ax', 'g', 'r', 'ae', 'f']
>>> phonemize("photograph", engine="sam")
['F', 'AA', 'T', 'AA', 'G', 'R', 'AE', 'F']
```

MacinTalk has the word in its dictionary and flaps the `t`; DECtalk and SAM sound
it out with their own rules and get flatter vowels.

## The DECtalk dictionary caveat

`phonemize(text, engine="dectalk")` runs DECtalk's own front end — genuine
DECtalk phonemes, its number expansion, and its inflectional morphology. The
DECtalk dictionary is not distributed with this package, so out of the box the
DECtalk front end pronounces every word from rules and morphology. Installing a
DECtalk dictionary gives it dictionary lookups.

## Markers

By default `phonemize` returns speech sounds only. With `markers=True`, the
MacinTalk and DECtalk front ends also emit the control symbols their engines
carry alongside the sounds — word boundaries, stress marks, and clause
terminators (for DECtalk, stress levels `s1`–`s3`, boundary markers, and
`period`/`quest`/`exclaim`). SAM has no such markers.

```python
>>> phonemize("cats.", engine="dectalk", markers=True)
```

## Word by word

`phonemize_words` keeps each word separate and reports whether the engine
recognized it or sounded it out:

```python
>>> from pyretrotts.g2p import phonemize_words
>>> for p in phonemize_words("the cats sat"):
...     print(p, "(dictionary)" if p.from_dictionary else "(rules)")
```

Each result is a `Pronunciation` with `word`, `phonemes`, and `from_dictionary`.
SAM has no dictionary, so `from_dictionary` is always `False` there; DECtalk
reports `True` only when an installed dictionary supplied the word.

## Related

- [engines.md](engines.md) — how the three engines compare, and how each front
  end feeds its synthesizer.
- [dectalk.md](dectalk.md) — the authoritative reference for DECtalk's front end
  and its measured parity.
