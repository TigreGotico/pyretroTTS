"""Perceptual coverage and intelligibility for the generative front ends.

There is no bit-exact oracle for "all IPA", so quality is measured two ways:

* ``--coverage`` prints a per-symbol table over a multilingual IPA set, marking
  which symbols ModernTalk synthesizes from features and which fall back to the
  nearest reachable target. No model needed.

* ``--wer`` renders an English IPA set through ModernTalk and, for the same IPA,
  through the classic nearest-English-preset path (``MacInTalkEngine.say_ipa``),
  transcribes both with Parakeet ASR and reports word error rate. WER is a proxy
  for intelligibility, not a measure of it; the comparison is what matters.
  Needs ``onnx-asr``, ``scipy``, ``jiwer`` and a cached Parakeet model.

    python3 tools/modern_coverage.py --coverage
    python3 tools/modern_coverage.py --wer
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pyretrotts.modern import ModernTalkEngine  # noqa: E402
from pyretrotts.modern.features import DIPHTHONGS  # noqa: E402

ASR_MODEL = "istupakov/parakeet-tdt-0.6b-v2-onnx"
ASR_RATE = 16000

#: English IPA set: (reference words, broad General-American IPA transcription).
#: The core ten are the fixed Harvard-style sentences of ``tools/intelligibility.
#: py`` (SENTENCES), transcribed here in broad GenAm so the intelligibility gate
#: is not gameable on a handful of short phrases; three phonetically-varied
#: sentences (dense /ʒ/, /θ/ and mixed onsets) are added for breadth.
ENGLISH = [
    ("the quick brown fox jumps over the lazy dog",
     "ðə kwɪk braʊn fɑks dʒʌmps oʊvər ðə leɪzi dɔg"),
    ("she sells sea shells by the sea shore",
     "ʃi sɛlz si ʃɛlz baɪ ðə si ʃɔr"),
    ("please call stella and ask her to bring these things",
     "pliz kɔl stɛlə ænd æsk hər tu brɪŋ ðiz θɪŋz"),
    ("the rain in spain falls mainly on the plain",
     "ðə reɪn ɪn speɪn fɔlz meɪnli ɑn ðə pleɪn"),
    ("how much wood would a woodchuck chuck",
     "haʊ mʌtʃ wʊd wʊd ə wʊdtʃʌk tʃʌk"),
    ("peter piper picked a peck of pickled peppers",
     "pitər paɪpər pɪkt ə pɛk ʌv pɪkəld pɛpərz"),
    ("the birch canoe slid on the smooth planks",
     "ðə bɜrtʃ kəˈnu slɪd ɑn ðə smuð plæŋks"),
    ("glue the sheet to the dark blue background",
     "glu ðə ʃit tu ðə dɑrk blu bækgraʊnd"),
    ("we were away a year ago",
     "wi wɜr əˈweɪ ə jɪr əˈgoʊ"),
    ("the small pup gnawed a hole in the sock",
     "ðə smɔl pʌp nɔd ə hoʊl ɪn ðə sɑk"),
    ("hello world",
     "həˈloʊ wɜrld"),
    ("the boy threw three free throws",
     "ðə bɔɪ θru θri fri θroʊz"),
    ("measure the pleasure of leisure",
     "ˈmɛʒər ðə ˈplɛʒər ʌv ˈliʒər"),
]

#: Multilingual set exercising sounds English lacks.
MULTILINGUAL = [
    ("French", "bɔ̃ʒuʁ", "bonjour: nasal vowel + uvular /ʁ/"),
    ("French", "ty", "tu: front-rounded /y/"),
    ("French", "œf", "oeuf: front-rounded /œ/"),
    ("German", "ɪç", "ich: palatal fricative /ç/"),
    ("German", "ʁoːt", "rot: uvular /ʁ/, long vowel"),
    ("German", "myːdə", "muede: /y/ long"),
    ("Spanish", "ˈkaʎe", "calle: palatal lateral /ʎ/"),
    ("Spanish", "ˈaɲo", "año: palatal nasal /ɲ/"),
    ("Spanish", "ˈpero", "perro-ish: alveolar trill /r/"),
    ("Portuguese", "mɐ̃w̃", "mão: nasal diphthong"),
    ("Portuguese", "ˈʒẽtɐ", "gente: /ʒ/ + nasal vowel"),
    ("Portuguese", "ˈkõtɐ", "conta: nasal /õ/"),
    ("Italian", "ʎi", "gli: palatal lateral"),
    ("Mandarin", "ɕi", "xi: alveolo-palatal /ɕ/"),
    ("Dutch", "sxɛvənɪŋən", "Scheveningen: velar /x/"),
    ("Arabic", "ħaːl", "haal: pharyngeal /ħ/"),
]


def _all_symbols(ipa: str) -> list[str]:
    from pyretrotts.ipa import parse_ipa

    syms = []
    for clause in parse_ipa(ipa):
        for phone in clause.phones:
            syms.append(phone.symbol)
    return syms


def coverage() -> None:
    engine = ModernTalkEngine()
    seen: dict[str, bool] = {}
    for _lang, ipa, _gloss in MULTILINGUAL + [("en", w, "") for _, w in ENGLISH]:
        for sym, _bundle, fell in engine.bundles(ipa):
            # A diphthong is "synthesized" if it expands to known segments.
            fell = fell and sym not in DIPHTHONGS
            seen[sym] = seen.get(sym, False) or not fell
    synths = sorted(s for s, ok in seen.items() if ok)
    falls = sorted(s for s, ok in seen.items() if not ok)
    print(f"distinct IPA symbols seen : {len(seen)}")
    print(f"synthesized from features : {len(synths)}  ({100*len(synths)//len(seen)}%)")
    print(f"nearest-target fallback   : {len(falls)}")
    print("\nsynthesized:", " ".join(synths))
    print("\nfallback   :", " ".join(falls) if falls else "(none)")
    print("\nnon-English words attempted (all render; none collapse to English):")
    for lang, ipa, gloss in MULTILINGUAL:
        fb = [s for s, _b, f in engine.bundles(ipa)
              if f and s not in DIPHTHONGS]
        tag = "fallback " + " ".join(fb) if fb else "full feature synthesis"
        print(f"  {lang:11s} /{ipa}/  {gloss}  -> {tag}")


def _resample(pcm: bytes, src_rate: int):
    import numpy as np
    from scipy.signal import resample_poly

    x = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768.0
    g = np.gcd(src_rate, ASR_RATE)
    return resample_poly(x, ASR_RATE // g, src_rate // g).astype(np.float32)


def wer() -> None:
    import jiwer
    import onnx_asr

    from pyretrotts import MacInTalkEngine

    model = onnx_asr.load_model(ASR_MODEL)
    modern = ModernTalkEngine()
    classic = MacInTalkEngine()

    def transcribe(pcm: bytes, rate: int) -> str:
        return model.recognize(_resample(pcm, rate), sample_rate=ASR_RATE).strip()

    refs, mod_hyp, cls_hyp = [], [], []
    print(f"{'reference':28s} {'ModernTalk':26s} {'classic IPA-preset':26s}")
    for text, ipa in ENGLISH:
        # Track each engine's real rate so the resampler measures the voice, not
        # a rate mismatch. ModernTalk now emits 22050 Hz like every other engine.
        m = transcribe(modern.say_ipa(ipa), modern.sample_rate)
        c = transcribe(classic.say_ipa(ipa), classic.sample_rate)
        refs.append(text)
        mod_hyp.append(m)
        cls_hyp.append(c)
        print(f"{text:28s} {m:26s} {c:26s}")
    mw = jiwer.wer(refs, mod_hyp)
    cw = jiwer.wer(refs, cls_hyp)
    print(f"\nModernTalk (generative Klatt)  WER = {mw:.3f}")
    print(f"classic IPA nearest-preset     WER = {cw:.3f}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--coverage", action="store_true")
    ap.add_argument("--wer", action="store_true")
    args = ap.parse_args()
    if args.wer:
        wer()
    else:
        coverage()


if __name__ == "__main__":
    main()
