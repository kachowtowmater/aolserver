"""Index the stock AOL 3.0 client's MAIN.IDX: which art each local form needs,
and which art the client already has. -> server/data/client_art.json

usage: build_form_art.py MAIN.IDX
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "server"))
from fdo import codec  # noqa: E402
from idb_dump import gid_str, records  # noqa: E402

NESTED = {"act_append_action", "act_replace_action", "act_replace_select_action", "act_set_db_action",
          "act_append_select_action", "uni_start_large_atom", "uni_large_atom_segment", "uni_end_large_atom"}


def art_refs(data: bytes, out: set):
    try:
        atoms = codec.decode(data)
    except Exception:
        return
    for a in atoms:
        if a.name == "mat_art_id" and len(a.args) == 4:
            t, sub, i = a.args[0], a.args[1], int.from_bytes(a.args[2:4], "big")
            out.add(f"{t}-{sub}-{i}")
        elif a.name in NESTED and len(a.args) > 2:
            art_refs(a.args, out)


def main():
  local_art, forms = set(), {}
  for g, flags, body in records(Path(sys.argv[1]).read_bytes()):
    name = gid_str(g)
    if name.startswith("1-"):
        if flags & 0x2000:  # without it the client treats the record as stale and DODs it
            local_art.add(name)
        continue
    refs = set()
    art_refs(body, refs)
    if refs:
        forms[name] = sorted(refs)
  out = Path(__file__).resolve().parent.parent / "server" / "data" / "client_art.json"
  out.write_text(json.dumps({"local_art": sorted(local_art), "forms": forms}, indent=0))
  missing = {a for v in forms.values() for a in v} - local_art
  print(f"{len(forms)} forms reference art; {len(local_art)} art local; {len(missing)} referenced art missing -> {out}")


if __name__ == "__main__":
    main()
