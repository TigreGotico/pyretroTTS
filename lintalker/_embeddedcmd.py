"""
Port of the per-frame embedded-control-command dispatcher: DoCtrl (BackEnd.c).

DoCtrl is *not* the FrontEnd.c/EmbeddedCmd.c bracket-delimited text-escape
parser (that parser -- ProcessEmbeddedCommands and friends in
EmbeddedCmd.c -- lives one level up, turning `[[pbas200]]`-style text
escapes -- `[[`/`]]` are the real engine's default command delimiters,
`mt4.h`'s `defaultCmdBeginDelim`/`defaultCmdEndDelim`, changeable at
runtime via the `dlim` command itself -- into vv->PendingCommands bits;
none of FrontEnd.c is ported here). DoCtrl is the *consumer* at the
bottom of the pipeline: once a phoneme plan is built, some phonemes may carry
a count in `user_Cmd_Buf2[phonIndex]` of queued (type, data) control words
sitting in the `CMDQueue` ring buffer, and `say_frame` (BackEnd.c Talk())
calls DoCtrl once per frame to drain and apply that phoneme's share of them.

This is invoked from ``_backend.py``'s ``start_new_phon`` (the ported
Talk()/start-new-phon frame-boundary block) exactly where BackEnd.c calls
``DoCtrl (vv)``.

What's real here (faithfully ported, same shape as DoCtrl):
    C_absMod, C_absPitch, C_relPitch, C_absVol, C_relVol -- all pure
    arithmetic over already-ported state (VP_pitchRange, voiceNaturalPitch,
    VP_baselinePitch, user_Volume via _backend.set_volume/e_midi_to_pitch).

What's stubbed (raises NotImplementedError if actually hit), and why:
    * C_reset -- real DoCtrl calls e_ResetFE_FUNC (FrontEnd.c, not ported)
      then ResetVoice (fsynth.c, not ported in _backend.py under any name --
      see _engine.py's e_reinit_voice/e_reset_params for the same gap).
    * C_voice -- real DoCtrl's case is itself commented out in BackEnd.c
      (`//NewVoice (vv, &vv->zz->IntervalVoices[ctrlData-1]);`) and NewVoice
      is not ported either; this mirrors upstream's own no-op plus a marker
      so a caller that actually relies on voice-switching notices instead of
      silently doing nothing.

No currently-shipped voice/text data in this port emits queued embedded
commands (ctrlCount stays 0 for every test case in test/test_voices.py), so
do_ctrl's body never runs during the existing regression suite -- exercising
it requires hand-populating vv.CMDQueue/vv.user_Cmd_Buf2.
"""
from __future__ import annotations

from ._consts import *
from ._backend import VoiceVar, e_midi_to_pitch, set_volume

__all__ = ["do_ctrl", "scan_bracket_commands"]

# Divisors[] (Data.c:3844), used by Get32BitFixedValue's fractional-digit
# scaling (EmbeddedCmd.c:203-251).
_FIXED_DIVISORS = [10, 100, 1000, 10000, 50000]


