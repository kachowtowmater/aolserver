"""Parse FDO91 source text (the language AOL's forms are written in) into atoms.

    uni_start_stream <00x>
      man_start_object <ind_group, "Hello">
        act_replace_select_action
            <
            uni_start_stream
              sm_send_token_arg <"zA", 5>
            >

An atom is a name, optionally followed by <args>.  Args are comma separated; each is a
list of tokens (word, number, hex byte "1fx", gid "32-221"/"1-0-24836", "string",
"|").  An argument may itself be a nested atom stream (act_* atoms); the parser keeps
the raw tokens and the compiler decides by atom type.
"""
import re
from dataclasses import dataclass, field

TOKEN = re.compile(r'''
    (?P<ws>\s+)
  | (?P<comment>;[^\n]*)
  | (?P<str>"(?:[^"\\]|\\.)*")
  | (?P<gid>\d+-\d+(?:-\d+)?(?![\w-]))
  | (?P<hex>[0-9a-fA-F]{1,2}x(?![\w]))
  | (?P<num>-?\d+(?![\w-]))
  | (?P<word>[A-Za-z_][A-Za-z0-9_]*|[^\s<>,|"\d-][^\s<>,|"]*)
  | (?P<punct>[<>,|])
''', re.X)


@dataclass
class Tok:
    kind: str   # str gid hex num word punct
    text: str


@dataclass
class Atom:
    name: str
    args: list = field(default_factory=list)   # list of args; each arg = list[Tok | Atom-stream]
    has_args: bool = False


class ParseError(Exception):
    pass


def tokenize(src: str) -> list[Tok]:
    out, i = [], 0
    while i < len(src):
        m = TOKEN.match(src, i)
        if not m:
            raise ParseError(f"bad character {src[i]!r} at {i}: {src[max(0, i - 30):i + 30]!r}")
        i = m.end()
        if m.lastgroup != "ws":
            out.append(Tok(m.lastgroup, m.group()))
    return out


ESCAPES = {"r": 13, "t": 9, "n": 10, "\\": 92, '"': 34}


def _hexval(c: str) -> int:
    return int(c, 16) if c in "0123456789abcdefABCDEF" else 0


def unescape(s: str) -> bytes:
    """Body of an FDO string literal -> bytes, as AOL's compiler reads it: \\r \\t \\n \\\\ \\"
    and \\xNN (always the next two characters; a non-hex digit counts as 0)."""
    out, i = bytearray(), 0
    while i < len(s):
        c = s[i]
        if c == "\\":
            n = s[i + 1] if i + 1 < len(s) else ""
            if n == "x":
                out.append((_hexval(s[i + 2:i + 3] or "0") << 4 | _hexval(s[i + 3:i + 4] or "0")) & 0xFF)
                i += 4
                continue
            if n not in ESCAPES:
                raise ParseError(f"bad escape \\{n}")
            out.append(ESCAPES[n])
            i += 2
            continue
        out += c.encode("latin1", "replace")
        i += 1
    return bytes(out)


def parse(src: str) -> list[Atom]:
    toks = tokenize(src)
    atoms, pos = _stream(toks, 0, top=True)
    return atoms


def _stream(toks, pos, top=False):
    atoms = []
    while pos < len(toks):
        t = toks[pos]
        if t.kind == "punct" and t.text == ">" and not top:
            return atoms, pos
        if t.kind == "comment":
            # "; text" is itself an atom: hfs_attr_fdo_comment, the rest of the line verbatim
            atoms.append(Atom("hfs_attr_fdo_comment", [[Tok("raw", t.text[1:].rstrip("\r"))]], True))
            pos += 1
            continue
        if t.kind != "word":
            raise ParseError(f"expected atom name, got {t.text!r}")
        atom = Atom(t.text)
        pos += 1
        if pos < len(toks) and toks[pos].text == "<":
            atom.has_args = True
            atom.args, pos = _args(toks, pos + 1)
        atoms.append(atom)
    return atoms, pos


def _args(toks, pos):
    """Tokens up to the matching '>' split on top-level commas.  A nested '<' (only inside a
    nested atom stream) is kept balanced inside the current arg."""
    args, cur, depth = [], [], 0
    while pos < len(toks):
        t = toks[pos]
        if t.kind == "punct" and t.text == "<":
            depth += 1
        elif t.kind == "punct" and t.text == ">":
            if depth == 0:
                if cur or args:
                    args.append(cur)
                return args, pos + 1
            depth -= 1
        elif t.kind == "punct" and t.text == "," and depth == 0:
            args.append(cur)
            cur = []
            pos += 1
            continue
        cur.append(t)
        pos += 1
    raise ParseError("unterminated <")


def parse_tokens_as_stream(toks: list[Tok]) -> list[Atom]:
    atoms, pos = _stream(toks, 0, top=True)
    return atoms
