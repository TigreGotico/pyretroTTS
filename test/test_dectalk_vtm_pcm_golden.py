"""CI gate: `vtm.py` reproduces the oracle's real per-voice samples.

Runs `synthesize_frames` over the captured `parambuff` frames the C vocal tract
model consumed and asserts the 16-bit output matches the captured `iwave` digest,
for all ten voices. Unlike the synthetic `dectalk_golden` vector, these are real
DECtalk frames, so they exercise the post-speaker-definition `ldspdef` silence
ramp and would catch a regression there. No oracle binary needed.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from dectalk_vtm_pcm_golden import check, load

from pyretrotts.dectalk.voices import VOICE_NAMES


def test_vtm_matches_captured_oracle_samples():
    data = load()
    assert set(data["frames"]) == set(VOICE_NAMES)
    bad = check()
    assert not bad, f"vtm.py output diverges from the captured oracle for: {bad}"


if __name__ == "__main__":
    failures = check()
    print("FAIL: " + ", ".join(failures) if failures
          else f"OK: {len(VOICE_NAMES)} voices match the captured oracle iwave")
    raise SystemExit(1 if failures else 0)
