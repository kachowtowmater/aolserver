"""Build server/fdo/atoms.json (name -> protocol id, atom number) from the FDO91 manual text."""
import json, re, sys
from pathlib import Path

PREFIX = {"act": 2, "activex": 54, "ad": 39, "doc": 31, "mat": 16, "async": 13, "adp": 66, "buf": 4,
          "chart": 23, "chat": 11, "cm": 10, "ccl": 34, "if": 15, "de": 3, "idb": 5, "dice": 57, "man": 1,
          "exapi": 26, "fm": 8, "xfer": 7, "gallery": 56, "hfs": 51, "image": 22, "imgxfer": 21, "lm": 9,
          "mip": 17, "morg": 24, "mmi": 20, "pictalk": 29, "p3": 35, "dod": 27, "radio": 28, "rich": 25,
          "sm": 14, "spell": 61, "mt": 42, "uni": 0, "var": 12, "vid": 53, "vrm": 47, "www": 48}
HEAD = re.compile(r"^\s*atom\$([a-z0-9_]+)\s*\n\s*(\d+)\s*\(\$([0-9A-Fa-f]+)\)", re.M)



def main():
    atoms = {}
    for f in sorted(Path(sys.argv[1]).glob("*.txt")):
        for m in HEAD.finditer(f.read_text(errors="replace")):
            name, num = m.group(1), int(m.group(2))
            if int(m.group(3), 16) != num:
                continue
            proto = next((PREFIX[p] for p in sorted(PREFIX, key=len, reverse=True) if name.startswith(p + "_")), None)
            if proto is not None:
                atoms.setdefault(name, {"proto": proto, "atom": num})
    out = Path(sys.argv[2])
    out.write_text(json.dumps(dict(sorted(atoms.items())), indent=0))
    print(len(atoms), "atoms ->", out)


if __name__ == "__main__":
    main()
