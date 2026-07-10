# Songs

DECtalk scores, and what this repository makes of them.

Each `.EN` file is a song written in DECtalk's phoneme notation. `[:phone on]`
puts the engine into phoneme mode; after that every phoneme carries its own
duration and pitch:

```
weh<250,13>
```

is the phonemes `w` and `eh`, lasting 250 milliseconds, sung on tone 13. A tone
of 37 or less is a semitone index running from C2 (tone 1) to C5 (tone 37);
anything larger is a frequency in Hz. `_` is silence, so `_<500>` is a half-second
rest. `[:np]`, `[:nu]` and the other `[:n?]` commands choose a voice, and a score
may switch voice mid-song — several of these are duets.

## Rendering

```bash
python3 songs/render.py                  # every score into songs/wav/
python3 songs/render.py --voice "Huge Harry"
```

`songs/wav/` holds one render of each score, committed so the result can be
heard without running anything.

These are voiced on the **MacinTalk** synthesizer, because the DECtalk
synthesizer is not ported yet (see `docs/dectalk-port-plan.md`). The notes, the
rhythm and the phonemes are the score's; the timbre is not DECtalk's. Each
DECtalk voice is standing in as the nearest MacinTalk voice — Perfect Paul is
sung by Fred.

## Provenance

Every score here sets a traditional or public-domain song: sea shanties,
nursery rhymes, and Christmas carols long out of copyright. The wider corpus
these came from is mostly transcriptions of commercial recordings, which are
not distributable, and are deliberately not included.

`test/test_engines.py` parses and renders each score on every test run, and
pins the output to a sha256 in `test/golden_songs.json`.
