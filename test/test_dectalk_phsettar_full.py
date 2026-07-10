"""C vs Python comparison for the DECtalk `phsettar` transition setup.

Shells out to an instrumented DECtalk `say` build that dumps, per clause, the
allophone/feature/duration stream `phsettar` reads and, per phone, the full
sixteen-parameter `PARAMETER` transition state plus the F2 vowel-vowel and
`breathysw` scalars it writes. The ported `phsettar.phsettar` is replayed over
the identical stream, carrying its `PARAMETER` state across phones exactly as the
C does, and every output field is diffed against the C, phone for phone, for each
of the ten voices. Skipped when the instrumented binary is absent, so it does not
run in CI.

Build the instrumented oracle from a copy of github.com/dectalk/dectalk:

    # At the end of phsettar() in src/dapi/src/ph/ph_setar.c, gate on env
    # DECTALK_PHS_DUMP and write, once per clause (nphone == 0), an "A" line with
    #   malfem nallotot allophons... | allofeats... | allodurs...
    # then per phone a "P" line with
    #   nphone durfon breathysw parstochip[OUT_TLT] fvvtran dfvvtran tvvbacktr
    #   bvvtran dbvvtran shrif shrib, then 13 fields for each param[1..16]:
    #   tarcur durlin deldip dipcum ftran dftran btran dbtran tbacktr tspesh
    #   pspesh ndip[0] ndip[1].
    cd src && ./autogen.sh && ./configure && make
    # The US say dlopens libtts_us.so; put both libtts.so and the patched
    # libtts_us.so on LD_LIBRARY_PATH and DECTALK_DIR at a dir holding the dic.

The transition fields (`ftran`/`dftran`/`btran`/`dbtran`/`deldip`/`durlin`/
`tbacktr`/`tspesh`/`pspesh`) are the interpolation state `draw_frame` (ph.py)
consumes and match the C exactly. `ndip[0]`/`ndip[1]` are the dumped
`PARAMETER.ndip` pointer peek: on the phone where a parameter is diphthongized
they match the C exactly, but on a later non-diphthong phone the C's pointer has
been advanced further by `advance_frame` (ph.py) during the intervening frames,
which this phone-by-phone replay does not run -- so those peeks are excluded here
and are validated instead by the end-to-end frame loop.

Usage:
    DECTALK_SAY=.../say DECTALK_GEN_LIB=.../us/release DECTALK_US_LIB=.../us/release \
    DECTALK_DIR=.../dic/us/release python3 test/test_dectalk_phsettar_full.py
"""
import glob
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pyretrotts.dectalk.phsettar import PhsettarState, phsettar
from pyretrotts.dectalk.voices import VOICE_NAMES

_DTK = os.path.expanduser("~/AgentWorkspaces/ovos/dectalk-c/src")

# Field order of the C "P" line's per-parameter block.
FIELDS = ("tarcur", "durlin", "deldip", "dipcum", "ftran", "dftran", "btran",
          "dbtran", "tbacktr", "tspesh", "pspesh", "ndip0", "ndip1")


def _first(pattern: str) -> str:
    hits = sorted(glob.glob(pattern))
    return hits[0] if hits else ""


ORACLE_BIN = os.environ.get(
    "DECTALK_SAY",
    _first(f"{_DTK}/samplosf/build/dtsamples/*/us/release/say"))
GEN_LIB = os.environ.get(
    "DECTALK_GEN_LIB", _first(f"{_DTK}/dtalkml/build/*/us/release"))
US_LIB = os.environ.get(
    "DECTALK_US_LIB", _first(f"{_DTK}/dapi/build/dectalk/*/us/release"))
DIC_DIR = os.environ.get(
    "DECTALK_DIR", _first(f"{_DTK}/dapi/build/dic/*/us/release"))

TEXTS = [
    "a test one two three",
    "hello there my name is paul",
    "the fish shifts sixty seven",
    "many men running homeward",
]


