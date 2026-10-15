"""Keywords and areas: Kk (keyword), K1/k1/f1 (go to area / fetch form by GID).

The 1997 navigation is kept exactly (toolbar, Channels screen, Keyword box);
what's behind each area is live 2026 content.
"""
import time
from datetime import datetime

from fdo.codec import atom, gid, stream

from . import art, chat, content, screens
from .util import alert, name_of, request, run_bg

# Channel / toolbar GIDs from the client's own Channels (32-5483) and toolbar (32-4650) forms.
GID_AREAS = {
    "40-37744": "news", "32-2573": "news", "4-63721": "newsstand", "4-63695": "finance", "40-5000": "sports",
    "32-2576": "entertainment", "4-63698": "computing", "17-38822": "digital city", "40-25114": "games",
    "17-38830": "health", "40-38978": "the hub", "17-37981": "international", "32-4728": "internet",
    "4-63731": "kids only", "4-63727": "learning", "4-63697": "lifestyles", "4-63720": "marketplace",
    "17-35616": "musicspace", "4-63728": "reference", "40-39017": "style", "17-38784": "travel",
    "17-35059": "presenting", "40-4218": "member services", "40-3760": "aol live", "40-4408": "my aol",
    "17-35044": "find", "3-4604": "what's hot", "19-7766": "www",
    "8-62": "room:Center Stage", "8-20": "room:PC Studio",
    "17-22746": "buddy list", "17-21293": "buddy setup",
    "8-11975": "file search", "8-63415": "finance", "8-16035": "clock", "": "what's hot",
    "40-25172": "member directory", "40-4391": "mail", "8-53727": "news search", "32-322": "find",
    "2-15919": "parental control", "32-1163": "internet mail", "2-43263": "internet mail", "2-1921": "news",
    "32-384": "screen names",
}

import json as _json
from pathlib import Path as _Path

_CHANNEL_ART = _json.loads((_Path(__file__).resolve().parent.parent / "data" / "channel_art.json").read_text())
# each area wears the banner its button has on the client's own Channels screen
AREA_ART = {}
for _g, _a in GID_AREAS.items():
    if _g in _CHANNEL_ART:
        AREA_ART.setdefault(_a, _CHANNEL_ART[_g])
AREA_ART.setdefault("what's hot", AREA_ART.get("news"))
AREA_ART.setdefault("business", AREA_ART.get("finance"))

NEWS_AREAS = {  # area -> (window title, intro, feed topic)
    "news": ("Today's News", "Top stories, updated around the clock.", "top"),
    "newsstand": ("Newsstand", "The day's papers and magazines.", "us"),
    "international": ("International", "News from around the world.", "world"),
    "sports": ("Sports", "Scores, stories and standings.", "sports"),
    "entertainment": ("Entertainment", "Movies, TV, music and the arts.", "entertainment"),
    "computing": ("Computers & Software", "Technology news.", "tech"),
    "the hub": ("The Hub", "What's new and what's next.", "tech"),
    "health": ("Health & Fitness", "Health news and advice.", "health"),
    "games": ("Games", "Gaming news.", "games"),
    "learning": ("Learning & Culture", "Education, science and culture.", "education"),
    "kids only": ("Kids Only", "Science and discovery.", "science"),
    "musicspace": ("MusicSpace", "New music and reviews.", "music"),
    "style": ("Style Channel", "Fashion and style.", "style"),
    "travel": ("Travel", "Destinations and travel news.", "travel"),
    "lifestyles": ("Life, Styles & Interests", "People, places and pastimes.", "style"),
    "what's hot": ("What's Hot", "The most talked-about stories right now.", "top"),
    "presenting": ("Presenting...", "Featured stories.", "entertainment"),
    "business": ("Business News", "Markets, companies and the economy.", "business"),
    "marketplace": ("Marketplace", "Today's best deals from around the Web.", "deals"),
}

