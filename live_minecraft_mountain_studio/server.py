from __future__ import annotations

from copy import deepcopy
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from threading import Lock, Thread
import json
import mimetypes
import os
import queue
import random
import time
import urllib.parse

from game_engine import Course, GameEngine, MultiplierState
from local_server import LocalMinecraftServer
from rcon import RconClient

APP_VERSION = "0.1.2"
ROOT = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("LOCALAPPDATA", ROOT)) / "LiveMinecraftMountainStudio"
DATA_DIR.mkdir(parents=True, exist_ok=True)
STATE_FILE = DATA_DIR / "settings.json"
HOST, PORT = "127.0.0.1", 8776
LOCK = Lock()

DEFAULT = {
    "rcon": {"host": "127.0.0.1", "port": 25576, "password": ""},
    "course": {"world": "world", "startX": 0, "startY": 64, "startZ": 0,
               "goalX": 0, "goalY": 160, "goalZ": 0, "goalRadius": 4,
               "checkpointRise": 20, "goalWin": 1, "daylightFixed": True, "clearWeather": True},
    "multiplier": {"enabled": True, "threshold": 5000, "durationSeconds": 300, "multiplier": 2},
    "effects": {},
    "gachas": {},
    "socialRuntime": {"followedUsers": [], "individualLikes": {}, "totalLikes": 0},
    "overlay": {"background": "#080a0f", "backgroundOpacity": 84, "border": "#ef334e",
                "text": "#ffffff", "accent": "#54e694", "width": 600, "titleSize": 28,
                "textSize": 18, "outline": True, "outlineColor": "#000000", "outlineWidth": 3},
}


