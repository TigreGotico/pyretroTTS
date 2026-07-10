"""Comprehensive voice-by-voice C vs Python comparison.

For each of the 17 voices, runs the C test harness through the full pipeline
(frontend + backend) to produce reference data, then feeds the extracted
sentence plan through the Python backend and compares frame data + audio --
including the actual PCM sample VALUES, not just their count.

Usage:
    python3 tests/test_voices.py                     # Fred only (quick smoke)
    python3 tests/test_voices.py --all               # all 17 voices
    python3 tests/test_voices.py --voices 0,2,5      # specific voices
    python3 tests/test_voices.py --texts "hello"     # one text

IMPORTANT HISTORY -- read before trusting a green run of this file:
until real sample-level comparison was added, this file only compared
per-frame CONTROL values (f0/formants/amplitude/bandwidth) and the PCM
sample COUNT, never the actual synthesized sample VALUES. A user report
that Cellos/PipeOrgan/Bells/Hysterical still sounded like garbage led to
discovering the actual audio waveform was completely wrong for those
voices despite every frame-level control value and the WAV length
matching exactly. Two real bugs in `_backend.py`'s `init_voice` were
found: (1) `zz.hfEmph` (a per-voice high-frequency emphasis flag used in
`say_frame`'s per-sample output stage) was hardcoded to always-on,
ignoring the voice data's `emphVoice` flag -- correct only for voices
that happen to have `emphVoice=1` (e.g. Fred). (2) `zz.reverbDepth`/
`zz.reverbDelay` were raw percentage copies with no fixed-point scaling
or clipping at all, wildly overstating the reverb echo contribution for
every voice with reverb enabled. Both are fixed. Moral: matching
intermediate control parameters does not prove the final signal matches
-- always verify the actual output your users hear, not just the values
that feed into producing it.
"""
import os
import struct
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

C_BIN = os.path.expanduser("~/AgentWorkspaces/ovos/lintalker-c/bin/Debug/test_harness")

import pylintalker._backend as be
from pylintalker._backend import (
    calc_ramp_steps,
    e_fill_next_frame,
    say_frame,
    start_new_pitch_clause,
    start_talk,
)
from pylintalker._consts import (
    kFrame1,
    kSpeakLastFrame,
)
from pylintalker._data import (
    BadNews_Voice,
    Bells_Voice,
    Boing_Voice,
    Bubbles_Voice,
    Cellos_Voice,
    Deranged_Voice,
    Fred_Voice,
    GoodNews_Voice,
    Hysterical_Voice,
    Junior_Voice,
    Kathy_Voice,
    PipeOrgan_Voice,
    Princess_Voice,
    Ralph_Voice,
    Trinoids_Voice,
    Whisper_Voice,
    Zarvox_Voice,
)
from pylintalker.api import new_voice

VOICE_DICTS = [
    Fred_Voice,       # 0
    Kathy_Voice,      # 1
    Princess_Voice,   # 2
    Junior_Voice,     # 3
    Ralph_Voice,      # 4
    Whisper_Voice,    # 5
    Zarvox_Voice,     # 6
    Trinoids_Voice,   # 7
    Bubbles_Voice,    # 8
    Boing_Voice,      # 9
    Bells_Voice,      # 10
    Hysterical_Voice, # 11
    Deranged_Voice,   # 12
    GoodNews_Voice,   # 13
    BadNews_Voice,    # 14
    PipeOrgan_Voice,  # 15
    Cellos_Voice,     # 16
]

VOICE_NAMES = [
    "Fred", "Kathy", "Princess", "Junior", "Ralph", "Whisper",
    "Zarvox", "Trinoids", "Bubbles", "Boing", "Bells",
    "Hysterical", "Deranged", "GoodNews", "BadNews", "PipeOrgan", "Cellos",
]

DEFAULT_TEXTS = [
    "hello",
    "goodbye",
    "testing one two three",
    "I am.",
]