KEYWORDS = {  # keyword -> area (case/space-insensitive)
    **{k: k for k in NEWS_AREAS}, "top news": "news", "todays news": "news", "today's news": "news",
    "world": "international", "tech": "computing", "computers": "computing", "computing": "computing",
    "stocks": "finance", "quotes": "finance", "quote": "finance", "personal finance": "finance",
    "money": "finance", "finance": "finance", "weather": "weather", "time": "clock", "clock": "clock",
    "online clock": "clock", "chat": "people connection", "people connection": "people connection",
    "pc": "people connection", "lobby": "people connection", "channels": "channels", "welcome": "welcome",
    "help": "member services", "member services": "member services", "business": "business",
    "web": "www", "www": "www", "internet": "www", "browser": "www", "search": "find", "find": "find",
    "reference": "reference", "encyclopedia": "reference", "wikipedia": "reference", "files": "file search",
    "file search": "file search", "software": "file search", "download": "file search", "shopping": "marketplace",
    "deals": "marketplace", "my aol": "my aol", "aol live": "aol live", "live": "aol live",
    "mail": "mail", "read mail": "mail", "mailbox": "mail", "new mail": "mail",
    "boards": "boards", "message boards": "boards", "board": "boards", "bbs": "boards",
    "buddy": "buddy list", "buddies": "buddy list", "buddy list": "buddy list", "buddy view": "buddy list",
}


def _norm(word: str) -> str:
    return " ".join(word.lower().replace("_", " ").split())


def _session_items(link):
    return link.session.setdefault("items", {})


def _item(link, payload) -> int:
    items = _session_items(link)
    n = 1 + (link.session.get("item_seq", 0) % 250)
    link.session["item_seq"] = n
    items[n] = payload
    return n


# ---------- areas ----------

def news_area(link, area: str, rid=None):
    title, intro, topic = NEWS_AREAS[area]

    def done(items):
        if not items:
            return link.send_stream(screens.text_window(title, "This area is temporarily unavailable.", rid))
        rows = [(f"{h['title']}", _item(link, ("article", h))) for h in items]
        when = datetime.now().strftime("%A, %B %-d, %Y  %-I:%M %p")
        art.ensure_art(link, [AREA_ART[area]] if AREA_ART.get(area) else [])
        link.send_stream(screens.list_window(title, f"{intro}  {when}.  Double-click a headline to read it.",
                                             rows, response_id=rid, art=AREA_ART.get(area), window=area))
    run_bg(lambda: content.headlines(topic, 25), done)


def show_article(link, h):
    parts = [h["title"], "", h["summary"] or "(No summary available.)", ""]
    if h.get("source"):
        parts.append(f"Source: {h['source']}")
    if h.get("date"):
        parts.append(h["date"])
    if h.get("link"):
        parts += ["", h["link"]]
    link.send_stream(screens.text_window(h["title"][:60], "\r".join(parts)))


def _fmt_quote(q) -> str:
    arrow = "+" if q["change"] >= 0 else ""
    return f"{q['symbol']:<8} {q['price']:>12,.2f}  {arrow}{q['change']:,.2f} ({arrow}{q['pct']:.2f}%)  {q['name']}"


def finance_area(link, rid=None):
    idx = [("^DJI", "Dow Jones"), ("^GSPC", "S&P 500"), ("^IXIC", "Nasdaq"), ("^RUT", "Russell 2000"),
           ("CL=F", "Crude Oil"), ("GC=F", "Gold"), ("BTC-USD", "Bitcoin"), ("EURUSD=X", "Euro")]

    def work():
        return [(name, content.quote(sym)) for sym, name in idx]

    def done(rows):
        lines = [f"{name:<14} {q['price']:>12,.2f}  {'+' if q['change'] >= 0 else ''}{q['change']:,.2f} "
                 f"({'+' if q['pct'] >= 0 else ''}{q['pct']:.2f}%)" for name, q in rows if q]
        intro = "Market summary  " + datetime.now().strftime("%-I:%M %p %b %-d") + "\r" + "\r".join(lines)
        link.send_stream(screens.list_window(
            "Personal Finance", intro, art=AREA_ART.get("finance"), window="finance", items= [("Business news", _item(link, ("area", "business")))],
            buttons=[("Stock Quotes", '          sm_send_token_arg <"zA", %d>' % _item(link, ("quote_box",)))],
            response_id=rid, width=56))
    run_bg(work, done)


