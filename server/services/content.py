"""Live 2026 content behind the 1997 screens: news (RSS), quotes, weather.

All network work runs off the event loop (run_bg); results are cached in
state.CACHE so hot reloads don't refetch.
"""
import html
import json
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

import state

state.__dict__.setdefault("CACHE", {})

UA = {"User-Agent": "Mozilla/5.0 (aolserver; +https://github.com/kachowtowmater/aolserver)"}

FEEDS = {
    "top": ["https://feeds.npr.org/1001/rss.xml", "https://feeds.bbci.co.uk/news/rss.xml"],
    "us": ["https://feeds.npr.org/1003/rss.xml", "https://rss.nytimes.com/services/xml/rss/nyt/US.xml"],
    "world": ["https://feeds.bbci.co.uk/news/world/rss.xml", "https://feeds.npr.org/1004/rss.xml"],
    "business": ["https://feeds.npr.org/1006/rss.xml", "https://feeds.bbci.co.uk/news/business/rss.xml"],
    "tech": ["https://www.theverge.com/rss/index.xml", "https://feeds.bbci.co.uk/news/technology/rss.xml"],
    "sports": ["https://feeds.bbci.co.uk/sport/rss.xml", "https://rss.nytimes.com/services/xml/rss/nyt/Sports.xml"],
    "entertainment": ["https://feeds.bbci.co.uk/news/entertainment_and_arts/rss.xml",
                      "https://rss.nytimes.com/services/xml/rss/nyt/Arts.xml"],
    "health": ["https://feeds.npr.org/1128/rss.xml", "https://feeds.bbci.co.uk/news/health/rss.xml"],
    "science": ["https://feeds.npr.org/1007/rss.xml", "https://feeds.bbci.co.uk/news/science_and_environment/rss.xml"],
    "travel": ["https://rss.nytimes.com/services/xml/rss/nyt/Travel.xml"],
    "games": ["https://www.theverge.com/rss/games/index.xml"],
    "music": ["https://feeds.npr.org/1039/rss.xml"],
    "style": ["https://rss.nytimes.com/services/xml/rss/nyt/FashionandStyle.xml"],
    "education": ["https://feeds.npr.org/1013/rss.xml"],
}
NEWS_TTL = 600
QUOTE_TTL = 60


def _get(url: str, timeout=8) -> bytes:
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return r.read()


def _clean(text: str) -> str:
    text = html.unescape(re.sub(r"<[^>]+>", " ", text or ""))
    return re.sub(r"\s+", " ", text).strip()


def _cached(key, ttl, fetch):
    hit = state.CACHE.get(key)
    if hit and time.time() - hit[0] < ttl:
        return hit[1]
    try:
        value = fetch()
    except Exception as e:
        print(f"      content fetch {key} failed: {e}")
        return hit[1] if hit else None
    state.CACHE[key] = (time.time(), value)
    return value


def headlines(topic: str, limit: int = 20) -> list[dict]:
    """[{title, summary, link, source, date}] newest first, deduped across feeds."""
    def fetch():
        items, seen = [], set()
        for url in FEEDS.get(topic, FEEDS["top"]):
            try:
                root = ET.fromstring(_get(url))
            except Exception as e:
                print(f"      feed {url}: {e}")
                continue
            src = _clean(root.findtext("channel/title") or "")
            ns = {"a": "http://www.w3.org/2005/Atom"}
            entries = root.findall("channel/item") or root.findall("a:entry", ns)
            for it in entries:
                title = _clean(it.findtext("title") or it.findtext("a:title", namespaces=ns) or "")
                if not title or title.lower() in seen:
                    continue
                seen.add(title.lower())
                summary = _clean(it.findtext("description") or it.findtext("a:summary", namespaces=ns)
                                 or it.findtext("a:content", namespaces=ns) or "")
                link = it.findtext("link") or (it.find("a:link", ns).get("href") if it.find("a:link", ns) is not None else "")
                date = it.findtext("pubDate") or it.findtext("a:updated", namespaces=ns) or ""
                items.append({"title": title, "summary": summary, "link": link, "source": src, "date": date})
        return items
    return (_cached(f"news:{topic}", NEWS_TTL, fetch) or [])[:limit]


def quote(symbol: str) -> dict | None:
    sym = symbol.strip().upper()

    def fetch():
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(sym)}?range=1d&interval=1d"
        meta = json.loads(_get(url))["chart"]["result"][0]["meta"]
        price, prev = meta.get("regularMarketPrice"), meta.get("chartPreviousClose") or meta.get("previousClose")
        return {"symbol": meta.get("symbol", sym), "name": meta.get("longName") or meta.get("shortName") or sym,
                "price": price, "prev": prev, "change": (price - prev) if price and prev else 0.0,
                "pct": ((price - prev) / prev * 100) if price and prev else 0.0, "time": meta.get("regularMarketTime")}
    return _cached(f"quote:{sym}", QUOTE_TTL, fetch)


WMO = {0: "Clear", 1: "Mostly Clear", 2: "Partly Cloudy", 3: "Cloudy", 45: "Fog", 48: "Fog", 51: "Drizzle",
       53: "Drizzle", 55: "Drizzle", 61: "Rain", 63: "Rain", 65: "Heavy Rain", 71: "Snow", 73: "Snow",
       75: "Heavy Snow", 80: "Showers", 81: "Showers", 82: "Heavy Showers", 95: "Thunderstorms",
       96: "Thunderstorms", 99: "Thunderstorms"}


def weather(place: str) -> dict | None:
    def fetch():
        g = json.loads(_get("https://geocoding-api.open-meteo.com/v1/search?count=1&name=" + urllib.parse.quote(place)))
        if not g.get("results"):
            return {"error": f"No forecast found for {place}."}
        r = g["results"][0]
        q = (f"https://api.open-meteo.com/v1/forecast?latitude={r['latitude']}&longitude={r['longitude']}"
             "&current=temperature_2m,weather_code,wind_speed_10m,relative_humidity_2m"
             "&daily=weather_code,temperature_2m_max,temperature_2m_min&forecast_days=5"
             "&temperature_unit=fahrenheit&wind_speed_unit=mph&timezone=auto")
        w = json.loads(_get(q))
        return {"place": f"{r['name']}, {r.get('admin1') or r.get('country', '')}", "current": w["current"],
                "daily": w["daily"]}
    return _cached(f"wx:{place.lower()}", NEWS_TTL, fetch)
