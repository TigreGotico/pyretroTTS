"""DECtalk `[: ]` command parser (`cmd/`, US command table `c_us_cde.h`).

Derived from the Fonix/Force DECtalk C source (`dectalk/dectalk`,
`src/dapi/src/cmd/`). FONIX Corporation declares that source proprietary and
confidential. This file is NOT covered by this project's MIT licence. See
NOTICE.

The C `cmd/` layer scans a text+markup string, splitting it into plain-text runs
(handed to `lts/`) and inline commands (voice select, rate, mode switches,
`[:dv]` voice definitions, pitch, ...). This ports the scanning and the US
command table (`c_us_cde.h:390-485`) into a list of `TextRun` / `Command`
events plus the resolved control state a run is spoken under.

The parser reconciles with the singing-notation reader in
`pyretrotts/_dectalk.py`: both scan `[:...]` the same way (a command runs to the
closing `]` or to the next `[:`, closers routinely omitted), but this module
targets the front-end control model rather than a sung score.

Not ported: the argument *effects* beyond voice / rate / mode (`[:dv]` parameter
resolution, `[:pitch]`, `[:tone]`, `[:play]`, DTMF), and the `[:phoneme on]`
phonetic-input decoder (`cm_phon.c`), whose text is captured on the command but
not turned into phoneme codes here.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# c_us_cde.h:403-415 -- `[:n?]` voice shortcuts to the ten built-in voices,
# in the `-s N` / voices.py order (nc/Chris has no `-s` slot).
VOICE_SELECT: dict[str, int] = {
    "np": 0, "nb": 1, "nh": 2, "nf": 3, "nd": 4,
    "nk": 5, "nu": 6, "nr": 7, "nw": 8, "nv": 9,
}

# c_us_cde.h:390-485 -- command name -> argument signature (d=decimal, a=alpha,
# ""=none). The scan needs the names; effects are resolved for the subset below.
COMMANDS: dict[str, str] = {
    "rate": "d", "latin": "d", "name": "d",
    "comma": "d", "cp": "d", "period": "d", "pp": "d",
    "volume": "add", "vs": "d", "index": "add", "error": "a",
    "phoneme": "aaa", "log": "aa", "mode": "aa", "say": "a",
    "punctuation": "a", "skip": "a", "pause": "d", "play": "a",
    "resume": "", "sync": "", "flush": "ad", "enable": "",
    "mtone": "dddd", "dial": "a", "tone": "dd", "timeout": "d",
    "pronounce": "aa", "digitized": "", "language": "a", "remove": "",
    "pitch": "d", "define_voice": "ad*", "dv": "ad*", "debug": "h",
    "setv": "d", "loadv": "d", "gender": "a", "preamble": "d",
    "dbgv": "dddddddddd",
}
COMMANDS.update({name: "" for name in VOICE_SELECT})

# cm_pars.c: a command body runs to the closing `]`, or to the next `[:` when
# the closer is omitted. Matches pyretrotts/_dectalk.py's `_COMMAND`.
_COMMAND = re.compile(r"\[:\s*([a-zA-Z_]+)((?:(?!\[:)[^\]])*)\]?")


@dataclass(frozen=True)
class TextRun:
    """A run of plain text to hand to the letter-to-sound stage."""

    text: str


@dataclass(frozen=True)
class Command:
    """One `[: ]` command: its name and raw argument string."""

    name: str
    args: str


@dataclass(frozen=True)
class Control:
    """Front-end control state a text run is spoken under."""

    voice: int = 0
    rate: int | None = None
    phoneme_mode: bool = False


Event = TextRun | Command


def tokenize(markup: str) -> list[Event]:
    """Split a text+markup string into `TextRun` and `Command` events.

    Unknown `[:...]` tokens are still emitted as `Command`s (the C parser
    likewise scans them before rejecting), so a caller can diff the token stream.
    """
    events: list[Event] = []
    pos = 0
    for m in _COMMAND.finditer(markup):
        if m.start() > pos:
            events.append(TextRun(markup[pos:m.start()]))
        events.append(Command(m.group(1).lower(), m.group(2).strip()))
        pos = m.end()
    if pos < len(markup):
        events.append(TextRun(markup[pos:]))
    return events


def _apply(control: Control, cmd: Command) -> Control:
    name = cmd.name
    if name in VOICE_SELECT:
        return Control(VOICE_SELECT[name], control.rate, control.phoneme_mode)
    if name in ("rate", "name") and cmd.args.lstrip("-").isdigit():
        return Control(control.voice, int(cmd.args), control.phoneme_mode)
    if name == "phoneme":
        on = "on" in cmd.args.split()
        return Control(control.voice, control.rate, on)
    return control


@dataclass(frozen=True)
class Run:
    """A text run with the control state in force when it is spoken."""

    control: Control
    text: str


def runs(markup: str) -> list[Run]:
    """Resolve `markup` to text runs, each tagged with its control state.

    Commands mutate a running `Control` (voice/rate/phoneme-mode); text between
    them becomes a `Run`. Empty/whitespace-only runs are dropped.
    """
    control = Control()
    out: list[Run] = []
    for ev in tokenize(markup):
        if isinstance(ev, Command):
            control = _apply(control, ev)
        elif ev.text.strip():
            out.append(Run(control, ev.text))
    return out
