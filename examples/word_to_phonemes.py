"""Turn a single English word into a phoneme opcode list via the ported
letter-to-sound rule engine (EngToP.c).

This does not tokenize sentences or consult the pronunciation dictionary
(english_lex) — see README.md / docs/architecture.md for the current scope.
"""
from lintalker._engtop import engtop
from lintalker._phonemes import PHONEME_NAMES_BY_INDEX


def phonemes_to_names(opcodes):
    return [PHONEME_NAMES_BY_INDEX.get(op, f"?{op}") for op in opcodes]


if __name__ == "__main__":
    for word in ["HELLO", "GOODBYE", "PSYCHOLOGY", "KNIGHT"]:
        opcodes = engtop(word)
        print(f"{word}: {phonemes_to_names(opcodes)}")