def run_c(voice_idx, text):
    """Run C test harness, return (stdout, stderr, wav_path)."""
    wav_path = os.path.join(os.path.dirname(C_BIN), "test_output.wav")
    if os.path.exists(wav_path):
        os.remove(wav_path)
    try:
        r = subprocess.run(
            [C_BIN, "-v", str(voice_idx), text],
            capture_output=True, timeout=60,
            cwd=os.path.dirname(C_BIN),
        )
        return r.stdout, r.stderr, wav_path
    except subprocess.TimeoutExpired:
        return None, None, None


def parse_sentence_plan(stdout_bytes):
    """Extract phoneme/ctrl/dur/pitch arrays from C stdout."""
    text = stdout_bytes.decode('latin-1')
    lines = text.split('\n')

    phonemes = []
    ctrls = []
    durs = []
    pitch_freq = []
    pitch_time = []
    pitch_flags = []

    in_phon_table = False
    in_pitch_table = False

    for line in lines:
        line = line.strip()
        if line.startswith('S '):
            in_phon_table = True
            in_pitch_table = False
            continue
        if not line:
            continue

        if in_phon_table and line.startswith('N '):
            in_phon_table = False
            in_pitch_table = True

        if in_phon_table and line.startswith('P '):
            parts = line.split()
            if len(parts) >= 5:
                phonemes.append(int(parts[2]))  # index=parts[1], phon=parts[2], ctrl=parts[3], dur=parts[4]
                ctrls.append(int(parts[3]))
                durs.append(int(parts[4]))

        if in_pitch_table and line.startswith('N '):
            parts = line.split()
            if len(parts) >= 5:
                pitch_freq.append(int(parts[2]))  # index=parts[1], freq=parts[2], time=parts[3], flags=parts[4]
                pitch_time.append(int(parts[3]))
                pitch_flags.append(int(parts[4]))

    return phonemes, ctrls, durs, pitch_freq, pitch_time, pitch_flags


def parse_frames(stdout_bytes):
    """Extract F-lines from C stdout."""
    text = stdout_bytes.decode('latin-1')
    frames = []
    for line in text.split('\n'):
        line = line.strip()
        if not line.startswith('F '):
            continue
        parts = line.split()
        if len(parts) < 20:
            continue
        try:
            frames.append({
                'num': int(parts[1]),
                'phon_idx': int(parts[2]),
                'phon_id': int(parts[3]),
                'dur_done': int(parts[4]),
                'f0': int(parts[5]),
                'f1': int(parts[6]),
                'f2': int(parts[7]),
                'f3': int(parts[8]),
                'bw1': int(parts[9]),
                'bw2': int(parts[10]),
                'bw3': int(parts[11]),
                'Av': int(parts[12]),
                'Af': int(parts[13]),
                'a2': int(parts[14]),
                'a3': int(parts[15]),
                'a4': int(parts[16]),
                'a5': int(parts[17]),
                'a6': int(parts[18]),
                'AB': int(parts[19]),
                'FNZ': int(parts[20]),
                'marker': int(parts[21]),
            })
        except (ValueError, IndexError):
            continue
    return frames


