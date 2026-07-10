"""Regenerate `pyretrotts/dectalk/targets.py` from the DECtalk C source.

The US-English target ROM (`p_us_rom_dectalk_1996m_43f.c`, selected by the build
macro `VOICE_ROM_DECTALK_1996M_43F`) holds the per-phoneme Klatt target tables
that `us_gettar` (`p_us_st0.c:67`) reads. Several of those arrays are written
with macro tokens (`F2BACKF`, feature-bit names), so they cannot be transcribed
by parsing the source text. Instead this tool links a tiny C program against the
built `libtts_us.so`, reads the resolved `const short` symbols at their real
addresses, and prints each array. The values are therefore guaranteed identical
to what the compiled synthesizer uses, not retyped.

Array lengths are fixed by the built ROM's dimensions
(`US_TOT_ALLOPHONES == 57`, `PHO_SYM_TOT == 105`) and cross-checked against a
comma-count of the source initializers.

The emitted file carries the FONIX proprietary-source notice, because the values
descend from source FONIX declares confidential (see NOTICE); it is not covered
by this project's MIT licence.

Usage:
    python3 tools/dump_dectalk_targets.py [--lib PATH] [--out FILE]

`--lib` is the built US shared library (default: the instrumented oracle copy).
"""
from __future__ import annotations

import argparse
import os
import subprocess
import tempfile

DEFAULT_LIB = os.path.expanduser(
    "~/AgentWorkspaces/ovos/dectalk-c/src/dapi/build/dectalk/"
    "7.1.3-arch1-1/us/release/libtts_us.so")
DEFAULT_OUT = os.path.join(
    os.path.dirname(__file__), "..", "pyretrotts", "dectalk", "targets.py")

# name -> element count, from p_us_rom_dectalk_1996m_43f.c initializers.
# The F/BW/AV target block is US_TOT_ALLOPHONES(57) * 7 param slots = 399.
ARRAYS = {
    "US_MALTAR": ("us_maltar", 399),
    "US_FEMTAR": ("us_femtar", 399),
    "US_MALDIP": ("us_maldip", 450),
    "US_FEMDIP": ("us_femdip", 450),
    "US_MALAMP": ("us_malamp", 385),
    "US_FEMAMP": ("us_femamp", 385),
    "US_PLACE": ("us_place", 57),
    "US_BEGTYP": ("us_begtyp", 57),
    "US_ENDTYP": ("us_endtyp", 57),
    "US_PTRAM": ("us_ptram", 57),
    "US_FEATB": ("us_featb", 105),
    "PARINI": ("parini", 16),
    "PARTYP": ("partyp", 16),
}

_HEADER = '''"""Per-phoneme Klatt target ROM of the DECtalk US-English front end.

Derived from the Fonix/Force DECtalk C source (`dectalk/dectalk`,
`src/dapi/src/ph/p_us_rom_dectalk_1996m_43f.c`, the ROM selected by the build
macro `VOICE_ROM_DECTALK_1996M_43F`). FONIX Corporation declares that source
proprietary and confidential. This file is NOT covered by this project's MIT
licence. See NOTICE.

Values are read from the built `libtts_us.so` by `tools/dump_dectalk_targets.py`
(a C program that links the library and prints each resolved symbol), so they are
guaranteed identical to the compiled reference rather than retyped.

`us_gettar` (`p_us_st0.c:67`) indexes these tables:

  US_TOT_ALLOPHONES = 57 phones per parameter block.
  US_MALTAR/US_FEMTAR   F1,F2,F3,B1,B2,B3,AV target blocks; index
                        (phone & 0xFF) + pphotr, pphotr = npar*57 (npar < FZ)
                        else (npar-1)*57. Negative < -1 => -pointer into *DIP.
  US_MALDIP/US_FEMDIP   diphthong (time,value) target sequences, -1 terminated.
  US_MALAMP/US_FEMAMP   parallel-formant amplitude targets for obstruents,
                        base = ptram(phone), + (npar - A2 + 1 + 6*begtypnex).
  US_PLACE              place-of-articulation feature bits (F2BACKI/F2BACKF ...).
  US_BEGTYP/US_ENDTYP   onset/offset transition class per phone.
  US_PTRAM              per-phone pointer into the amplitude ROM (0 => none).
  US_FEATB              phonetic feature bitmask per symbol (PHO_SYM_TOT = 105),
                        indexed by (phone & 0xFF); phone_feature() reads it.
  PARINI                default target per parameter (F1..TILT).
  PARTYP                parameter type code: 0 AV/AH, 1 nasal-zero, 2 parallel
                        amp, 3 formant freq, 4 formant bandwidth.
"""
'''

_DUMPER_C_TMPL = r'''
#include <stdio.h>
%s
int main(void){
%s
    return 0;
}
'''


def regenerate(lib: str, out: str) -> None:
    # partyp is a `char[]` in the source; the rest are `short[]`.
    ctype = {"PARTYP": "char"}
    externs = "\n".join(
        f"extern const {ctype.get(py, 'short')} {sym}[];"
        for py, (sym, _n) in ARRAYS.items())
    body = []
    for py, (sym, n) in ARRAYS.items():
        body.append(f'    printf("{py}\\n");')
        body.append(f'    for(int i=0;i<{n};i++)printf("%d\\n",(int){sym}[i]);')
        body.append('    printf(".\\n");')
    csrc_text = _DUMPER_C_TMPL % (externs, "\n".join(body))
    with tempfile.TemporaryDirectory() as tmp:
        csrc = os.path.join(tmp, "dumptar.c")
        cbin = os.path.join(tmp, "dumptar")
        with open(csrc, "w") as f:
            f.write(csrc_text)
        subprocess.run(
            ["gcc", "-o", cbin, csrc, lib, f"-Wl,-rpath,{os.path.dirname(lib)}"],
            check=True)
        raw = subprocess.run(
            [cbin], check=True, capture_output=True, text=True).stdout
    # Parse: NAME line, then integers until '.'.
    tables: dict[str, list[int]] = {}
    cur: str | None = None
    for line in raw.splitlines():
        line = line.strip()
        if line == ".":
            cur = None
        elif line in ARRAYS:
            cur = line
            tables[cur] = []
        elif cur is not None and line:
            tables[cur].append(int(line))
    for py, (_sym, n) in ARRAYS.items():
        got = len(tables.get(py, []))
        if got != n:
            raise SystemExit(f"{py}: dumped {got} elements, expected {n}")
    with open(out, "w") as f:
        f.write(_HEADER + "\n")
        for py in ARRAYS:
            vals = tables[py]
            f.write(f"{py}: tuple[int, ...] = (\n")
            for i in range(0, len(vals), 12):
                f.write("    " + ", ".join(str(v) for v in vals[i:i + 12]) + ",\n")
            f.write(")\n\n")
    print(f"wrote {out} ({len(ARRAYS)} arrays)")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lib", default=DEFAULT_LIB)
    ap.add_argument("--out", default=os.path.normpath(DEFAULT_OUT))
    args = ap.parse_args()
    regenerate(args.lib, args.out)


if __name__ == "__main__":
    main()
