"""Pluggable pronunciation dictionaries."""
import pathlib

import pytest

from pyretrotts import MacInTalkEngine
from pyretrotts._lexicon import lookup
from pyretrotts._phonemes import _Word_
from pyretrotts.dictionaries import (
    Dictionary,
    UserDictionary,
    active_dictionary,
    load_dictionary,
    parse_pronunciation,
    use_dictionary,
)


def test_a_pronunciation_parses_to_word_prefixed_opcodes():
    opcodes = parse_pronunciation("g IH f")
    assert opcodes[0] == _Word_
    assert len(opcodes) == 4


def test_mnemonics_may_run_together():
    assert parse_pronunciation("gIHf") == parse_pronunciation("g IH f")


def test_an_unknown_mnemonic_is_rejected():
    with pytest.raises(ValueError, match="not a phoneme mnemonic"):
        parse_pronunciation("g QQ f")


def test_a_user_dictionary_satisfies_the_protocol():
    assert isinstance(UserDictionary({}), Dictionary)


def test_a_user_dictionary_is_case_insensitive():
    d = UserDictionary({"GIF": "g IH f"})
    assert d.lookup("gif") is not None
    assert d.lookup("GIF") is not None
    assert d.lookup("jif") is None


def test_no_dictionary_is_installed_by_default():
    assert active_dictionary() is None


def test_the_overlay_is_consulted_before_the_builtin():
    builtin = lookup("HELLO")
    assert builtin is not None
    with use_dictionary(UserDictionary({"HELLO": "h EH l OW"})):
        assert lookup("HELLO").phon_str != builtin.phon_str


def test_the_overlay_falls_through_for_words_it_lacks():
    with use_dictionary(UserDictionary({"GIF": "g IH f"})):
        assert lookup("HELLO") is not None


def test_an_empty_overlay_cannot_change_a_render():
    engine = MacInTalkEngine()
    baseline = engine.synthesize("a gif file.", "Fred")
    with use_dictionary(None):
        assert engine.synthesize("a gif file.", "Fred") == baseline


def test_a_custom_pronunciation_changes_the_render():
    engine = MacInTalkEngine()
    baseline = engine.synthesize("a gif file.", "Fred")
    with use_dictionary(UserDictionary({"GIF": "JIH f"})):
        assert engine.synthesize("a gif file.", "Fred") != baseline


def test_the_overlay_is_removed_on_exit():
    engine = MacInTalkEngine()
    baseline = engine.synthesize("a gif file.", "Fred")
    with use_dictionary(UserDictionary({"GIF": "JIH f"})):
        pass
    assert engine.synthesize("a gif file.", "Fred") == baseline
    assert active_dictionary() is None


def test_a_dictionary_file_loads_and_ignores_comments(tmp_path: pathlib.Path):
    path = tmp_path / "mine.dic"
    path.write_text("; a comment\n# another\n\nGIF  g IH f\nJIF  JIH f\n")
    loaded = load_dictionary(path)
    assert set(loaded.words) == {"GIF", "JIF"}
    assert loaded.lookup("GIF") is not None
