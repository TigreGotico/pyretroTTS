"""Extract C array definitions from Data.c/Data.h into Python modules.

Usage: python3 tools/extract_data.py
"""

import os
import re

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
C_SRC = os.path.join(os.path.dirname(REPO), "lintalker-c", "src")
C_INC = os.path.join(os.path.dirname(REPO), "lintalker-c", "include")
OUT = os.path.join(REPO, "pyretrotts")

# `_data.py` interleaves these generated tables with hand-maintained content --
# the 17 voice dicts, the marker tables, and the base64 lexicon blob -- so it
# cannot be regenerated wholesale. Emit the tables beside it for review instead.
GENERATED_NAME = "_data_tables.generated.py"


def strip_c_comments(text):
    """Remove C-style comments from text."""
    # Remove // comments
    text = re.sub(r'//[^\n]*', '', text)
    # Remove /* */ comments
    text = re.sub(r'/\*.*?\*/', '', text, flags=re.DOTALL)
    return text


def extract_array(text, name):
    """Extract a C array by name. Returns list of ints or None."""
    # Clean text first
    cleaned = strip_c_comments(text)

    # Match: optional type name[] = { ... } ;
    # Type can include const, volatile, etc.
    pat = re.compile(
        r'(?:const\s+)?(?:unsigned\s+)?(?:signed\s+)?'
        r'\w+(?:\s+const)?\s+' +
        re.escape(name) +
        r'\s*\[\s*(?:\d+)?\s*\]\s*=\s*\{(.*?)\}\s*;',
        re.DOTALL
    )
    m = pat.search(cleaned)
    if not m:
        return None

    body = m.group(1)
    # Parse comma-separated values, handling nested braces
    vals = []
    for part in body.split(','):
        part = part.strip()
        if not part:
            continue
        # Remove any remaining whitespace
        part = part.strip()
        if not part:
            continue
        try:
            vals.append(int(part, 0))
        except ValueError:
            # Handle expressions: k100pct / N, etc.
            part2 = part.replace('k100pct', str(0x10000))
            # Try to evaluate simple arithmetic
            try:
                # Safe eval of simple integer expressions
                val = eval(part2, {"__builtins__": {}}, {})
                if isinstance(val, (int, float)):
                    vals.append(int(val))
                else:
                    print(f"  WARN: non-int eval for '{part[:50]}' in {name}")
                    vals.append(0)
            except Exception as e:
                print(f"  WARN: can't parse '{part[:50]}' in {name}: {e}")
                vals.append(0)

    return vals


def extract_voice_data(text):
    """Extract voiceData struct definitions from Data.c."""
    cleaned = strip_c_comments(text)
    voices = []

    # Find all struct voiceData init blocks that have a comment name before them
    # Pattern: comment with voice name before a { ... } block
    idx = 0
    while True:
        # Look for a comment followed by a struct initializer
        m = re.search(r'/\*\s*(\w+(?:\s+\w+)*)\s*\*/\s*\{', cleaned[idx:])
        if not m:
            # Try // comment pattern
            m = re.search(r'//\s*(\w+(?:\s+\w+)*)\s*\n\s*\{', cleaned[idx:])
        if not m:
            break

        name = m.group(1).strip()

        # Find matching closing brace
        brace_start = cleaned.index('{', idx + m.start())
        depth = 1
        pos = brace_start + 1
        while depth > 0 and pos < len(cleaned):
            if cleaned[pos] == '{':
                depth += 1
            elif cleaned[pos] == '}':
                depth -= 1
            pos += 1
        block_text = cleaned[brace_start:pos]

        voices.append({'name': name, 'text': block_text})
        idx = pos

    return voices


def format_table(vals, name, indent=0):
    """Format a list of ints as a Python list literal."""
    sp = "    " * indent
    lines = [f"{sp}{name}: List[int] = ["]
    # Determine column width based on max abs value
    max_abs = max(abs(v) for v in vals) if vals else 1
    if max_abs < 100:
        w = 4
    elif max_abs < 1000:
        w = 6
    elif max_abs < 100000:
        w = 8
    else:
        w = 10

    for i in range(0, len(vals), 16):
        row = vals[i:i+16]
        fmt = ", ".join(f"{v:{w}d}" for v in row)
        comma = "," if i + 16 < len(vals) else ","
        lines.append(f"{sp}    {fmt}{comma}")
    lines.append(f"{sp}]")
    return "\n".join(lines)


