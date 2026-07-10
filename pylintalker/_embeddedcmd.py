"""DECtalk's inline `[[...]]` commands: the scanner and the dispatcher.

`scan_bracket_commands` is the text-level scanner (EmbeddedCmd.c's
ProcessEmbeddedCommands): it strips the bracketed commands out of a clause and
records what each one asks for.

`do_ctrl` is the frame-level dispatcher (BackEnd.c's DoCtrl) at the other end
of the pipeline: once a phoneme plan is built, some phonemes carry a count of
queued control words in `user_Cmd_Buf2`, and `say_frame` calls `do_ctrl` once
per frame to apply that phoneme's share of them.

`C_voice` is a no-op, as in the C source, whose case body is commented out.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ._backend import VoiceVar, e_midi_to_pitch, reset_voice, set_volume
from ._consts import (
    C_absMod,
    C_absPitch,
    C_absVol,
    C_relMod,
    C_relPitch,
    C_relVol,
    C_reset,
    C_sync,
    C_voice,
    kLastPOS,
    kMaxVoice,
    kMIDI_50HZ,
    kMinRate,
    kNormal_Speech_Rate,
    kNoteDur,
    kNotePitch,
)
from ._frontend import (
    tokenize,
)
from ._rawphon import (
    parse_raw_phonemes,
    split_into_word_groups,
)

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


def _parse_long_value(text: str, i: int):
    """Port of `Get32BitLongValue` (`EmbeddedCmd.c:259-284`): a plain
    unsigned decimal integer, no Fixed-point scaling (used by `sync`,
    unlike `pbas`/`pmod`/`volm`/`rset`/`dlim`/`slnc` which all use the
    Fixed-point grammar above). Returns `(value, next_i)`."""
    n = len(text)
    val = 0
    while i < n and text[i].isdigit():
        val = val * 10 + int(text[i])
        i += 1
    return val, i


def _skip_spaces(text: str, i: int):
    n = len(text)
    while i < n and text[i] in ' \t':
        i += 1
    return i


def _parse_selector_value(text: str, i: int):
    """Port of `GetSelectorValue`'s bare (unquoted) form
    (`EmbeddedCmd.c:292-332`): packs each ASCII character up to the next
    whitespace into a 32-bit value (`selector = (selector << 8) | ch`),
    the classic Mac OS four-character-code convention (e.g. `mtk3` ->
    `kMacInTalkCreator`). Quoted selectors (`'XXXX'`/`"XXXX"`) aren't
    supported -- not needed for `xtnd`'s two arguments in practice.
    Returns `(value, next_i)`."""
    n = len(text)
    val = 0
    while i < n and text[i] > ' ':
        val = (val << 8) | ord(text[i])
        i += 1
    return val, i


def _fourcc(code: str) -> int:
    """Pack a four-character code the way `_parse_selector_value` reads one."""
    value = 0
    for ch in code:
        value = (value << 8) | ord(ch)
    return value


# Versions.h's kMacInTalkCreator ('mtk3') and EmbeddedCmd.c's 'wpos'
# selector, both four-character codes packed the same way
# _parse_selector_value builds them.
_MACINTALK_CREATOR = _fourcc('mtk3')
_WPOS_SELECTOR = _fourcc('wpos')

# SpeechEqu.h's modeNormal ('NORM')/modeLiteral ('LTRL') mode-argument
# constants, shared by `char`/`nmbr` (Parse_char_Command/
# Parse_nmbr_Command mask their argument with 0xDFDFDFDF to uppercase it
# before comparing against these -- _parse_selector_value already reads
# raw ASCII, so the uppercasing happens by using upper() on the parsed
# text below instead of replicating the bitmask).
_MODE_NORMAL = _fourcc('NORM')
_MODE_LITERAL = _fourcc('LTRL')

# SpeechEqu.h's modeText ('TEXT')/modePhonemes ('PHON') constants, used
# by `mode` (`Parse_mode_Command`/`ChangeInputMode`).
_MODE_TEXT = _fourcc('TEXT')
_MODE_PHON = _fourcc('PHON')


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


@dataclass(frozen=True)
class BracketCommands:
    """What a clause's `[[...]]` commands ask for, stripped out of the text.

    Every mapping is keyed by word index: how many words of `text` precede
    the command, so it applies to (or immediately before) that word.
    """

    #: the input with every recognized bracket command removed
    text: str = ""
    #: (word_index, ctrl_type, ctrl_data) triples destined for the CMDQueue
    queued: tuple[tuple[int, int, int], ...] = ()
    #: word_index -> "emphasize" | "deemphasize"
    emphasis: dict[int, str] = field(default_factory=dict)
    #: word_index -> milliseconds of silence to insert before the word
    silences: dict[int, int] = field(default_factory=dict)
    #: word_index -> part-of-speech code, overriding the tagger
    pos: dict[int, int] = field(default_factory=dict)
    #: word_index -> speaking rate in words per minute
    rates: dict[int, int] = field(default_factory=dict)
    #: word_index -> read digits one at a time (latched, not one-shot)
    digit_by_digit: dict[int, bool] = field(default_factory=dict)
    #: word_index -> literal phoneme string, from `mode PHON`
    raw_phonemes: dict[int, list] = field(default_factory=dict)
    #: word_index -> spell the word out letter by letter, from `char LTRL`
    spelled: dict[int, bool] = field(default_factory=dict)
    #: word_index -> a packed note word: MIDI pitch in kNotePitch, length code
    #: in kNoteDur. Any note switches the voice into singing mode.
    notes: dict[int, int] = field(default_factory=dict)
    #: word_index -> a marker time, in queue order. Markers switch the voice
    #: into marker-synced singing.
    markers: dict[int, int] = field(default_factory=dict)
    #: beats per minute, from the last `tempo` command, or None
    tempo: int | None = None
    #: rate in force at the end of the clause, or None if no rate command ran
    final_rate: int | None = None


def scan_bracket_commands(text: str, initial_rate: int = kNormal_Speech_Rate) -> BracketCommands:
    """Strip DECtalk's `[[...]]` commands out of `text` and record what they ask for.

    Delimiters default to `[[` and `]]` (`mt4.h`'s defaultCmdBeginDelim /
    defaultCmdEndDelim). Commands recognized, and where each one lands in the
    returned `BracketCommands`:

        pbas, pmod, volm   pitch base, pitch modulation, volume  -> queued
        rset, sync         reset, sync marker                    -> queued
        emph               emphasize / deemphasize a word        -> emphasis
        slnc               insert a silence                      -> silences
        xtnd wpos          override a word's part of speech      -> pos
        rate, ratr         speaking rate, absolute or relative   -> rates
        nmbr               read digits one at a time             -> digit_by_digit
        mode PHON / TEXT   literal phoneme input                 -> raw_phonemes
        char LTRL / NORM   spell words out letter by letter      -> spelled
        dlim               change the delimiters from here on
        cmnt, vers         no-ops, stripped

    `nmbr`, `mode` and `char` latch: they stay in force until switched back.
    The others apply once, at the word they precede.

    `pbas`, `pmod` and `volm` take a Fixed-point value that may be relative
    (`+50`, `-50`); `sync` takes a plain integer; `slnc` takes milliseconds;
    `dlim` takes two decimal character codes (e.g. `91 93` for `[` and `]`).

    An unrecognized keyword, or a span with no closing delimiter, is left in
    the text as written rather than raising -- matching `LogParseError`, which
    simply leaves that command's PendingCommands bit unset.

    Only `pbas`/`pmod`/`volm`/`rset`/`sync` become CMDQueue entries that
    `do_ctrl` applies. The rest are per-word overrides that
    `_assembly.collect_fe_tokens` consumes directly.
    """

    commands = []
    emphasis = {}
    silences = {}
    pos_overrides = {}
    rates = {}
    nmbr_overrides = {}
    raw_phon_overrides = {}
    char_overrides = {}
    notes = {}
    markers = {}
    tempo = None
    last_rate = initial_rate
    out_parts = []
    word_count = 0
    phon_mode = False
    i = 0
    n = len(text)
    BEGIN, END = '[[', ']]'

    def _emit_segment(segment: str) -> None:
        """Appends `segment` to `clean_text`/advances `word_count`,
        routing through raw-phoneme parsing instead of plain text when
        `mode PHON` is active (`ChangeInputMode`'s `kRawPhonemes`,
        `FrontEnd.c:667-675`) -- see `raw_phon_overrides` in this
        function's docstring."""
        nonlocal word_count
        if not phon_mode:
            out_parts.append(segment)
            word_count += len(list(tokenize(segment)))
            return
        groups = split_into_word_groups(parse_raw_phonemes(segment))
        placeholders = []
        for group in groups:
            placeholders.append(f"RAWPHON{word_count}")
            raw_phon_overrides[word_count] = group
            word_count += 1
        out_parts.append(' '.join(placeholders))

    while i < n:
        start = text.find(BEGIN, i)
        if start == -1:
            _emit_segment(text[i:])
            break
        _emit_segment(text[i:start])

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

        if keyword in ('CMNT', 'VERS'):
            # No state-changing effect either way (Parse_cmnt_Command is
            # a genuine no-op; Parse_vers_Command only ever validates
            # its argument and logs a parse error on mismatch) -- just
            # strip the span.
            i = end + len(END)
            continue

        if keyword == 'DLIM':
            old_end_len = len(END)
            begin_val, j = _parse_fixed_value(inner, 4)
            while j < len(inner) and inner[j] in ' \t':
                j += 1
            end_val, j = _parse_fixed_value(inner, j)
            begin_code = begin_val >> 16
            end_code = end_val >> 16
            if 0 <= begin_code <= 0xFF and 0 <= end_code <= 0xFF:
                BEGIN = chr(begin_code)
                END = chr(end_code)
            i = end + old_end_len
            continue

        if keyword == 'NOTE':
            # Parse_Embedded_Command's EC_note (BackEnd.c:3679-3683): the Fixed
            # value's integer part is a MIDI note, its fraction a length code.
            value, _ = _parse_fixed_value(inner, _skip_spaces(inner, 4))
            notes[word_count] = ((value >> 16) & kNotePitch) | (value & kNoteDur)
            i = end + len(END)
            continue

        if keyword == 'TMPO':
            # Parse_tempo_Command. EC_tempo's body is commented out in the C
            # source, so this changes nothing there; recorded here because
            # e_set_tempo, which it would drive, is ported.
            value, _ = _parse_fixed_value(inner, _skip_spaces(inner, 4))
            tempo = value >> 16
            i = end + len(END)
            continue

        if keyword == 'MARK':
            # Parse_marker_Command; applied by EC_marker (BackEnd.c), which
            # records the marker time and flags the phoneme it precedes.
            value, _ = _parse_fixed_value(inner, _skip_spaces(inner, 4))
            markers[word_count] = value
            i = end + len(END)
            continue

        if keyword == 'SVOX':
            # Parse_svox_Command: an internal voice number, 1..kMaxVoice, no
            # fractional part. EC_svox queues it as C_voice, which DoCtrl
            # leaves as a no-op -- the C source's own case body is commented out.
            value, _ = _parse_fixed_value(inner, _skip_spaces(inner, 4))
            voice_num = value >> 16
            if not 1 <= voice_num <= kMaxVoice:
                voice_num = 1
            commands.append((word_count, C_voice, voice_num))
            i = end + len(END)
            continue

        if keyword == 'SLNC':
            value, _ = _parse_fixed_value(inner, 4)
            duration = value >> 16
            if duration > 0:
                silences[word_count] = silences.get(word_count, 0) + duration
            i = end + len(END)
            continue

        if keyword == 'RSET':
            # Parse_rset_Command (EmbeddedCmd.c:724-739): the ONLY valid
            # argument is 0 -- HandleReset is called only in that case,
            # else LogParseError fires and no reset happens (matched
            # here by simply not queuing a command for a nonzero value).
            value, _ = _parse_fixed_value(inner, 4)
            if value == 0:
                commands.append((word_count, C_reset, 0))
            i = end + len(END)
            continue

        if keyword == 'RATE':
            # Parse_rate_Command/ChangeRate (EmbeddedCmd.c:691-720):
            # same relative-sign/Fixed-value grammar as pbas/pmod/volm,
            # but EC_rate/EC_ratr (BackEnd.c:1900-1915) write directly
            # to vv->lastRate/user_Rate_Buf1, not CMDQueue. Absolute:
            # lastRate = integer part of the Fixed value, clamped to
            # kMinRate. Relative: lastRate += the signed integer delta,
            # same clamp.
            tagged, _ = _parse_signed_command_value(inner, 4)
            is_relative, resolved = _resolve_tagged_value(tagged)
            delta_or_abs = resolved >> 16
            if is_relative:
                last_rate = last_rate + delta_or_abs
            else:
                last_rate = delta_or_abs
            if last_rate < kMinRate:
                last_rate = kMinRate
            rates[word_count] = last_rate
            i = end + len(END)
            continue

        if keyword == 'NMBR':
            # Parse_nmbr_Command/ChangeNumberMode (EmbeddedCmd.c:604-620):
            # argument is a bare NORM/LTRL selector (case-insensitive --
            # the real code masks with 0xDFDFDFDF to uppercase first,
            # matched here by upper()-ing the parsed selector text).
            j = _skip_spaces(inner, 4)
            mode_val, _ = _parse_selector_value(inner.upper(), j)
            if mode_val == _MODE_NORMAL:
                nmbr_overrides[word_count] = False
            elif mode_val == _MODE_LITERAL:
                nmbr_overrides[word_count] = True
            i = end + len(END)
            continue

        if keyword == 'CHAR':
            # Parse_char_Command/ChangeCharMode (EmbeddedCmd.c: search
            # for "Parse_char_Command"): same NORM/LTRL selector shape
            # as `nmbr`, toggling `kCharByChar` letter-by-letter
            # spelling (`_letters.spell_word`) for every following
            # alphabetic word until changed again.
            j = _skip_spaces(inner, 4)
            mode_val, _ = _parse_selector_value(inner.upper(), j)
            if mode_val == _MODE_NORMAL:
                char_overrides[word_count] = False
            elif mode_val == _MODE_LITERAL:
                char_overrides[word_count] = True
            i = end + len(END)
            continue

        if keyword == 'MODE':
            # Parse_mode_Command/ChangeInputMode (EmbeddedCmd.c: search
            # for "Parse_mode_Command"): argument is a bare TEXT/PHON
            # selector (case-insensitive, same as `nmbr`'s NORM/LTRL).
            # Toggles whether SUBSEQUENT text (up to the next `mode`
            # command or end of input) is parsed as raw phoneme
            # mnemonics (`_rawphon.parse_raw_phonemes`) instead of
            # English words -- see `_emit_segment` above.
            j = _skip_spaces(inner, 4)
            mode_val, _ = _parse_selector_value(inner.upper(), j)
            if mode_val == _MODE_TEXT:
                phon_mode = False
            elif mode_val == _MODE_PHON:
                phon_mode = True
            i = end + len(END)
            continue

        if keyword == 'SYNC':
            # Parse_sync_Command (EmbeddedCmd.c:753-765): a plain LONG
            # value (not Fixed-point), queued as C_sync -- do_ctrl has
            # no case for C_sync (matching the real DoCtrl switch, which
            # doesn't either, BackEnd.c:272-322's `default: break;`), so
            # this is a genuine no-op in the real engine too, not a gap
            # in this port.
            value, _ = _parse_long_value(inner, 4)
            commands.append((word_count, C_sync, value))
            i = end + len(END)
            continue

        if keyword == 'XTND':
            # Parse_xtnd_Command (EmbeddedCmd.c:895-921): a vendor
            # extension mechanism -- the first argument is a
            # four-character creator code, checked against
            # kMacInTalkCreator ('mtk3') and silently ignored if it
            # doesn't match (some OTHER application's extension, not
            # ours); the second is a command selector, of which only
            # 'wpos' (word part-of-speech) is implemented in the real
            # dispatch (anything else logs kUnknownEmbeddedCmd and does
            # nothing) -- ported here as `pos_overrides`, matching
            # `SetPOStoVal`'s effect (`FrontEnd.c:138-145`: sets
            # `POScode1[0]`/`compPOS1`/`hiRank`/`POScount1` directly on
            # the token, applied by `_assembly.collect_fe_tokens` before
            # `resolve_pos` runs, same insertion point as
            # `emphasis_overrides`).
            j = _skip_spaces(inner, 4)
            creator, j = _parse_selector_value(inner, j)
            if creator == _MACINTALK_CREATOR:
                j = _skip_spaces(inner, j)
                selector, j = _parse_selector_value(inner, j)
                if selector == _WPOS_SELECTOR:
                    j = _skip_spaces(inner, j)
                    value, j = _parse_fixed_value(inner, j)
                    pos_val = value >> 16
                    if 0 <= pos_val <= kLastPOS:
                        pos_overrides[word_count] = pos_val
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

    return BracketCommands(
        text=''.join(out_parts),
        queued=tuple(commands),
        emphasis=emphasis,
        silences=silences,
        pos=pos_overrides,
        rates=rates,
        digit_by_digit=nmbr_overrides,
        raw_phonemes=raw_phon_overrides,
        spelled=char_overrides,
        notes=notes,
        markers=markers,
        tempo=tempo,
        final_rate=last_rate if rates else None,
    )


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
            # DoCtrl also calls e_ResetFE, which resets FrontEnd.c's streaming
            # parser. This port has no such parser -- text is parsed per clause
            # -- so there is nothing to reset there.
            reset_voice(vv)

        elif ctrlType == C_voice:
            pass  # upstream DoCtrl's C_voice case body is itself commented out

        # else: unknown/unhandled type -- upstream falls through to `default: break;`
