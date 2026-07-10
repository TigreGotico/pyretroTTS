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

from ._backend import VoiceVar, e_midi_to_pitch, set_volume
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
    kMIDI_50HZ,
    kMinRate,
    kNormal_Speech_Rate,
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


# Versions.h's kMacInTalkCreator ('mtk3') and EmbeddedCmd.c's 'wpos'
# selector, both four-character codes packed the same way
# _parse_selector_value builds them.
_MACINTALK_CREATOR = (ord('m') << 24) | (ord('t') << 16) | (ord('k') << 8) | ord('3')
_WPOS_SELECTOR = (ord('w') << 24) | (ord('p') << 16) | (ord('o') << 8) | ord('s')

# SpeechEqu.h's modeNormal ('NORM')/modeLiteral ('LTRL') mode-argument
# constants, shared by `char`/`nmbr` (Parse_char_Command/
# Parse_nmbr_Command mask their argument with 0xDFDFDFDF to uppercase it
# before comparing against these -- _parse_selector_value already reads
# raw ASCII, so the uppercasing happens by using upper() on the parsed
# text below instead of replicating the bitmask).
_MODE_NORMAL = (ord('N') << 24) | (ord('O') << 16) | (ord('R') << 8) | ord('M')
_MODE_LITERAL = (ord('L') << 24) | (ord('T') << 16) | (ord('R') << 8) | ord('L')

# SpeechEqu.h's modeText ('TEXT')/modePhonemes ('PHON') constants, used
# by `mode` (`Parse_mode_Command`/`ChangeInputMode`).
_MODE_TEXT = (ord('T') << 24) | (ord('E') << 16) | (ord('X') << 8) | ord('T')
_MODE_PHON = (ord('P') << 24) | (ord('H') << 16) | (ord('O') << 8) | ord('N')


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


