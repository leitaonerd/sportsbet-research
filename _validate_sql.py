# Validate that SQL INSERT IGNORE statements have %s placeholders
# matching the number of columns. Plain ASCII. No live DB needed.
import re
import sys


def colnames(inner):
    cols = [c.strip() for c in inner.split(",")]
    return [c for c in cols if c]


def count_ph(sql):
    return len(re.findall(r"%s", sql))

src = open("sofascore.py", encoding="utf-8").read()

# Python concatenates multi-line string segments with quotes between them.
# Strip string literals and collapse newlines so the full INSERT text is contiguous.

collapsed = re.sub(r'"[^"]*"', "", src)
collapsed = collapsed.replace("\n", " ").replace("\r", " ")

ok = True
for m in re.finditer(
    r'INSERT IGNORE INTO (\w+)\s*\((.*?)\)\s*VALUES\s*\((.*?)\)', collapsed
):
    table, cols_txt, ph_txt = m.group(1), m.group(2), m.group(3)
    ncols = len(colnames(cols_txt))
    nph = count_ph(ph_txt)
    status = "OK" if ncols == nph else "MISMATCH"
    if ncols != nph:
        ok = False
    print(f"{table}: {ncols} cols, {nph} placeholders -> {status}")

print("VALIDATE_OK" if ok else "VALIDATE_FAIL")
sys.exit(3 if ok else 1)