def run_python_backend(vv, phonemes, ctrls, durs,
                       pitch_freq, pitch_time, pitch_flags):
    """Run the Python synthesis backend with given reference arrays."""
    # Fill phoneme buffers
    for i in range(len(phonemes)):
        vv.phon_Buf_2[i] = phonemes[i]
        vv.phon_Ctrl_Buf_2[i] = ctrls[i]
        vv.dur_Buf[i] = durs[i]
    vv.phonBuf_2_In_Index = len(phonemes)

    # Fill pitch buffers
    for i in range(len(pitch_freq)):
        vv.pitch_Buf_Freq[i] = pitch_freq[i]
        vv.pitch_Buf_Time[i] = pitch_time[i]
        vv.pitch_Buf_Flags[i] = pitch_flags[i]
    vv.pitchBuf_In_Index = len(pitch_freq)

    # Init ramp steps
    calc_ramp_steps(vv)
    start_new_pitch_clause(vv)

    # Run pipeline with frame capture
    frames = []
    frame_num = [0]

    def on_frame(vv):
        zz = vv.synthVars
        if zz.curFrameBuf == kFrame1:
            fp = zz.frameBuf2
        else:
            fp = zz.frameBuf1
        phon_idx = vv.cur_PhonBuf_Index_CF
        phon_id = vv.phon_Buf_2[phon_idx] if phon_idx < len(vv.phon_Buf_2) else 0
        frames.append({
            'num': frame_num[0],
            'phon_idx': phon_idx,
            'phon_id': phon_id,
            'dur_done': vv.dur_Done_in_Phon_CF,
            'f0': fp.f0, 'f1': fp.f1, 'f2': fp.f2, 'f3': fp.f3,
            'bw1': fp.bw1, 'bw2': fp.bw2, 'bw3': fp.bw3,
            'Av': fp.Av, 'Af': fp.Af,
            'a2': fp.a2, 'a3': fp.a3, 'a4': fp.a4, 'a5': fp.a5, 'a6': fp.a6,
            'AB': fp.AB, 'FNZ': fp.FNZ, 'marker': fp.marker,
        })
        frame_num[0] += 1

    be.post_frame_hook = on_frame
    start_talk(vv)
    while vv.speakState != kSpeakLastFrame:
        say_frame(vv)
        e_fill_next_frame(vv)
    say_frame(vv)
    be.post_frame_hook = None

    return frames, vv


def get_wav_samples(wav_path):
    """Read 16-bit PCM samples from a WAV file."""
    with open(wav_path, 'rb') as f:
        f.seek(40)
        data_size = struct.unpack('<I', f.read(4))[0]
        n_samples = data_size // 2
        f.seek(44)
        raw = f.read(data_size)
    return struct.unpack(f'<{n_samples}h', raw), n_samples


def compare_frames(c_frames, py_frames):
    """Compare C and Python frame data. Returns list of mismatches."""
    keys = ['f0', 'f1', 'f2', 'f3', 'bw1', 'bw2', 'bw3',
            'Av', 'Af', 'a2', 'a3', 'a4', 'a5', 'a6', 'AB', 'FNZ', 'marker',
            'phon_idx', 'phon_id', 'dur_done']

    mismatches = []
    for i, (cf, pf) in enumerate(zip(c_frames, py_frames, strict=False)):
        for k in keys:
            cv = cf[k]
            pv = pf[k]
            if cv != pv:
                mismatches.append((i, k, cv, pv))

    return mismatches


