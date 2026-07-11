"""Render an A/B listening reel for the generative ModernTalk front end.

Two sections, written as WAVs to an output directory (default ``modern_reel/``),
all at the engines' real **22050 Hz** so the reel is comparable to every other
render:

* **English A/B** -- each sentence rendered three ways: through ModernTalk
  (generative Klatt, with the full prosody/timing/coarticulation layer), through
  the classic **text** path (``DECtalkEngine.synthesize`` -- the intelligible
  reference, ~0.25 WER), and through the classic **IPA nearest-preset** path
  (``MacInTalkEngine.say_ipa``, ~0.61 WER on this set), so the gap the WER
  harness measures can be judged by ear (``talk_en_*`` vs ``text_en_*`` vs
  ``preset_en_*``).
* **Multilingual** -- sounds English lacks, rendered through ModernTalk only;
  the classic paths cannot attempt them at all.

    python3 tools/modern_reel.py [outdir]
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pyretrotts import DECtalkEngine, MacInTalkEngine  # noqa: E402
from pyretrotts.modern import ModernTalkEngine  # noqa: E402
from tools.modern_coverage import ENGLISH as _WER_ENGLISH  # noqa: E402


def _label(text: str) -> str:
    return "_".join(text.split()[:3]).lower()


#: (label, reference text, IPA) -- the fixed WER sentence set from the harness.
ENGLISH = [(_label(text), text, ipa) for text, ipa in _WER_ENGLISH]

#: (label, IPA, gloss) -- sounds outside the English inventory.
MULTILINGUAL = [
    ("fr_bonjour", "bɔ̃ʒuʁ", "French: nasal vowel + uvular /ʁ/"),
    ("fr_tu", "ty", "French: front-rounded /y/"),
    ("de_ich", "ɪç", "German: palatal fricative /ç/"),
    ("de_muede", "myːdə", "German: long /yː/"),
    ("es_calle", "ˈkaʎe", "Spanish: palatal lateral /ʎ/"),
    ("es_ano", "ˈaɲo", "Spanish: palatal nasal /ɲ/"),
    ("pt_gente", "ˈʒẽtɐ", "Portuguese: /ʒ/ + nasal vowel"),
    ("cmn_xi", "ɕi", "Mandarin: alveolo-palatal /ɕ/"),
    ("ar_haal", "ħaːl", "Arabic: pharyngeal /ħ/"),
    ("nl_scheveningen", "sxɛvənɪŋən", "Dutch: velar /x/"),
]


def main() -> None:
    outdir = sys.argv[1] if len(sys.argv) > 1 else "modern_reel"
    os.makedirs(outdir, exist_ok=True)
    talk = ModernTalkEngine()
    text_engine = DECtalkEngine()          # classic text path (~0.25 WER)
    preset = MacInTalkEngine()             # classic IPA nearest-preset (~0.61)
    assert talk.sample_rate == text_engine.sample_rate == 22050

    print(f"English A/B at {talk.sample_rate} Hz "
          "(ModernTalk IPA | classic text | classic IPA-preset):")
    for label, text, ipa in ENGLISH:
        talk.say_ipa(ipa, path=os.path.join(outdir, f"talk_en_{label}.wav"))
        text_engine.say(text + ".", os.path.join(outdir, f"text_en_{label}.wav"))
        preset.say_ipa(ipa, path=os.path.join(outdir, f"preset_en_{label}.wav"))
        print(f"  {text[:34]:34s} -> talk_en_{label}.wav | "
              f"text_en_{label}.wav | preset_en_{label}.wav")

    print("\nMultilingual (ModernTalk only; the classic paths cannot attempt these):")
    for label, ipa, gloss in MULTILINGUAL:
        talk.say_ipa(ipa, path=os.path.join(outdir, f"talk_{label}.wav"))
        print(f"  /{ipa}/  {gloss}  -> talk_{label}.wav")

    n = 3 * len(ENGLISH) + len(MULTILINGUAL)
    print(f"\n{n} WAVs in {outdir}/ (all 22050 Hz)")


if __name__ == "__main__":
    main()
