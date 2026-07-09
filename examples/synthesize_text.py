"""Synthesize plain English text end-to-end and write it to a WAV file.

This exercises the full pipeline: text -> tokenize -> dictionary/rule
lookup -> sentence assembly -> allophone selection -> pitch contour ->
duration -> formant synthesis. See README.md/docs/architecture.md for
known gaps (no Morph.c, no non-punctuation phrase boundaries, no embedded
commands, single-sentence input only).
"""
from lintalker._data import Fred_Voice
from lintalker.api import pcm_to_wav, synthesize_text


def main():
    pcm = synthesize_text(Fred_Voice, "hello, this is a test.")
    pcm_to_wav(pcm, "hello_test.wav")
    print(f"wrote hello_test.wav ({len(pcm)} bytes of PCM)")


if __name__ == "__main__":
    main()
