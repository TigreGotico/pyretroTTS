"""Automated C-vs-Python comparison for all voices and test phrases."""
import sys, os, subprocess, re, json, struct
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

C_BIN = os.path.expanduser("~/AgentWorkspaces/ovos/lintalker-c/bin/Debug/test_harness")

VOICES = [
    "Fred", "Kathy", "Princess", "Junior", "Ralph", "Whisper",
    "Zarvox", "Trinoids", "Bubbles", "Boing", "Bells",
    "Hysterical", "Deranged", "GoodNews", "BadNews", "PipeOrgan", "Cellos"
]

VOICE_WORDS = [
    "hello", "goodbye", "testing one two three",
    "the quick brown fox", "this is a test",
    "I am.", "hello world",
]

def run_c(voice_idx, text):
    """Run C test harness, return (stdout, stderr)."""
    env = os.environ.copy()
    # Run with time limit
    try:
        r = subprocess.run(
            [C_BIN, "-v", str(voice_idx), text],
            capture_output=True, timeout=30, env=env,
            cwd=os.path.dirname(C_BIN)
        )
        return r.stdout.decode('latin-1'), r.stderr.decode('latin-1')
    except subprocess.TimeoutExpired:
        return None, None
    except FileNotFoundError:
        return None, None

def parse_sentence_plan(stdout):
    """Parse C test_harness stdout into phonemes, ctrls, durs, pitches."""
    lines = stdout.strip().split('\n')
    phonemes = []
    ctrls = []
    durs = []
    pitch_freq = []
    pitch_time = []
    pitch_flags = []
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line.startswith('P ') and len(line) > 2:
            parts = line.split()
            if len(parts) == 4:
                try:
                    idx = int(parts[1])
                    phon = int(parts[2])
                    ctrl = int(parts[3])
                    dur = int(parts[0])  # not right
                except ValueError:
                    pass
        # Actually let me look at the actual output format better
        # P   0     23     268500993       1
        # P   1     11     268502089      26
        # P   2     54             0      10
        # etc.
    
    return phonemes, ctrls, durs

def main():
    # Quick test: just run C for each voice, capture WAV size and frame count
    print("=== C test harness baseline ===")
    results = []
    for vi, vname in enumerate(VOICES):
        for text in VOICE_WORDS[:1]:  # just "hello" for now
            so, se = run_c(vi, text)
            if so is None:
                print(f"  FAIL: voice {vi} {vname}")
                continue
            
            # Parse frame count from stderr
            frames = len(re.findall(r'^FLINE ', se, re.MULTILINE))
            
            # Get WAV sample count
            wav_path = os.path.join(os.path.dirname(C_BIN), "test_output.wav")
            wav_samples = 0
            if os.path.exists(wav_path):
                with open(wav_path, 'rb') as f:
                    f.seek(40)  # data subchunk size
                    data = f.read(4)
                    if len(data) == 4:
                        wav_samples = struct.unpack('<I', data)[0] // 2
            
            print(f"  {vname:12s} text='{text}'  frames={frames:4d}  WAV_samples={wav_samples}")
            results.append((vi, vname, text, frames, wav_samples))
    
    print("\n=== Done ===")

if __name__ == '__main__':
    main()