def _parse_fixed_value(text: str, i: int):
    """Port of `Get32BitFixedValue` (`EmbeddedCmd.c:203-251`): parses an
    unsigned unsigned-Fixed-point value (`digits[.digits]`) starting at
    `text[i]`. Returns `(value, next_i)`, `value` being `(msb << 16) |
    lsb` exactly as the C source constructs it."""
    n = len(text)
    msb = 0
    while i < n and text[i].isdigit():
        msb = msb * 10 + int(text[i])
        i += 1
    lsb = 0
    if i < n and text[i] == '.':
        i += 1
        k = 0
        while i < n and text[i].isdigit() and k < 5:
            d = int(text[i])
            amt = ((d << 16) + _FIXED_DIVISORS[k] // 2) // _FIXED_DIVISORS[k]
            if k == 4:
                amt >>= 1
            lsb += amt
            i += 1
            k += 1
        while i < n and text[i].isdigit():  # skip insignificant remaining digits
            i += 1
    return (msb << 16) | lsb, i


def _parse_signed_command_value(text: str, i: int):
    """Port of the common preamble shared by `Parse_pbas_Command`/
    `Parse_pmod_Command`/`Parse_volm_Command` (`EmbeddedCmd.c:625-716`,
    `806-813`): an optional leading `+`/`-` (marking a RELATIVE change),
    then a Fixed value, clamped to `0x3FFFFFFF` if too large, with the
    relative direction tagged into bits 30-31 (`0x40000000` for `+`,
    `0xC0000000` for `-`) exactly as `ChangePitchBase`/`ChangePitchModula
    tion`/`ChangeVolume`'s callers do before storing it. Returns
    `(tagged_value, next_i)`."""
    n = len(text)
    relative = None
    if i < n and text[i] in '+-':
        relative = text[i]
        i += 1
        while i < n and text[i] in ' \t':
            i += 1
    value, i = _parse_fixed_value(text, i)
    if value & (0xC000 << 16):          # value is greater than our allowed max
        value = 0x3FFFFFFF               # limit to our max
    if relative == '+':
        value |= 0x40000000              # means relative addition
    elif relative == '-':
        value |= 0xC0000000              # means relative subtraction
    return value, i


def _resolve_tagged_value(tagged: int):
    """Port of `ProcessPendingCommands`'s per-command relative/absolute
    resolution (`FrontEnd.c:735-805`, identical shape for pitch-base/
    pitch-mod/volume): checks the `0xC000<<16` tag bits set by
    `_parse_signed_command_value`, and if set, sign-extends the tagged
    32-bit value and recovers the signed magnitude (`-(tagged &
    0x3FFFFFFF)` if the sign bit was set, else `tagged & 0x3FFFFFFF`).
    Returns `(is_relative, resolved_value)` -- `resolved_value` is
    exactly the `embedData` `Parse_Embedded_Command` (`BackEnd.c:3600
    -3660`) would see."""
    if tagged & (0xC000 << 16):
        signed = tagged - (1 << 32) if tagged & 0x80000000 else tagged
        magnitude = -(tagged & 0x3FFFFFFF) if signed < 0 else (tagged & 0x3FFFFFFF)
        return True, magnitude
    return False, tagged


# Commands ported here (scoped subset -- see module docstring's "What's
# NOT ported" note below): the four-letter keyword recognized inside
# `[[...]]`, mapped to (absolute ctrl_type, relative ctrl_type). `pmod`'s
# relative form (`C_relMod`) has no case in the real `DoCtrl` switch
# (`BackEnd.c:272-322` falls through to `default: break;` for it) -- a
# genuine no-op in the upstream engine, not a gap in this port -- so
# it's included here for completeness but never actually changes state.
_BRACKET_COMMANDS = {
    'PBAS': (C_absPitch, C_relPitch),
    'PMOD': (C_absMod, C_relMod),
    'VOLM': (C_absVol, C_relVol),
}


def scan_bracket_commands(text: str):
    """Port of `EmbeddedCmd.c`'s bracket-delimited text-command scanner
    (`ProcessEmbeddedCommands` and the `pbas`/`pmod`/`volm`/`emph`
    members of its command dispatch, `EmbeddedCmd.c:990-1010`), scoped
    to the three commands that resolve to a `CMDQueue` entry `do_ctrl`
    can actually apply (`C_absPitch`/`C_relPitch`, `C_absMod`/
    `C_relMod`, `C_absVol`/`C_relVol`) plus `emph` (a plain per-token
    field override, no `CMDQueue` involved) -- see below for what's NOT
    covered.

    Default delimiters are `[[`/`]]` (`mt4.h`'s `defaultCmdBeginDelim`/
    `defaultCmdEndDelim`; the `dlim` command that changes them at
    runtime is not ported). CAUTION for whoever next touches this:
    an earlier pass of this same investigation tried `` `pbas60`hello ``
    (single backtick) against the compiled `lintalker-c` `test_harness`
    and initially misread a genuine `f0` shift as confirmation that
    backtick was the real delimiter -- direct phoneme decoding proved
    otherwise: "PBAS" isn't a dictionary word, so the text between the
    backticks was being SPOKEN LITERALLY (spelled letter-by-letter, then
    "60" read as separate digits "SIX"/"ZERO"), not silently consumed as
    a command. `[[pbas60]]hello`/`[pbas60]hello` produced no such
    literal-reading artifact but ALSO no detectable pitch change on
    "hello" itself -- the compiled `test_harness` binary shows no
    evidence of recognizing EITHER delimiter as a real embedded command,
    for either given only a `-v <voice> <text>` CLI text argument. This
    is the same class of blocker as the `Symbols` dictionary
    investigation: this port cannot verify a bracket-command
    implementation frame-exact against THIS specific compiled reference
    (see docs/architecture.md), so `[[`/`]]` is used here because it's
    what the C SOURCE documents as the default, not because it was
    empirically confirmed to work. Returns `(clean_text, commands)`:
    `clean_text` is `text` with every recognized bracketed command
    span removed, and `commands` is a list of `(word_index, ctrl_type,
    ctrl_data)` -- `word_index` is how many words (per
    `_frontend.tokenize`) of `clean_text` PRECEDE that command, i.e. the
    command should be applied before that word's own phonemes are
    spoken, matching where `ProcessPendingCommands` embeds its `BE_ECmd`
    opcode in the real token stream (right before the next real word
    token). An unrecognized keyword, or a span with no `]]` before the
    end of `text`, is left in `clean_text` untouched (matches
    `LogParseError`'s effect of leaving `PendingCommands` unset for
    that command -- this port simply doesn't strip what it can't
    parse, rather than raising).

    Also recognizes `emph+`/`emph-` (`Parse_emph_Command`,
    `EmbeddedCmd.c:558-580`): overrides the word-prominence of the very
    NEXT token (`vv->NewEmphasis` copied straight into `tok->tokEmphasis`
    when that token is created, `FrontEnd.c:343-344`/`369-370`/`460-461`
    -- a plain field copy, not a `CMDQueue`/`phon_Buf_1`-opcode
    mechanism at all, unlike `pbas`/`pmod`/`volm` above). Returned
    separately from `commands` (see below) since it isn't a `CMDQueue`
    entry.

    NOT ported: `rate` (routes through `vv->lastRate`/
    `user_Rate_Buf1`, not `CMDQueue`, and `e_set_speech_rate`'s
    non-singing branch already isn't ported -- see `_engine.py`),
    `rset`/`vers`/`xtnd`/`char`/`cmnt`/`dlim`/`mode`/`nmbr`/`slnc`/
    `sync` (each its own separate parser/side-effect, not reachable via
    `CMDQueue` or a plain token field the way `emph` is), and
    mid-clause phoneme-accurate positioning (a command found after the
    Nth word of ONE clause is applied before that clause's Nth word,
    but this port has no opcode-in-phon_str pipeline the way the real
    engine's `StuffBECommand`/`Parse_Embedded_Command` do -- see module
    docstring).

    Returns `(clean_text, commands, emphasis)`: `clean_text` is `text`
    with every recognized bracketed command span removed; `commands` is
    a list of `(word_index, ctrl_type, ctrl_data)` for `pbas`/`pmod`/
    `volm`; `emphasis` is a `{word_index: "emphasize"|"deemphasize"}`
    dict for `emph`. `word_index` is how many words (per
    `_frontend.tokenize`) of `clean_text` PRECEDE that command, i.e. the
    command/override applies to (or right before) that word. An
    unrecognized keyword, or a span with no `]]` before the end of
    `text`, is left in `clean_text` untouched (matches
    `LogParseError`'s effect of leaving `PendingCommands` unset for
    that command -- this port simply doesn't strip what it can't
    parse, rather than raising).
    """
    from ._frontend import tokenize

    commands = []
    emphasis = {}
    out_parts = []
    word_count = 0
    i = 0
    n = len(text)
    BEGIN, END = '[[', ']]'
    while i < n:
        start = text.find(BEGIN, i)
        if start == -1:
            segment = text[i:]
            out_parts.append(segment)
            word_count += len(list(tokenize(segment)))
            break
        segment = text[i:start]
        out_parts.append(segment)
        word_count += len(list(tokenize(segment)))

        end = text.find(END, start + len(BEGIN))
        if end == -1:
            # Unterminated command -- leave the rest of the text as-is
            # (matches DoneWithCommand/GetNextCh hitting EOF; no clean
            # way to recover the intended command).
            out_parts.append(text[start:])
            i = n
            break

        inner = text[start + len(BEGIN):end]
        keyword = inner[:4].upper()

        if keyword == 'EMPH' and len(inner) > 4 and inner[4] in '+-':
            emphasis[word_count] = 'emphasize' if inner[4] == '+' else 'deemphasize'
            i = end + len(END)
            continue

        entry = _BRACKET_COMMANDS.get(keyword)
        if entry is None:
            # Unrecognized keyword -- leave this span untouched (not
            # stripped), matching LogParseError's effect of not
            # applying any state change for it.
            out_parts.append(text[start:end + len(END)])
            i = end + len(END)
            continue

        tagged, _ = _parse_signed_command_value(inner, 4)
        is_relative, resolved = _resolve_tagged_value(tagged)
        abs_type, rel_type = entry
        ctrl_type = rel_type if is_relative else abs_type
        ctrl_data = resolved
        if keyword == 'PMOD' and is_relative:
            # EC_pmor's embedData is >>16 relative to EC_pbar/EC_volr
            # (BackEnd.c:3628 vs 3620/3652) -- ported for completeness
            # even though C_relMod is a no-op in do_ctrl (see above).
            ctrl_data = resolved >> 16
        commands.append((word_count, ctrl_type, ctrl_data))

        i = end + len(END)

    return ''.join(out_parts), commands, emphasis


def do_ctrl(vv: VoiceVar) -> None:
    """DoCtrl (BackEnd.c). Drains vv.ctrlCount queued commands from
    vv.CMDQueue starting at vv.cmdBufCount, applying each to vv."""
    while vv.ctrlCount:
        ctrlType, ctrlData = vv.CMDQueue[vv.cmdBufCount]
        vv.cmdBufCount += 1
        vv.ctrlCount -= 1

        if ctrlType == C_absMod:
            if ctrlData < 0:
                ctrlData = 0
            elif ctrlData > (200 << 16):
                ctrlData = 200 << 16
            vv.VP_pitchRange = ctrlData // 100

        elif ctrlType == C_absPitch:
            ctrlData >>= 8
            vv.voiceNaturalPitch = e_midi_to_pitch(ctrlData)
            vv.VP_baselinePitch = vv.voiceNaturalPitch

        elif ctrlType == C_relPitch:
            vv.voiceNaturalPitch = e_midi_to_pitch(
                ((vv.VP_baselinePitch * 12) + kMIDI_50HZ) + (ctrlData >> 8)
            )
            vv.VP_baselinePitch = vv.voiceNaturalPitch

        elif ctrlType == C_absVol:
            set_volume(vv, ctrlData)

        elif ctrlType == C_relVol:
            set_volume(vv, (vv.user_Volume << 8) + ctrlData)

        elif ctrlType == C_reset:
            raise NotImplementedError(
                "do_ctrl: C_reset requires e_ResetFE (FrontEnd.c) and "
                "ResetVoice (fsynth.c), neither of which is ported."
            )

        elif ctrlType == C_voice:
            pass  # upstream DoCtrl's C_voice case body is itself commented out

        # else: unknown/unhandled type -- upstream falls through to `default: break;`
