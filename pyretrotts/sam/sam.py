"""Top-level SAM driver: text or phoneme mnemonics in, 8-bit PCM out.

Derived from vidarh/SAM, which is an opcode-by-opcode translation of SoftVoice,
Inc.'s 6502 program; NOT covered by this project's MIT licence; see NOTICE.

Ports sam.c's SAMMain/PrepareOutput. It runs the phoneme pipeline (prosody.py),
splits the result into clause segments on the BREAK sentinel, and renders each
through a single Renderer whose output buffer spans the whole utterance.
"""
from __future__ import annotations

from . import prosody, reciter
from .phonemes import BREAK, END
from .render import Renderer

# render.c's native output format.
SAMPLE_RATE = 22050

# SAM's four voice knobs and their C defaults (sam.c:20-23).
DEFAULT_SPEED = 72
DEFAULT_PITCH = 64
DEFAULT_MOUTH = 128
DEFAULT_THROAT = 128


def _prepare_output(st: prosody.Buffers, renderer: Renderer) -> None:
    index_output = bytearray(256)
    stress_output = bytearray(256)
    length_output = bytearray(256)
    srcpos = 0
    destpos = 0
    while True:
        a = st.phonemeindex[srcpos]
        index_output[destpos] = a
        if a == END:
            renderer.render(index_output, stress_output, length_output)
            return
        if a == BREAK:
            index_output[destpos] = END
            renderer.render(index_output, stress_output, length_output)
            destpos = 0
        elif a == 0:
            pass
        else:
            length_output[destpos] = st.phonemeLength[srcpos]
            stress_output[destpos] = st.stress[srcpos]
            destpos += 1
        srcpos = (srcpos + 1) & 0xFF


def render_pcm(
    source: str,
    speed: int = DEFAULT_SPEED,
    pitch: int = DEFAULT_PITCH,
    mouth: int = DEFAULT_MOUTH,
    throat: int = DEFAULT_THROAT,
    singmode: bool = False,
    phonetic: bool = False,
) -> bytes:
    """Render `source` and return raw 8-bit unsigned PCM at 22050 Hz mono.

    With `phonetic=False` the text is run through the reciter first; with
    `phonetic=True` `source` is already SAM phoneme mnemonics (``/HEHLOW``).
    Returns an empty buffer when the reciter rejects the text, as sam.c does.
    """
    upper = source.upper().encode("latin-1", "replace")
    if phonetic:
        phonemes = upper + b"\x9b"
    else:
        phonemes = reciter.text_to_phonemes(upper)
        if phonemes is None:
            return b""

    st = prosody.Buffers(phonemes[:254])
    # sam.c SAMMain: phonemeindex[255] is set to END in Init() then immediately
    # overwritten with 32 here. Both writes are reproduced; the FIXME in the C
    # notes they conflict.
    st.phonemeindex[255] = 32

    if not prosody.parser1(st):
        return b""
    prosody.parser2(st)
    prosody.copy_stress(st)
    prosody.set_phoneme_length(st)
    prosody.adjust_lengths(st)
    prosody.code41240(st)

    x = 0
    while True:
        if st.phonemeindex[x] > 80:
            st.phonemeindex[x] = END
            break
        x = (x + 1) & 0xFF
        if x == 0:
            break

    prosody.insert_breath(st)

    renderer = Renderer(speed, pitch, mouth, throat, singmode)
    _prepare_output(st, renderer)
    return renderer.pcm()
