"""Annotated x86 disassembly of a PE (imports + strings resolved). Complements codemap decompile.

usage: disasm.py <pe> [start_hex [end_hex]]
"""
import sys

import capstone
import pefile

pe = pefile.PE(sys.argv[1])
base = pe.OPTIONAL_HEADER.ImageBase
imp = {i.address: f"{d.dll.decode()}!{(i.name or str(i.ordinal).encode()).decode()}"
       for d in getattr(pe, "DIRECTORY_ENTRY_IMPORT", []) for i in d.imports}
strs = {}
for s in pe.sections:
    if s.Name.startswith((b".data", b".rdata")):
        data, va, i = s.get_data(), base + s.VirtualAddress, 0
        while i < len(data):
            j = i
            while j < len(data) and 32 <= data[j] < 127:
                j += 1
            if j - i >= 4 and j < len(data) and data[j] == 0:
                strs[va + i] = data[i:j].decode()
            i = max(j, i + 1)
lo = int(sys.argv[2], 16) if len(sys.argv) > 2 else 0
hi = int(sys.argv[3], 16) if len(sys.argv) > 3 else 1 << 32
text = next(s for s in pe.sections if s.Name.startswith(b".text"))
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
for ins in md.disasm(text.get_data(), base + text.VirtualAddress):
    if not lo <= ins.address < hi:
        continue
    note = ""
    for tok in ins.op_str.replace("[", " ").replace("]", " ").replace(",", " ").split():
        if tok.startswith("0x") and ":" not in tok:
            v = int(tok, 16)
            note += f" ; {imp[v]}" if v in imp else ""
            note += f' ; "{strs[v][:60]}"' if v in strs else ""
    print(f"{ins.address:08x}  {ins.mnemonic:6} {ins.op_str}{note}")
