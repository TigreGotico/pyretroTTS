"""List the 17 built-in DECtalk voices ported into lintalker._data."""
from lintalker import _data

VOICE_NAMES = [
    "Fred", "Kathy", "Princess", "Junior", "Ralph", "Whisper",
    "Zarvox", "Trinoids", "Bubbles", "Boing", "Bells",
    "Hysterical", "Deranged", "GoodNews", "BadNews", "PipeOrgan", "Cellos",
]

if __name__ == "__main__":
    for name in VOICE_NAMES:
        voice = getattr(_data, f"{name}_Voice")
        print(f"{name}: {len(voice)} fields")
