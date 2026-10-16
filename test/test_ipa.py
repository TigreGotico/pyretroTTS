"""IPA as a universal input notation, across all three engines."""
import struct

import pytest

from pyretrotts import (
    DECtalkEngine,
    MacInTalkEngine,
    SAMEngine,
    ipa,
)
from pyretrotts._frontend import words_to_phonemes
from pyretrotts._phonemes import (
    PHONEME_NAMES,
    PHONEME_NAMES_BY_INDEX,
    kNumPhoneme,
)
from pyretrotts.dectalk.lts import US_PHONEME_CODES, US_PHONEME_NAMES
from pyretrotts.dectalk.sentence_us import sentence_to_clauses
from pyretrotts.g2p import _sam_indices
from pyretrotts.ipa import (
    IpaClause,
    IpaPhone,
    Stress,
    ipa_to_native,
    native_to_ipa,
    parse_ipa,
)
from pyretrotts.sam.phonemes import mnemonic

# A General American word set with its native front-end output, used for the
# round-trip fidelity measurements below.
_WORDS = (
    "the quick brown fox jumps over a lazy dog hello world photograph computer "
    "language synthesis america people because different water").split()


# --- parsing ---------------------------------------------------------------

def test_stress_marks_attach_to_the_following_vowel():
    (clause,) = parse_ipa("həˈloʊ")
    stressed = [p for p in clause.phones if p.stress is Stress.PRIMARY]
    assert stressed == [IpaPhone("oʊ", Stress.PRIMARY)]


def test_secondary_stress_is_kept_distinct():
    (clause,) = parse_ipa("ˌɛ")
    assert clause.phones[0].stress is Stress.SECONDARY


def test_diphthongs_tokenize_as_one_segment():
    (clause,) = parse_ipa("aɪ ɔɪ aʊ oʊ eɪ")
    assert [p.symbol for p in clause.phones] == ["aɪ", "ɔɪ", "aʊ", "oʊ", "eɪ"]


def test_affricates_and_r_coloured_vowels_are_single_segments():
    (clause,) = parse_ipa("tʃ dʒ ɪɚ")
    assert [p.symbol for p in clause.phones] == ["tʃ", "dʒ", "ɪɚ"]


def test_clauses_split_on_punctuation():
    clauses = parse_ipa("hi, ðɛr. baɪ?")
    assert [c.terminator for c in clauses] == [",", ".", "?"]
    assert len(clauses) == 3


def test_length_and_nasal_diacritics_are_absorbed():
    (clause,) = parse_ipa("iː ɑ̃")
    assert [p.symbol for p in clause.phones] == ["iː", "ɑ̃"]


# --- round-trip fidelity ----------------------------------------------------

def _macintalk_round_trip():
    total = faithful = 0
    for word in _WORDS:
        ids = [p for p in words_to_phonemes(word) if p < kNumPhoneme]
        for i in ids:
            symbol = ipa._MACINTALK_TO_IPA.get(PHONEME_NAMES_BY_INDEX.get(i))
            if symbol is None:
                continue
            total += 1
            (back,) = native_to_ipa_ids("macintalk", symbol)
            if back == i:
                faithful += 1
    return faithful, total


def native_to_ipa_ids(engine, symbol):
    """Round an IPA `symbol` forward to `engine`'s id(s) via the clause path."""
    payload, _ = ipa_to_native(engine, [IpaClause((IpaPhone(symbol),), "")])
    if engine == "macintalk":
        plan = payload[0]
        return [p for p in plan.phonemes[1:-1]]
    if engine == "dectalk":
        clause = payload[0]
        return [c & 0x00FF for c in clause.symbols
                if c >= ipa._DEC_FONT]
    raise AssertionError(engine)


def test_macintalk_round_trip_is_essentially_lossless():
    faithful, total = _macintalk_round_trip()
    assert total > 80
    assert faithful / total >= 0.99  # measured 100.0%


def test_dectalk_round_trip_stays_high():
    total = faithful = 0
    for word in _WORDS:
        codes = []
        for clause in sentence_to_clauses(word, None):
            codes.extend(clause.symbols)
        for code in codes:
            name = US_PHONEME_NAMES.get(code & 0x00FF)
            if name not in ipa._DECTALK_TO_IPA:
                continue
            total += 1
            symbol = ipa._DECTALK_TO_IPA[name]
            resolved, _ = ipa._lookup(ipa._IPA_TO_DECTALK_NAME, symbol)
            if US_PHONEME_CODES[resolved] == (code & 0x00FF):
                faithful += 1
    assert total > 80
    assert faithful / total >= 0.97  # measured 99.0%


def test_sam_round_trip_is_lower_than_the_klatt_engines():
    sam_index = ipa._sam_index()
    total = faithful = 0
    for word in _WORDS:
        for i in _sam_indices(word):
            name = mnemonic(i).strip()
            if name not in ipa._SAM_TO_IPA:
                continue
            total += 1
            symbol = ipa._SAM_TO_IPA[name]
            resolved, _ = ipa._lookup(ipa._IPA_TO_SAM_NAME, symbol)
            if sam_index.get(resolved) == i:
                faithful += 1
    assert total > 80
    assert faithful / total >= 0.95  # measured 98.9%


def _forward_preserved(engine, symbols):
    """How many IPA `symbols` survive IPA -> native -> IPA unchanged."""
    forward = {
        "macintalk": (ipa._IPA_TO_MACINTALK_NAME, ipa._MACINTALK_TO_IPA),
        "sam": (ipa._IPA_TO_SAM_NAME, ipa._SAM_TO_IPA),
    }[engine]
    to_native, to_ipa = forward
    kept = 0
    for symbol in symbols:
        name = to_native[symbol]
        if to_ipa.get(name) == symbol:
            kept += 1
    return kept