def quote_box(link):
    link.send_stream(screens.input_window("Stock Quotes", "Symbol:", "Get Quote", "zQ",
                                          "Enter a ticker symbol (for example AAPL, MSFT or ^DJI)."))


def get_quote(link, stream_id, body):
    sym = (request(body)["texts"] or [""])[0].strip()
    if not sym:
        return

    def done(q):
        if not q:
            return alert(link, f"No quote found for {sym}.")
        link.send_stream(screens.text_window(f"Quote: {q['symbol']}", _fmt_quote(q) + "\r\rQuotes delayed.",
                                             width=64, height=4))
    run_bg(lambda: content.quote(sym), done)


def weather_box(link, rid=None):
    link.send_stream(screens.input_window("Weather", "City:", "Get Forecast", "zW",
                                          "Get today's weather and a 5-day forecast.", response_id=rid))


def get_weather(link, stream_id, body):
    place = (request(body)["texts"] or [""])[0].strip()
    if not place:
        return

    def done(w):
        if not w or "error" in w:
            return alert(link, (w or {}).get("error", "Weather is temporarily unavailable."))
        c, d = w["current"], w["daily"]
        lines = [w["place"], "", f"Now: {content.WMO.get(c['weather_code'], '')}, {c['temperature_2m']:.0f} F, "
                 f"humidity {c['relative_humidity_2m']}%, wind {c['wind_speed_10m']:.0f} mph", "", "Forecast:"]
        for day, code, hi, lo in zip(d["time"], d["weather_code"], d["temperature_2m_max"], d["temperature_2m_min"]):
            lines.append(f"{datetime.fromisoformat(day).strftime('%a %b %-d')}:  "
                         f"{content.WMO.get(code, ''):<14} High {hi:.0f}  Low {lo:.0f}")
        link.send_stream(screens.text_window(f"Weather: {w['place']}", "\r".join(lines), width=56, height=12))
    run_bg(lambda: content.weather(place), done)