def scan_bracket_commands(text: str, initial_rate: int = kNormal_Speech_Rate):
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

    Also recognizes `cmnt` (`Parse_cmnt_Command`, `EmbeddedCmd.c:521-525`
    -- a genuine no-op even in the real engine, it just skips the rest
    of the command) and `vers` (`Parse_vers_Command`, `EmbeddedCmd.c:768
    -778` -- validates the version argument is `1.0`/`0.0` and otherwise
    logs a parse error; has no state-changing effect either way) as
    silently-stripped no-ops, and `dlim` (`Parse_dlim_Command`,
    `EmbeddedCmd.c:527-556`): changes the begin/end delimiters used for
    subsequent commands later in the SAME `text` (matches
    `ChangeDelimiters`'s real scope -- it only affects commands parsed
    afterward, mid-utterance). Its two arguments are each a decimal
    character CODE (e.g. `91` for `[`), matching `Get32BitValue`'s
    `newBegin >> 16`/`newEnd >> 16` extraction (a plain integer part,
    no fractional digits expected in practice).

    Also recognizes `slnc` (`Parse_slnc_Command`, `EmbeddedCmd.c:741-751`):
    inserts a real `_SIL_` phoneme at the given position (the ONE command
    ported here that DOES have a per-phoneme pipeline equivalent -- see
    `_assembly.collect_fe_tokens`'s `silence_overrides` parameter and
    `sa.note_buf`, consumed by `_moduration.mod_duration`'s existing
    `kSilenceDuration` branch). Its argument is a plain Fixed value;
    `embedData >> 16` (`BackEnd.c`'s `Parse_Embedded_Command` `EC_slnc`
    case) recovers the millisecond count the user typed.

    Also recognizes `rset` (`Parse_rset_Command`, `EmbeddedCmd.c:724
    -739` -- only argument `0` is valid, resolving to `C_reset`; `do_ctrl`
    already stubs that with `NotImplementedError`) and `sync`
    (`Parse_sync_Command`, `EmbeddedCmd.c:753-765` -- a plain LONG
    argument, not Fixed-point, resolving to `C_sync`; `do_ctrl` has no
    case for `C_sync` at all, matching the real `DoCtrl` switch's own
    `default: break;` for it -- a genuine no-op in the reference too).

    Also recognizes `xtnd`'s `wpos` (word part-of-speech) selector
    (`Parse_xtnd_Command`, `EmbeddedCmd.c:895-921` -- the only selector
    the real dispatch implements; any other selector, or a creator code
    other than `kMacInTalkCreator`/`mtk3`, is silently ignored): sets the
    next word's part-of-speech directly, matching `SetPOStoVal`
    (`FrontEnd.c:138-145`) -- returned separately as `pos_overrides`,
    applied by `_assembly.collect_fe_tokens` to the token's
    `pos_code1`/`comp_pos1` fields right before `resolve_pos` runs, the
    same insertion point as `emphasis_overrides`.

    Also recognizes `rate`/`ratr` (`Parse_rate_Command`/`ChangeRate`,
    `EmbeddedCmd.c:691-720`): sets the speaking rate at an exact word
    position, matching `Parse_Embedded_Command`'s `EC_rate`/`EC_ratr`
    cases (`BackEnd.c:1900-1915`) -- unlike `pbas`/`pmod`/`volm`, these
    write DIRECTLY to `user_Rate_Buf1`/`vv->lastRate`, not `CMDQueue`, so
    this is returned separately as `rates`, and (like `emph`/`xtnd wpos`)
    positioned at the real word index rather than applied at clause
    start. `initial_rate` seeds the relative-change accumulator
    (`vv->lastRate`'s value before any `rate`/`ratr` command in `text` --
    pass the voice's current `vv.speech_Rate` for correct behavior
    across a multi-clause utterance where an earlier clause already
    changed the rate); the LAST resolved rate (or `None` if `text` has
    no `rate`/`ratr` command at all) is returned as `final_rate`, for the
    caller to persist onto `vv.speech_Rate` for subsequent clauses.

    Also recognizes `nmbr` (`Parse_nmbr_Command`/`ChangeNumberMode`,
    `EmbeddedCmd.c:604-620`): its argument is `NORM`/`LTRL` (matching
    `modeNormal`/`modeLiteral`, `SpeechEqu.h`), toggling `kDigitByDigit`
    mode (`FrontEnd.c:2057-2062`'s `SpeakTokenCharByChar` branch for
    numeric tokens -- each digit read on its own, e.g. "123" -> "one two
    three", instead of grouped into a cardinal number). Unlike `emph`/
    `xtnd wpos`/`rate` (single-word overrides) this is a LATCHED mode
    that stays in effect for every following numeric token until changed
    again, matching `vv->Mode`'s persistent bit -- so it's returned
    separately as `nmbr_overrides`, a `{word_index: is_digit_by_digit}`
    dict applied by `_assembly.collect_fe_tokens` as a running flag
    rather than a one-shot lookup.

    Also recognizes `mode` (`Parse_mode_Command`/`ChangeInputMode`,
    search `EmbeddedCmd.c` for `Parse_mode_Command`): its argument is a
    bare `TEXT`/`PHON` selector (same shape as `nmbr`'s `NORM`/`LTRL`),
    toggling whether SUBSEQUENT text is parsed as raw phoneme mnemonics
    (`kRawPhonemes`, `GetNextPhonemeOpcode`/`CollectPhonemeToken`,
    `FrontEnd.c:247-345`) instead of English words -- e.g. `[[mode
    PHON]]_1AAt[[mode TEXT]]` speaks the literal phonemes `_Word_
    _Stress1_ _AA_ _t_` instead of trying to read "_1AAt" as an English
    word. `_rawphon.MAGIC_MAP` (`Data.c:3307`'s `MAGIC_CHAR_MAP[]`/
    `Data.c:3394`'s `MAGIC_OPCODE_MAP[]`) is a direct, bit-exact
    transcription of a literal compile-time C source table, not a
    runtime dictionary lookup, so -- unlike `char`'s letter-name
    spelling below -- it carries no `Symbols`-dictionary corruption
    caveat. Like `nmbr`, this is a LATCHED mode (stays in effect until
    the next `mode` command or end of text), applied here in
    `scan_bracket_commands` itself (not deferred to `_assembly.
    collect_fe_tokens` the way `nmbr` is): while `PHON` mode is active,
    `_emit_segment` routes the text between commands through
    `_rawphon.parse_raw_phonemes`/`split_into_word_groups` instead of
    treating it as literal English text, synthesizing one placeholder
    word (`"RAWPHONn"`) per resulting opcode group and recording that
    group's raw phonemes in `raw_phon_overrides: {word_index:
    phon_str}` -- `_assembly.collect_fe_tokens` builds that word's
    `FEWordToken` directly from the recorded phonemes instead of
    running `make_fe_word_token`'s normal dictionary/`EngToP` lookup on
    the meaningless placeholder string.

    Also recognizes `char` (`Parse_char_Command`/`ChangeCharMode`,
    search `EmbeddedCmd.c` for `Parse_char_Command`): the same bare
    `NORM`/`LTRL` selector shape as `nmbr`, toggling `kCharByChar`
    letter-by-letter spelling (`_letters.spell_word`, e.g. "cab" ->
    "see ay bee") for every following alphabetic word until changed
    again -- also a LATCHED mode, returned as `char_overrides:
    {word_index: is_spelled}`, applied by `_assembly.collect_fe_tokens`
    as a running flag exactly like `nmbr_overrides`. `_letters.
    LETTER_PHONEMES` is extracted bit-exact from the compiled
    `lintalker-c` reference's real `Symbols`-dictionary letter lookup
    (a genuine RUNTIME lookup, unlike `mode`'s literal `MAGIC_MAP` --
    but confirmed NOT corrupted for plain single-character keys, unlike
    the `"100"`/`"1000"`-class SCALE-WORD numeric keys documented
    elsewhere); see that module's docstring for the extraction method
    and a documented multi-letter vowel-hiatus caveat.

    NOT ported: mid-clause
    phoneme-accurate positioning for `pbas`/`pmod`/`volm`
    (a command found after the Nth word of ONE clause is applied before
    that clause's Nth word for `emph`/`slnc`/`xtnd`/`rate`/`nmbr`/`mode`/
    `char`, but `pbas`/`pmod`/`volm` are applied as an immediate
    `do_ctrl` state change at the whole clause's start instead -- see
    `api.build_phoneme_plan`).

    Returns `(clean_text, commands, emphasis, silences, pos_overrides,
    rates, final_rate, nmbr_overrides, raw_phon_overrides,
    char_overrides)`: `clean_text`
    is `text` with every recognized bracketed command span removed
    (raw-phoneme spans replaced with `"RAWPHONn"` placeholder words, one
    per opcode group); `commands` is a
    list of `(word_index, ctrl_type, ctrl_data)` for `pbas`/`pmod`/
    `volm`/`rset`/`sync`; `emphasis` is a `{word_index: "emphasize"|
    "deemphasize"}` dict for `emph`; `silences` is a `{word_index:
    duration_ms}` dict for `slnc`; `pos_overrides` is a `{word_index:
    pos_value}` dict for `xtnd wpos`; `rates` is a `{word_index: wpm}`
    dict for `rate`/`ratr`; `final_rate` is described above;
    `nmbr_overrides` is a `{word_index: is_digit_by_digit}` dict for
    `nmbr`; `raw_phon_overrides` is a `{word_index: phon_str}` dict for
    `mode PHON`; `char_overrides` is a `{word_index: is_spelled}` dict
    for `char`. `word_index`
    is how many words (per
    `_frontend.tokenize`) of `clean_text` PRECEDE that command, i.e. the
    command/override applies to (or right before) that word. An
    unrecognized keyword, or a span with no closing delimiter before
    the end of `text`, is left in `clean_text` untouched (matches
    `LogParseError`'s effect of leaving `PendingCommands` unset for
    that command -- this port simply doesn't strip what it can't
    parse, rather than raising).
    """

    commands = []
    emphasis = {}
    silences = {}
    pos_overrides = {}
    rates = {}
    nmbr_overrides = {}
    raw_phon_overrides = {}
    char_overrides = {}
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

    final_rate = last_rate if rates else None
    return (
        ''.join(out_parts), commands, emphasis, silences, pos_overrides,
        rates, final_rate, nmbr_overrides, raw_phon_overrides, char_overrides,
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
            raise NotImplementedError(
                "do_ctrl: C_reset requires e_ResetFE (FrontEnd.c) and "
                "ResetVoice (fsynth.c), neither of which is ported."
            )

        elif ctrlType == C_voice:
            pass  # upstream DoCtrl's C_voice case body is itself commented out

        # else: unknown/unhandled type -- upstream falls through to `default: break;`
