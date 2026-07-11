"""Regenerate the UK-English target ROM modules from `libtts_uk.so`.

The UK-English `ph/` target ROM (`ph/p_uk_rom.c`) holds the per-phoneme Klatt
target tables that `uk_gettar` (`ph/p_uk_st1.c:76`) and the UK `phsettar` smooth
rules read -- the British-English analogue of the US ROM extracted by
`tools/dump_dectalk_targets.py`. Several arrays are written with feature-bit
macro tokens, so they are read from the built `libtts_uk.so` symbols at their
resolved addresses rather than transcribed: guaranteed identical to the compiled
reference.

Array element counts are fixed by the linked ROM's dimensions and were
cross-checked against both the C source initializers and the ELF symbol sizes of
`libtts_uk.so` (`UK_TOT_ALLOPHONES == 57`; `uk_featb` is a `short[101]`; the
diphthong/amplitude/locus tables differ in length from US). `parini`, `partyp`,
`divtab` and `lineartilt` are language-shared symbols and are NOT re-dumped here
-- the UK path reuses `targets.py`/`targets_transitions.py` for them.

The emitted files carry the FONIX proprietary-source notice (see NOTICE); they
are not covered by this project's MIT licence.

Usage:
    python3 tools/dump_dectalk_uk_targets.py [--lib PATH] [--out FILE]
"""
from __future__ import annotations

import argparse
import os

from dump_dectalk_targets import _dump_arrays, _write_module

DEFAULT_LIB = os.path.expanduser(
    "~/AgentWorkspaces/ovos/dectalk-c/src/dapi/build/dectalk/"
    "7.1.3-arch1-1/uk/release/libtts_uk.so")
DEFAULT_OUT = os.path.join(
    os.path.dirname(__file__), "..", "pyretrotts", "dectalk", "targets_uk.py")
DEFAULT_OUT_TRANS = os.path.join(
    os.path.dirname(__file__), "..", "pyretrotts", "dectalk",
    "targets_transitions_uk.py")

# name -> (symbol, element count), from `p_uk_rom.c` initializers, confirmed by
# the ELF symbol sizes of `libtts_uk.so` (short = 2 bytes; `uk_featb` short too).
ARRAYS = {
    "UK_MALTAR": ("uk_maltar", 399),
    "UK_FEMTAR": ("uk_femtar", 399),
    "UK_MALDIP": ("uk_maldip", 432),
    "UK_FEMDIP": ("uk_femdip", 366),
    "UK_MALAMP": ("uk_malamp", 542),
    "UK_FEMAMP": ("uk_femamp", 542),
    "UK_PLACE": ("uk_place", 57),
    "UK_BEGTYP": ("uk_begtyp", 57),
    "UK_ENDTYP": ("uk_endtyp", 57),
    "UK_PTRAM": ("uk_ptram", 57),
    "UK_FEATB": ("uk_featb", 101),
}

TRANS_ARRAYS = {
    "UK_INHDR": ("uk_inhdr", 57),
    "UK_BURDR": ("uk_burdr", 57),
    "UK_MALELOC": ("uk_maleloc", 866),
    "UK_PLOCU": ("uk_plocu", 228),
    "UK_FEMLOC": ("uk_femloc", 866),
}

_HEADER = '''"""Per-phoneme Klatt target ROM of the DECtalk UK-English front end.

Derived from the Fonix/Force DECtalk C source (`dectalk/dectalk`,
`src/dapi/src/ph/p_uk_rom.c`). FONIX Corporation declares that source
proprietary and confidential. This file is NOT covered by this project's MIT
licence. See NOTICE.

Values are read from the built `libtts_uk.so` by
`tools/dump_dectalk_uk_targets.py` (a C program that links the library and
prints each resolved symbol), so they are guaranteed identical to the compiled
reference rather than retyped. `uk_gettar` (`p_uk_st1.c:76`) indexes these tables
exactly as `us_gettar` indexes the US ROM (see `targets.py`), with
`UK_TOT_ALLOPHONES = 57` phones per parameter block. The shared `parini`,
`partyp` and `divtab` symbols are not per-language; the UK path reuses
`targets.py`/`targets_transitions.py` for them.
"""
'''

_HEADER_TRANS = '''"""Locus, burst- and inherent-duration ROM of the DECtalk UK-English front end.

Derived from the Fonix/Force DECtalk C source (`dectalk/dectalk`,
`src/dapi/src/ph/p_uk_rom.c`). FONIX Corporation declares that source
proprietary and confidential. This file is NOT covered by this project's MIT
licence. See NOTICE.

Values are read from the built `libtts_uk.so` by
`tools/dump_dectalk_uk_targets.py`, guaranteed identical to the compiled
reference. The UK transition machinery (`ph_setar.c` `phsettar` -> the UK smooth
rules in `p_uk_st1.c`, and `setloc` in `ph_sttr2.c`) reads these exactly as the
US path reads `targets_transitions.py`. `divtab` and `lineartilt` are shared
symbols and are reused from `targets_transitions.py`.
"""
'''


def regenerate(lib: str, out: str) -> None:
    _write_module(out, _HEADER, ARRAYS, _dump_arrays(lib, ARRAYS))


def regenerate_transitions(lib: str, out: str) -> None:
    _write_module(out, _HEADER_TRANS, TRANS_ARRAYS, _dump_arrays(lib, TRANS_ARRAYS))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lib", default=DEFAULT_LIB)
    ap.add_argument("--out", default=os.path.normpath(DEFAULT_OUT))
    ap.add_argument("--out-transitions", default=os.path.normpath(DEFAULT_OUT_TRANS))
    args = ap.parse_args()
    regenerate(args.lib, args.out)
    regenerate_transitions(args.lib, args.out_transitions)


if __name__ == "__main__":
    main()
