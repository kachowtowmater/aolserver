"""Extract every zip local-file entry embedded in a blob (AOL DynaZip installers)."""
import struct, sys, zlib, os
src, out = sys.argv[1], sys.argv[2]
d = open(src, 'rb').read()
os.makedirs(out, exist_ok=True)
i, n = 0, 0
while (i := d.find(b'PK\x03\x04', i)) >= 0:
    ver, flag, meth, t, dt, crc, csz, usz, nl, xl = struct.unpack('<HHHHHIIIHH', d[i+4:i+30])
    name = d[i+30:i+30+nl].decode('latin1').replace('\\', '/')
    data = d[i+30+nl+xl:i+30+nl+xl+csz]
    i += 30 + nl + xl + csz
    if flag & 8 or not name or name.endswith('/'):
        continue
    raw = data if meth == 0 else zlib.decompress(data, -15) if meth == 8 else None
    if raw is None or zlib.crc32(raw) != crc:
        print('skip', name, 'method', meth); continue
    dst = os.path.join(out, os.path.normpath(name).lstrip('./'))
    if os.path.exists(dst) and open(dst, 'rb').read() != raw:
        dst += f'.{n}'
    os.makedirs(os.path.dirname(dst) or out, exist_ok=True)
    open(dst, 'wb').write(raw); n += 1
print(n, 'files')
