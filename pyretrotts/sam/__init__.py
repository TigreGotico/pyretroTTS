"""SAM (Software Automatic Mouth) -- a bit-exact port of Don't Ask Software's
1982 Commodore 64 synthesizer.

Derived from vidarh/SAM, which is an opcode-by-opcode translation of SoftVoice,
Inc.'s 6502 program; NOT covered by this project's MIT licence; see NOTICE.

This subpackage is kept separate from the MIT-licensed core precisely because
SAM's provenance differs; see the SAM section of NOTICE.
"""
from .engine import SAMEngine, SamVoice

__all__ = ["SAMEngine", "SamVoice"]
