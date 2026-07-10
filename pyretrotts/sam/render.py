"""The synthesis output stage: frames, transitions, and sample playback.

Derived from vidarh/SAM, which is an opcode-by-opcode translation of SoftVoice,
Inc.'s 6502 program; NOT covered by this project's MIT licence; see NOTICE.

Ports render.c, processframes.c and createtransitions.c. SAM is not a formant
filter: each 10 ms frame carries three oscillators (two sine, one rectangle)
summed open-loop, and consonants that cannot be built that way are played from a
1-bit compressed sample table. All arithmetic is unsigned-byte, so every value
is masked to eight bits exactly where the 6502/C original relied on wraparound.
"""
from __future__ import annotations

from .tables import (
    AMPL1DATA,
    AMPL2DATA,
    AMPL3DATA,
    AMPLITUDE_RESCALE,
    BLEND_RANK,
    FREQ1DATA,
    FREQ2DATA,
    FREQ3DATA,
    IN_BLEND_LENGTH,
    MULTTABLE,
    OUT_BLEND_LENGTH,
    RECTANGLE,
    SAMPLE_TABLE,
    SAMPLED_CONSONANT_FLAGS,
    SINUS,
    TAB47492,
    TAB48426,
)

PHONEME_PERIOD = 1
PHONEME_QUESTION = 2
RISING_INFLECTION = 1
FALLING_INFLECTION = 255

# render.c Output(): timetable for a more accurate C64 byte-rate simulation.
_TIMETABLE = (
    (162, 167, 167, 127, 128),
    (226, 60, 60, 0, 0),
    (225, 60, 59, 0, 0),
    (200, 0, 0, 54, 55),
    (199, 0, 0, 54, 54),
)

_BUFFER_BYTES = 22050 * 10


def _s8(value: int) -> int:
    """Reinterpret the low byte of `value` as a signed char."""
    value &= 0xFF
    return value - 256 if value >= 128 else value


