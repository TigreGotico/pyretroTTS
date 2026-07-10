"""The two engine classes, and the song scores they render."""
import hashlib
import json
import pathlib
import struct

import pytest

from pyretrotts.engines import (
    DECtalkEngine,
    Engine,
    MacInTalkEngine,
    pcm_duration,
    pcm_peak,
    scale_to_headroom,
)

SONGS = pathlib.Path(__file__).parent.parent / "songs"
GOLDEN = pathlib.Path(__file__).parent / "golden_songs.json"


def f0(pcm: bytes, sample_rate: int = 22050) -> float:
    """Fundamental frequency of the middle of `pcm`, by autocorrelation."""
    x = struct.unpack(f"<{len(pcm) // 2}h", pcm)
    x = x[len(x) // 4: 3 * len(x) // 4]
    if not any(x):
        return 0.0
    best_score, best_lag = 0, 0
    for lag in range(sample_rate // 700, sample_rate // 50):
        score = sum(x[i] * x[i + lag] for i in range(0, len(x) - lag, 8))
        if score > best_score:
            best_score, best_lag = score, lag
    return sample_rate / best_lag if best_lag else 0.0


# --- the common surface ---------------------------------------------------

@pytest.mark.parametrize("engine", [MacInTalkEngine(), DECtalkEngine()])
def test_every_engine_implements_the_surface(engine):
    assert isinstance(engine, Engine)
    assert engine.name and engine.dialect
    assert engine.voices
    assert engine.sample_rate == 22050


def test_the_two_engines_speak_different_dialects():
    assert MacInTalkEngine().dialect != DECtalkEngine().dialect


def test_macintalk_has_the_seventeen_apple_voices():
    voices = MacInTalkEngine().voices
    assert len(voices) == 17
    assert "Fred" in voices and "Zarvox" in voices


def test_dectalk_has_the_ten_dec_voices():
    voices = DECtalkEngine().voices
    assert len(voices) == 10
    assert "Perfect Paul" in voices and "Beautiful Betty" in voices


# --- synthesis ------------------------------------------------------------

def test_macintalk_speaks_text():
    pcm = MacInTalkEngine().synthesize("hello, this is a test.", "Fred")
    assert pcm_duration(pcm) > 0.5
    assert pcm_peak(pcm) > 1000


def test_dectalk_speaks_plain_text_through_the_backend():
    pcm = DECtalkEngine().synthesize("hello there")
    assert pcm_peak(pcm) > 1000


def test_dectalk_sings_a_score():
    pcm = DECtalkEngine().synthesize("[:phone on][:np] hxeh<200,13>lb<100>ow<400,20>")
    assert pcm_duration(pcm) > 0.5
    assert pcm_peak(pcm) > 1000


@pytest.mark.parametrize("tone,hz", [(13, 130.8), (20, 196.0), (25, 261.6)])
def test_a_sung_note_lands_on_its_pitch(tone, hz):
    """Within a quarter tone (about 3%) of the note the score asks for."""
    pcm = DECtalkEngine().synthesize(f"[:phone on][:np] aa<500,{tone}>")
    assert abs(f0(pcm) - hz) / hz < 0.03


def test_rendering_leaves_headroom():
    pcm = DECtalkEngine().synthesize("[:phone on][:np] aa<400,25>iy<400,25>")
    assert pcm_peak(pcm) <= int(32767 * 0.92) + 1


def test_scale_to_headroom_is_a_no_op_below_the_limit():
    quiet = struct.pack("<4h", 100, -200, 300, -400)
    assert scale_to_headroom(quiet) == quiet


def test_scale_to_headroom_handles_silence():
    assert scale_to_headroom(b"") == b""
    assert scale_to_headroom(struct.pack("<2h", 0, 0)) == struct.pack("<2h", 0, 0)


# --- the song scores ------------------------------------------------------

def _scores():
    return sorted(SONGS.glob("*.EN"))


def test_the_repository_ships_song_scores():
    assert _scores(), "no .EN scores under songs/"


@pytest.mark.parametrize("path", _scores(), ids=lambda p: p.stem)
def test_every_score_parses_and_renders(path):
    engine = DECtalkEngine()
    score = engine.parse(path.read_text(errors="replace"))
    assert score.phoneme_mode, "a song score must turn phoneme mode on"
    assert score.notes, "a song score must carry notes"
    assert score.duration_ms > 5000, "a song should be more than five seconds"


@pytest.mark.parametrize("path", _scores(), ids=lambda p: p.stem)
def test_rendered_songs_match_their_golden_hash(path):
    goldens = json.loads(GOLDEN.read_text())
    engine = DECtalkEngine()
    score = engine.parse(path.read_text(errors="replace"))
    digest = hashlib.sha256(engine.render(score)).hexdigest()
    assert digest == goldens[path.name], (
        f"the render of {path.name} changed. Synthesis is deterministic, so "
        f"this is a regression -- do not regenerate golden_songs.json."
    )
