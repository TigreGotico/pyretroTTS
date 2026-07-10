"""English text to SAM phoneme mnemonics (reciter.c's rule engine).

Derived from vidarh/SAM, which is an opcode-by-opcode translation of SoftVoice,
Inc.'s 6502 program; NOT covered by this project's MIT licence; see NOTICE.

The reciter walks the input left to right, and at each letter tries the rules
for that letter in order until one whose bracketed pattern and left/right
context all match; it then appends that rule's phonemes to the output. The
control flow keeps reciter.c's three jump targets -- next character (pos36554),
next rule (pos36700) and apply rule (pos37184) -- as exceptions rather than
gotos. `mem56`, `mem61`, `X` and `A` are the shared 6502 pseudo-registers.
"""
from __future__ import annotations

from .tables import RULES, RULES2, TAB36376, TAB37489, TAB37515


class _NextChar(Exception):
    """goto pos36554: emit finished, advance to the next input character."""


class _NextRule(Exception):
    """goto pos36700: current rule failed, try the next candidate rule."""


class _Return0(Exception):
    """reciter.c's `return 0`: the whole conversion fails."""


class _Done(Exception):
    """The terminal '[' or the overflow guard: conversion succeeded."""


def _get_rule_byte(mem62: int, y: int) -> int:
    if mem62 >= 37541:
        return RULES2[mem62 - 37541 + y]
    return RULES[mem62 - 32000 + y]


