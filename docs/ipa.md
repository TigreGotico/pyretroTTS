# IPA input

Every engine here has its own English-centric phoneme alphabet. IPA mode makes
IPA a universal input notation on top of them: give an engine an IPA string, it
translates that IPA into its own internal phones and renders them through its
existing synthesis seam. No text front end runs, and no golden path changes —
the classic voices stay bit-for-bit identical.

## Saying IPA

`Engine.say_ipa` is on all three engines:

```python
from pyretrotts import MacInTalkEngine, DECtalkEngine, SAMEngine

MacInTalkEngine().say_ipa("həˈloʊ wɝld", path="hello.wav")
DECtalkEngine().say_ipa("fəˈnɛtɪk")          # -> raw 16-bit PCM
SAMEngine().say_ipa("aɪ æm sæm", voice="Little Robot")
```

`say_ipa(ipa, voice=None, path=None) -> bytes` returns raw 16-bit mono PCM and,
when `path` is given, also writes a WAV at the engine's sample rate. The DECtalk
IPA render runs the ported phoneme synthesizer (no FONIX dictionary required)
and doubles its 11025 Hz core to 22050 Hz, so every engine reports one rate.

The IPA it accepts:

- **Stress** — a leading `ˈ` (primary) or `ˌ` (secondary) attaches to the
  following vowel and drives each engine's stress mechanism.
- **Diphthongs** — `eɪ aɪ ɔɪ aʊ oʊ` are read as single segments.
- **Affricates** — `tʃ dʒ`.
- **r-coloured vowels** — `ɚ ɝ` and `ɪɚ ɛɚ ɑɚ ɔɚ ʊɚ`.
- **Diacritics** — `ː` (length) and a combining tilde (nasalization) are
  absorbed onto the vowel they modify. Neither is representable in any engine,
  so both drop to the base vowel (see the loss table).

Duration and pitch are engine-decided defaults; IPA carries stress, not a
prosodic contour.

## Inspecting what an engine will say

`phonemize` gains a `notation` argument. The default, `"native"`, is unchanged;
`"ipa"` re-expresses the engine's own front-end output as IPA:

```python
from pyretrotts.g2p import phonemize

phonemize("photograph")                      # ['f', 'OW', 'DX', 'AX', ...]
phonemize("photograph", notation="ipa")      # ['f', 'oʊ', 'ɾ', 'ə', ...]
phonemize("photograph", "sam", notation="ipa")
```

## The mapping approach

Each engine has two tables: IPA to its own phoneme, and its phoneme back to a
canonical IPA. Consonants map nearly one to one. General American vowels have
faithful targets. An IPA segment with no faithful target falls back to the
nearest available one — length and nasalization drop to the base vowel, an
unmapped symbol drops to schwa — and every fallback is recorded (see
`pyretrotts.ipa.Fallback` and the second return value of `ipa_to_native`).

`ipa_to_native(engine, clauses)` returns the engine's synthesis input — a list
of `PhonemePlan` for MacinTalk, a list of DECtalk `Clause`, or a SAM mnemonic
string — paired with the fallbacks. `native_to_ipa(engine, ids)` runs the
reverse.

## Per-engine loss

The loss is structural, not tunable: the inventories were built for English.

| Feature | MacinTalk | DECtalk | SAM |
|---|---|---|---|
| Consonants | ~1:1 | ~1:1 | ~1:1 (no `/ʒ/`… present) |
| GA vowels | faithful | faithful | faithful |
| `ɑ` vs `ɒ` | collapse to one | collapse to one | collapse to one |
| `/ju/` | dedicated vowel | dedicated vowel | collapses to `u` |
| r-coloured vowels | `ɪɚ ɛɚ ɑɚ ɔɚ ʊɚ` distinct | `ɛɚ` reduces to `ER`; rest distinct | all collapse to `ER`/`AA`/`AO`/`UH` |
| Vowel length `ː` | dropped | dropped | dropped |
| Nasalization | dropped | dropped | dropped |
| Non-English vowels | nearest GA vowel | nearest GA vowel | nearest GA vowel |

Measured segment fidelity on a General American word set, running each engine's
own front end and mapping its phonemes out to IPA and back
(`native -> IPA -> native`): MacinTalk **100%**, DECtalk **99%**, SAM **98.9%**.
Going the other way (`IPA -> native -> IPA`), SAM is the coarsest: `/ju/` and
every r-coloured vowel survive on the Klatt engines but collapse on SAM.

The summary strings are available at runtime as `pyretrotts.ipa.IPA_LOSS`.
