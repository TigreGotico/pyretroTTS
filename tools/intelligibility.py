"""Rank the voices by how well a speech recognizer understands them.

    python3 tools/intelligibility.py                 # every voice
    python3 tools/intelligibility.py --engine sam

Word error rate is a proxy for intelligibility, not a measure of it. A recognizer
is not a listener: it was trained on human speech, so it penalizes a synthetic
voice for being synthetic as well as for being unclear. The ranking is worth
more than the absolute numbers.

DECtalk's voices are MacinTalk voices standing in for them until the DECtalk
synthesizer is ported, so each DECtalk row duplicates the MacinTalk row it
substitutes. Rows are labelled with what they actually render.

Needs `onnx-asr`, `scipy` and `jiwer`, and a cached Parakeet model. The renders
are 22050 Hz; the recognizer wants 16 kHz, so they are resampled with a
band-limited polyphase filter -- a naive decimation would alias and score the
resampler rather than the voice.
"""
import argparse
import os
import statistics
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np  # noqa: E402
from scipy.signal import resample_poly  # noqa: E402

ASR_MODEL = "istupakov/parakeet-tdt-0.6b-v2-onnx"
ASR_RATE = 16000
NATIVE_RATE = 22050

#: Phonetically varied, unambiguous, and free of proper nouns a recognizer
#: would guess at. The last two are the Harvard sentences' opening lines.
SENTENCES = (
    "the quick brown fox jumps over the lazy dog",
    "she sells sea shells by the sea shore",
    "please call stella and ask her to bring these things",
    "the rain in spain falls mainly on the plain",
    "how much wood would a woodchuck chuck",
    "peter piper picked a peck of pickled peppers",
    "the birch canoe slid on the smooth planks",
    "glue the sheet to the dark blue background",
    "we were away a year ago",
    "the small pup gnawed a hole in the sock",
)


def _to_asr(pcm: bytes) -> np.ndarray:
    """22050 Hz 16-bit PCM to the float32 16 kHz mono the recognizer expects."""
    samples = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768.0
    return resample_poly(samples, ASR_RATE, NATIVE_RATE).astype(np.float32)


def _voices(engine_name: str):
    from pyretrotts import DECtalkEngine, MacInTalkEngine, SAMEngine

    engines = {
        "macintalk": MacInTalkEngine(),
        "dectalk": DECtalkEngine(),
        "sam": SAMEngine(),
    }
    for name, engine in engines.items():
        if engine_name not in (None, name):
            continue
        for voice in engine.voices:
            yield name, engine, voice


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", choices=["macintalk", "dectalk", "sam"])
    parser.add_argument("--sentences", type=int, default=len(SENTENCES))
    args = parser.parse_args()

    import jiwer
    import onnx_asr

    recognizer = onnx_asr.load_model(ASR_MODEL)
    sentences = SENTENCES[: args.sentences]

    results = []
    for engine_name, engine, voice in _voices(args.engine):
        rates = []
        for sentence in sentences:
            pcm = engine.synthesize(sentence + ".", voice)
            heard = recognizer.recognize(_to_asr(pcm), sample_rate=ASR_RATE)
            rates.append(jiwer.wer(sentence, jiwer.ToLowerCase()(heard).strip(" .,!?")))
        renders_as = ""
        if engine_name == "dectalk":
            from pyretrotts.engines import DECtalkEngine
            renders_as = f"(as {DECtalkEngine.VOICE_SUBSTITUTES[voice]})"
        results.append((statistics.mean(rates), engine_name, voice, renders_as))
        print(f"  {engine_name:10} {voice:20} WER {results[-1][0]:6.1%} {renders_as}",
              flush=True)

    print(f"\n{'rank':>4}  {'engine':10} {'voice':20} {'WER':>7}")
    for rank, (wer, engine_name, voice, renders_as) in enumerate(sorted(results), start=1):
        print(f"{rank:>4}  {engine_name:10} {voice:20} {wer:6.1%} {renders_as}")


if __name__ == "__main__":
    main()