class _Reciter:
    def __init__(self, text: bytes) -> None:
        self.inputtemp = bytearray(256)
        self.out = bytearray(256)
        self.mem56 = 255
        self.mem61 = 255
        self.A = 0
        self.X = 0

        self.inputtemp[0] = ord(" ")
        src = bytearray(256)
        src[: len(text)] = text
        x = 0
        while True:
            a = src[x] & 127
            if a >= 112:
                a = a & 95
            elif a >= 96:
                a = a & 79
            x += 1
            self.inputtemp[x] = a
            if x >= 255:
                break
        self.inputtemp[255] = 27

    # -- 6502 helper subroutines (share the A/X pseudo-registers) ----------

    def _code37055(self, npos: int, mask: int) -> int:
        self.X = npos
        return TAB36376[self.inputtemp[self.X]] & mask

    def _match(self, s: str) -> int:
        for ch in s:
            a = self.inputtemp[self.X]
            self.X = (self.X + 1) & 0xFF
            if a != ord(ch):
                return 0
        return 1

    def _handle_ch2(self, ch: int, mem: int) -> int:
        self.X = mem
        tmp = TAB36376[self.inputtemp[mem]]
        if ch == ord(" "):
            return 1 if tmp & 128 else 0
        if ch == ord("#"):
            return 1 if not (tmp & 64) else 0
        if ch == ord("."):
            return 1 if not (tmp & 8) else 0
        if ch == ord("^"):
            return 1 if not (tmp & 32) else 0
        return -1

    def _handle_ch(self, ch: int, mem: int) -> int:
        self.X = mem
        tmp = TAB36376[self.inputtemp[self.X]]
        if ch == ord(" "):
            if tmp & 128:
                return 1
        elif ch == ord("#"):
            if (tmp & 64) == 0:
                return 1
        elif ch == ord("."):
            if (tmp & 8) == 0:
                return 1
        elif ch == ord("&"):
            if (tmp & 16) == 0:
                if self.inputtemp[self.X] != 72:
                    return 1
                self.X = (self.X + 1) & 0xFF
        elif ch == ord("^"):
            if (tmp & 32) == 0:
                return 1
        elif ch == ord("+"):
            self.X = mem
            c = self.inputtemp[self.X]
            if c != 69 and c != 73 and c != 89:
                return 1
        else:
            return -1
        return 0

    def _emit(self, value: int) -> None:
        self.mem56 = (self.mem56 + 1) & 0xFF
        self.out[self.mem56] = value

    # -- pos36554: scan to the next letter/punctuation --------------------

    def _scan(self) -> int:
        """Return the rule base address for the next letter to expand."""
        while True:
            while True:
                self.mem61 = (self.mem61 + 1) & 0xFF
                self.X = self.mem61
                mem64 = self.inputtemp[self.X]
                if mem64 == ord("["):
                    self._emit(155)
                    raise _Done
                if mem64 != ord("."):
                    break
                self.X = (self.X + 1) & 0xFF
                if (TAB36376[self.inputtemp[self.X]] & 1) != 0:
                    break
                self._emit(ord("."))
                self.X = self.mem56

            mem57 = TAB36376[mem64]
            if (mem57 & 2) != 0:
                return 37541
            if mem57 != 0:
                break
            self.inputtemp[self.X] = ord(" ")
            self.mem56 = (self.mem56 + 1) & 0xFF
            self.X = self.mem56
            if self.X > 120:
                self.out[self.X] = 155
                raise _Done
            self.out[self.X] = 32

        if not (mem57 & 128):
            raise _Return0
        self.X = (mem64 - ord("A")) & 0xFF
        return TAB37489[self.X] | (TAB37515[self.X] << 8)

    # -- pos36700: try each candidate rule --------------------------------

    def _process(self, mem62: int) -> None:
        self.mem62 = mem62
        while True:
            try:
                self._try_rule()
                return
            except _NextRule:
                continue

    def _try_rule(self) -> None:
        while True:
            self.mem62 += 1
            if (_get_rule_byte(self.mem62, 0) & 128) != 0:
                break
        mem62 = self.mem62

        y = 0
        while True:
            y += 1
            if _get_rule_byte(mem62, y) == ord("("):
                break
        mem66 = y
        while True:
            y += 1
            if _get_rule_byte(mem62, y) == ord(")"):
                break
        mem65 = y
        while True:
            y += 1
            if (_get_rule_byte(mem62, y) & 127) == ord("="):
                break
        mem64 = y

        mem60 = self.X = self.mem61
        y = mem66 + 1
        while True:
            if _get_rule_byte(mem62, y) != self.inputtemp[self.X]:
                raise _NextRule
            y += 1
            if y == mem65:
                break
            self.X = (self.X + 1) & 0xFF
            mem60 = self.X

        mem59 = self.mem61
        mem58 = self._match_left(mem62, mem59, mem60, mem66)
        self._apply_right(mem62, mem58, mem60, mem64, mem65)

    def _match_left(self, mem62, mem59, mem60, mem66) -> int:
        while True:
            while True:
                mem66 = (mem66 - 1) & 0xFF
                mem57 = _get_rule_byte(mem62, mem66)
                if (mem57 & 128) != 0:
                    return mem60  # mem58 = mem60; fall through to right context
                self.X = mem57 & 127
                if (TAB36376[self.X] & 128) == 0:
                    break
                if self.inputtemp[(mem59 - 1) & 0xFF] != mem57:
                    raise _NextRule
                mem59 = (mem59 - 1) & 0xFF

            ch = mem57
            r = self._handle_ch2(ch, (mem59 - 1) & 0xFF)
            if r == -1:
                if ch == ord("&"):
                    if not self._code37055((mem59 - 1) & 0xFF, 16):
                        if self.inputtemp[self.X] != ord("H"):
                            r = 1
                        else:
                            self.X = (self.X - 1) & 0xFF
                            self.A = self.inputtemp[self.X]
                            if self.A != ord("C") and self.A != ord("S"):
                                r = 1
                elif ch == ord("@"):
                    if not self._code37055((mem59 - 1) & 0xFF, 4):
                        self.A = self.inputtemp[self.X]
                        if self.A != 72:
                            r = 1
                        if self.A != 84 and self.A != 67 and self.A != 83:
                            r = 1
                elif ch == ord("+"):
                    self.X = (mem59 - 1) & 0xFF
                    self.A = self.inputtemp[self.X]
                    if self.A != ord("E") and self.A != ord("I") and self.A != ord("Y"):
                        r = 1
                elif ch == ord(":"):
                    while self._code37055((mem59 - 1) & 0xFF, 32):
                        mem59 = (mem59 - 1) & 0xFF
                    continue
                else:
                    raise _Return0
            if r == 1:
                raise _NextRule
            mem59 = self.X

    def _apply_right(self, mem62, mem58, mem60, mem64, mem65) -> None:
        first = True
        while True:  # do ... while(A == '%')
            if not first:
                self.X = (mem58 + 1) & 0xFF
                if self.inputtemp[self.X] == ord("E"):
                    if TAB36376[self.inputtemp[(self.X + 1) & 0xFF]] & 128:
                        self.X = (self.X + 1) & 0xFF
                        self.A = self.inputtemp[self.X]
                        if self.A == ord("L"):
                            self.X = (self.X + 1) & 0xFF
                            if self.inputtemp[self.X] != ord("Y"):
                                raise _NextRule
                        elif (
                            self.A != ord("R")
                            and self.A != ord("S")
                            and self.A != ord("D")
                            and not self._match("FUL")
                        ):
                            raise _NextRule
                else:
                    if not self._match("ING"):
                        raise _NextRule
                    mem58 = self.X
            first = False

            r = 0
            while True:  # pos37184: do ... while(r == 0)
                broke = False
                while True:
                    y = (mem65 + 1) & 0xFF
                    if y == mem64:
                        self.mem61 = mem60
                        while True:
                            mem57 = _get_rule_byte(mem62, y)
                            self.A = mem57 & 127
                            if self.A != ord("="):
                                self._emit(self.A)
                            if (mem57 & 128) != 0:
                                raise _NextChar
                            y = (y + 1) & 0xFF
                    mem65 = y
                    mem57 = _get_rule_byte(mem62, y)
                    if (TAB36376[mem57] & 128) == 0:
                        broke = True
                        break
                    if self.inputtemp[(mem58 + 1) & 0xFF] != mem57:
                        r = 1
                        break
                    mem58 = (mem58 + 1) & 0xFF

                if r == 0 and broke:
                    self.A = mem57
                    if self.A == ord("@"):
                        if self._code37055((mem58 + 1) & 0xFF, 4) == 0:
                            self.A = self.inputtemp[self.X]
                            if self.A != 82 and self.A != 84 and self.A != 67 and self.A != 83:
                                r = 1
                        else:
                            r = -2
                    elif self.A == ord(":"):
                        while self._code37055((mem58 + 1) & 0xFF, 32):
                            mem58 = self.X
                        r = -2
                    else:
                        r = self._handle_ch(self.A, (mem58 + 1) & 0xFF)

                if r == 1:
                    raise _NextRule
                if r == -2:
                    r = 0
                    continue
                if r == 0:
                    mem58 = self.X
                if r != 0:
                    break

            if self.A == ord("%"):
                continue
            raise _Return0

    def run(self) -> bytes | None:
        try:
            while True:
                mem62 = self._scan()
                try:
                    self._process(mem62)
                except _NextChar:
                    continue
        except _Done:
            return bytes(self.out[: self.mem56 + 1])
        except _Return0:
            return None


def text_to_phonemes(text: bytes) -> bytes | None:
    """Convert uppercased English `text` to SAM phoneme bytes ending in 0x9B.

    Returns None when no rule chain matches, mirroring reciter.c returning 0.
    """
    return _Reciter(text + b" [").run()