def test_sam_is_the_coarsest_inventory():
    """/ju/ and the r-coloured vowels survive IPA -> native -> IPA on the Klatt
    engines but collapse on SAM, so fewer segments come back unchanged."""
    symbols = ["ju", "ɪɚ", "ɑɚ", "ɔɚ", "ʊɚ"]
    mac = _forward_preserved("macintalk", symbols)
    sam = _forward_preserved("sam", symbols)
    assert mac == len(symbols)  # MacinTalk keeps every one
    assert sam < mac            # SAM collapses them


# --- rendering --------------------------------------------------------------

@pytest.mark.parametrize("engine", [MacInTalkEngine, DECtalkEngine, SAMEngine])
def test_say_ipa_returns_pcm(engine):
    pcm = engine().say_ipa("həˈloʊ wɝld")
    assert pcm
    assert len(pcm) % 2 == 0


def test_dectalk_say_ipa_is_22050_hz_from_the_upsampler():
    engine = DECtalkEngine()
    assert engine.sample_rate == 22050
    pcm = engine.say_ipa("həˈloʊ wɝld")
    # `_upsample_2x` doubles the 11025 Hz core, so the sample count is even.
    assert (len(pcm) // 2) % 2 == 0


def test_say_ipa_writes_a_wav(tmp_path):
    out = tmp_path / "ipa.wav"
    pcm = MacInTalkEngine().say_ipa("həˈloʊ", path=str(out))
    assert out.exists()
    assert out.read_bytes()[:4] == b"RIFF"
    assert pcm


# --- fallback reporting -----------------------------------------------------

def test_a_nasal_vowel_falls_back_to_its_base_and_is_reported():
    clauses = parse_ipa("ɑ̃")
    _, fallbacks = ipa_to_native("macintalk", clauses)
    assert len(fallbacks) == 1
    assert fallbacks[0].symbol == "ɑ̃"
    assert fallbacks[0].target == "AA"  # the base vowel


def test_an_unknown_symbol_falls_back_to_schwa():
    clauses = parse_ipa("ʁ")  # uvular r, no target
    _, fallbacks = ipa_to_native("macintalk", clauses)
    assert fallbacks
    assert fallbacks[0].target == "AX"


# --- mutation sanity --------------------------------------------------------

def test_the_mapping_pins_a_specific_ipa_to_id():
    """A concrete IPA-to-id fact; corrupting the table would break this."""
    assert ipa._IPA_TO_MACINTALK_NAME["æ"] == "AE"
    (front,) = native_to_ipa_ids("macintalk", "æ")
    assert front == PHONEME_NAMES["AE"]


def test_a_corrupted_table_would_change_the_render(monkeypatch):
    good = MacInTalkEngine().say_ipa("æ")
    monkeypatch.setitem(ipa._IPA_TO_MACINTALK_NAME, "æ", "IY")
    bad = MacInTalkEngine().say_ipa("æ")
    assert good != bad


def test_native_to_ipa_drops_prosodic_and_silence_codes():
    # A DECtalk clause carries WBOUND/terminator codes that are not phonemes.
    codes = [c for c in sentence_to_clauses("hi.", None)[0].symbols]
    out = native_to_ipa("dectalk", codes)
    assert all(isinstance(s, str) and s for s in out)


def test_round_trip_helper_matches_struct_expectations():
    pcm = SAMEngine().say_ipa("sæm")
    assert len(struct.unpack(f"<{len(pcm) // 2}h", pcm)) == len(pcm) // 2


# --- SAM word separators / breath breakpoints -------------------------------

# A punctuation-free Portuguese IPA phrase: many words, no clause terminators.
# Its SAM run exceeds insert_breath's 232-frame window, so without word
# separators the breath pass finds no breakpoint and loops forever.
_PT_IPA = "bˈoŋ dˈiɐ eʊ suw ˌumɐ vˈɔʃ sˌiŋtˈɛtikɐ"


def test_sam_payload_carries_word_separators():
    """The IPA -> SAM payload spaces words the way the reciter does."""
    clauses = parse_ipa(_PT_IPA)
    source, _ = ipa_to_native("sam", clauses)
    assert " " in source
    # one separator per word boundary (seven words -> six gaps)
    assert source.count(" ") == 6


def test_parse_ipa_threads_word_boundaries():
    (clause,) = parse_ipa("sæm iz hir")
    assert clause.word_breaks  # boundaries are recorded, not dropped
    # the boundary indices fall on the first phone of each later word
    assert all(0 < b < len(clause.phones) for b in clause.word_breaks)


@pytest.mark.timeout(30)
def test_sam_say_ipa_no_punctuation_does_not_hang():
    """Regression: a spaceless SAM run used to loop forever in insert_breath."""
    pcm = SAMEngine().say_ipa(_PT_IPA, "Sam")
    assert pcm
    assert len(pcm) % 2 == 0


@pytest.mark.timeout(30)
def test_sam_say_ipa_long_no_punctuation_renders():
    long_ipa = ("bˈoŋ dˈiɐ " * 6).strip()
    pcm = SAMEngine().say_ipa(long_ipa, "Sam")
    assert pcm


@pytest.mark.timeout(30)
def test_sam_spaceless_phonemes_cap_terminates():
    """The defensive cap stops even a breakpoint-free phoneme run from looping."""
    pcm = SAMEngine().speak_phonemes("DIYAX" * 40)
    # malformed spaceless input never hangs; PCM may be empty but must return.
    assert pcm is not None
