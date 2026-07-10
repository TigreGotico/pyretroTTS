"""Frame-driven entry point to the ported DECtalk vocal tract model.

Derived from the Fonix/Force DECtalk C source (`dectalk/dectalk`). FONIX
Corporation declares that source proprietary and confidential. This file is
NOT covered by this project's MIT licence. See NOTICE.

Phase 1 ports only the synthesizer (`vtm/`). It turns a sequence of Klatt
parameter frames into 16-bit PCM, exactly as the C `speech_waveform_generator`
does. The stage that turns text into those frames (`cmd/`, `lts/`, `ph/`) is
not ported, so there is no `synthesize_text` here yet; the shipping DECtalk
markup still renders through MacinTalk (`pyretrotts.engines.DECtalkEngine`).
"""
from __future__ import annotations

import struct

from .consts import SAMPLE_RATE_HZ
from .voices import VOICE_NAMES, VOICE_SELECT
from .vtm import SpeakerState, VtmState, process_frame

__all__ = [
    "SAMPLE_RATE_HZ",
    "VOICE_NAMES",
    "VOICE_SELECT",
    "synthesize_frames",
    "frames_to_wav",
]


def synthesize_frames(speaker: SpeakerState, frames: list[list[int]]) -> list[int]:
    """Run a fresh vocal tract model over `frames`, returning 16-bit samples.

    Each frame is `variabpars[0..19]` (see `consts.OUT_*`). State starts at the
    process-start zero of the C engine, with the speaker definition loaded.
    """
    state = VtmState(spk=speaker, t0jitr=speaker.t0jitr)
    samples: list[int] = []
    for frame in frames:
        samples.extend(process_frame(state, frame))
    return samples


def frames_to_wav(speaker: SpeakerState, frames: list[list[int]]) -> bytes:
    """Synthesize `frames` and wrap the PCM in a 16-bit mono WAV container."""
    samples = synthesize_frames(speaker, frames)
    pcm = struct.pack(f"<{len(samples)}h", *samples)
    data = len(pcm)
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF", 36 + data, b"WAVE", b"fmt ", 16, 1, 1,
        SAMPLE_RATE_HZ, SAMPLE_RATE_HZ * 2, 2, 16, b"data", data,
    )
    return header + pcm
