"""DECtalk engine, ported from the Fonix/Force DECtalk C source.

Derived from the Fonix/Force DECtalk C source (`dectalk/dectalk`). FONIX
Corporation declares that source proprietary and confidential. This subpackage
is NOT covered by this project's MIT licence. See NOTICE.

The vocal tract model (`src/dapi/src/vtm/`, VTM1 integer Klatt synthesizer)
and the US text front end (`cmd/`, `lts/`, `ph/`) are ported. `DECtalkEngine`
drives plain text through them when the FONIX dictionary is present; the
shipping DECtalk markup for singing still renders through MacinTalk
(`pyretrotts._dectalk`).
"""
