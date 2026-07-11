# pyretroTTS documentation

pyretroTTS is a set of standalone Python ports of three classic speech
synthesizers — the "robot voices" of 1980s and 1990s computing. No neural
network, no audio corpus, no GPU: a few hundred kilobytes of tables and rules,
and integer arithmetic. It ports **MacinTalk** (Apple), **DECtalk** (DEC/FONIX),
and **SAM** (SoftVoice), and reproduces the original voices sample for sample.

This page is the map. Two reading paths follow.

## Start here (newcomer path)

Read these in order to understand what pyretroTTS is and to make it talk.

1. **[history.md](history.md)** — what these three synthesizers are, where they
   came from, why Fred is not Perfect Paul, and why formant synthesis still
   matters.
2. **[engines.md](engines.md)** — the three engines compared side by side: how
   each makes sound, how each decides what to say, and which one to use.
3. **[creating-voices.md](creating-voices.md)** — formant synthesis from first
   principles, and a step-by-step tutorial for building your own voice.

The top-level [`README`](../README.md) has installation and the shortest
possible "text in, WAV out" examples.

## Reference (advanced path)

Jump straight to the internals.

- **[architecture.md](architecture.md)** — the MacinTalk engine: how each stage
  of the pipeline maps onto Apple's C source, the state it threads through, and
  how it is checked against the reference.
- **[dectalk.md](dectalk.md)** — the DECtalk engine: every stage of the port,
  its module, and its measured parity. The authoritative source for all DECtalk
  internals.
- **[sam.md](sam.md)** — the SAM engine: its additive (non-formant) synthesis
  model, its knob-preset voices, and the quirks the port preserves.
- **[precision.md](precision.md)** — the fixed-point arithmetic: what integer
  math costs, what an exact mode changes, and what has and has not been verified.
- **[g2p.md](g2p.md)** — the grapheme-to-phoneme API: all three front ends
  exposed without synthesis, the `markers` option, and the DECtalk-dictionary
  caveat.
- **[ipa.md](ipa.md)** — IPA as a universal input notation: `say_ipa`,
  `phonemize(notation="ipa")`, the per-engine mapping, and the honest loss table.

## The engines at a glance

| Engine | Origin | Synthesis | Port state | Reference |
|---|---|---|---|---|
| MacinTalk | Apple, 1991–1995 | Klatt source-filter | fully bit-exact, end to end | [architecture.md](architecture.md) |
| DECtalk | DEC/FONIX, 1984 | Klatt source-filter | phoneme→PCM bit-exact for ten voices; US-English front end from rules + morphology (native dictionary optional) | [dectalk.md](dectalk.md) |
| SAM | SoftVoice, 1982 | additive, 3 oscillators | fully bit-exact | [sam.md](sam.md) |

## Licensing

pyretroTTS itself is MIT. The SAM and DECtalk (FONIX) code and extracted data are
**not** MIT and live in their own subpackages under provenance headers — see
[`NOTICE`](../NOTICE). The top-level [`README`](../README.md) carries the full
authorship and derivation caveat; read it before copying or redistributing
anything here.