def main():
    os.makedirs(OUT, exist_ok=True)
    os.makedirs(os.path.join(REPO, "tools"), exist_ok=True)

    # Read source files
    with open(os.path.join(C_SRC, "Data.c"), errors='replace') as f:
        data_c = f.read()
    with open(os.path.join(C_INC, "Data.h"), errors='replace') as f:
        data_h = f.read()

    combined = data_c + "\n\n" + data_h

    # Tables to extract
    table_names = [
        "CosTbl",
        "BcoeffTbl",
        "CcoeffTbl",
        "TopOctave",
        "PhonFlags2",
        "One_Over_X_Tbl",
        "LogToLin",
        "LogToLin1",
        "logOf2Tbl",
        "ExpOf2Tbl",
        "OctFreqTbl",
        "SineWave15",
        "SineWave",
        "NoiseWave",
        "BandNoise",
        "HPNoise",
        "CtrlBlockTypeTbl",
        "PhonTypeTbl",
        "f1FreqTblM",
        "f2FreqTblM",
        "f3FreqTblM",
        "b1FreqTblM",
        "b2FreqTblM",
        "b3FreqTblM",
        "avVolTblM",
        "EnvelopeListTbl",
        "f1FreqTblF",
        "f2FreqTblF",
        "f3FreqTblF",
        "b1FreqTblF",
        "b2FreqTblF",
        "b3FreqTblF",
        "avVolTblF",
        "Front_Loci_Tbl",
        "Mid_Loci_Tbl",
        "Back_Loci_Tbl",
        "Male_NoiseAmpTbl",
        "Female_NoiseAmpTbl",
        "Male_Loci_Tbl",
        "Female_Loci_Tbl",
        "BurstDurTbl",
        "NoiseIndexTbl",
        "Rank_FWD_Tbl",
        "Rank_BKWD_Tbl",
        "DefaultTargTbl",
        "phonPitchTbl",
        "maxDurTbl",
        "minDurTbl",
        "XlateToAllo",
        "Allo_to_Phon",
        "Phon_to_Phon",
        "MagicCharMap",
        "MagicOpcodeMap",
        "CharAttr",
        "KindTBL",
        "dashruletab",
        "atruletab",
        "lruletab",
        "mruletab",
        "zruletab",
        "percentruletab",
        "bruletab",
        "BoundryDurTbl",
        "divisorsPtr",
        "SuffixTab",
        "SuffixType",
        "Opcode_To_ASCII",
        "AndPhonStr",
        "PowerStr",
        "ControlPhonStr",
        "SilencePhonStr",
        "AppleSCII",
        "DollarPhonStr",
        "CentPhonStr",
        "ClockPhonStr",
        "OhPhonStr",
        "NonASCIIPhonStr",
    ]

    arrays = []
    not_found = []

    for name in table_names:
        vals = extract_array(combined, name)
        if vals is not None:
            print(f"  {name}: {len(vals)} values")
            arrays.append({'name': name, 'vals': vals})
        else:
            not_found.append(name)

    if not_found:
        print(f"\nNot found: {', '.join(not_found)}")

    # Write _data.py
    if arrays:
        lines = [
            "# Auto-generated from Data.c / Data.h",
            "# ruff: noqa: all",
            "from typing import List",
            "",
            ""
        ]
        for arr in arrays:
            lines.append(format_table(arr['vals'], arr['name']))
            lines.append("")
            lines.append("")

        out_path = os.path.join(OUT, GENERATED_NAME)
        with open(out_path, 'w') as f:
            f.write("\n".join(lines))
        print(f"\nWrote {out_path}")
        print("Diff its tables into pyretrotts/_data.py; do not copy the file "
              "over _data.py, which also holds the voice dicts and lexicon.")

    # Extract voice data
    print("\n--- Voice Data ---")
    voices = extract_voice_data(data_c)
    print(f"Found {len(voices)} voice definitions")


if __name__ == "__main__":
    main()
