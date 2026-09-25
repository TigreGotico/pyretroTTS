"""Integer and exact arithmetic modes."""
import pytest

from pyretrotts._backend import _trunc, exact_arithmetic, mMul2, mUnScale
from pyretrotts._consts import kPrecision
from pyretrotts._data import Fred_Voice, Kathy_Voice
from pyretrotts.api import synthesize_text


@pytest.fixture
def integer_mode():
    previous = exact_arithmetic(False)
    yield
    exact_arithmetic(previous)


@pytest.fixture
def exact_mode():
    previous = exact_arithmetic(True)
    yield
    exact_arithmetic(previous)


def test_the_default_is_integer(integer_mode):
    assert mUnScale(-7, 1) == -4          # -7 >> 1 floors


def test_exact_truncates_toward_zero(exact_mode):
    assert mUnScale(-7, 1) == -3          # C truncates a double toward zero
    assert mUnScale(7, 1) == 3


def test_the_two_agree_on_positive_values(exact_mode):
    for numerator in range(0, 4096, 37):
        assert _trunc(numerator, kPrecision) == numerator >> kPrecision


def test_the_two_differ_only_on_negatives():
    exact_arithmetic(False)
    integer = [mMul2(-x, 3, 4) for x in range(1, 200)]
    exact_arithmetic(True)
    exact = [mMul2(-x, 3, 4) for x in range(1, 200)]
    exact_arithmetic(False)
    assert integer != exact
    assert all(e >= i for i, e in zip(integer, exact, strict=True))  # exact never floors lower


def test_exact_returns_integers(exact_mode):
    """Fixed-point scaling is unchanged; only the rounding direction moves."""
    assert isinstance(mMul2(3, 5, 1), int)
    assert isinstance(mUnScale(-7, 1), int)


def test_the_mode_switch_reports_the_previous_setting():
    assert exact_arithmetic(True) is False
    assert exact_arithmetic(False) is True


def test_integer_renders_are_unchanged_by_the_feature(integer_mode):
    assert len(synthesize_text(Fred_Voice, "hello world.")) > 1000


def test_exact_renders_differ_from_integer():
    baseline = synthesize_text(Fred_Voice, "hello world.")
    exact_arithmetic(True)
    exact = synthesize_text(Fred_Voice, "hello world.")
    exact_arithmetic(False)
    restored = synthesize_text(Fred_Voice, "hello world.")
    assert len(exact) == len(baseline)
    assert exact != baseline
    assert restored == baseline


@pytest.mark.parametrize("voice", [Fred_Voice, Kathy_Voice])
def test_exact_is_deterministic(voice, exact_mode):
    assert synthesize_text(voice, "testing one two three") == \
           synthesize_text(voice, "testing one two three")
