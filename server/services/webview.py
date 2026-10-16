"""The World Wide Web, drawn in an AOL window: no IE, no Wine Gecko.

AOL 4.0's own browser window is Internet Explorer's engine; under Wine that is Wine Gecko 2.47,
which only works on the first thread that used it (AOL runs each browser window on its own
thread) and crashes navigating within a window under x86 emulation.  So the host browses
instead: a headless modern Chrome (driven over the DevTools protocol) loads the page, and the
member gets an AOL window holding a picture of it (JPEG art, format 7, as AOL's own art) with
every visible link laid over it as a picture button cut from the same image -- click one and
the host follows it and redraws.  Back / Forward / Reload / Home / Page Up / Page Down, an
address box (a URL, or words to search), and a status line, like the 4.0 browser.

One Chrome process for the host, one tab per member who browses (closed when they sign off).
AOL_WEBVIEW=0 turns it off (the 4.0 client's own IE window is used again).
"""
import base64
import json
import os
import random
import shutil
import socket
import struct
import subprocess
import threading
import time
import urllib.request
from pathlib import Path
from urllib.parse import quote_plus, urlparse

ENABLED = os.environ.get("AOL_WEBVIEW", "1") != "0"
HOME = "https://www.aol.com/"
VIEW_W, VIEW_H = 760, 440          # page picture, pixels
PORT = int(os.environ.get("AOL_WEBVIEW_PORT", "9333"))
PROFILE = Path(__file__).resolve().parent.parent / "var" / "webview-chrome"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/140.0.0.0 Safari/537.36")
MAX_LINKS = 120
SLOTS = 16                          # pages of art kept in the client (rotating ids 1-200-*)
WINDOW = "webview"

_chrome_lock = threading.Lock()
_chrome = None                      # subprocess.Popen


# ---------- a minimal WebSocket client (RFC 6455), enough for the DevTools protocol ----------

class WebSocket:
    def __init__(self, url: str, timeout: float = 30):
        u = urlparse(url)
        self.sock = socket.create_connection((u.hostname, u.port or 80), timeout=timeout)
        key = base64.b64encode(os.urandom(16)).decode()
        path = u.path + (f"?{u.query}" if u.query else "")
        self.sock.sendall((f"GET {path} HTTP/1.1\r\nHost: {u.hostname}:{u.port}\r\nUpgrade: websocket\r\n"
                           f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
        head = b""
        while b"\r\n\r\n" not in head:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise ConnectionError("websocket handshake failed")
            head += chunk
        if b" 101 " not in head.split(b"\r\n", 1)[0]:
            raise ConnectionError(head.split(b"\r\n", 1)[0].decode("latin1"))
        self.buf = head.split(b"\r\n\r\n", 1)[1]

    def send(self, text: str):
        data = text.encode()
        n = len(data)
        hdr = bytes([0x81])
        if n < 126:
            hdr += bytes([0x80 | n])
        elif n < 65536:
            hdr += bytes([0x80 | 126]) + struct.pack(">H", n)
        else:
            hdr += bytes([0x80 | 127]) + struct.pack(">Q", n)
        mask = os.urandom(4)
        self.sock.sendall(hdr + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(data)))

    def _read(self, n: int) -> bytes:
        while len(self.buf) < n:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise ConnectionError("websocket closed")
            self.buf += chunk
        out, self.buf = self.buf[:n], self.buf[n:]
        return out

    def recv(self) -> str:
        msg = b""
        while True:
            b1, b2 = self._read(2)
            op, n = b1 & 0x0F, b2 & 0x7F
            if n == 126:
                n = struct.unpack(">H", self._read(2))[0]
            elif n == 127:
                n = struct.unpack(">Q", self._read(8))[0]
            mask = self._read(4) if b2 & 0x80 else None
            data = self._read(n)
            if mask:
                data = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
            if op == 8:
                raise ConnectionError("websocket closed by peer")
            if op == 9:  # ping -> pong
                self.sock.sendall(bytes([0x8A, 0x80 | len(data)]) + bytes(4) + data)
                continue
            if op in (0, 1, 2):
                msg += data
                if b1 & 0x80:
                    return msg.decode("utf-8", "replace")

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


class Tab:
    """One Chrome page, driven over its DevTools websocket."""

    def __init__(self, target: dict):
        self.id = target["id"]
        self.ws = WebSocket(target["webSocketDebuggerUrl"])
        self.seq = 0
        self.events = []
        self.lock = threading.Lock()
        self.offset = 0               # scroll position shown
        self.call("Page.enable")
        self.call("Network.enable")
        self.call("Network.setUserAgentOverride", userAgent=UA)
        self.call("Emulation.setDeviceMetricsOverride", width=VIEW_W, height=VIEW_H,
                  deviceScaleFactor=1, mobile=False)

    def call(self, method, timeout=30, **params):
        self.seq += 1
        mid = self.seq
        self.ws.send(json.dumps({"id": mid, "method": method, "params": params}))
        end = time.time() + timeout
        while time.time() < end:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == mid:
                if "error" in msg:
                    raise RuntimeError(f"{method}: {msg['error'].get('message')}")
                return msg.get("result", {})
            if "method" in msg:
                self.events.append(msg["method"])
        raise TimeoutError(method)

    def wait_load(self, timeout=15):
        """Until the page fires load or finishes navigating (or timeout)."""
        done = {"Page.loadEventFired", "Page.frameStoppedLoading"}
        self.ws.sock.settimeout(1.0)
        end = time.time() + timeout
        try:
            while time.time() < end:
                if done & set(self.events):
                    break
                try:
                    msg = json.loads(self.ws.recv())
                except (socket.timeout, TimeoutError):
                    continue
                if "method" in msg:
                    self.events.append(msg["method"])
        finally:
            self.ws.sock.settimeout(30)
        time.sleep(1.0)  # let late layout and images settle

    def eval(self, js):
        r = self.call("Runtime.evaluate", expression=js, returnByValue=True)
        return r.get("result", {}).get("value")

    def close(self):
        self.ws.close()
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/close/{self.id}", timeout=5).read()
        except OSError:
            pass


# ---------- Chrome ----------

def find_browser():
    for name in ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable", "chrome", "msedge"):
        if p := shutil.which(name):
            return p
    for p in (r"C:\Program Files\Google\Chrome\Application\chrome.exe",
              r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
              r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
              "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
              "/Applications/Chromium.app/Contents/MacOS/Chromium"):
        if Path(p).exists():
            return p
    return None


def _devtools(path, method="GET"):
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}{path}", method=method)
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.loads(r.read())


