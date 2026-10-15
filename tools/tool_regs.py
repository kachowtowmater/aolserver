"""List ToolRegister(type, id, handler) calls in each AOL tool's ToolInit (type 2 = atom protocol)."""
import sys

import capstone
import pefile

for path in sys.argv[1:]:
    pe = pefile.PE(path)
    base = pe.OPTIONAL_HEADER.ImageBase
    exp = {e.name: base + e.address for e in pe.DIRECTORY_ENTRY_EXPORT.symbols if e.name}
    names = {base + e.address: e.name.decode() for e in pe.DIRECTORY_ENTRY_EXPORT.symbols if e.name}
    reg = {i.address for d in pe.DIRECTORY_ENTRY_IMPORT for i in d.imports
           if d.dll.upper().startswith(b"SUPERSUB") and (i.name == b"ToolRegister" or i.ordinal == 69)}
    thunks = set()
    text = next(s for s in pe.sections if s.Name.startswith(b".text"))
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
    insns = list(md.disasm(text.get_data(), base + text.VirtualAddress))
    for ins in insns:  # jmp [iat] thunks
        if ins.mnemonic == "jmp" and ins.op_str.startswith("dword ptr [0x") and int(ins.op_str[13:-1], 16) in reg:
            thunks.add(ins.address)
    start = exp.get(b"ToolInit")
    if not start:
        continue
    regs, pushes = [], []
    for ins in insns:
        if ins.address < start or ins.address > start + 0x600:
            continue
        if ins.mnemonic == "push":
            pushes.append(ins.op_str)
        elif ins.mnemonic == "call":
            tgt = ins.op_str
            hit = (tgt.startswith("0x") and int(tgt, 16) in thunks) or any(f"{a:#x}" in tgt for a in reg)
            if hit:
                args = list(reversed(pushes[-5:]))
                h = args[2] if len(args) > 2 else "?"
                h = names.get(int(h, 16), h) if h.startswith("0x") else h
                regs.append(f"({args[0]},{args[1]},{h})")
            pushes = []
        elif ins.mnemonic == "ret":
            break
    print(path.split("/")[-1], " ".join(regs))
