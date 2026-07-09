"""Synthesize a hand-built phoneme plan to a WAV file.

There is no text-to-speech frontend yet (see README.md), so this example
uses a pre-built phoneme plan for the word "hi" captured from the C
reference (see test/test_pipeline.py for how such plans are structured).
"""
from lintalker._data import Fred_Voice
from lintalker.api import pcm_to_wav, synthesize_phonemes

# phoneme ids, control words, durations (see lintalker/_phonemes.py)
PHONEMES = [23, 11, 54, 3, 33, 22, 23]
CTRLS = [1, 268500993, 0, 268502089, 9, 16393, 2621440]
DURS = [1, 26, 10, 54, 23, 5, 135]


def main():
    pcm = synthesize_phonemes(Fred_Voice, PHONEMES, CTRLS, DURS)
    pcm_to_wav(pcm, "hi.wav")
    print(f"wrote hi.wav ({len(pcm)} bytes of PCM)")


if __name__ == "__main__":
    main()
