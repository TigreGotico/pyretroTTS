"""The ten built-in DECtalk voices and their resolved chip parameters.

Derived from the Fonix/Force DECtalk C source (`dectalk/dectalk`). FONIX
Corporation declares that source proprietary and confidential. This file is
NOT covered by this project's MIT licence. See NOTICE.

The canonical names and `[:n?]` codes are from `cmd/c_us_cde.h:301-315,403-415`.
Each `SpeakerState` is the resolved integer coefficient set that
`read_speaker_definition` (`vtm/vtm1.c`) produces from a voice's high-level
`[:dv]` Klatt parameters (defined in `ph/p_us_vdf*.c`; that layer is Phase 3).
These values are captured verbatim from the C oracle, one speaker-definition
packet per voice, so they match the reference exactly. Variable Val (`nv`)
resolves to the Perfect Paul defaults until `[:dv]` overrides it.
"""
from __future__ import annotations

from .vtm import SpeakerState

# say(1) speaker number -> canonical name.
VOICE_NAMES: tuple[str, ...] = (
    'Perfect Paul',  # -s 0 / [:np]
    'Beautiful Betty',  # -s 1 / [:nb]
    'Huge Harry',  # -s 2 / [:nh]
    'Frail Frank',  # -s 3 / [:nf]
    'Doctor Dennis',  # -s 4 / [:nd]
    'Kit the Kid',  # -s 5 / [:nk]
    'Uppity Ursula',  # -s 6 / [:nu]
    'Rough Rita',  # -s 7 / [:nr]
    'Whispering Wendy',  # -s 8 / [:nw]
    'Variable Val',  # -s 9 / [:nv]
)

# `[:n?]` two-letter select code -> say(1) speaker number.
VOICE_SELECT: dict[str, int] = {
    'np': 0,
    'nb': 1,
    'nh': 2,
    'nf': 3,
    'nd': 4,
    'nk': 5,
    'nu': 6,
    'nr': 7,
    'nw': 8,
    'nv': 9,
}

