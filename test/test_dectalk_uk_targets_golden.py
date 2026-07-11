"""CI gate for the DECtalk UK `uk_gettar` target lookup and the UK target ROM.

`dectalk_uk_targets_golden.json` is a deterministic regression digest over
synthetic UK allophone streams (see `dectalk_uk_targets_golden.py`); it needs no
C build. The UK oracle has no isolated target dump, so this guards the port and
the ROM against drift rather than proving a call-for-call oracle match (that
arrives with the UK `phsettar`/`DECTALK_PHS_DUMP` gate). The UK ROM values are
read verbatim from `libtts_uk.so`, so they are the compiled reference by
construction.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))

from dectalk_uk_targets_golden import SYNTH_STREAMS, digest, load


def test_uk_gettar_matches_golden():
    assert digest() == load()["sha256"]


def test_golden_gate_bites_on_mutation(monkeypatch):
    """A change in a UK-specific rule must move the digest."""
    import pyretrotts.dectalk.settar_uk as su

    base = digest()
    monkeypatch.setattr(su, "UKP_OW", -12345)  # neuter the UK-only TILT +10 rule
    # Re-evaluate through the module the golden imports.
    from importlib import reload

    import dectalk_uk_targets_golden as g
    reload(g)
    mutated = g.digest()
    reload(g)  # restore module-level SYNTH_STREAMS binding for later tests
    assert mutated != base


def test_uk_target_blocks_dimensioned_for_57_allophones():
    from pyretrotts.dectalk.targets_uk import UK_FEMTAR, UK_MALTAR, UK_PLACE

    assert len(UK_PLACE) == 57
    assert len(UK_MALTAR) == 7 * 57
    assert len(UK_FEMTAR) == 7 * 57


def test_uk_amp_and_dip_table_sizes():
    from pyretrotts.dectalk.targets_uk import (
        UK_FEATB,
        UK_FEMAMP,
        UK_FEMDIP,
        UK_MALAMP,
        UK_MALDIP,
    )

    # Confirmed against the ELF symbol sizes of libtts_uk.so.
    assert len(UK_MALDIP) == 432
    assert len(UK_FEMDIP) == 366
    assert len(UK_MALAMP) == 542
    assert len(UK_FEMAMP) == 542
    assert len(UK_FEATB) == 101


def test_uk_locus_table_sizes():
    from pyretrotts.dectalk.targets_transitions_uk import (
        UK_FEMLOC,
        UK_MALELOC,
        UK_PLOCU,
    )

    assert len(UK_MALELOC) == 866
    assert len(UK_FEMLOC) == 866
    assert len(UK_PLOCU) == 228


def test_streams_span_the_rom():
    assert SYNTH_STREAMS and all(s.nallotot == 13 for s in SYNTH_STREAMS)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
