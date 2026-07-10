"""Pronunciation dictionaries: the bundled one, and your own.

The engines ship with a dictionary because guessing a pronunciation from
spelling is unreliable in English. `SearchAllDicts` (`FrontEnd.c:1592-1608`)
consults application and user dictionaries before the built-in one, so a caller
has always been able to override a word.

    from pyretrotts.dictionaries import UserDictionary, use_dictionary

    mine = UserDictionary({"GIF": "g IH f", "PYRETROTTS": "p AY r EH t r OW t IY EH s"})
    with use_dictionary(mine):
        MacInTalkEngine().say("a GIF, in pyretrotts.", "out.wav")

Entries are written in MacinTalk mnemonics -- the same notation `g2p.phonemize`
returns, and the same one `[[mode PHON]]` accepts. `phoneme_names()` lists them.

With no user dictionary installed, lookup is exactly the built-in one, so a
classic render cannot change.

DECtalk ships six dictionaries of its own (US, UK, French, German, Spanish,
Latin-American Spanish), in its own notation. None is present here, and none can
be until the DECtalk engine is ported; see `NOTICE`.
"""
from __future__ import annotations

import pathlib
import threading
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from ._consts import kNoun, kUndefPOS
from ._lexicon import LexEntry
from ._phonemes import _Word_
from ._rawphon import MAGIC_MAP

__all__ = [
    "Dictionary",
    "UserDictionary",
    "load_dictionary",
    "use_dictionary",
    "active_dictionary",
    "parse_pronunciation",
]

_MNEMONICS: dict[str, int] = {}
for (_first, _second), _phoneme in MAGIC_MAP.items():
    _MNEMONICS[(_first + (_second or ""))] = _phoneme


@runtime_checkable
class Dictionary(Protocol):
    """Anything that can pronounce a word."""

    def lookup(self, word: str) -> LexEntry | None:
        """The entry for `word` (already uppercased), or None."""


def parse_pronunciation(text: str) -> list[int]:
    """`"g IH f"` -> the phoneme opcodes, `_Word_`-prefixed as the engine expects.

    Mnemonics may be separated by spaces or run together, and are matched
    longest-first exactly as `[[mode PHON]]` matches them.
    """
    opcodes = [_Word_]
    compact = text.replace(" ", "")
    position = 0
    while position < len(compact):
        for width in (2, 1):
            chunk = compact[position:position + width]
            if chunk in _MNEMONICS:
                opcodes.append(_MNEMONICS[chunk])
                position += width
                break
        else:
            raise ValueError(f"{compact[position]!r} is not a phoneme mnemonic")
    return opcodes


@dataclass(frozen=True)
class UserDictionary:
    """Words you want pronounced your way.

    Maps an uppercase word to a pronunciation written in MacinTalk mnemonics.
    Every entry is treated as a noun; the engine's own dictionary is what
    carries part-of-speech information.
    """

    words: Mapping[str, str] = field(default_factory=dict)

    def lookup(self, word: str) -> LexEntry | None:
        pronunciation = self.words.get(word.upper())
        if pronunciation is None:
            return None
        return LexEntry(
            phon_str=parse_pronunciation(pronunciation),
            pos_code1=[kNoun, kUndefPOS, kUndefPOS, kUndefPOS],
            comp_pos1=0,
            is_abbrev=False,
            is_compound=False,
            has_alt=False,
        )


def load_dictionary(path: str | pathlib.Path) -> UserDictionary:
    """Read a dictionary file: one `WORD  mnemonics` per line.

    Blank lines and lines starting with `;` or `#` are ignored, which is the
    comment convention DECtalk's own dictionary sources use.
    """
    words: dict[str, str] = {}
    for line in pathlib.Path(path).read_text().splitlines():
        line = line.strip()
        if not line or line[0] in ";#":
            continue
        word, _, pronunciation = line.partition(" ")
        if pronunciation.strip():
            words[word.upper()] = pronunciation.strip()
    return UserDictionary(words)


# The overlay is per-thread: a caller installing a dictionary must not change
# what another thread hears.
_active = threading.local()


def active_dictionary() -> Dictionary | None:
    """The dictionary consulted before the built-in one, if any."""
    return getattr(_active, "dictionary", None)


@contextmanager
def use_dictionary(dictionary: Dictionary | None) -> Iterator[None]:
    """Consult `dictionary` before the built-in one, for this thread."""
    previous = active_dictionary()
    _active.dictionary = dictionary
    try:
        yield
    finally:
        _active.dictionary = previous
