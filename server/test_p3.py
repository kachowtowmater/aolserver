import asyncio

import p3
import server


def test_roundtrip():
    f = p3.Frame(0x10, 0x7F, p3.DATA, b"Dd\x00\x01hello")
    raw = p3.encode(f)
    assert raw[-1] == 0x0D and int.from_bytes(raw[3:5], "big") == len(f.payload) + 3
    out, n = p3.try_decode(bytearray(raw))
    assert n == len(raw) and out.crc_ok and out.token == b"Dd" and out.stream == 1 and out.payload == f.payload


def test_partial_and_junk():
    raw = p3.encode(p3.Frame(1, 2, p3.ACK))
    assert p3.try_decode(bytearray(raw[:-1])) == (None, 0)
    assert p3.try_decode(bytearray(b"xx" + raw)) == (None, 2)


def test_crc_known_vector():
    assert p3.crc16(b"123456789") == 0xBB3D  # CRC-16/ARC check value


def test_seq_wrap():
    assert p3.next_seq(127) == 16 and p3.next_seq(16) == 17


def test_handshake_over_tcp():
    async def run():
        srv = await asyncio.start_server(lambda r, w: server.Link(r, w).run(), "127.0.0.1", 0)
        port = srv.sockets[0].getsockname()[1]
        r, w = await asyncio.open_connection("127.0.0.1", port)
        # what AOLP3 sends: type | 0x80, seq 127/127
        w.write(p3.encode(p3.Frame(127, 127, p3.INIT | 0x80, b"\x00" * 4)))
        f, _ = p3.try_decode(bytearray(await asyncio.wait_for(r.read(64), 2)))
        assert f.type == p3.ACK and f.crc_ok
        w.write(p3.encode(p3.Frame(16, 127, p3.DATA | 0x80, b"Dd\x00\x01")))
        f, _ = p3.try_decode(bytearray(await asyncio.wait_for(r.read(64), 2)))
        assert f.type == p3.ACK and f.rx == 16
        w.close(); srv.close()
    asyncio.run(run())


def test_aol4_no_crc_marker():
    raw = bytearray(p3.encode(p3.Frame(16, 127, p3.DATA | 0x80, b"Wh\x00\x01")))
    raw[1:3] = b"**"
    f, n = p3.try_decode(raw)
    assert f.crc_ok and f.token == b"Wh" and n == len(raw)
