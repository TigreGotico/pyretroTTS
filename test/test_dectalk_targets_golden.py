"""CI gate for the DECtalk `us_gettar` target lookup: a digest over synthetic
allophone streams, no C build required.

`dectalk_targets_golden.json` is anchored to the C oracle at write time (see
`dectalk_targets_golden.py`; `--write` refuses unless the port matches the
instrumented C call for call over ten voices). This test only guards against
drift in the ported lookup and the target ROM it reads.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))

from dectalk_targets_golden import digest, load


def test_us_gettar_matches_golden():
    golden = load()
    assert digest() == golden["synth_streams"]


def test_partyp_and_parini_shapes():
    from pyretrotts.dectalk.targets import PARINI, PARTYP

    assert len(PARTYP) == 16
    assert len(PARINI) == 16
    # Parameter type codes: FZ nasal-zero, F/BW formant, AV/AP source, amps.
    assert PARTYP == (3, 3, 3, 1, 4, 4, 4, 0, 0, 2, 2, 2, 2, 2, 2, 2)


def test_target_blocks_dimensioned_for_57_allophones():
    from pyretrotts.dectalk.targets import US_FEMTAR, US_MALTAR, US_PLACE

    assert len(US_PLACE) == 57
    # F1,F2,F3,B1,B2,B3,AV target blocks over US_TOT_ALLOPHONES == 57.
    assert len(US_MALTAR) == 7 * 57
    assert len(US_FEMTAR) == 7 * 57


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
