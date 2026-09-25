"""Extract the DECtalk US letter-to-sound rule tables from `libtts_us.so`.

The rule interpreter (`lts/ls_rule*.c`) walks compiled tables (`acna_lswtab`,
`acna_lsbtab`), the per-grapheme feature set (`feats`), the input case-fold
(`ls_fold`), the per-phoneme feature set (`pfeat`), and the stress-refusing
prefix table (`preftab`). Several are written in the C source with macro tokens,
so the values are read verbatim from the compiled library's exported symbols --
guaranteed identical to the reference, not retyped -- exactly as
`tools/dump_dectalk_targets.py` reads the target ROM.

This compiles a tiny C program that links `libtts_us.so`, prints every table
element, and writes `pyretrotts/dectalk/lts_rules_data.py` under the FONIX
notice (the extracted data descends from FONIX-proprietary source; see NOTICE).

Usage:
    python3 tools/dump_dectalk_lts_tables.py [--dist DIR] [--out FILE]

`--dist` is the built oracle `dist/` directory (holding `lib/libtts_us.so`).
"""
from __future__ import annotations

import argparse
import os
import subprocess
import tempfile

DEFAULT_DIST = os.path.expanduser("~/AgentWorkspaces/ovos/dectalk-c/dist")
DEFAULT_OUT = os.path.join(
    os.path.dirname(__file__), "..", "pyretrotts", "dectalk", "lts_rules_data.py")

# Element counts from the ELF symbol sizes (`readelf -sW libtts_us.so`):
# acna_lswtab 16804 B / 2, acna_lsbtab 22904 B, feats 62 B / 2, ls_fold 256 B,
# pfeat 240 B / 2, preftab 230 B.
_LSWTAB_N = 8402
_LSBTAB_N = 22904
_FEATS_N = 31
_LSFOLD_N = 256
_PFEAT_N = 120
_PREFTAB_N = 230

def _dumper_c() -> str:
    def block(label: str, sym: str, n: int, mask: str, spec: str) -> str:
        return (
            f'    printf("{label} {n}\\n");\n'
            f'    for (int i = 0; i < {n}; i++) '
            f'printf("{spec}\\n", {sym}[i]{mask});\n')

    return (
        "#include <stdio.h>\n"
        "typedef unsigned short U16;\n"
        "typedef short S16;\n"
        "extern U16 acna_lswtab[];\n"
        "extern unsigned char acna_lsbtab[];\n"
        "extern S16 feats[];\n"
        "extern unsigned char ls_fold[];\n"
        "extern U16 pfeat[];\n"
        "extern unsigned char preftab[];\n"
        "int main(void) {\n"
        + block("LSWTAB", "acna_lswtab", _LSWTAB_N, " & 0xFFFF", "%u")
        + block("LSBTAB", "acna_lsbtab", _LSBTAB_N, " & 0xFF", "%u")
        + block("FEATS", "feats", _FEATS_N, "", "%d")
        + block("LSFOLD", "ls_fold", _LSFOLD_N, " & 0xFF", "%u")
        + block("PFEAT", "pfeat", _PFEAT_N, " & 0xFFFF", "%u")
        + block("PREFTAB", "preftab", _PREFTAB_N, " & 0xFF", "%u")
        + "    return 0;\n}\n")

_HEADER = '''"""DECtalk US letter-to-sound rule tables (`l_us_rta.c`, ACNA build).

Derived from the Fonix/Force DECtalk C source (`dectalk/dectalk`,
`src/dapi/src/lts/l_us_rta.c`, `l_us_con.c`, `ls_defs.h`). FONIX Corporation
declares that source proprietary and confidential. This data, extracted verbatim
from the compiled `libtts_us.so` symbols (`acna_lswtab`, `acna_lsbtab`, `feats`,
`ls_fold`, `pfeat`, `preftab`) by `tools/dump_dectalk_lts_tables.py`, is NOT
covered by this project's MIT licence. See NOTICE.

`LSWTAB` (U16) and `LSBTAB` (u8) are the compiled letter-to-sound rule dictionary
the `ls_rule*` interpreter walks; `FEATS` are the per-grapheme feature bitsets
(grapheme code 0..30); `LSFOLD` folds an input byte to its case-folded character;
`PFEAT` are the per-phoneme feature bitsets; `PREFTAB` is the stress-refusing
prefix table.
"""
'''


def _fmt(arr: list[int], per: int = 16) -> str:
    rows = []
    for k in range(0, len(arr), per):
        rows.append("    " + ",".join(str(x) for x in arr[k:k + per]) + ",")
    return "\n".join(rows)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dist", default=DEFAULT_DIST)
    ap.add_argument("--out", default=DEFAULT_OUT)
    args = ap.parse_args()

    lib = os.path.join(args.dist, "lib")
    src = _dumper_c()
    with tempfile.TemporaryDirectory() as td:
        cpath = os.path.join(td, "dump.c")
        binpath = os.path.join(td, "dump")
        with open(cpath, "w") as f:
            f.write(src)
        subprocess.run(
            ["gcc", cpath, "-L", lib, "-ltts_us", "-Wl,-rpath," + lib, "-o", binpath],
            check=True)
        out = subprocess.run(
            [binpath], check=True, capture_output=True, text=True,
            env=dict(os.environ, LD_LIBRARY_PATH=lib)).stdout

    vals: dict[str, list[int]] = {}
    lines = out.split("\n")
    i = 0
    while i < len(lines):
        if not lines[i].strip():
            i += 1
            continue
        name, n = lines[i].split()
        n = int(n)
        i += 1
        vals[name] = [int(lines[i + j]) for j in range(n)]
        i += n

    with open(args.out, "w") as o:
        o.write(_HEADER)
        o.write("\nLSWTAB = (\n" + _fmt(vals["LSWTAB"]) + "\n)\n")
        o.write("\nLSBTAB = bytes((\n" + _fmt(vals["LSBTAB"]) + "\n))\n")
        o.write("\nFEATS = (" + ",".join(str(x) for x in vals["FEATS"]) + ",)\n")
        o.write("\nLSFOLD = bytes((" + ",".join(str(x) for x in vals["LSFOLD"]) + ",))\n")
        o.write("\nPFEAT = (\n" + _fmt(vals["PFEAT"]) + "\n)\n")
        o.write("\nPREFTAB = bytes((\n" + _fmt(vals["PREFTAB"]) + "\n))\n")
    print(f"wrote {args.out}: {len(vals['LSWTAB'])} lswtab, {len(vals['LSBTAB'])} lsbtab")


if __name__ == "__main__":
    main()
