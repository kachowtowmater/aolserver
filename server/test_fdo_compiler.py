"""The pure-Python FDO compiler must produce exactly what AOL's own Ada32 compiler does.

The golden files (server/fdo/golden/) were made with the real Ada32 (tools/fdo_corpus.py
build), so these tests run anywhere without Wine.  Run: python3 test_fdo_compiler.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from fdo.pycompiler import CompileError, compile_source  # noqa: E402


def body(src: str) -> bytes:
    """Compile one atom inside a stream and return just that atom's bytes."""
    out = compile_source(f"uni_start_stream <00x>\n  {src}\nuni_end_stream <00x>")
    return out[4:-4]


def test_golden_corpus():
    import fdo_corpus
    total, failures = fdo_corpus.check(verbose=False)
    assert total > 1200 and not failures, failures[:5]


def test_full_style_atoms():
    assert compile_source("uni_start_stream <00x>\nuni_end_stream <00x>") == bytes.fromhex("00010100 00020100")
    assert body('man_start_object <ind_group, "Hi">') == bytes.fromhex("010003014869")
    assert body("mat_size <52, 3>") == bytes.fromhex("1017023403")


def test_numbers_are_minimal_big_endian_and_saturate():
    assert body("man_set_response_id <17>") == bytes.fromhex("01070111")
    assert body("man_set_response_id <300>") == bytes.fromhex("010702012c")
    assert body("man_set_response_id <70000>") == bytes.fromhex("01070301 1170".replace(" ", ""))
    assert body("var_number_set <A, 4294967295>") == bytes.fromhex("0c0105007fffffff")
    assert body("mat_size <30, 1, 40>") == bytes.fromhex("1017041e010028")   # 3rd size arg is 2 bytes


def test_gids():
    assert body("uni_invoke_local <32-5483>") == bytes.fromhex("001403 20156b".replace(" ", ""))
    assert body("mat_art_id <1-0-24836>") == bytes.fromhex("100e0401006104")
    assert body("man_preset_gid <0-0-5>") == bytes.fromhex("01160105")


def test_strings_and_escapes():
    assert body(r'man_append_data <"a\rb\tc\x41\"">') == b"\x01\x14\x07a\rb\tcA\""
    try:
        body(r'man_append_data <"bad \q">')
        assert False, "bad escape accepted"
    except CompileError:
        pass


def test_words_flags_and_atom_refs():
    assert body("mat_position <center_center>") == bytes.fromhex("10400105")
    assert body("mat_title_pos <above | 32>") == bytes.fromhex("10110160")
    assert body("mat_font_sis <arial, 9, italic | bold>") == bytes.fromhex("100a03000903")
    assert body("man_get_attribute <mat_value>") == bytes.fromhex("01400210 33".replace(" ", ""))
    assert body("var_number_set <B, 1>") == bytes.fromhex("0c01020101")


def test_tokens_nested_streams_and_high_protocols():
    assert body('sm_send_token_arg <"zA", 300>') == bytes.fromhex("0e0c047a41012c")
    nested = body('act_replace_select_action\n  <\n  uni_start_stream\n    sm_send_token_raw <"CJ">\n  >')
    assert nested == bytes.fromhex("020408" + "000100" + "0e1002434a")
    assert body('www_browse <"http://x">') == bytes.fromhex("e8100f08") + b"http://x"
    assert body("; note") == bytes.fromhex("e8132405") + b" note"


def test_long_lengths():
    assert body(f'man_append_data <"{"A" * 200}">')[:4] == bytes.fromhex("011480c8")


if __name__ == "__main__":
    failed = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print(f"ok    {name}")
            except Exception as e:
                failed += 1
                import traceback
                traceback.print_exc()
                print(f"FAIL  {name}: {e!r}")
    print("all passed" if not failed else f"{failed} failed")
    sys.exit(1 if failed else 0)
