"""Tiny stdlib GIF writer (uncompressed-LZW trick) for placeholder art.

Always writes an 8-bit (256-entry) global palette and LZW min code size 8,
like the GIFs in AOL's own art database -- the 3.0 client's GIF filter
rejects smaller palettes ("image ... could not be decompressed").
"""


def encode(width: int, height: int, palette: list[tuple[int, int, int]], pixels: list[int]) -> bytes:
    pal = (palette + [(0, 0, 0)] * 256)[:256]
    head = b"GIF87a" + width.to_bytes(2, "little") + height.to_bytes(2, "little") + bytes([0xF7, 0, 0])
    head += b"".join(bytes(c) for c in pal)
    img = b"\x2c" + bytes(4) + width.to_bytes(2, "little") + height.to_bytes(2, "little") + b"\x00"
    # min code size 8: clear=256, end=257, 9-bit codes; a clear every 250 pixels
    # keeps the dictionary below 512 entries so the width never grows.
    bits, nbits, out = 0, 0, bytearray()

    def put(code):
        nonlocal bits, nbits
        bits |= code << nbits
        nbits += 9
        while nbits >= 8:
            out.append(bits & 0xFF)
            bits >>= 8
            nbits -= 8

    for i, p in enumerate(pixels):
        if i % 250 == 0:
            put(256)
        put(p)
    put(257)
    if nbits:
        out.append(bits & 0xFF)
    blocks = b"".join(bytes([len(out[i:i + 255])]) + bytes(out[i:i + 255]) for i in range(0, len(out), 255))
    return head + img + b"\x08" + blocks + b"\x00\x3b"


def placeholder(size: int = 32) -> bytes:
    """Bevelled AOL-blue square, like a generic 1996 toolbar button."""
    pal = [(0, 0, 128), (255, 255, 255), (128, 128, 128), (51, 102, 204)]
    px = []
    for y in range(size):
        for x in range(size):
            if x == 0 or y == 0:
                px.append(1)
            elif x == size - 1 or y == size - 1:
                px.append(2)
            else:
                px.append(3)
    return encode(size, size, pal, px)
