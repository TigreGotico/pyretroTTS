"""Synthesize plain English text end-to-end and write it to a WAV file.

This exercises the full pipeline: text -> tokenize -> dictionary/rule
lookup -> sentence assembly -> allophone selection -> pitch contour ->
duration -> formant synthesis, across as many clauses/sentences as the
text contains. See README.md/docs/architecture.md for the full feature
set (embedded bracket commands, number/date/currency reading, etc.) and
the few remaining scope limits.
"""
from pyretrotts._data import Fred_Voice
from pyretrotts.api import pcm_to_wav, synthesize_text


def main():
    pcm = synthesize_text(Fred_Voice, "hello, this is a test.")
    pcm_to_wav(pcm, "hello_test.wav")
    print(f"wrote hello_test.wav ({len(pcm)} bytes of PCM)")


if __name__ == "__main__":
    main()
