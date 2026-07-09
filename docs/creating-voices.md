# Creating a voice in lintalker: from zero to hero

This guide explains, from first principles, how DECtalk (and this port)
turns a set of ~70 numbers into a speaking voice, and walks through
building a new one. If you already know what a formant synthesizer is,
skip to ["The voice dict"](#the-voice-dict).

## Part 1: the theory

### 1.1 Why synthesized speech needs a "voice" at all

A recorded human voice is just a sequence of air-pressure measurements
(a waveform). If you want a computer to *generate* speech instead of
*playing back* a recording, you need a model that can produce a waveform
from a symbolic description ("here's the word CAT, here's how loud/fast/
high-pitched to say it"). DECtalk uses a **formant synthesizer**: instead
of storing recorded audio, it models the physics of the human vocal tract
directly. A "voice" in this scheme is a small set of parameters that bend
that physical model into sounding like a particular speaker (or a cartoon
robot, or a monster, or a chorus of bells).

### 1.2 The source-filter model

Human speech has two separable parts:

1. **The source** — energy from the lungs, either:
   - a periodic buzz from the vocal cords vibrating (voiced sounds: vowels,
     `b`, `d`, `g`, `m`, `n`, `z`...), whose repetition rate is the
     **pitch** (fundamental frequency, F0), or
   - turbulent noise from air forced through a constriction (unvoiced
     sounds: `s`, `f`, `t`, `p`, `k`...), which has no pitch, just hiss.
2. **The filter** — the vocal tract (throat, mouth, tongue, lips) reshapes
   that raw source into recognizable sounds by resonating at certain
   frequencies and damping others, the same way a guitar body's shape
   determines its tone regardless of the string.

This is exactly `_backend.py`'s `say_frame()`: it generates a
source (glottal pulse train for voiced sounds via `voiceWaveform`, noise
via a pseudo-random generator for unvoiced sounds) and runs it through a
cascade of resonant filters (formants).

### 1.3 Formants

The vocal tract's resonant frequencies are called **formants**, numbered
F1 (lowest) through F6. Each vowel has a distinctive *pattern* of formant
frequencies — that's literally what makes "ee" sound different from "ah":
say them out loud and feel your tongue/jaw move to different positions,
each position resonating at different frequencies.

- **F1** tracks tongue height (low F1 = tongue high, e.g. "ee"; high F1 =
  tongue low, e.g. "ah").
- **F2** tracks tongue front/back position (high F2 = tongue forward,
  e.g. "ee"; low F2 = tongue back, e.g. "oo").
- **F3-F6** shape timbre/voice "color" and consonant bursts more subtly;
  F3 in particular controls "R-coloring" (the difference between "ah" and
  "ar").

Each phoneme (see `_phonemes.py` for the full list DECtalk recognizes —
`_IY_` "ee", `_AA_` "ah", `_p_`, `_s_`, etc.) has its own target formant
frequencies, stored in `_data.py`'s big per-phoneme tables (`PhonPitchTbl`
and friends) — these are **shared across all voices** (a vowel's formant
*pattern* doesn't change between speakers). What a **voice** changes is
everything layered on top: how far apart the formants sit overall (a
bigger vocal tract = lower formants = a "deeper"/bigger-sounding voice),
how sharp or hissy each resonance is (bandwidth), how strong nasal
coupling is, how breathy or buzzy the glottal source is, and the pitch/
timing/emphasis behavior (prosody).

### 1.4 Prosody: pitch, duration, stress

Formants alone produce intelligible-but-flat speech ("robot voice"). What
makes speech sound alive is **prosody**:

- **Pitch contour** — F0 rises and falls over a sentence (a question
  rises at the end; a statement falls). See `_pitchcontour.py`
  (`Pitch_RaiseAndFall`) and `_pitchbuf.py` (`Fill_Pitch_Buf`) for how this
  port computes it, and `docs/architecture.md` for the pipeline.
- **Duration** — stressed syllables and phrase-final sounds get
  stretched; unstressed ones get compressed. See `_moduration.py`.
- **Stress** — which syllable in a word (and which word in a sentence) is
  emphasized.

A voice's parameters tune how *strongly* pitch rises/falls, how much
stress lengthens a vowel, etc. — the same underlying stress/duration/pitch
*algorithm* runs for every voice; the voice dict just scales its inputs
(see `VP_riseAmt`, `VP_stressGain`, etc. below).

### 1.5 "Special effect" voices are the same model, pushed further

`Bubbles`, `Boing`, `Deranged`, `Cellos`, `PipeOrgan` etc. aren't a
different synthesis engine — they're the *same* formant synthesizer with
parameters pushed to unusual extremes (huge chorus detuning, exaggerated
vibrato, sung note sequences instead of natural prosody) or driven from a
sampled/harmonic waveform instead of the default one. Once you understand
the parameter list below, these "characters" are just presets.

## Part 2: the voice dict

In this codebase, a voice is a plain Python `dict` (see `lintalker/_data.py`
for the 17 built-in ones: `Fred_Voice`, `Kathy_Voice`, ..., `Cellos_Voice`).
It's read once by `_backend.init_voice(vv, voice_dict)` (called from
`api.new_voice()`) to populate a `VoiceVar` instance — the mutable
"registers" the whole synthesis pipeline reads and writes as it runs.

There's no separate "voice registry" to update — a voice *is* its dict.
To make one usable, define the dict (see [Part 3](#part-3-building-a-new-voice))
and import it wherever you call `new_voice()`/`synthesize_text()`.

### 2.1 Core identity

| Key | Meaning |
|---|---|
| `pitch` | Baseline pitch in Hz (e.g. `97` for Fred — a fairly low male voice; higher = higher-pitched voice, e.g. Kathy/Princess use higher values). |
| `voice` | `0` = male formant tables, `1` = female formant tables (`kMaleTbls`/`kFemaleTbls`) — selects which base formant-frequency table `_data.py` uses as the "neutral" starting point before this voice's offsets are applied. |
| `rate` | Speaking rate in words per minute (normal ≈ 180). |
| `waveType` | `0` = harmonic-synthesis glottal source (`kUseHarm`, the default — the source is generated from `vWave`/`vWave1` harmonic coefficients). `1` = sampled source (`kUseSnd`, plays back a stored waveform — see `sndID`/`vWave` as a sample instead of harmonics). `2` = pitch-synced sampled source (`kUseSyncSnd`, used by Bells/Hysterical — **not fully ported**, see `docs/architecture.md`'s known gaps, so a new voice using this mode won't be validated against the C reference). |

### 2.2 Formant shaping

| Key | Meaning |
|---|---|
| `f4_Freq`, `f4_BW` | Formant 4 center frequency (Hz) and bandwidth (Hz) — bandwidth controls how "sharp" vs. "broad" the resonance peak is; narrow = ringing/tonal, wide = damped/breathy at that formant. |
| `f4p_Freq`/`f4p_BW`, `f5p_Freq`/`f5p_BW`, `f6p_Freq`(via `bw6_Par`)/`f6p_BW` | The "parallel" branch formants (4/5/6) — DECtalk's filter is a *cascade* of F1-F3 (each stage's output feeds the next, physically accurate for the main formants) plus a *parallel* bank for F4-F6 (each computed independently from the same source and summed — computationally cheaper and good enough for the less perceptually critical upper formants). |
| `f1_Offset`, `f2_Offset`, `f3_Offset` | Per-voice Hz offset applied to every vowel's table-driven F1/F2/F3 target — this is the single biggest lever for "voice color": shift all formants up for a smaller/higher-sounding vocal tract, down for a bigger/lower one. |
| `bwGain1`, `bwGain2`, `bwGain3` | Percentage scale (100 = unchanged) on F1/F2/F3 bandwidth — higher = breathier/softer resonance, lower = sharper/more tonal. |
| `locus` | Scales how strongly consonant-to-vowel transitions bend formants (the "locus" is the theoretical formant position a consonant is transitioning from/to) — affects how strongly consonants color adjacent vowels. |

### 2.3 Nasal coupling

| Key | Meaning |
|---|---|
| `nasal_Base`, `nasal_targ`, `nasal_BW` | The nasal resonance's starting frequency, target frequency, and bandwidth — controls how "nasal" (like a cold, or French nasal vowels) the voice sounds on nasal consonants (`m`, `n`, `NG`) and adjacent vowels. |
| `nasalAmt` | Overall nasal coupling amount/gain. |

### 2.4 Source character (glottal pulse / breathiness / noise)

| Key | Meaning |
|---|---|
| `vWave`, `vWave1` | 48-element harmonic-amplitude tables (only used when `waveType=0`/`kUseHarm`) defining the glottal pulse's harmonic content — this is literally the shape of one glottal-cycle waveform, expressed as Fourier coefficients, run through an inverse DFT (`_inv_dft` in `_backend.py`) once at voice-init time to produce the actual per-sample waveform the synthesizer plays back at the pitch-derived rate. `vWave1` is a second, independently-detuned copy used for `chorus`. |
| `vGain` | Overall gain (loudness, 0-100+ percent) applied to the glottal-source harmonic waveform. |
| `chorus` | Detuning amount between `vWave` and `vWave1`'s playback rates — small values give a natural "chorus" richness (multiple voices slightly out of tune, like a real larynx isn't a perfect oscillator); large values (Bubbles-style voices) sound washy/underwater. |
| `aGain`, `aCycle`, `AsperW` | Aspiration noise (breathiness) gain, its cycle/period, and its width — turns a clean tone into a breathy/whispery one (Whisper's defining parameter). |
| `nGain` | General frication/noise-source gain (used for unvoiced consonants like `s`/`f` and voiced-fricative noise components). |
| `sPitch`, `sGain`, `sndID` | Only relevant when `waveType != 0` (sampled source): MIDI-style pitch offset, sample gain, and which embedded sample (`Sounds.c`'s `*_Sound` blobs — **not ported**, see below) to use. |
| `customForm`, `vowelSync`, `loopPoint` | Advanced sampled-source controls (custom formant override, sample-loop alignment) — leave at defaults (`0`) unless you're deliberately building a sample-based voice, which this port doesn't fully support yet. |

### 2.5 Prosody scaling

These feed directly into `_pitchcontour.py`/`_pitchbuf.py`/`_moduration.py`
(all already-ported and bit-exact-verified — see `docs/architecture.md`),
so tuning them is safe and immediately audible without touching any
Python code.

| Key | Meaning |
|---|---|
| `stressGain` | How strongly a stressed syllable's pitch rises above baseline (percent scale). Higher = more sing-song/emphatic, lower = flatter/monotone. |
| `riseAmt`, `fallAmt` | Pitch delta (in internal units, roughly Hz-ish) at the sentence's first stressed vowel (rise) and last stressed vowel or clause boundary (fall) — the "main" intonation contour. |
| `riseAmt1`, `fallAmt1` | Secondary word-level rise/fall alternation for sentences with multiple stress groups (content/function word alternation). |
| `assertiveness` | Scales how strongly the pitch actually falls at sentence end (percent, `65536` = 100% in this fixed-point field specifically — note this one field uses 16.16 fixed point directly rather than a 0-100 percent, unlike most other percent-style fields here). |
| `baselineFall` | How much the overall pitch baseline declines over the course of a long utterance (natural "running out of air" droop). |
| `quickness` | How fast pitch transitions happen (snappy vs. gliding). |
| `pitchRange`, `intonation` | Percent scale (100 = unchanged) on overall pitch excursion range and general intonation liveliness. |
| `pitchCmdStep`, `durCmdStep`, `down_Ramp_Step` | Internal ramp step sizes for smoothing pitch/duration changes frame-to-frame — leave at Fred's defaults unless you're chasing a specific glitch. |
| `stressDurTime` | How long (ms) a stress's durational lengthening effect lasts. |
| `vibratoDepth1`, `vibratoDepth2`, `vibratoFreq` | Vibrato (periodic pitch wobble) depth (two components, for a richer non-sinusoidal wobble) and rate (Hz) — `0` depth = no vibrato. |
| `portamento` | For note-driven singing voices only (see 2.7): how quickly pitch glides between notes rather than jumping. |

### 2.6 Rate/reverb/misc

| Key | Meaning |
|---|---|
| `tempo` | Beats-per-minute used ONLY by note-driven singing voices (see 2.7) to convert note lengths (16th/8th/quarter/... notes) into actual milliseconds via `_engine.e_set_tempo`. Irrelevant for normal (non-singing) voices. |
| `rvbDelay`, `rvbDepth`, `rvbWetDry` | Simple reverb effect parameters (delay time, feedback depth, wet/dry mix). |
| `emphVoice` | Whether/how this voice responds to emphasis markup (mostly relevant once embedded-command support exists — see `docs/architecture.md`'s known gaps). |
| `voiceVers` | A version/metadata tag from the original data tables — cosmetic, doesn't affect synthesis. |
| `free1`-`free8` | Unused reserved slots in the original format — leave at `0`. |

### 2.7 Note-driven singing voices

`GoodNews`, `BadNews`, `PipeOrgan`, `Cellos` (and, with the caveat in 2.1,
`Bells`/`Hysterical`) aren't just tuned prosody — they carry an embedded
**note script**: a fixed melody the pitch contour follows regardless of
what text you feed them, turning speech into song.

| Key | Meaning |
|---|---|
| `notes` | `[count, note1, note2, ..., noteN]` — `count` is how many notes follow (must be `> 1` to activate singing mode at all; see `_backend.init_voice`'s `numOfNotes`/`singScript`/`singing` derivation). Each note packs a pitch and a duration class (16th/8th/quarter/half/whole note, dotted or not) into one integer — see `_backend.py`'s `do_note`/`do_note_script` and `_moduration.py`'s `singScript` branch for the exact bit layout (`kNoteDur`/`kNoteDurShift` for the duration nibble). |

If `notes` is present with `count > 1`, `init_voice()` automatically sets
`vv.singing = vv.singScript = True`, and `api.new_voice()` calls
`e_set_tempo(vv, vv.tempo)` to convert the note-length codes into actual
frame counts using `tempo`. **Both of these matter**: a real bug this
session was `api.new_voice()` forcing `singing = False` unconditionally,
which silently broke duration timing for every note-driven voice (their
notes were "sung" using the wrong duration formula) — if you're debugging
a new singing voice that sounds wrong, check `vv.singing`/`vv.singScript`
came out `True` and `vv.Note_Times` isn't all zeros before assuming your
`notes` array is wrong.

## Part 3: building a new voice

### 3.1 The pragmatic path: clone and tweak

Copy an existing voice dict from `_data.py` that's already close to what
you want (a "base male" like `Fred_Voice`, "base female" like
`Kathy_Voice`, or a special-effect voice if you want to build on an
existing character) and change a handful of keys:

```python
# in your own module, or appended to lintalker/_data.py
MyRobot_Voice = dict(Fred_Voice)   # shallow copy is fine -- lists like
                                    # vWave/notes aren't mutated in place
MyRobot_Voice.update({
    'pitch': 80,           # lower baseline pitch
    'f1_Offset': -20,      # shift formants down slightly (bigger-sounding tract)
    'f2_Offset': -40,
    'stressGain': 20,      # flatter, more monotone/robotic prosody
    'vibratoDepth1': 0,    # no vibrato
    'vibratoDepth2': 0,
    'chorus': 400,         # add a metallic doubled-voice effect
})
```

Then use it exactly like a built-in voice:

```python
from lintalker.api import synthesize_text, pcm_to_wav
pcm = synthesize_text(MyRobot_Voice, "hello, I am a robot.")
pcm_to_wav(pcm, "robot.wav")
```

Iterate by listening: change one or two parameters at a time (formant
offsets and `stressGain`/`riseAmt`/`fallAmt` have the biggest, most
obviously-audible effects), re-synthesize, listen, repeat. There's no
faster feedback loop than your own ears for "does this sound like the
character I'm going for."

### 3.2 Starting from scratch

If you want to understand every field rather than inherit unknown values
from a clone, start from this template (values are Fred's, a reasonable
neutral starting point) and work through Part 2's tables filling in your
own numbers:

```python
NewVoice = {
    'pitch': 97, 'pitchRange': 100, 'stressGain': 60, 'rate': 160,
    'voice': 0,  # 0=male tables, 1=female tables
    'vGain': 100, 'aGain': 0, 'aCycle': 192,
    'f4_Freq': 3000, 'f4_BW': 200,
    'f4p_Freq': 3600, 'f4p_BW': 150,
    'f5p_Freq': 3750, 'f5p_BW': 100,
    'f6p_Freq': 4500, 'f6p_BW': 150,
    'nasal_Base': 330, 'nasal_targ': 400, 'nasal_BW': 60,
    'locus': 100, 'bwGain1': 150, 'bwGain2': 100, 'bwGain3': 100,
    'f1_Offset': 0, 'f2_Offset': 0, 'f3_Offset': 0,
    'chorus': 0, 'nGain': 100, 'sPitch': 0, 'sGain': 0, 'AsperW': 2,
    'voiceVers': 260,
    'riseAmt': 29, 'fallAmt': -29, 'riseAmt1': 29, 'fallAmt1': -29,
    'assertiveness': 65536, 'baselineFall': 51, 'quickness': 7200,
    'pitchCmdStep': 42, 'durCmdStep': 341, 'down_Ramp_Step': 15360,
    'stressDurTime': 50, 'tempo': 85, 'waveType': 0,
    'vWave': [0] * 48, 'vWave1': [0] * 48,  # you need real harmonic data here -- see 3.3
    'sndID': 1, 'vowelSync': 0, 'loopPoint': 0, 'customForm': 0,
    'nasalAmt': 0,
    'vibratoDepth1': 31, 'vibratoDepth2': 16, 'vibratoFreq': 47,
    'intonation': 100, 'portamento': 0, 'emphVoice': 1,
    'rvbDelay': 35, 'rvbDepth': 0, 'rvbWetDry': 1,
    'free1': 0, 'free2': 0, 'free3': 0, 'free4': 0,
    'free5': 0, 'free6': 0, 'free7': 0, 'free8': 0,
    'notes': [0],  # [0] = not a singing voice; see 2.7 for the singing format
}
```

### 3.3 The one hard part: `vWave`/`vWave1`

Every other field is a single tunable number. `vWave`/`vWave1` are the
one field that actually defines *tone quality* at the source (before
formant shaping) — 48 harmonic-amplitude values describing the glottal
pulse's waveform shape. Don't hand-guess these: copy them from the
existing voice whose base tone quality (male/female, breathy/clear) is
closest to what you want, and rely on `f1_Offset`/`f2_Offset`/`bwGain*`/
`aGain` to get the rest of the way — that combination covers the vast
majority of "make it sound like a different voice" ground, and is exactly
how the built-in special-effect voices differ from the base 8.

### 3.4 Validating a new voice

There is no C-reference oracle for a voice that doesn't exist in the
original DECtalk — bit-exactness only applies to the 17 built-in voices
(see `docs/architecture.md`). For a new voice, "correct" just means "it
runs without crashing and sounds like what you intended." A minimal smoke
check:

```python
from lintalker.api import synthesize_text, pcm_to_wav
from lintalker._data import PhonFlags2  # sanity: package imports fine

pcm = synthesize_text(MyRobot_Voice, "testing one two three.")
assert len(pcm) > 0
pcm_to_wav(pcm, "/tmp/test_new_voice.wav")
```

then listen to the file. If synthesis raises an exception, the most
common causes are: a missing required key (`pitch`, `aGain`, `voice` have
no defaults in `init_voice` and will `KeyError`), or `vWave`/`vWave1` not
being 48-element lists.

If you're building a **singing** voice (2.7), also sanity-check
`vv.singing`/`vv.singScript`/`vv.Note_Times` came out as described above
before concluding a weird-sounding result is a `notes` data bug rather
than a wiring bug.