SPEAKERS: tuple[SpeakerState, ...] = (
    SpeakerState(fnscal=4100, avgain=2552, APgain=4547, AFgain=4547, Aturb=0, k1=8800, k2=0, t0jitr=0, r1cg=29491, r2cg=2273, r3cg=359, rnpa=7291, R4ca=1438, R4cb=-2317, R4cc=-3540, R5ca=3645, R5cb=-3645, R5cc=-3400, R4pb=-2400, r4pc=-3265, R5pb=-4140, r5pc=-3090, r6pb=-5702, r6pc=-1995, rnpb=7943, rnpc=-3953, rlpa=1262, rlpb=5913, rlpc=-2894, noiseb=-2913),  # Perfect Paul
    SpeakerState(fnscal=4100, avgain=2552, APgain=4547, AFgain=5751, Aturb=0, k1=13600, k2=0, t0jitr=0, r1cg=16384, r2cg=911, r3cg=455, rnpa=5751, R4ca=2552, R4cb=-6250, R4cc=-3540, R5ca=4096, R5cb=0, R5cc=0, R4pb=-5047, r4pc=-3265, R5pb=0, r5pc=0, r6pb=-5702, r6pc=-1995, rnpb=7943, rnpc=-3953, rlpa=1262, rlpb=5913, rlpc=-2894, noiseb=-2913),  # Beautiful Betty
    SpeakerState(fnscal=3485, avgain=2552, APgain=4547, AFgain=4547, Aturb=0, k1=6240, k2=40, t0jitr=0, r1cg=16384, r2cg=1823, r3cg=568, rnpa=6488, R4ca=1438, R4cb=-214, R4cc=-3665, R5ca=5104, R5cb=-2219, R5cc=-3575, R4pb=-1801, r4pc=-3265, R5pb=-4618, r5pc=-3090, r6pb=-5702, r6pc=-1995, rnpb=7943, rnpc=-3953, rlpa=1262, rlpb=5913, rlpc=-2894, noiseb=-2913),  # Huge Harry
    SpeakerState(fnscal=4510, avgain=2048, APgain=3645, AFgain=3645, Aturb=1276, k1=13600, k2=0, t0jitr=44, r1cg=29491, r2cg=2875, r3cg=911, rnpa=8192, R4ca=1137, R4cb=-4974, R4cc=-3503, R5ca=2048, R5cb=-6571, R5cc=-3451, R4pb=-2981, r4pc=-3265, R5pb=-4779, r5pc=-3090, r6pb=-5702, r6pc=-1995, rnpb=7943, rnpc=-3953, rlpa=1262, rlpb=5913, rlpc=-2894, noiseb=-2913),  # Frail Frank
    SpeakerState(fnscal=3895, avgain=2048, APgain=3645, AFgain=3645, Aturb=318, k1=20000, k2=40, t0jitr=0, r1cg=23429, r2cg=1622, r3cg=568, rnpa=9093, R4ca=1438, R4cb=-1207, R4cc=-3575, R5ca=8192, R5cb=-2806, R5cc=-3503, R4pb=-5047, r4pc=-3265, R5pb=0, r5pc=0, r6pb=-5702, r6pc=-1995, rnpb=7943, rnpc=-3953, rlpa=1262, rlpb=5913, rlpc=-2894, noiseb=-2913),  # Doctor Dennis
    SpeakerState(fnscal=4920, avgain=2552, APgain=4547, AFgain=5751, Aturb=911, k1=13600, k2=0, t0jitr=0, r1cg=6488, r2cg=455, r3cg=568, rnpa=5104, R4ca=4096, R4cb=0, R4cc=0, R5ca=4096, R5cb=0, R5cc=0, R4pb=-6002, r4pc=-3265, R5pb=0, r5pc=0, r6pb=-5702, r6pc=-1995, rnpb=7943, rnpc=-3953, rlpa=1262, rlpb=5913, rlpc=-2894, noiseb=-2913),  # Kit the Kid
    SpeakerState(fnscal=4305, avgain=2552, APgain=4547, AFgain=4547, Aturb=0, k1=4000, k2=40, t0jitr=0, r1cg=14582, r2cg=1137, r3cg=512, rnpa=7291, R4ca=2552, R4cb=-6764, R4cc=-3540, R5ca=3244, R5cb=0, R5cc=0, R4pb=-5623, r4pc=-3265, R5pb=0, r5pc=0, r6pb=-5702, r6pc=-1995, rnpb=7943, rnpc=-3953, rlpa=1262, rlpb=5913, rlpc=-2894, noiseb=-2913),  # Uppity Ursula
    SpeakerState(fnscal=4305, avgain=2552, APgain=4547, AFgain=5751, Aturb=811, k1=16800, k2=0, t0jitr=34, r1cg=20644, r2cg=719, r3cg=359, rnpa=6488, R4ca=5751, R4cb=-5591, R4cc=-3557, R5ca=4096, R5cb=0, R5cc=0, R4pb=-5047, r4pc=-3265, R5pb=0, r5pc=0, r6pb=-5702, r6pc=-1995, rnpb=7943, rnpc=-3953, rlpa=1262, rlpb=5913, rlpc=-2894, noiseb=-2913),  # Rough Rita
    SpeakerState(fnscal=4100, avgain=512, APgain=3645, AFgain=4547, Aturb=2273, k1=20000, k2=40, t0jitr=0, r1cg=20644, r2cg=811, r3cg=638, rnpa=8192, R4ca=1823, R4cb=-6126, R4cc=-3265, R5ca=4096, R5cb=0, R5cc=0, R4pb=-5047, r4pc=-3265, R5pb=0, r5pc=0, r6pb=-5702, r6pc=-1995, rnpb=7943, rnpc=-3953, rlpa=1262, rlpb=5913, rlpc=-2894, noiseb=-2913),  # Whispering Wendy
    SpeakerState(fnscal=4100, avgain=2552, APgain=4547, AFgain=4547, Aturb=0, k1=8800, k2=0, t0jitr=0, r1cg=29491, r2cg=2273, r3cg=359, rnpa=7291, R4ca=1438, R4cb=-2317, R4cc=-3540, R5ca=3645, R5cb=-3645, R5cc=-3400, R4pb=-2400, r4pc=-3265, R5pb=-4140, r5pc=-3090, r6pb=-5702, r6pc=-1995, rnpb=7943, rnpc=-3953, rlpa=1262, rlpb=5913, rlpc=-2894, noiseb=-2913),  # Variable Val
)

