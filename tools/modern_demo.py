"""Render a multilingual IPA set on ModernTalk and ModernSAM for listening.

Writes WAVs to an output directory (default: ``modern_demo/``) so a human can
judge quality by ear -- the only honest test for "all IPA".

    python3 tools/modern_demo.py [outdir]
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pyretrotts.modern import ModernSAMEngine, ModernTalkEngine  # noqa: E402

#: (label, IPA). English first, then sounds English lacks.
DEMO = [
    ("en_hello", "həˈloʊ wɜrld"),
    ("en_quick_fox", "ðə kwɪk braʊn fɑks"),
    ("en_sea_shells", "ʃi sɛlz si ʃɛlz"),
    ("fr_bonjour", "bɔ̃ʒuʁ"),           # nasal vowel + uvular /ʁ/
    ("fr_tu", "ty"),                     # front-rounded /y/
    ("de_ich", "ɪç"),                    # palatal fricative /ç/
    ("de_muede", "myːdə"),               # /y/ long
    ("es_calle", "ˈkaʎe"),               # palatal lateral /ʎ/
    ("es_ano", "ˈaɲo"),                  # palatal nasal /ɲ/
    ("pt_mao", "mɐ̃w̃"),                  # nasal diphthong
    ("pt_gente", "ˈʒẽtɐ"),               # /ʒ/ + nasal vowel
    ("ar_haal", "ħaːl"),                 # pharyngeal /ħ/
    ("nl_scheveningen", "sxɛvənɪŋən"),   # velar /x/
]


def main() -> None:
    outdir = sys.argv[1] if len(sys.argv) > 1 else "modern_demo"
    os.makedirs(outdir, exist_ok=True)
    talk = ModernTalkEngine()
    sam = ModernSAMEngine()
    for label, ipa in DEMO:
        talk.say_ipa(ipa, path=os.path.join(outdir, f"talk_{label}.wav"))
        sam.say_ipa(ipa, path=os.path.join(outdir, f"sam_{label}.wav"))
        print(f"/{ipa}/ -> talk_{label}.wav, sam_{label}.wav")
    print(f"\n{2 * len(DEMO)} WAVs in {outdir}/")


if __name__ == "__main__":
    main()
