"""Chat regulars: 90s-style screen names that keep public rooms lively.

Each public room gets a few personas who show up in the people list, chat
among themselves now and then (often about today's real headlines) and answer
people who talk to the room. Lines come from the local LLM on mcqueen
(OpenAI-compatible); if it's unreachable the regulars simply stay quiet.
"""
import asyncio
import json
import random
import sys
import time
import urllib.request

import state

LLM_URL = "http://100.64.17.32:8095/v1/chat/completions"
LLM_MODEL = "glm-5.3-flash"
PERSONAS = {
    "kewlguy97": "a 16-year-old skater who types in lowercase, says 'phat', 'da bomb', asks a/s/l",
    "SkaterGrrl": "a sarcastic 17-year-old girl into grunge and zines",
    "TechieTom": "a 34-year-old engineer who loves computers, Linux and gadgets, slightly nerdy",
    "Mom2Three": "a friendly suburban mom who is new to the internet and very polite",
    "BigDaddyB": "a 40-something sports fan who talks football and grilling",
    "xXRaverXx": "a club kid who loves techno and uses lots of !!! and caps",
    "PoetGirl22": "a college student who writes poetry and is a bit dramatic",
    "NetNinja": "a know-it-all teen who brags about his modem speed",
}
ROOM_CAST = {"Lobby": 4, "Romance": 3, "Thirtysomething": 3, "Nineties Kids": 3, "Tech Talk": 3,
             "News Talk": 3, "Sports Arena": 3, "Center Stage": 2, "PC Studio": 2}
IDLE_SECONDS = (35, 80)


class Regular:
    """Stands in for a Link in a room's member list; never has a socket."""
    def __init__(self, name):
        self.session = {"name": name, "regular": True}

    def send_stream(self, *_): pass
    def send_data_raw(self, *_): pass
    def send_data(self, *_): pass


def _cast_for(room_name: str) -> int:
    for prefix, n in ROOM_CAST.items():
        if room_name.startswith(prefix):
            return n
    return 0


def populate(room_name: str, room: dict):
    """Seat regulars in a room (once)."""
    if room.get("regulars") is not None:
        return
    names = random.sample(list(PERSONAS), _cast_for(room_name))
    room["regulars"] = [Regular(n) for n in names]
    for r in room["regulars"]:
        room["slots"][r] = room["next"]
        room["next"] += 1
    room.setdefault("history", [])


def humans(room) -> list:
    return [m for m in room["slots"] if not m.session.get("regular")]


def _llm(persona: str, name: str, room: str, history: list, topic: str) -> str | None:
    convo = "\n".join(f"{w}: {t}" for w, t in history[-14:]) or "(the room is quiet)"
    system = (f"You are {name} in the AOL chat room \"{room}\". You are {persona}. The client software and "
              "vibe are 1997 AOL, but the real date is October 2026 and you know current events. "
              f"Something in the news today: {topic}. Write exactly ONE short chat line (max 15 words) as {name}, "
              "casual chatroom style, no emoji, no quotes, no name prefix. Be friendly; never be explicit or hateful.")
    body = json.dumps({"model": LLM_MODEL, "max_tokens": 40, "temperature": 1.0,
                       "messages": [{"role": "system", "content": system},
                                    {"role": "user", "content": f"Recent chat:\n{convo}\n\nYour line:"}]}).encode()
    try:
        req = urllib.request.Request(LLM_URL, data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=20) as r:
            text = json.loads(r.read())["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"      regulars: llm unavailable ({e})")
        return None
    line = text.strip().splitlines()[0].strip().strip('"')
    if line.lower().startswith(name.lower() + ":"):
        line = line[len(name) + 1:].strip()
    return line[:120] or None


CANNED = [
    "lol", "brb", "re", "hey all", "anyone here from cali?", "a/s/l anyone?", "this room is dead lol",
    "wb!", "*waves*", "who wants to trade sigs", "my modem is so slow tonight", "LOL", "rofl",
    "any1 wanna chat?", "hehe", "hiya!", "afk dinner", "back", "kewl", "omg did u see the news?",
    "{topic}... can u believe it", "anyone talking about {topic}?", "just read about {topic}",
]


def canned(room_history, topic) -> str:
    line = random.choice(CANNED)
    return line.replace("{topic}", topic[:60].rstrip(" .") if topic else "the news")


def _topic() -> str:
    from . import content
    hits = state.CACHE.get("news:top")
    if hits and hits[1]:
        return random.choice(hits[1][:10])["title"]
    return "the weather"


async def speak(room_name: str, who: "Regular"):
    room = state.ROOMS.get(room_name)
    if not room or not humans(room) or who not in room["slots"]:
        return
    name = who.session["name"]
    line = await asyncio.get_running_loop().run_in_executor(
        None, _llm, PERSONAS[name], name, room_name, list(room["history"]), _topic())
    if not line:
        line = canned(room["history"], _topic())
    if line and room_name in state.ROOMS and humans(state.ROOMS[room_name]):
        sys.modules["services.chat"].broadcast_line(state.ROOMS[room_name], name, line)


def heard(room_name: str, room: dict, speaker: str, text: str):
    """A person said something: maybe a regular answers after a human-ish pause."""
    regs = room.get("regulars") or []
    if not regs or speaker in {r.session["name"] for r in regs}:
        return
    mentioned = [r for r in regs if r.session["name"].lower() in text.lower()]
    if mentioned or random.random() < 0.7:
        who = mentioned[0] if mentioned else random.choice(regs)
        loop = asyncio.get_running_loop()
        loop.call_later(random.uniform(3, 8), lambda: asyncio.ensure_future(speak(room_name, who)))


async def _idle_loop():
    while True:
        await asyncio.sleep(random.uniform(*IDLE_SECONDS))
        try:
            mod = sys.modules.get("services.regulars")  # always the hot-reloaded code
            for name, room in list(state.ROOMS.items()):
                if room.get("regulars") and mod.humans(room) and time.time() - room.get("last_line", 0) > 25:
                    await mod.speak(name, random.choice(room["regulars"]))
        except Exception as e:
            print(f"      regulars idle loop: {e}")


def ensure_running():
    task = state.__dict__.get("REGULARS_TASK")
    if task is None or task.done():
        state.REGULARS_TASK = asyncio.get_running_loop().create_task(_idle_loop())
