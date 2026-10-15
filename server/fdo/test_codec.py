from fdo import codec


def test_hello_world_matches_reference():
    # compiled example from deceptio.org/re/fdo
    ref = bytes.fromhex("0001000D070C0148656C6C6F20576F726C64000200")
    assert codec.stream(codec.atom("async_alert", b"\x01Hello World")) == ref
    names = [a.name for a in codec.decode(ref)]
    assert names == ["uni_start_stream", "async_alert", "uni_end_stream"]


def test_decode_client_signon_form():
    data = bytes.fromhex("000100010a0400000001010b0400000001030 10a4e6577205573657220200 11d00011d00".replace(" ", ""))
    got = [repr(a) for a in codec.decode(data)]
    assert got[3] == "de_data <'New User  '>" and got[-1] == "man_end_context"


def test_compact_styles():
    # 0x72 = style 3 (atom), num 18, protocol carried over from previous atom
    atoms = codec.decode(bytes.fromhex("015A0161") + b"\x72")
    assert atoms[1].proto == 1 and atoms[1].num == 18 and atoms[1].args == b""


def test_split_on_atom_boundaries():
    data = codec.stream(*[codec.atom("idb_append_data", bytes(300)) for _ in range(5)])
    parts = codec.split(data, 700)
    assert b"".join(parts) == data and len(parts) > 1
    for p in parts:
        assert codec.decode(p)  # every chunk is whole atoms
