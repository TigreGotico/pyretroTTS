"""CI gate: the composed DECtalk allophone -> PCM chain matches the oracle WAV.

Replays `phsettar -> advance_frame/draw_frame -> finalize_av -> send_pars -> vtm`
over a captured allophone stream (borrowing only the F0 contour and phone
durations) and asserts the PCM digest matches the oracle's, for all ten voices.
This gates every ported layer at once and needs no oracle binary.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from dectalk_endtoend_golden import check, load

from pyretrotts.dectalk.voices import VOICE_NAMES


def test_endtoend_pcm_matches_oracle():
    data = load()
    assert set(data["cases"]) == set(VOICE_NAMES)
    bad = check()
    assert not bad, f"allophone->PCM chain diverges from the oracle for: {bad}"


if __name__ == "__main__":
    failures = check()
    print("FAIL: " + ", ".join(failures) if failures
          else f"OK: {len(VOICE_NAMES)} voices match the oracle PCM")
    raise SystemExit(1 if failures else 0)