class Renderer:
    """Holds the frame tables and the growing 8-bit output buffer.

    One Renderer spans a whole utterance: PrepareOutput calls `render` once per
    clause segment, and the output position, timetable index and buffer persist
    across those calls exactly as render.c's globals do.
    """

    def __init__(
        self, speed: int, pitch: int, mouth: int, throat: int, singmode: bool
    ) -> None:
        self.speed = speed
        self.pitch = pitch
        self.singmode = singmode

        # SetMouthThroat rewrites the F1/F2 frequency tables, so these are
        # per-run mutable copies rather than the shared module tables.
        self.freq1data = bytearray(FREQ1DATA)
        self.freq2data = bytearray(FREQ2DATA)
        self.freq3data = bytearray(FREQ3DATA)

        self.pitches = bytearray(256)
        self.frequency1 = bytearray(256)
        self.frequency2 = bytearray(256)
        self.frequency3 = bytearray(256)
        self.amplitude1 = bytearray(256)
        self.amplitude2 = bytearray(256)
        self.amplitude3 = bytearray(256)
        self.sampled_consonant_flag = bytearray(256)

        # Output stage (render.c globals).
        self.buffer = bytearray(_BUFFER_BYTES)
        self.bufferpos = 0
        self._oldtimetableindex = 0

        self.set_mouth_throat(mouth, throat)

    # -- mouth/throat knobs ------------------------------------------------

    def set_mouth_throat(self, mouth: int, throat: int) -> None:
        """Rescale the voiced-phoneme F1 (mouth) and F2 (throat) tables."""
        mouth_formants5_29 = (
            0, 0, 0, 0, 0, 10,
            14, 19, 24, 27, 23, 21, 16, 20, 14, 18, 14, 18, 18,
            16, 13, 15, 11, 18, 14, 11, 9, 6, 6, 6,
        )
        throat_formants5_29 = (
            255, 255,
            255, 255, 255, 84, 73, 67, 63, 40, 44, 31, 37, 45, 73, 49,
            36, 30, 51, 37, 29, 69, 24, 50, 30, 24, 83, 46, 54, 86,
        )
        mouth_formants48_53 = (19, 27, 21, 27, 18, 13)
        throat_formants48_53 = (72, 39, 31, 43, 30, 34)

        def trans(a: int, b: int) -> int:
            return (((a * b) >> 8) << 1) & 0xFF

        new_frequency = 0
        for pos in range(5, 30):
            initial = mouth_formants5_29[pos]
            if initial != 0:
                new_frequency = trans(mouth, initial)
            self.freq1data[pos] = new_frequency
            initial = throat_formants5_29[pos]
            if initial != 0:
                new_frequency = trans(throat, initial)
            self.freq2data[pos] = new_frequency

        for pos in range(6):
            self.freq1data[pos + 48] = trans(mouth, mouth_formants48_53[pos])
            self.freq2data[pos + 48] = trans(throat, throat_formants48_53[pos])

    # -- output ------------------------------------------------------------

    def _output(self, index: int, value: int) -> None:
        self.bufferpos += _TIMETABLE[self._oldtimetableindex][index]
        self._oldtimetableindex = index
        sample = (value & 15) * 16
        base = self.bufferpos // 50
        for k in range(5):
            self.buffer[base + k] = sample

    def pcm(self) -> bytes:
        """The rendered utterance as 8-bit unsigned PCM (bufferpos/50 bytes)."""
        return bytes(self.buffer[: self.bufferpos // 50])

    # -- frame creation ----------------------------------------------------

    def _create_frames(self, phoneme_index_output, stress_output, phoneme_length_output) -> None:
        x = 0
        i = 0
        while i < 256:
            phoneme = phoneme_index_output[i]
            if phoneme == 255:
                break
            if phoneme == PHONEME_PERIOD:
                self._add_inflection(RISING_INFLECTION, x)
            elif phoneme == PHONEME_QUESTION:
                self._add_inflection(FALLING_INFLECTION, x)

            phase1 = TAB47492[stress_output[i] + 1]
            phase2 = phoneme_length_output[i]
            while True:
                self.frequency1[x] = self.freq1data[phoneme]
                self.frequency2[x] = self.freq2data[phoneme]
                self.frequency3[x] = self.freq3data[phoneme]
                self.amplitude1[x] = AMPL1DATA[phoneme]
                self.amplitude2[x] = AMPL2DATA[phoneme]
                self.amplitude3[x] = AMPL3DATA[phoneme]
                self.sampled_consonant_flag[x] = SAMPLED_CONSONANT_FLAGS[phoneme]
                self.pitches[x] = (self.pitch + phase1) & 0xFF
                x = (x + 1) & 0xFF
                phase2 = (phase2 - 1) & 0xFF
                if phase2 == 0:
                    break
            i += 1

    def _rescale_amplitude(self) -> None:
        for i in range(255, -1, -1):
            self.amplitude1[i] = AMPLITUDE_RESCALE[self.amplitude1[i]]
            self.amplitude2[i] = AMPLITUDE_RESCALE[self.amplitude2[i]]
            self.amplitude3[i] = AMPLITUDE_RESCALE[self.amplitude3[i]]

    def _assign_pitch_contour(self) -> None:
        for i in range(256):
            self.pitches[i] = (self.pitches[i] - (self.frequency1[i] >> 1)) & 0xFF

    def _add_inflection(self, inflection: int, pos: int) -> None:
        end = pos
        pos = 0 if pos < 30 else (pos - 30) & 0xFF
        while self.pitches[pos] == 127:
            pos = (pos + 1) & 0xFF
        a = self.pitches[pos]
        while pos != end:
            a = (a + inflection) & 0xFF
            self.pitches[pos] = a
            pos = (pos + 1) & 0xFF
            while pos != end and self.pitches[pos] == 255:
                pos = (pos + 1) & 0xFF

    # -- transitions -------------------------------------------------------

    def _read(self, table, y):
        return {
            168: self.pitches,
            169: self.frequency1,
            170: self.frequency2,
            171: self.frequency3,
            172: self.amplitude1,
            173: self.amplitude2,
            174: self.amplitude3,
        }[table][y]

    def _write(self, table, y, value):
        {
            168: self.pitches,
            169: self.frequency1,
            170: self.frequency2,
            171: self.frequency3,
            172: self.amplitude1,
            173: self.amplitude2,
            174: self.amplitude3,
        }[table][y] = value & 0xFF

    def _interpolate(self, width, table, frame, mem53) -> None:
        sign = mem53 < 0
        remainder = abs(mem53) % width
        # C truncates the signed division toward zero, then narrows to a byte.
        div = (abs(mem53) // width)
        if mem53 < 0:
            div = -div
        div &= 0xFF

        error = 0
        pos = width
        val = (self._read(table, frame) + div) & 0xFF
        while True:
            pos = (pos - 1) & 0xFF
            if pos == 0:
                break
            error = (error + remainder) & 0xFF
            if error >= width:
                error -= width
                if sign:
                    val = (val - 1) & 0xFF
                elif val:
                    val = (val + 1) & 0xFF
            frame = (frame + 1) & 0xFF
            self._write(table, frame, val)
            val = (val + div) & 0xFF

    def _interpolate_pitch(self, pos, mem49, phase3, phoneme_length_output) -> None:
        cur_width = phoneme_length_output[pos] // 2
        next_width = phoneme_length_output[pos + 1] // 2
        width = (cur_width + next_width) & 0xFF
        pitch = _s8(self.pitches[(next_width + mem49) & 0xFF] - self.pitches[(mem49 - cur_width) & 0xFF])
        self._interpolate(width, 168, phase3, pitch)

    def _create_transitions(self, phoneme_index_output, phoneme_length_output) -> int:
        mem49 = 0
        pos = 0
        while True:
            phoneme = phoneme_index_output[pos]
            next_phoneme = phoneme_index_output[pos + 1]
            if next_phoneme == 255:
                break

            next_rank = BLEND_RANK[next_phoneme]
            rank = BLEND_RANK[phoneme]
            if rank == next_rank:
                phase1 = OUT_BLEND_LENGTH[phoneme]
                phase2 = OUT_BLEND_LENGTH[next_phoneme]
            elif rank < next_rank:
                phase1 = IN_BLEND_LENGTH[next_phoneme]
                phase2 = OUT_BLEND_LENGTH[next_phoneme]
            else:
                phase1 = OUT_BLEND_LENGTH[phoneme]
                phase2 = IN_BLEND_LENGTH[phoneme]

            mem49 = (mem49 + phoneme_length_output[pos]) & 0xFF
            speedcounter = (mem49 + phase2) & 0xFF
            phase3 = (mem49 - phase1) & 0xFF
            transition = (phase1 + phase2) & 0xFF

            if (((transition - 2) & 0xFF) & 128) == 0:
                self._interpolate_pitch(pos, mem49, phase3, phoneme_length_output)
                table = 169
                while table < 175:
                    value = _s8(self._read(table, speedcounter) - self._read(table, phase3))
                    self._interpolate(transition, table, phase3, value)
                    table += 1
            pos += 1

        return (mem49 + phoneme_length_output[pos]) & 0xFF

    # -- sampled consonants ------------------------------------------------

    def _render_voiced_sample(self, hi, off, phase1) -> int:
        while True:
            bit = 8
            sample = SAMPLE_TABLE[hi + off]
            while True:
                if sample & 128:
                    self._output(3, 26)
                else:
                    self._output(4, 6)
                sample = (sample << 1) & 0xFF
                bit -= 1
                if bit == 0:
                    break
            off = (off + 1) & 0xFF
            phase1 = (phase1 + 1) & 0xFF
            if phase1 == 0:
                break
        return off

    def _render_unvoiced_sample(self, hi, off, mem53) -> None:
        while True:
            bit = 8
            sample = SAMPLE_TABLE[hi + off]
            while True:
                if sample & 128:
                    self._output(2, 5)
                else:
                    self._output(1, mem53)
                sample = (sample << 1) & 0xFF
                bit -= 1
                if bit == 0:
                    break
            off = (off + 1) & 0xFF
            if off == 0:
                break

    def _render_sample(self, mem66, consonant_flag, mem49) -> int:
        hibyte = ((consonant_flag & 7) - 1) & 0xFF
        hi = (hibyte * 256) & 0xFFFF
        pitchl = consonant_flag & 248
        if pitchl == 0:
            pitchl = self.pitches[mem49] >> 4
            return self._render_voiced_sample(hi, mem66, pitchl ^ 255)
        self._render_unvoiced_sample(hi, pitchl ^ 255, TAB48426[hibyte])
        return mem66

    # -- inner synthesis loop ----------------------------------------------

    def _combine_glottal_and_formants(self, phase1, phase2, phase3, y) -> None:
        tmp = MULTTABLE[SINUS[phase1] | self.amplitude1[y]]
        tmp += MULTTABLE[SINUS[phase2] | self.amplitude2[y]]
        tmp += 1 if tmp > 255 else 0
        tmp += MULTTABLE[RECTANGLE[phase3] | self.amplitude3[y]]
        tmp += 136
        tmp >>= 4
        self._output(0, tmp & 0xF)

    def _process_frames(self, mem48) -> None:
        speedcounter = 72
        phase1 = 0
        phase2 = 0
        phase3 = 0
        # mem66 reproduces upstream: processframes.c leaves it uninitialised.
        mem66 = 0
        y = 0

        glottal_pulse = self.pitches[0]
        mem38 = (glottal_pulse - (glottal_pulse >> 2)) & 0xFF

        while mem48:
            flags = self.sampled_consonant_flag[y]
            if flags & 248:
                mem66 = self._render_sample(mem66, flags, y)
                y = (y + 2) & 0xFF
                mem48 = (mem48 - 2) & 0xFF
                speedcounter = self.speed
            else:
                self._combine_glottal_and_formants(phase1, phase2, phase3, y)
                speedcounter = (speedcounter - 1) & 0xFF
                if speedcounter == 0:
                    y = (y + 1) & 0xFF
                    mem48 = (mem48 - 1) & 0xFF
                    if mem48 == 0:
                        return
                    speedcounter = self.speed
                glottal_pulse = (glottal_pulse - 1) & 0xFF
                if glottal_pulse != 0:
                    mem38 = (mem38 - 1) & 0xFF
                    if mem38 != 0 or flags == 0:
                        phase1 = (phase1 + self.frequency1[y]) & 0xFF
                        phase2 = (phase2 + self.frequency2[y]) & 0xFF
                        phase3 = (phase3 + self.frequency3[y]) & 0xFF
                        continue
                    mem66 = self._render_sample(mem66, flags, y)

            glottal_pulse = self.pitches[y]
            mem38 = (glottal_pulse - (glottal_pulse >> 2)) & 0xFF
            phase1 = 0
            phase2 = 0
            phase3 = 0

    # -- top-level render --------------------------------------------------

    def render(self, phoneme_index_output, stress_output, phoneme_length_output) -> None:
        """Render one clause segment, appending its samples to the buffer."""
        if phoneme_index_output[0] == 255:
            return
        self._create_frames(phoneme_index_output, stress_output, phoneme_length_output)
        t = self._create_transitions(phoneme_index_output, phoneme_length_output)
        if not self.singmode:
            self._assign_pitch_contour()
        self._rescale_amplitude()
        self._process_frames(t)
