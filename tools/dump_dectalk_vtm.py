"""Regenerate `pyretrotts/dectalk/tables.py` from the DECtalk C source.

The vocal tract model's fixed-point tables (`vtm/vtmtable.h`) are transcribed
into Python by compiling a tiny C program that includes the real header and
prints each array, so the values are guaranteed identical to the reference
rather than retyped by hand. This mirrors `tools/extract_data.py` for MacinTalk.

The emitted file carries the FONIX proprietary-source notice, because the
values descend from source FONIX declares confidential (see NOTICE); it is not
covered by this project's MIT licence.

Usage:
    python3 tools/dump_dectalk_vtm.py [--source DIR] [--out FILE]

`--source` is a read-only checkout of github.com/dectalk/dectalk
(default ~/AgentWorkspaces/ovos/dectalk).

This tool also holds `parse_vtm_dump`, the reader for frame dumps produced by
an instrumented oracle build (see docs/dectalk.md); the tests import it.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import tempfile

DEFAULT_SOURCE = os.path.expanduser("~/AgentWorkspaces/ovos/dectalk")
DEFAULT_OUT = os.path.join(
    os.path.dirname(__file__), "..", "pyretrotts", "dectalk", "tables.py")

_HEADER = '''"""Fixed-point tables of the DECtalk vocal tract model.

Derived from the Fonix/Force DECtalk C source (`dectalk/dectalk`,
`src/dapi/src/vtm/vtmtable.h`). FONIX Corporation declares that source
proprietary and confidential. This file is NOT covered by this project's MIT
licence. See NOTICE.

Values are transcribed verbatim from the C by `tools/dump_dectalk_vtm.py`
(a C dumper that includes the real `vtmtable.h`), so they are guaranteed
identical to the reference rather than retyped.

  B0            glottal-pulse shaping coefficient, indexed by (nopen - 40)
  AZERO/BZERO/CZERO_TAB   nasal-zero antiresonator coefficients, index (FZ>>3)-31
  AMPTABLE      dB-to-linear amplitude conversion (Q12)
  COSINE_TABLE  2*cos(2*pi*T*f) in Q12, indexed by (frequency >> 3)
  RADIUS_TABLE  exp(-pi*T*bw) in Q12, indexed by (bandwidth >> 3)
"""
'''

_DUMPER_C = r'''
#include <stdio.h>
typedef short S16;
typedef int S32;
#include "vtmtable.h"
static void p(const char*n,const S16*a,int len){
    printf("%s: tuple[int, ...] = (",n);
    for(int i=0;i<len;i++){if(i%12==0)printf("\n    ");printf("%d, ",a[i]);}
    printf("\n)\n\n");
}
int main(void){
    p("B0",B0,224);
    p("AZERO_TAB",azero_tab,35);
    p("BZERO_TAB",bzero_tab,35);
    p("CZERO_TAB",czero_tab,35);
    p("AMPTABLE",amptable,88);
    p("COSINE_TABLE",cosine_table,sizeof(cosine_table)/sizeof(cosine_table[0]));
    p("RADIUS_TABLE",radius_table,sizeof(radius_table)/sizeof(radius_table[0]));
    return 0;
}
'''


def regenerate_tables(source: str, out: str) -> None:
    vtm = os.path.join(source, "src/dapi/src/vtm")
    inc = os.path.join(source, "src/dapi/src/include")
    with tempfile.TemporaryDirectory() as tmp:
        csrc = os.path.join(tmp, "dumptab.c")
        cbin = os.path.join(tmp, "dumptab")
        with open(csrc, "w") as f:
            f.write(_DUMPER_C)
        subprocess.run(
            ["gcc", "-I", vtm, "-I", inc, "-DPC_SAMPLE_RATE=11025",
             "-o", cbin, csrc],
            check=True)
        body = subprocess.run([cbin], check=True, capture_output=True, text=True).stdout
    body = "\n".join(line.rstrip() for line in body.splitlines()) + "\n"
    with open(out, "w") as f:
        f.write(_HEADER + "\n" + body)
    print(f"wrote {out}")


def parse_vtm_dump(path: str) -> tuple[dict[str, int], list[tuple[list[int], list[int]]]]:
    """Parse an instrumented-oracle dump into (speaker_state, [(frame, iwave)]).

    The dump has one `S ...` line of resolved speaker state and one `F n p... w...`
    line per frame (20 parameters then `n` samples).
    """
    speaker: dict[str, int] = {}
    frames: list[tuple[list[int], list[int]]] = []
    with open(path) as fh:
        for line in fh:
            tok = line.split()
            if not tok:
                continue
            if tok[0] == "S":
                speaker = {k: int(v) for k, v in (kv.split("=") for kv in tok[1:])}
            elif tok[0] == "F":
                n = int(tok[1])
                nums = [int(x) for x in tok[2:]]
                frames.append((nums[:20], nums[20:20 + n]))
    return speaker, frames


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default=DEFAULT_SOURCE)
    ap.add_argument("--out", default=os.path.normpath(DEFAULT_OUT))
    args = ap.parse_args()
    regenerate_tables(args.source, args.out)


if __name__ == "__main__":
    main()
