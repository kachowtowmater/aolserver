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
}

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
}

KEYWORDS = {  # keyword -> area (case/space-insensitive)
    **{k: k for k in NEWS_AREAS}, "top news": "news", "todays news": "news", "today's news": "news",
    "world": "international", "tech": "computing", "computers": "computing", "computing": "computing",
    "stocks": "finance", "quotes": "finance", "quote": "finance", "personal finance": "finance",
    "money": "finance", "finance": "finance", "weather": "weather", "time": "clock", "clock": "clock",
    "online clock": "clock", "chat": "people connection", "people connection": "people connection",
    "pc": "people connection", "lobby": "people connection", "channels": "channels", "welcome": "welcome",
    "help": "member services", "member services": "member services", "business": "business",
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
        link.send_stream(screens.list_window(title, f"{intro}  {when}.  Double-click a headline to read it.",
                                             rows, response_id=rid))
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
            "Personal Finance", intro, [("Business news", _item(link, ("area", "business")))],
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


def open_area(link, area: str, rid=None):
    if area in NEWS_AREAS:
        return news_area(link, area, rid)
    if area == "finance":
        return finance_area(link, rid)
    if area in ("weather", "digital city"):
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
        from .util import render
        return link.send_stream(render("welcome", name=name_of(link)))
    link.send_stream(stream(atom("uni_wait_off")))
    alert(link, f"{area.title()} is not currently available.  Please try again later.")


def keyword(link, stream_id, body):
    word = _norm(" ".join(request(body)["texts"]))
    print(f"      keyword: {word!r}")
    area = KEYWORDS.get(word) or KEYWORDS.get(word.replace(" ", ""))
    if area:
        return open_area(link, area)
    link.send_stream(stream(atom("uni_wait_off")))
    alert(link, f'"{word}" is not a valid keyword.  Please check the spelling and try again.')


def by_gid(link, stream_id, body):
    req = request(body)
    print(f"      area request gid={req['gid']} rid={req['response_id']!r}")
    area = GID_AREAS.get(req["gid"] or "")
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
    else:
        link.send_stream(stream(atom("uni_wait_off")))


TOKENS = {b"Kk": keyword, b"K1": by_gid, b"k1": by_gid, b"f1": by_gid,
          b"zA": item, b"zQ": get_quote, b"zW": get_weather}
