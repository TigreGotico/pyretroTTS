"""Extract the DECtalk US inflectional-suffix trie from `libtts_us.so`.

The suffix stripper (`lts/ls_suff.c` `ls_suff_suffix_find` / `ls_suff_append_pron`)
walks two compiled tables when a word misses the main dictionary: `suffix_index`
(one byte offset per case-folded first-of-search letter, `'a'..'z'` then a
non-alpha slot) and `suffix_table` (a flat array of `struct suff_rule`
`{U32 next; U32 fc; unsigned char rule[]}`, `ls_dict.h:86`). The rule bytes use
the `SF_*` control tokens (`ls_suff.c:92-100`). Both are written in the C source
as a compiled binary blob, so the values are read verbatim from the exported
symbols of `libtts_us.so` -- guaranteed identical to the reference, not retyped --
exactly as `tools/dump_dectalk_lts_tables.py` reads the rule tables.

Usage:
    python3 tools/dump_dectalk_suffix.py [--dist DIR] [--out FILE]

`--dist` is the built oracle `dist/` directory (holding `lib/libtts_us.so`).
"""
from __future__ import annotations

import argparse
import os
import subprocess
import tempfile

DEFAULT_DIST = os.path.expanduser("~/AgentWorkspaces/ovos/dectalk-c/dist")
DEFAULT_OUT = os.path.join(
    os.path.dirname(__file__), "..", "pyretrotts", "dectalk", "suffix_data.py")

# ELF symbol sizes (`readelf -sW libtts_us.so`): suffix_table 5988 B (u8),
# suffix_index 108 B / 4 = 27 U32.
_TABLE_N = 5988
_INDEX_N = 27

_DUMP_C = (
    "#include <stdio.h>\n"
    "typedef unsigned int U32;\n"
    "extern unsigned char suffix_table[];\n"
    "extern U32 suffix_index[];\n"
    "int main(void) {\n"
    f'    printf("TABLE {_TABLE_N}\\n");\n'
    f"    for (int i = 0; i < {_TABLE_N}; i++) "
    'printf("%u\\n", suffix_table[i] & 0xff);\n'
    f'    printf("INDEX {_INDEX_N}\\n");\n'
    f"    for (int i = 0; i < {_INDEX_N}; i++) "
    'printf("%u\\n", suffix_index[i]);\n'
    "    return 0;\n}\n")

_HEADER = '''"""DECtalk US inflectional-suffix trie (`lts/ls_suff.c`, `ls_dict.h`).

Derived from the Fonix/Force DECtalk C source (`dectalk/dectalk`,
`src/dapi/src/lts/ls_suff.c`, `lts/ls_dict.h`). FONIX Corporation declares that
source proprietary and confidential. This data, extracted verbatim from the
compiled `libtts_us.so` symbols (`suffix_table`, `suffix_index`) by
`tools/dump_dectalk_suffix.py`, is NOT covered by this project's MIT licence.
See NOTICE.

`SUFFIX_INDEX[k]` (k = case-folded letter `'a'..'z'` as 0..25, or 26 for a
non-alpha search head) is the byte offset of the first `struct suff_rule` in
`SUFFIX_TABLE` for words whose search letter is `k`, or `0xffff` for none. Each
rule is `{U32 next; U32 fc; unsigned char rule[]}` little-endian; `next` chains
to the next rule offset (`0xffff` ends the chain).
"""
'''


def _fmt(arr, per: int = 20) -> str:
    return "\n".join(
        "    " + ",".join(str(x) for x in arr[k:k + per]) + ","
        for k in range(0, len(arr), per))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dist", default=DEFAULT_DIST)
    ap.add_argument("--out", default=DEFAULT_OUT)
    args = ap.parse_args()

    lib = os.path.join(args.dist, "lib")
    with tempfile.TemporaryDirectory() as td:
        cpath = os.path.join(td, "dump.c")
        binpath = os.path.join(td, "dump")
        with open(cpath, "w") as f:
            f.write(_DUMP_C)
        subprocess.run(
            ["gcc", cpath, "-L", lib, "-ltts_us", "-Wl,-rpath," + lib,
             "-o", binpath], check=True)
        out = subprocess.run(
            [binpath], check=True, capture_output=True, text=True,
            env=dict(os.environ, LD_LIBRARY_PATH=lib)).stdout

    lines = out.split("\n")
    vals: dict[str, list[int]] = {}
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
        o.write("\nSUFFIX_TABLE = bytes((\n" + _fmt(vals["TABLE"]) + "\n))\n")
        o.write("\nSUFFIX_INDEX = (" + ",".join(str(x) for x in vals["INDEX"])
                + ",)\n")
    print(f"wrote {args.out}: {len(vals['TABLE'])} table bytes, "
          f"{len(vals['INDEX'])} index")


if __name__ == "__main__":
    main()