def ensure_chrome():
    global _chrome
    with _chrome_lock:
        try:
            _devtools("/json/version")
            return
        except OSError:
            pass
        exe = find_browser()
        if not exe:
            raise RuntimeError("No Chrome, Chromium or Edge is installed on the host.")
        PROFILE.mkdir(parents=True, exist_ok=True)
        _chrome = subprocess.Popen(
            [exe, "--headless=new", f"--remote-debugging-port={PORT}", "--remote-allow-origins=*",
             f"--user-data-dir={PROFILE}", "--no-first-run", "--no-default-browser-check", "--disable-gpu",
             "--hide-scrollbars", "--mute-audio", f"--window-size={VIEW_W},{VIEW_H}", "about:blank"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(60):
            try:
                _devtools("/json/version")
                return
            except OSError:
                time.sleep(0.25)
        raise RuntimeError("Chrome didn't start.")


def tab_for(link) -> Tab:
    tab = link.session.get("webview_tab")
    if tab:
        return tab
    ensure_chrome()
    tab = Tab(_devtools("/json/new?about:blank", method="PUT"))
    link.session["webview_tab"] = tab
    return tab


def on_disconnect(link):
    tab = link.session.pop("webview_tab", None)
    if tab:
        threading.Thread(target=tab.close, daemon=True).start()


# ---------- reading a page ----------

LINKS_JS = """(() => {
  const out = [], seen = new Set();
  const W = innerWidth, H = innerHeight;
  for (const a of document.querySelectorAll('a[href], area[href], button, input[type=submit]')) {
    const href = a.href || '';
    if (a.tagName === 'A' && (!href || href.startsWith('javascript:'))) continue;
    for (const r of a.getClientRects()) {
      const x = Math.max(0, Math.floor(r.left)), y = Math.max(0, Math.floor(r.top));
      const w = Math.min(W, Math.ceil(r.right)) - x, h = Math.min(H, Math.ceil(r.bottom)) - y;
      if (w < 6 || h < 6 || x >= W || y >= H) continue;
      const k = x + ',' + y + ',' + w + ',' + h;
      if (seen.has(k)) continue;
      seen.add(k);
      out.push({x, y, w, h, href, tag: a.tagName, text: (a.innerText || a.value || a.title || '').trim().slice(0, 60)});
      break;
    }
  }
  return {links: out, title: document.title, url: location.href,
          height: document.documentElement.scrollHeight, y: scrollY};
})()"""


def snapshot(tab: Tab):
    """Picture of the visible part of the page + its links (coordinates in the picture)."""
    tab.eval(f"scrollTo(0, {tab.offset})")
    time.sleep(0.3)
    info = tab.eval(LINKS_JS) or {"links": [], "title": "", "url": "", "height": VIEW_H, "y": 0}
    tab.offset = info.get("y", 0)
    shot = tab.call("Page.captureScreenshot", format="jpeg", quality=55)["data"]
    links = [l for l in info["links"] if l["href"] or l["tag"] in ("BUTTON", "INPUT")][:MAX_LINKS]
    crops = []
    for l in links:
        c = tab.call("Page.captureScreenshot", format="jpeg", quality=60,
                     clip={"x": l["x"], "y": l["y"] + tab.offset, "width": l["w"], "height": l["h"], "scale": 1})
        crops.append(base64.b64decode(c["data"]))
    return base64.b64decode(shot), links, crops, info


def go(tab: Tab, url: str):
    tab.events.clear()
    tab.offset = 0
    tab.call("Page.navigate", url=url)
    tab.wait_load()


def normalize(text: str) -> str:
    t = text.strip()
    if t.lower().startswith(("http://", "https://")):
        return t
    host = t.split("/", 1)[0]
    if " " not in t and "." in host.strip(".") and host.rsplit(".", 1)[-1].isalpha():
        return "https://" + t
    return "https://duckduckgo.com/html/?q=" + quote_plus(t)


# ---------- the AOL window ----------

def jpeg_record(img: bytes, w: int, h: int) -> bytes:
    """AOL art record for a JPEG (format 7), laid out like the JPEG art on AOL's CDs."""
    total = 40 + len(img)
    return (b"\x01\x00\x01\x00\x02\x00" + (total - 4).to_bytes(4, "little") + bytes(4) + bytes([7, 2])
            + w.to_bytes(2, "little") + h.to_bytes(2, "little") + bytes(2) + len(img).to_bytes(4, "little")
            + (0x24).to_bytes(4, "little") + bytes(10) + img)


def push_art(link, art_id: str, rec: bytes):
    from fdo.codec import atom, stream
    t, sub, i = (int(p) for p in art_id.split("-"))
    link.send_stream(stream(atom("idb_start_obj", b"p"), atom("idb_atr_globalid", bytes([t, sub]) + i.to_bytes(2, "big")),
                            *[atom("idb_append_data", rec[k:k + 900]) for k in range(0, len(rec), 900)],
                            atom("idb_end_obj")))


def _trigger(label, x, y, w, h, n, art=None):
    lines = [f'    man_start_sibling <trigger, "{label}">',
             f"      mat_precise_x <{x}>", f"      mat_precise_y <{y}>",
             f"      mat_precise_width <{w}>", f"      mat_precise_height <{h}>"]
    if art:
        lines += ["      mat_trigger_style <plain_picture>", f"      mat_art_id <{art}>"]
    lines += ["      act_replace_select_action", "        <", "        uni_start_stream_wait_on <00x>",
              f'        sm_send_token_arg <"zA", {n}>', "        >"]
    return lines


def render(link, shot: bytes, links: list, crops: list, info: dict, status: str = ""):
    from . import screens
    from .areas import _item
    from .util import fdo_text
    slot = link.session.get("webview_slot", random.randrange(SLOTS))
    slot = (slot + 1) % SLOTS
    link.session["webview_slot"] = slot
    base = slot * 256
    push_art(link, f"1-200-{base}", jpeg_record(shot, VIEW_W, VIEW_H))
    for i, (l, c) in enumerate(zip(links, crops), start=1):
        push_art(link, f"1-200-{base + i}", jpeg_record(c, l["w"], l["h"]))

    url = info.get("url") or ""
    link.session["webview_url"] = url
    pad, top = 8, 34
    nav = [("Back", "back"), ("Forward", "forward"), ("Reload", "reload"), ("Home", "home"),
           ("Page Up", "pgup"), ("Page Down", "pgdn")]
    lines = ['  man_start_object <ind_group, "World Wide Web">',
             "    mat_bool_precise <yes>", "    mat_position <center_center>",
             "    mat_color_face <255, 251, 240>",
             f"    mat_precise_width <{VIEW_W + 2 * pad}>",
             f"    mat_precise_height <{top + VIEW_H + 30}>",
             '    man_start_object <ornament, "">',
             f"      mat_precise_x <{pad}>", f"      mat_precise_y <{top}>",
             f"      mat_precise_width <{VIEW_W}>", f"      mat_precise_height <{VIEW_H}>",
             f"      mat_art_id <1-200-{base}>"]
    x = pad
    for label, act in nav:
        w = 62 if " " not in label else 74
        lines += _trigger(label, x, 6, w, 22, _item(link, ("webview", act)))
        x += w + 4
    # address box + Go: the typed text goes to the host as zG
    lines += ['    man_start_sibling <edit_view, "">',
              f"      mat_precise_x <{x + 6}>", "      mat_precise_y <7>",
              f"      mat_precise_width <{VIEW_W + pad - x - 6 - 40}>", "      mat_precise_height <20>",
              "      mat_relative_tag <1>", "      mat_bool_writeable <yes>",
              f'      man_append_data <"{fdo_text(url[:250])}">',
              '    man_start_sibling <trigger, "Go">',
              f"      mat_precise_x <{VIEW_W + pad - 36}>", "      mat_precise_y <6>",
              "      mat_precise_width <36>", "      mat_precise_height <22>", "      mat_bool_default <yes>",
              "      act_replace_select_action",
              "          <\n          uni_start_stream\n            de_start_extraction\n"
              '            buf_set_token <"zG">\n            man_set_context_relative <1>\n'
              "            de_get_data\n            man_end_context\n            de_end_extraction\n"
              "            buf_close_buffer\n          uni_end_stream\n          >"]
    for i, l in enumerate(links, start=1):
        target = ("webview", "link", l["href"]) if l["href"] else ("webview", "click", l["x"], l["y"])
        lines += _trigger("", pad + l["x"], top + l["y"], l["w"], l["h"], _item(link, target), f"1-200-{base + i}")
    total_h = max(info.get("height") or VIEW_H, VIEW_H)
    page = f"page {tab_page(link)} of {max(1, -(-total_h // VIEW_H))}"
    title = (info.get("title") or url)[:70]
    lines += ['    man_start_sibling <view, "">',
              f"      mat_precise_x <{pad}>", f"      mat_precise_y <{top + VIEW_H + 6}>",
              f"      mat_precise_width <{VIEW_W}>", "      mat_precise_height <18>",
              f'      man_append_data <"{fdo_text((status or title) + "   (" + page + ")")}">', "      man_end_data",
              "    man_end_object"]
    link.send_stream(screens._wrap("\n".join(lines), None, WINDOW))


def tab_page(link):
    tab = link.session.get("webview_tab")
    return (tab.offset // (VIEW_H - 40) + 1) if tab else 1


def alert_error(link, text):
    from .util import alert
    from fdo.codec import atom, stream
    link.send_stream(stream(atom("uni_wait_off")))
    alert(link, text)


def run(link, work, status=""):
    """work(tab) runs on a worker thread under the member's tab lock, then we redraw."""
    from .util import run_bg

    def job():
        tab = tab_for(link)
        with tab.lock:
            work(tab)
            return snapshot(tab)

    def done(result):
        if isinstance(result, Exception) or result is None:
            return alert_error(link, "This Web page is not available right now.  Please try again later.")
        render(link, *result, status=status)

    def safe():
        try:
            return job()
        except ConnectionError as e:
            print(f"      webview: {e!r}")
            tab = link.session.pop("webview_tab", None)
            if tab:
                tab.close()
            return e
        except Exception as e:  # noqa: BLE001 -- shown to the member as an AOL message
            print(f"      webview: {e!r}")
            return e
    run_bg(safe, done)


# ---------- entry points ----------

def open_url(link, url: str):
    run(link, lambda tab: go(tab, normalize(url)))


def action(link, payload):
    """zA from the viewer: ("webview", what, ...)."""
    what = payload[1]
    if what == "link":
        return run(link, lambda tab: go(tab, payload[2]))
    if what == "click":  # a button without a URL: click it in the page
        x, y = payload[2], payload[3]

        def click(tab):
            tab.events.clear()
            for kind in ("mousePressed", "mouseReleased"):
                tab.call("Input.dispatchMouseEvent", type=kind, x=x + 2, y=y + 2, button="left", clickCount=1)
            tab.wait_load(timeout=4)
        return run(link, click)
    if what in ("back", "forward"):
        def hist(tab):
            h = tab.call("Page.getNavigationHistory")
            step = -1 if what == "back" else 1
            i = h["currentIndex"] + step
            while 0 <= i < len(h["entries"]):
                if h["entries"][i]["url"] not in ("about:blank", ""):
                    break
                i += step
            else:
                return
            tab.events.clear()
            tab.offset = 0
            tab.call("Page.navigateToHistoryEntry", entryId=h["entries"][i]["id"])
            tab.wait_load()
        return run(link, hist)
    if what == "reload":
        def reload(tab):
            tab.events.clear()
            tab.call("Page.reload")
            tab.wait_load()
        return run(link, reload)
    if what == "home":
        return run(link, lambda tab: go(tab, HOME))
    if what in ("pgup", "pgdn"):
        def scroll(tab):
            tab.offset = max(0, tab.offset + (VIEW_H - 40) * (1 if what == "pgdn" else -1))
        return run(link, scroll)


def typed(link, stream_id, body):
    """zG: the address box."""
    from .util import request
    text = (request(body)["texts"] or [""])[0].strip()
    if text:
        open_url(link, text)


TOKENS = {b"zG": typed}