def merge(base, loaded):
    result = deepcopy(base)
    for key, value in (loaded or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = merge(result[key], value)
        else:
            result[key] = value
    return result


try:
    STATE = merge(DEFAULT, json.loads(STATE_FILE.read_text("utf-8")))
except Exception:
    STATE = deepcopy(DEFAULT)


def make_engine():
    c = STATE["course"]
    m = STATE["multiplier"]
    return GameEngine(Course(c["world"], float(c["startX"]), float(c["startY"]), float(c["startZ"]),
                             float(c["goalX"]), float(c["goalY"]), float(c["goalZ"]), float(c["goalRadius"]),
                             int(c["checkpointRise"]), int(c["goalWin"])),
                      MultiplierState(bool(m["enabled"]), int(m["threshold"]), int(m["durationSeconds"]), int(m["multiplier"])))


ENGINE = make_engine()
LOCAL = LocalMinecraftServer(DATA_DIR)
STATUS = {"rcon": "未接続", "lastError": "", "lastSync": 0, "wins": []}
GACHA_EVENTS = []
GACHA_QUEUE = queue.Queue()


def save():
    STATE_FILE.write_text(json.dumps(STATE, ensure_ascii=False, indent=2), "utf-8")


def rcon(command: str):
    cfg = STATE["rcon"]
    with RconClient(cfg["host"], int(cfg["port"]), cfg["password"]) as client:
        raw = client.command(command)
    try:
        reply = json.loads(raw)
    except Exception:
        return raw
    if isinstance(reply, dict) and reply.get("ok") is False:
        raise RuntimeError(reply.get("message", "Minecraft側で失敗しました"))
    return reply


def public_state():
    return {"version": APP_VERSION, "config": STATE, "game": ENGINE.snapshot(),
            "status": {**STATUS, "localServer": LOCAL.status()}, "gachaEvents": list(GACHA_EVENTS[-30:]),
            "effectKinds": [
                ["tnt", "TNTを降らせる"], ["zombie", "ゾンビ"], ["creeper", "クリーパー"],
                ["launch", "上へ吹き飛ばす"], ["freeze", "牢屋へ閉じ込める"], ["darkness", "暗闇"],
                ["lightning", "雷"], ["reset", "スタートへ戻す"], ["checkpoint", "チェックポイントへ救済"],
                ["shield", "無敵"], ["speed", "スピード"], ["jump", "ジャンプ力"],
                ["boost", "前方ブースト"], ["clear_mobs", "敵を全消去"], ["obstacle", "障害物"],
                ["car", "車"], ["bike", "バイク"]]}


def sync_loop():
    while True:
        try:
            reply = rcon("lmsmountain status")
            if isinstance(reply, dict):
                ENGINE.update_world({"active": reply.get("active", False), "world": reply.get("world", ""),
                                     "players": reply.get("players", []), "start": reply.get("start", {}),
                                     "goal": reply.get("goal", {})})
                for event in reply.get("wins", []):
                    if event.get("eventId") not in {x.get("eventId") for x in STATUS["wins"]}:
                        STATUS["wins"] = (STATUS["wins"] + [event])[-30:]
                    rcon("lmsmountain ack " + str(event.get("eventId", "")))
            STATUS.update({"rcon": "接続中", "lastError": "", "lastSync": time.time()})
        except Exception as exc:
            STATUS.update({"rcon": "未接続", "lastError": str(exc)})
        time.sleep(2)


def run_effect(effect, sender, coins=0):
    result = ENGINE.receive(effect, sender, coins)
    for command in result["commands"]: rcon(command)
    return result


def enqueue_gacha(gacha_id, sender, count=1):
    for _ in range(max(1, min(1000, int(count)))): GACHA_QUEUE.put((gacha_id, sender))


def gacha_loop():
    while True:
        gacha_id, sender = GACHA_QUEUE.get()
        try:
            g = STATE.get("gachas", {}).get(gacha_id, {})
            if not g.get("enabled", True): continue
            entries = [e for e in g.get("entries", []) if float(e.get("weight", 0)) > 0]
            if not entries: continue
            spin = max(.5, min(30, float(g.get("spinSeconds", 4))))
            event = {"eventId": str(time.time_ns()), "gachaName": g.get("name", "ガチャ"), "sender": sender,
                     "state": "spinning", "result": "", "at": time.time(), "spinSeconds": spin}
            GACHA_EVENTS.append(event); time.sleep(spin)
            chosen = random.choices(entries, weights=[float(e.get("weight", 1)) for e in entries], k=1)[0]
            effect = STATE.get("effects", {}).get(str(chosen.get("effectId", "")))
            event["state"] = "result"; event["result"] = chosen.get("label") or (effect or {}).get("name", "結果")
            if effect: run_effect(effect, sender)
            time.sleep(max(.5, min(10, float(g.get("resultSeconds", 2)))))
        except Exception as exc:
            STATUS["lastError"] = str(exc)
        finally:
            GACHA_QUEUE.task_done()


def receive_social(body):
    kind = str(body.get("type") or body.get("eventType") or body.get("event") or "").lower()
    kind = "follow" if "follow" in kind else "like" if "like" in kind else kind
    user_id = str(body.get("userId") or body.get("uniqueId") or (body.get("user") or {}).get("uniqueId") or "")
    sender = str(body.get("userName") or body.get("nickname") or (body.get("user") or {}).get("nickname") or user_id)
    runtime = STATE.setdefault("socialRuntime", deepcopy(DEFAULT["socialRuntime"])); targets = []
    if kind == "follow":
        followed = set(runtime.get("followedUsers", []))
        if not user_id or user_id in followed: return 0
        followed.add(user_id); runtime["followedUsers"] = list(followed)[-100000:]
        targets = [("effect", k, v) for k,v in STATE["effects"].items() if v.get("enabled",True) and v.get("trigger")=="follow"]
        targets += [("gacha", k, v) for k,v in STATE["gachas"].items() if v.get("enabled",True) and v.get("trigger")=="follow"]
    elif kind == "like":
        count=max(1,int(body.get("count",body.get("likeCount",1)))); likes=runtime.setdefault("individualLikes",{})
        before=int(likes.get(user_id,0)); after=before+count; likes[user_id]=after
        total_before=int(runtime.get("totalLikes",0));runtime["totalLikes"]=total_before+count
        for typ,items in (("effect",STATE["effects"]),("gacha",STATE["gachas"])):
            for k,v in items.items():
                if not v.get("enabled",True) or v.get("trigger") not in ("like","total_like"): continue
                every=max(1,int(v.get("triggerAmount",100))); a,b=(before,after) if v["trigger"]=="like" else (total_before,runtime["totalLikes"])
                targets += [(typ,k,v)]*min(20,b//every-a//every)
    else: raise ValueError("typeはfollowまたはlikeを指定してください")
    for typ,k,v in targets:
        if typ=="effect": run_effect(v,sender)
        else: enqueue_gacha(k,sender)
    save(); return len(targets)


class Handler(SimpleHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def _json(self, body, status=200):
        data = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(status); self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)

    def _body(self):
        length = min(int(self.headers.get("Content-Length", "0")), 25_000_000)
        return json.loads(self.rfile.read(length) or b"{}")

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path in ("/api/state", "/api/overlay"):
            return self._json(public_state())
        if path == "/": path = "/index.html"
        target = (ROOT / path.lstrip("/")).resolve()
        if ROOT not in target.parents or not target.is_file():
            return self.send_error(404)
        data = target.read_bytes(); self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(target.name)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        try:
            body = self._body()
            if path == "/api/config":
                with LOCK:
                    for key in ("course", "multiplier", "overlay", "rcon"):
                        if isinstance(body.get(key), dict): STATE[key].update(body[key])
                    if isinstance(body.get("effects"), dict): STATE["effects"] = body["effects"]
                    if isinstance(body.get("gachas"), dict): STATE["gachas"] = body["gachas"]
                    global ENGINE
                    old_world = ENGINE.world_state; old_events = ENGINE.announcements
                    ENGINE = make_engine(); ENGINE.world_state = old_world; ENGINE.announcements = old_events
                    save()
                return self._json({"ok": True, "state": public_state()})
            if path == "/api/course/apply":
                rcon(ENGINE.configure_command())
                c = STATE["course"]
                rcon(f"lmsmountain environment {str(c.get('daylightFixed', True)).lower()} {str(c.get('clearWeather', True)).lower()}")
                return self._json({"ok": True, "message": "スタート・ゴール地点を適用しました"})
            if path == "/api/effect/test":
                effect = body.get("effect") or STATE["effects"].get(body.get("id"), {})
                result = run_effect(effect, body.get("sender", "テスト"), int(body.get("coins", 0)))
                return self._json({"ok": True, "result": result, "state": public_state()})
            if path == "/api/gift":
                event_type = str(body.get("eventType") or body.get("type") or "").lower()
                if "follow" in event_type or "like" in event_type:
                    return self._json({"ok": True, "triggered": receive_social(body)})
                gift = str(body.get("giftName") or body.get("giftId") or "")
                sender_id = str(body.get("userId", ""))
                repeat = max(1, int(body.get("repeatCount", 1)))
                fired = 0
                for effect in STATE["effects"].values():
                    if not effect.get("enabled", True) or str(effect.get("trigger", "gift")) != "gift": continue
                    if str(effect.get("gift", "")) != gift: continue
                    allowed = str(effect.get("userId", "")).strip()
                    if allowed and allowed != sender_id: continue
                    for _ in range(repeat):
                        result = ENGINE.receive(effect, body.get("userName", ""), int(body.get("coins", 0)))
                        for command in result["commands"]: rcon(command)
                        fired += 1
                for gacha_id, gacha in STATE.get("gachas", {}).items():
                    if not gacha.get("enabled", True) or gacha.get("trigger", "gift") != "gift": continue
                    if str(gacha.get("gift", "")) != gift: continue
                    allowed = str(gacha.get("userId", "")).strip()
                    if allowed and allowed != sender_id: continue
                    enqueue_gacha(gacha_id, body.get("userName", ""), repeat); fired += repeat
                return self._json({"ok": True, "fired": fired})
            if path == "/api/social":
                return self._json({"ok": True, "triggered": receive_social(body)})
            if path == "/api/gacha/test":
                enqueue_gacha(str(body.get("id")), body.get("sender", "テスト"), int(body.get("count", 1)))
                return self._json({"ok": True, "queued": GACHA_QUEUE.qsize()})
            if path == "/api/server/prepare":
                result = LOCAL.prepare(bool(body.get("eulaAccepted")))
                STATE["rcon"].update({"host": "127.0.0.1", "port": 25576, "password": result["password"]}); save()
                return self._json({"ok": True, "status": LOCAL.status(), "state": public_state()})
            if path == "/api/server/start":
                return self._json({"ok": True, "status": LOCAL.start()})
            if path == "/api/server/stop":
                return self._json({"ok": True, "status": LOCAL.stop(STATE["rcon"])})
            if path == "/api/reset":
                rcon("lmsmountain reset"); return self._json({"ok": True})
            return self._json({"ok": False, "message": "不明な操作です"}, 404)
        except Exception as exc:
            return self._json({"ok": False, "message": str(exc)}, 400)


def make_server():
    Thread(target=sync_loop, daemon=True).start()
    Thread(target=gacha_loop, daemon=True).start()
    return ThreadingHTTPServer((HOST, PORT), Handler)


if __name__ == "__main__":
    print(f"Live Minecraft Mountain Studio v{APP_VERSION}: http://{HOST}:{PORT}/")
    make_server().serve_forever()
