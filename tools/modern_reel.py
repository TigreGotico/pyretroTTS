"""Render an A/B listening reel for the generative ModernTalk front end.

Two sections, written as WAVs to an output directory (default ``modern_reel/``):

* **English A/B** -- each sentence rendered twice, once through ModernTalk
  (generative Klatt) and once through the classic nearest-English-preset path
  (``MacInTalkEngine``), so the quality gap the WER harness measures can be
  judged by ear (``talk_en_*`` vs ``classic_en_*``).
* **Multilingual** -- sounds English lacks, rendered through ModernTalk only;
  the classic path cannot attempt them at all.

    python3 tools/modern_reel.py [outdir]
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pyretrotts import MacInTalkEngine  # noqa: E402
from pyretrotts.modern import ModernTalkEngine  # noqa: E402

#: (label, reference text, IPA) -- the fixed WER sentence set.
ENGLISH = [
    ("quick_fox", "the quick brown fox", "ðə kwɪk braʊn fɑks"),
    ("sea_shells", "she sells sea shells", "ʃi sɛlz si ʃɛlz"),
    ("stella", "please call stella", "pliz kɔl stɛlə"),
    ("hello_world", "hello world", "həˈloʊ wɜrld"),
    ("these_things", "bring these things", "brɪŋ ðiz θɪŋz"),
    ("peter", "peter picked a peck", "pitər pɪkt ə pɛk"),
]

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
    classic = MacInTalkEngine()

    print("English A/B (ModernTalk vs classic nearest-preset):")
    for label, text, ipa in ENGLISH:
        talk.say_ipa(ipa, path=os.path.join(outdir, f"talk_en_{label}.wav"))
        classic.say_ipa(ipa, path=os.path.join(outdir, f"classic_en_{label}.wav"))
        print(f"  {text:26s} /{ipa}/  -> talk_en_{label}.wav | classic_en_{label}.wav")

    print("\nMultilingual (ModernTalk only; classic path cannot attempt these):")
    for label, ipa, gloss in MULTILINGUAL:
        talk.say_ipa(ipa, path=os.path.join(outdir, f"talk_{label}.wav"))
        print(f"  /{ipa}/  {gloss}  -> talk_{label}.wav")

    n = 2 * len(ENGLISH) + len(MULTILINGUAL)
    print(f"\n{n} WAVs in {outdir}/")


if __name__ == "__main__":
    main()