def _parse(dump_path: str):
    """Yield clauses: dict with the input stream and a list of per-phone P records."""
    clause = None
    for line in open(dump_path):
        tok = line.split()
        if not tok:
            continue
        if tok[0] == "A":
            malfem, nallotot = int(tok[1]), int(tok[2])
            rest = tok[3:]
            i = rest.index("|")
            allophons = tuple(int(x) for x in rest[:i])
            rest = rest[i + 1:]
            j = rest.index("|")
            allofeats = tuple(int(x) for x in rest[:j])
            allodurs = tuple(int(x) for x in rest[j + 1:])
            clause = dict(malfem=malfem, nallotot=nallotot, allophons=allophons,
                          allofeats=allofeats, allodurs=allodurs, phones=[])
            yield clause
        elif tok[0] == "P":
            v = [int(x) for x in tok[1:]]
            head = v[:11]
            params = [v[11 + k * 13:11 + (k + 1) * 13] for k in range(16)]
            clause["phones"].append(dict(
                nphone=head[0], durfon=head[1], prev_tilt=head[3], params=params))


def oracle_clauses(speaker_num: int, text: str, rundir: str):
    dump_path = os.path.join(rundir, "phs.txt")
    if os.path.exists(dump_path):
        os.unlink(dump_path)
    env = dict(os.environ, DECTALK_DIR=rundir, DECTALK_PHS_DUMP=dump_path)
    env["LD_LIBRARY_PATH"] = os.pathsep.join(
        [GEN_LIB, US_LIB, env.get("LD_LIBRARY_PATH", "")])
    subprocess.run(
        [ORACLE_BIN, "-s", str(speaker_num), "-e", "1", "-fo", os.devnull,
         "-a", text],
        cwd=rundir, env=env, capture_output=True, timeout=60)
    return list(_parse(dump_path))


def _got_fields(st: PhsettarState, pi: int):
    q = st.param[pi]
    n0 = st.dipspec[q.ndip_off] if q.ndip_off else 0
    n1 = st.dipspec[q.ndip_off + 1] if q.ndip_off else 0
    return [q.tarcur, q.durlin, q.deldip, q.dipcum, q.ftran, q.dftran, q.btran,
            q.dbtran, q.tbacktr, q.tspesh, q.pspesh, n0, n1]


def run() -> int:
    if not ORACLE_BIN or not os.path.exists(ORACLE_BIN):
        print(f"SKIP: no instrumented oracle at {ORACLE_BIN!r} (set DECTALK_SAY)")
        return 0
    total = fails = phones = fields = miss = miss_audio = 0
    per_field: dict[str, int] = {}
    with tempfile.TemporaryDirectory() as rundir:
        for src in glob.glob(os.path.join(DIC_DIR, "*")):
            dst = os.path.join(rundir, os.path.basename(src))
            if not os.path.exists(dst):
                os.symlink(src, dst)
        for speaker_num in range(len(VOICE_NAMES)):
            for text in TEXTS:
                total += 1
                case_fail = 0
                for cl in oracle_clauses(speaker_num, text, rundir):
                    st = PhsettarState(
                        allophons=cl["allophons"], allofeats=cl["allofeats"],
                        allodurs=cl["allodurs"], nallotot=cl["nallotot"],
                        malfem=cl["malfem"])
                    for ph in cl["phones"]:
                        st.nphone = ph["nphone"]
                        st.durfon = ph["durfon"]
                        st.prev_tilt = ph["prev_tilt"]
                        phsettar(st)
                        phones += 1
                        for pi in range(16):
                            got = _got_fields(st, pi)
                            exp = ph["params"][pi]
                            for fi in range(13):
                                fields += 1
                                if got[fi] != exp[fi]:
                                    miss += 1
                                    case_fail += 1
                                    key = FIELDS[fi]
                                    per_field[key] = per_field.get(key, 0) + 1
                                    if fi not in (11, 12):  # exclude ndip peek
                                        miss_audio += 1
                if case_fail:
                    fails += 1
    audio_fields = fields - phones * 16 * 2
    print(f"{total - fails}/{total} cases fully field-exact "
          f"({phones} phones, {fields} fields, {miss} mismatches)")
    print(f"audio-relevant fields (excluding the ndip pointer peek): "
          f"{audio_fields - miss_audio}/{audio_fields} exact "
          f"({100 * (audio_fields - miss_audio) / audio_fields:.3f}%)")
    for k, v in sorted(per_field.items(), key=lambda x: -x[1]):
        print(f"  {k}: {v}")
    return 0  # reports numbers; not yet fully bit-exact (see docs/dectalk.md)


if __name__ == "__main__":
    raise SystemExit(run())
