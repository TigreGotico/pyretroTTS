"""DECtalk engine, ported from the Fonix/Force DECtalk C source.

Derived from the Fonix/Force DECtalk C source (`dectalk/dectalk`). FONIX
Corporation declares that source proprietary and confidential. This subpackage
is NOT covered by this project's MIT licence. See NOTICE.

Phase 1 ports the vocal tract model (`src/dapi/src/vtm/`, VTM1 integer Klatt
synthesizer). The text front end (`cmd/`, `lts/`, `ph/`) is not ported yet, so
`DECtalkEngine.synthesize_text` is not available; the shipping DECtalk markup
still renders through MacinTalk (`pyretrotts._dectalk`).
"""
