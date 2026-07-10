"""Unit tests for the DECtalk vocal tract model's numeric core.

The fixed-point primitives and the resonator coefficient functions are the
self-contained heart of the synthesizer. Their reference values are dumped from
the real C (`vtm/vtmfunc.h` with `vtm/vtmtable.h`) by a standalone program that
uses the genuine tables and the `viphdefs.h` `frac?mul` macros at the 11025 Hz
`SAMPLE_RATE_INCREASE` path (`inv_rate_scale = 29722`). They are held here as
inline literals, so this needs no C build. The full-loop, sample-for-sample
comparison lives in test_dectalk_oracle.py.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from pyretrotts.dectalk import consts
from pyretrotts.dectalk.tables import AMPTABLE, B0, RADIUS_TABLE
from pyretrotts.dectalk.vtm import (
    d2pole_cf45,
    d2pole_cf123,
    d2pole_pf,
    frac1mul,
    frac4mul,
    s16,
    s32,
)


def test_s16_wraps_like_c():
    assert s16(0x7FFF) == 32767
    assert s16(0x8000) == -32768
    assert s16(0x10000) == 0
    assert s16(-1) == -1


def test_s32_wraps_like_c():
    assert s32(0x7FFFFFFF) == 2147483647
    assert s32(0x80000000) == -2147483648


def test_frac_muls_are_shifts_in_32bit():
    # frac4mul is >>12, frac1mul is >>15, both floor (arithmetic) shifts.
    assert frac4mul(4096, 4096) == 4096
    assert frac1mul(32768, 16384) == 16384
    assert frac4mul(-4096, 4096) == -4096
    assert frac1mul(-1, 32768) == -1


def test_amptable_and_b0_spot_values():
    # Verbatim table values from the C (vtm/vtmtable.h).
    assert len(AMPTABLE) == 88
    assert AMPTABLE[:16] == (0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 6, 7, 8)
    assert B0[0] == 1200  # B0[nopen-40] at nopen == 40
    assert RADIUS_TABLE[0] == 4096  # exp(0) = 1.0 in Q12


# (frequency, bandwidth, gain) -> (acoef, bcoef, ccoef), dumped from the C.
CF123 = [
    (250, 40, 0, 0, 8028, -4014),
    (250, 120, 1024, 42, 7848, -3836),
    (250, 400, 2048, 120, 7240, -3265),
    (500, 40, 4096, 640, 7790, -4014),
    (500, 1000, 1024, 246, 5922, -2320),
    (700, 90, 2048, 624, 7365, -3894),
    (1000, 400, 2048, 1196, 6164, -3265),
    (1500, 40, 4096, 5572, 5324, -4014),
    (2000, 200, 4096, 8996, 3263, -3665),
    (3000, 120, 1024, 4512, -1092, -3836),
    (4000, 40, 4096, 26746, -5263, -4014),
    (4600, 200, 4096, 28952, -6715, -3665),
]

CF45 = [
    (3000, 200, 0, 0, -1068, -3665),
    (4600, 400, 0, 0, -6337, -3265),
    (500, 90, 0, 0, 7673, -3894),
]

PF = [
    (2500, 400, 2048, 6280, 1080, -3265),
    (4600, 500, 0, 0, -6165, -3090),
    (700, 120, 4096, 1244, 7310, -3836),
]


@pytest.mark.parametrize("f,bw,g,a,b,c", CF123)
def test_d2pole_cf123(f, bw, g, a, b, c):
    assert d2pole_cf123(f, bw, g) == (a, b, c)


@pytest.mark.parametrize("f,bw,g,a,b,c", CF45)
def test_d2pole_cf45(f, bw, g, a, b, c):
    assert d2pole_cf45(f, bw, g) == (a, b, c)


@pytest.mark.parametrize("f,bw,g,a,b,c", PF)
def test_d2pole_pf(f, bw, g, a, b, c):
    assert d2pole_pf(f, bw, g) == (a, b, c)


def test_output_format_constants():
    assert consts.SAMPLE_RATE_HZ == 11025
    assert consts.SAMPLE_WIDTH_BITS == 16
    assert consts.CHANNELS == 1
    assert consts.SAMPLES_PER_FRAME == 71
