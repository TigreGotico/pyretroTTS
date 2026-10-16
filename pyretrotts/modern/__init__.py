"""Generative IPA front ends for pyretroTTS (experimental).

The classic engines map IPA to the nearest of a fixed set of English phoneme
presets before synthesis (`pyretrotts.ipa`). That collapse is lossy: any sound
outside the English inventory is rounded to an English neighbour.

The ``modern`` package takes the opposite approach. It decomposes an IPA symbol
into articulatory features and *generates* synthesis parameters from those
features, so an arbitrary IPA phone -- including sounds English lacks -- drives
the synthesizer directly instead of being replaced by a preset.

Two front ends share the feature model:

* :class:`~pyretrotts.modern.talk.ModernTalkEngine` generates Klatt parameter
  frames and renders them through DECtalk's bit-exact vocal tract model. Klatt
  synthesis has high headroom, so this is the high-value path.
* :class:`~pyretrotts.modern.sam.ModernSAMEngine` generates three-oscillator
  parameters for SAM's 8-bit renderer. SAM's fixed sample tables and coarse
  frequency codes cap its fidelity; this path is a lo-fi curiosity.

Nothing here alters the classic engines or their bit-exact goldens.
"""
from .features import FeatureBundle, decompose, nearest_target
from .sam import ModernSAMEngine
from .talk import ModernTalkEngine

__all__ = [
    "FeatureBundle",
    "decompose",
    "nearest_target",
    "ModernTalkEngine",
    "ModernSAMEngine",
]