def verify_voice(voice_idx, text, verbose=True):
    """Run full C vs Python comparison for one (voice, text) combo."""
    voice_name = VOICE_NAMES[voice_idx]
    vd = VOICE_DICTS[voice_idx]

    # Run C
    c_stdout, c_stderr, wav_path = run_c(voice_idx, text)
    if c_stdout is None:
        return {'voice': voice_idx, 'name': voice_name, 'text': text,
                'error': 'C timeout or failure'}

    # Parse C outputs
    phonemes, ctrls, durs, pf, pt, pfl = parse_sentence_plan(c_stdout)
    c_frames = parse_frames(c_stdout)

    if not phonemes:
        return {'voice': voice_idx, 'name': voice_name, 'text': text,
                'error': 'no sentence plan found'}

    # Get WAV info -- actual sample VALUES, not just length. A per-frame
    # CONTROL-parameter match (f0/formants/amplitude/bandwidth, compared
    # below) does NOT guarantee the actual synthesized PCM waveform
    # matches: say_frame's per-sample DSP loop (glottal source mixing,
    # cascade/parallel resonator filters, emphasis, reverb) has its own
    # state and voice-specific parameters that never appear in the
    # per-frame dump at all. This was a real, confirmed gap: frame-level
    # control values matched exactly for Cellos/PipeOrgan/Bells/Hysterical
    # while actual PCM samples were completely wrong (hfEmph hardcoded to
    # always-on regardless of the per-voice emphVoice flag, and
    # reverbDepth/reverbDelay copied as raw percentages with no fixed-point
    # scaling or clipping) -- neither bug was visible without comparing
    # real sample values.
    c_wav_samples = ()
    c_wav_len = 0
    if os.path.exists(wav_path):
        c_wav_samples, c_wav_len = get_wav_samples(wav_path)

    # Run Python
    vv = new_voice(vd)
    py_frames, vv = run_python_backend(vv, phonemes, ctrls, durs, pf, pt, pfl)

    # Collect Python audio
    py_pcm = bytes(vv.sampleBuffer) if hasattr(vv, 'sampleBuffer') else b''
    py_wav_len = len(py_pcm) // 2
    py_wav_samples = struct.unpack(f'<{py_wav_len}h', py_pcm) if py_wav_len else ()

    # Compare frame counts
    c_fc = len(c_frames)
    py_fc = len(py_frames)

    # Compare frame data (only if counts match)
    mismatches = []
    if c_fc == py_fc:
        mismatches = compare_frames(c_frames, py_frames)
    else:
        mismatches = [(-1, 'frame_count', c_fc, py_fc)]

    # Compare actual PCM sample values (only if counts match)
    sample_mismatches = 0
    if c_wav_len == py_wav_len:
        sample_mismatches = sum(1 for a, b in zip(c_wav_samples, py_wav_samples, strict=False) if a != b)
    else:
        sample_mismatches = -1  # length mismatch itself is the failure

    return {
        'voice': voice_idx,
        'name': voice_name,
        'text': text,
        'c_frames': c_fc,
        'py_frames': py_fc,
        'c_wav_samples': c_wav_len,
        'py_wav_samples': py_wav_len,
        'sample_mismatches': sample_mismatches,
        'phonemes': len(phonemes),
        'mismatches': mismatches,
        'error': None,
    }


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--all', action='store_true', help='Test all 17 voices')
    parser.add_argument('--voices', type=str, default='0',
                        help='Comma-separated voice indices to test')
    parser.add_argument('--texts', type=str, default=None,
                        help='Comma-separated texts')
    args = parser.parse_args()

    if args.all:
        voice_indices = list(range(17))
    else:
        voice_indices = [int(v.strip()) for v in args.voices.split(',')]

    if args.texts:
        texts = [t.strip() for t in args.texts.split(',')]
    else:
        texts = DEFAULT_TEXTS

    total_errors = 0
    total_mismatches = 0

    for vi in voice_indices:
        for text in texts:
            result = verify_voice(vi, text)

            if result.get('error'):
                print(f"FAIL {VOICE_NAMES[vi]:12s} text='{text}': {result['error']}")
                total_errors += 1
                continue

            mm = len(result['mismatches'])
            sm = result['sample_mismatches']
            report = (
                f"  {VOICE_NAMES[vi]:12s} text='{text}'  "
                f"frames={result['c_frames']}  "
                f"WAV={result['c_wav_samples']}  "
                f"phon={result['phonemes']}  "
            )
            if result['c_frames'] != result['py_frames']:
                report += f"**FRAME COUNT** C={result['c_frames']} Py={result['py_frames']}"
                total_mismatches += 1
            elif mm > 0:
                # Show first 3 mismatches
                details = ' '.join(f"[fr{m[0]} {m[1]}: C={m[2]} Py={m[3]}]" for m in result['mismatches'][:3])
                report += f"**{mm} mismatches** {details}"
                total_mismatches += mm
                if mm > 3:
                    report += f" ... (+{mm-3} more)"
            elif sm != 0:
                # Frame-level control values matched, but actual PCM sample
                # values didn't -- a real bug in say_frame's per-sample DSP
                # loop, invisible to the frame-level comparison above.
                report += (
                    f"**{sm} SAMPLE mismatches** (C={result['c_wav_samples']} "
                    f"Py={result['py_wav_samples']} samples)" if sm > 0
                    else f"**WAV LENGTH mismatch** C={result['c_wav_samples']} Py={result['py_wav_samples']}"
                )
                total_mismatches += max(sm, 1)
            else:
                report += "OK"

            print(report)

    print(f"\nSummary: {len(voice_indices)} voices × {len(texts)} texts = "
          f"{len(voice_indices)*len(texts)} tests")
    if total_mismatches:
        print(f"FAIL: {total_mismatches} mismatches found")
        sys.exit(1)
    else:
        print("ALL PASSED")

if __name__ == '__main__':
    main()