def clock(link, rid=None):
    mins = int((time.time() - link.session.get("signed_on", time.time())) // 60)
    alert(link, datetime.now().strftime("It's %A, %B %-d, %Y %-I:%M %p.  ")
          + f"You have been online for {mins} minute{'s' if mins != 1 else ''}.")
    link.send_stream(stream(atom("uni_wait_off")))


INFO = {
    "parental control": ("Parental Controls", [
        "Parental Controls let you decide where your family can go online.", "",
        "On this host every member is a grown-up, so there is nothing to set.  "
        "Chat regulars in the People Connection are computer-generated."]),
    "internet mail": ("Internet Mail", [
        "Mail between members works right now: just address it to a screen name.", "",
        "Sending mail to Internet addresses (name@domain.com) is coming soon."]),
    "screen names": ("Screen Names", [
        "To create a new screen name, sign off, choose New User on the Welcome screen and sign on.  "
        "You'll be asked to pick your screen name and password."]),
    "member services": ("Member Services", [
        "Welcome to Member Services.", "",
        "This America Online host was rebuilt from scratch in 2026 for the original AOL 3.0 for Windows 95 "
        "software.  Everything you see is the real 1997 client; the content behind it is live.", "",
        "GETTING AROUND", "  Keyword (Ctrl+K): type a keyword such as NEWS, STOCKS, WEATHER, SPORTS, WEB, "
        "REFERENCE, FILES, CHAT or TIME.", "  Channels: browse every area by subject.",
        "  People Connection: chat live in the lobbies and public rooms.",
        "  Instant Messages (Ctrl+I): talk privately with anyone signed on.", "",
        "THE WORLD WIDE WEB", "  Keyword WEB lets you visit any 2026 Web page as plain text, or search the Web.",
        "", "Have fun, and remember: you've got mail!"]),
    "aol live": ("AOL Live!", [
        "AOL Live! -- events in the People Connection auditoriums.", "",
        "Center Stage: open chat all day.  Go there from any chat room with the Center Stage button.",
        "PC Studio: hang out with the regulars.", "",
        "Today's hot topics in the lobbies come straight from the day's headlines."]),
}


def info_area(link, area, rid=None):
    title, lines = INFO[area]
    link.send_stream(screens.text_window(title, "\r".join(lines), rid, width=60, height=14))


def my_aol(link, rid=None):
    name = name_of(link)
    mins = int((time.time() - link.session.get("signed_on", time.time())) // 60)
    rows = [("Today's News", _item(link, ("area", "news"))), ("Stock Quotes", _item(link, ("quote_box",))),
            ("Weather", _item(link, ("area", "weather"))), ("People Connection", _item(link, ("area", "people connection"))),
            ("World Wide Web", _item(link, ("area", "www"))), ("Member Services", _item(link, ("area", "member services")))]
    link.send_stream(screens.list_window("My AOL", f"Screen name: {name}.  Online for {mins} minutes.  "
                                         "Your favorite places:", rows, response_id=rid, width=40))


def ask(link, title, prompt, button, token, intro, rid=None):
    link.send_stream(screens.input_window(title, prompt, button, token, intro, response_id=rid))


def open_area(link, area: str, rid=None):
    if area == "boards":
        from . import boards
        return boards.board_list(link, rid)
    if area in ("buddy list", "buddy setup"):
        from . import buddy
        return buddy.show(link, rid) if area == "buddy list" else buddy.setup(link, rid)
    if area == "member directory":
        from . import members
        return members.directory(link, rid)
    if area == "news search":
        return ask(link, "Search Today's News", "Search for:", "Search", "zN", "Search today's headlines.", rid)
    if area == "mail":
        from . import mail
        return mail.read_new_mail(link, 0)
    if area in INFO:
        return info_area(link, area, rid)
    if area == "my aol":
        return my_aol(link, rid)
    if area in ("www", "internet"):
        return ask(link, "World Wide Web", "Address:", "Go", "zU",
                   "Type a Web address (like www.npr.org) or words to search the Web.", rid)
    if area == "find":
        return ask(link, "Find", "Find:", "Search", "zU", "Search the Web, members and AOL areas.", rid)
    if area == "reference":
        return ask(link, "Reference Desk", "Look up:", "Look Up", "zR", "Search the encyclopedia.", rid)
    if area == "file search":
        return ask(link, "File Search", "Search for:", "List Files", "zF",
                   "Search thousands of files and software in the Internet Archive.", rid)
    if area.startswith("room:"):
        return chat.join(link, area[5:])
    if area in NEWS_AREAS:
        return news_area(link, area, rid)
    if area == "finance":
        return finance_area(link, rid)
    if area in ("weather", "digital city"):  # Digital City = your local news & weather
        return weather_box(link, rid)
    if area == "clock":
        return clock(link, rid)
    if area == "people connection":
        link.send_stream(stream(atom("uni_wait_off")))
        return chat.enter_people_connection(link, 0, b"")
    if area == "channels":
        art.ensure_form(link, "32-5483")
        return link.send_stream(stream(atom("uni_invoke_local", gid("32-5483")), atom("uni_wait_off")))
    if area == "welcome":
        from . import signon
        return signon.welcome(link)
    link.send_stream(stream(atom("uni_wait_off")))
    alert(link, f"{area.title()} is not currently available.  Please try again later.")


def _module_areas():
    """Other service modules can add keywords/areas: AREAS = {"keyword": handler(link, rid)}."""
    import sys
    found = {}
    for name, mod in list(sys.modules.items()):
        if name.startswith("services.") and isinstance(getattr(mod, "AREAS", None), dict):
            found.update(mod.AREAS)
    return found


def keyword(link, stream_id, body):
    word = _norm(" ".join(request(body)["texts"]))
    print(f"      keyword: {word!r}")
    extra = _module_areas().get(word) or _module_areas().get(word.replace(" ", ""))
    if extra:
        return extra(link, None)
    area = KEYWORDS.get(word) or KEYWORDS.get(word.replace(" ", ""))
    if area:
        return open_area(link, area)
    link.send_stream(stream(atom("uni_wait_off")))
    alert(link, f'"{word}" is not a valid keyword.  Please check the spelling and try again.')


def by_gid(link, stream_id, body):
    req = request(body)
    print(f"      area request gid={req['gid']} rid={req['response_id']!r}")
    area = GID_AREAS.get(req["gid"] or "")  # K1 with no gid = What's Hot (magic-token button)
    if area:
        return open_area(link, area, req["response_id"])
    link.send_stream(stream(atom("uni_wait_off")))
    alert(link, "This area is not currently available.  Please try again later.")


def item(link, stream_id, body):
    from .util import atoms as _atoms
    vals = [a.args for a in _atoms(body) if a.name == "de_data"]
    n = int.from_bytes(vals[0], "big") if vals else 0
    payload = _session_items(link).get(n)
    print(f"      zA item {n}: {payload[0] if payload else None}")
    if not payload:
        return link.send_stream(stream(atom("uni_wait_off")))
    kind = payload[0]
    if kind == "article":
        show_article(link, payload[1])
    elif kind == "area":
        open_area(link, payload[1])
    elif kind == "quote_box":
        quote_box(link)
    elif kind == "room":
        chat.join(link, payload[1])
    elif kind == "create_room":
        chat.create_room_form(link)
    elif kind == "mail":
        from . import mail
        mail.open_message(link, payload[1])
    elif kind == "profile":
        from . import members
        members.get_profile(link, 0, payload[1].encode("latin1"))
    elif kind == "mailbox":
        from . import mail
        mail.read_new_mail(link, 0, b"", payload[1])
    elif kind in ("board", "topic", "new_topic", "reply"):
        from . import boards
        {"board": boards.board, "topic": boards.topic, "new_topic": boards.new_topic_form,
         "reply": boards.reply_form}[kind](link, payload[1])
    elif kind == "buddy":
        from . import buddy
        buddy.buddy_im(link, payload[1])
    elif kind == "buddy_setup":
        from . import buddy
        buddy.setup(link)
    elif kind == "web":
        show_page(link, payload[1])
    elif kind == "wiki":
        show_wiki(link, payload[1])
    elif kind == "ia_item":
        file_description(link, payload[1])
    elif kind == "ia_download":
        from . import xfer
        xfer.archive_download(link, *payload[1:])
    else:
        link.send_stream(stream(atom("uni_wait_off")))


def show_page(link, url):
    def done(p):
        rows = [(l["title"], _item(link, ("web", l["link"]))) for l in p["links"]]
        link.send_stream(screens.page_window(p["title"], p["url"] + "\r\r" + p["text"], rows))
    run_bg(lambda: content.web_page(url), done)


def web(link, stream_id, body):
    q = (request(body)["texts"] or [""])[0].strip()
    if not q:
        return link.send_stream(stream(atom("uni_wait_off")))
    if "." in q and " " not in q:
        return show_page(link, q)

    def done(results):
        rows = [(r["title"], _item(link, ("web", r["link"]))) for r in results]
        link.send_stream(screens.list_window(f"Search: {q}", f"{len(rows)} matches.  Double-click to visit.", rows))
    run_bg(lambda: content.web_search(q), done)


def show_wiki(link, title):
    def done(w):
        if not w:
            return alert(link, "That article is not available.")
        link.send_stream(screens.text_window(w["title"], w["text"] + "\r\r" + w["link"], width=60, height=14))
    run_bg(lambda: content.wiki_summary(title), done)


def reference(link, stream_id, body):
    q = (request(body)["texts"] or [""])[0].strip()
    if not q:
        return link.send_stream(stream(atom("uni_wait_off")))

    def done(titles):
        rows = [(t, _item(link, ("wiki", t))) for t in titles]
        link.send_stream(screens.list_window(f"Reference: {q}", "Double-click an article.", rows, width=44))
    run_bg(lambda: content.wiki_search(q), done)


def files(link, stream_id, body):
    q = (request(body)["texts"] or [""])[0].strip()
    if not q:
        return link.send_stream(stream(atom("uni_wait_off")))

    def done(results):
        rows = [(r["title"], _item(link, ("ia_item", r))) for r in results]
        link.send_stream(screens.list_window(f"File Search: {q}", f"{len(rows)} files found.  "
                                             "Double-click a file for its description.", rows))
    run_bg(lambda: content.archive_software(q), done)


def file_description(link, r):
    """A File Search hit: description, its downloadable files, and Download Now (services/xfer.py)."""
    from . import xfer
    ident = r["link"].rstrip("/").rsplit("/", 1)[-1]

    def done(info):
        files = (info or {}).get("files", [])[:20]
        text = (r.get("summary") or "(No description available.)")[:1500]
        if files:
            text += f"\r\rDownload Now sends {files[0]['name']} ({files[0]['size']:,} bytes).  " \
                    "Double-click another file below to download it instead."
        else:
            text += "\r\rThis item has no file small enough to download online."
        rows = [(f"{f['name']}  ({f['size']:,} bytes)", _item(link, ("ia_download", ident, f["name"]))) for f in files]
        buttons = [("Download Now", '          sm_send_token_arg <"zA", %d>' % _item(link, ("ia_download", ident)))] \
            if files else []
        link.send_stream(screens.list_window(r["title"][:60], text, rows, buttons=buttons, width=60))

    def work():
        try:
            return xfer.archive_files(ident)
        except Exception as e:
            print(f"      file description {ident} failed: {e}")
    run_bg(work, done)


def url_request(link, stream_id, body):
    """ur/UR (AOL 4.0): aol:// links and Web addresses from the keyword bar or forms."""
    from .util import atoms as _atoms
    url = ""
    for a in _atoms(body):
        if a.name in ("uni_data", "de_data") and a.args and all(32 <= c < 127 for c in a.args.rstrip(b"\0")):
            url = a.args.rstrip(b"\0").decode("latin1").strip()
    print(f"      url: {url!r}")
    low = url.lower()
    if low.startswith(("http://", "https://", "www.")):
        return show_page(link, url)
    if low.startswith("aol://"):
        target = url.split(":", 2)[-1] if url.count(":") >= 2 else url[6:]
        word = _norm(target.replace("_", " ").replace("%20", " "))
        area = KEYWORDS.get(word) or KEYWORDS.get(word.replace(" ", ""))
        if area:
            return open_area(link, area)
        if word in ("learnkeywords", "learn keywords", "keywordlist"):
            return info_area(link, "member services")
    link.send_stream(stream(atom("uni_wait_off")))
    alert(link, f"{url or 'That location'} is not currently available.")


def news_search(link, stream_id, body):
    q = (request(body)["texts"] or [""])[0].strip().lower()

    def work():
        hits = []
        for topic in ("top", "us", "world", "business", "tech", "sports", "entertainment", "health", "science"):
            hits += [h for h in content.headlines(topic, 30) if q in (h["title"] + " " + h["summary"]).lower()]
        seen, out = set(), []
        for h in hits:
            if h["title"] not in seen:
                seen.add(h["title"])
                out.append(h)
        return out[:30]

    def done(hits):
        rows = [(h["title"], _item(link, ("article", h))) for h in hits]
        link.send_stream(screens.list_window(f"News Search: {q}", f"{len(rows)} stories found.", rows))
    run_bg(work, done)


TOKENS = {b"ur": url_request, b"UR": url_request, b"zN": news_search, b"zU": web, b"zR": reference, b"zF": files, b"Kk": keyword, b"K1": by_gid, b"k1": by_gid, b"f1": by_gid,
          b"zA": item, b"zQ": get_quote, b"zW": get_weather}
