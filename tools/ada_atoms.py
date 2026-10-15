"""Extract the complete atom table from AOL's ADA.BIN (ships with the FDO compiler, Ada32.dll).

Each atom record: ff ed <atom u16> ff ed <flags u16> ff ed <argtype u16> ff ea 18 f5 7f 00 ff eb <ptr4> 00 01 00 01 ff ed <len u16> <name>
Protocol is implied by the name prefix. Merges into server/fdo/atoms.json (adds argtype).
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_atom_table import PREFIX  # noqa: E402

REC = re.compile(rb"\xff\xed(..)\xff\xed(..)\xff\xed(..)\xff\xea\x18\xf5\x7f\x00\xff\xeb....\x00\x01\x00\x01\xff\xed\x00(.)([a-z][a-z0-9_]+)", re.S)

d = Path(sys.argv[1]).read_bytes()
out_path = Path(sys.argv[2])
table = json.loads(out_path.read_text())
added = conflicts = 0
for m in REC.finditer(d):
    name = m.group(5).decode()
    if len(name) != m.group(4)[0]:
        continue
    prefix = next((p for p in sorted(PREFIX, key=len, reverse=True) if name.startswith(p + "_")), None)
    if prefix is None:
        continue
    entry = {"proto": PREFIX[prefix], "atom": int.from_bytes(m.group(1), "big"),
             "flags": int.from_bytes(m.group(2), "big"), "argtype": int.from_bytes(m.group(3), "big")}
    old = table.get(name)
    if old and (old["proto"], old["atom"]) != (entry["proto"], entry["atom"]):
        conflicts += 1
        print("conflict", name, old, entry)
    if not old:
        added += 1
    table[name] = {**(old or {}), **entry}
out_path.write_text(json.dumps(dict(sorted(table.items())), indent=0))
print(f"{len(table)} atoms ({added} new, {conflicts} conflicts)")
