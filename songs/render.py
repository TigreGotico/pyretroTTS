"""Render the DECtalk song scores in this directory to WAV.

    python3 songs/render.py                 # render every .EN into songs/wav/
    python3 songs/render.py --voice Fred    # sing every part in one voice

Each `.EN` file is a DECtalk score: `[:phone on]` puts the engine into phoneme
mode, and every phoneme then carries its own duration and pitch, as in
`weh<250,13>` -- the phonemes `w` and `eh`, lasting 250 ms, on tone 13.
See `pyretrotts/_dectalk.py`.
"""
import argparse
import os
import pathlib
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pyretrotts.api import pcm_to_wav  # noqa: E402
from pyretrotts.engines import DECtalkEngine, pcm_duration, pcm_peak  # noqa: E402

HERE = pathlib.Path(__file__).parent


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--voice", default="Perfect Paul",
                        help="DECtalk voice for parts the score does not name")
    parser.add_argument("--out", type=pathlib.Path, default=HERE / "wav")
    args = parser.parse_args()

    engine = DECtalkEngine()
    args.out.mkdir(parents=True, exist_ok=True)

    scores = sorted(HERE.glob("*.EN"))
    if not scores:
        raise SystemExit(f"no .EN scores in {HERE}")

    for path in scores:
        score = engine.parse(path.read_text(errors="replace"))
        pcm = engine.render(score, default_voice=args.voice)
        wav = args.out / (path.stem.lower().replace(" ", "-") + ".wav")
        pcm_to_wav(pcm, str(wav))
        voices = ", ".join(score.voices) or args.voice
        print(f"{path.stem:32} {pcm_duration(pcm):6.1f}s  peak={pcm_peak(pcm):5}  "
              f"{len(score.notes):4} notes  [{voices}] -> {wav.name}")


if __name__ == "__main__":
    main()
