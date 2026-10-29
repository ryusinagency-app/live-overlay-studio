from __future__ import annotations

from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from queue import Queue, Empty
from threading import Thread, Lock
from urllib.parse import urlparse
import json
import os
import secrets
import time
import urllib.request
import webbrowser

from game_engine import Arena, GameEngine, MultiplierState, clamp
from rcon import RconClient
from local_server import LocalMinecraftServer


APP_VERSION = "0.2.4"
ROOT = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("LOCALAPPDATA", ROOT)) / "LiveMinecraftStudio"
STATE_FILE = DATA_DIR / "state.json"
HOST, PORT = "127.0.0.1", 8775

DEFAULT = {
    "rcon": {"host": "127.0.0.1", "port": 25575, "password": "", "serverSoftware": "未判定", "serverVersionText": ""},
    "arena": {"x": 0, "y": 64, "z": 0, "width": 9, "depth": 9, "height": 12,
              "frameBlock": "minecraft:obsidian", "fillBlock": "minecraft:stone", "maxHealth": 100,
              "holdSeconds": 10, "holdWin": 1, "clearAfterSuccess": True},
    "multiplier": {"threshold": 5000, "durationSeconds": 300, "multiplier": 2,
                   "applyFill": True, "applyTnt": True, "applyWin": True},
    "commandDelayMs": 35,
    "winBridge": {"enabled": False, "url": "http://127.0.0.1:8765/api/minecraft-studio/win", "token": ""},
    "effects": {
        "demo-fill": {"name": "10ブロック埋め", "kind": "fill", "amount": 10, "win": 0,
                      "description": "埋め立てブロックを10個追加します"},
        "demo-tnt": {"name": "TNT", "kind": "tnt", "amount": 1, "damage": 10, "breakWin": -100,
                     "win": 0, "description": "TNTを1個落とし、底の耐久ゲージへ攻撃します"},
        "demo-repair": {"name": "修復", "kind": "repair", "amount": 20, "win": 0,
                        "description": "耐久ゲージを20回復します"},
        "demo-shield": {"name": "シールド", "kind": "shield", "amount": 1, "win": 0,
                        "description": "次のブロック破壊を1回無効化します"},
        "demo-time-plus": {"name": "カウント＋5秒", "kind": "countdown", "countdownMode": "add",
                           "seconds": 5, "win": 0, "description": "カウントの残り時間を5秒増やします"},
        "demo-time-minus": {"name": "カウント－3秒", "kind": "countdown", "countdownMode": "add",
                            "seconds": -3, "win": 0, "description": "カウントの残り時間を3秒短くします"},
        "demo-all": {"name": "全埋め", "kind": "fill_all", "amount": 1, "win": 100,
                     "description": "使用回数制限を想定した全埋めアイテムです"},
    },
}

STATE_LOCK = Lock()
COMMAND_QUEUE: Queue[str] = Queue(maxsize=100000)
WIN_QUEUE: Queue[dict] = Queue(maxsize=10000)
STATUS = {"rcon": "未接続", "lastError": "", "queuedCommands": 0, "pendingWin": 0}


def deep_merge(base, incoming):
    result = dict(base)
    for key, value in (incoming or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_state():
    try:
        raw = json.loads(STATE_FILE.read_text("utf-8"))
    except Exception:
        raw = {}
    state = deep_merge(DEFAULT, raw)
    state.setdefault("runtime", {})
    return state


STATE = load_state()
LOCAL_SERVER = LocalMinecraftServer(DATA_DIR)
arena_config = STATE["arena"]
multiplier_config = STATE["multiplier"]
ENGINE = GameEngine(
    Arena(x=int(arena_config["x"]), y=int(arena_config["y"]), z=int(arena_config["z"]),
          width=int(arena_config["width"]), depth=int(arena_config["depth"]), height=int(arena_config["height"]),
          frame_block=arena_config["frameBlock"], fill_block=arena_config["fillBlock"],
          max_health=int(arena_config["maxHealth"]), health=int(arena_config["maxHealth"]),
          hold_seconds=int(arena_config.get("holdSeconds", 10)), hold_win=int(arena_config.get("holdWin", 1)),
          clear_after_success=arena_config.get("clearAfterSuccess", True) is True),
    MultiplierState(threshold=int(multiplier_config["threshold"]),
                    duration_seconds=int(multiplier_config["durationSeconds"]),
                    multiplier=float(multiplier_config["multiplier"]),
                    total_coins=int(STATE.get("runtime", {}).get("totalCoins", 0)),
                    next_target=int(STATE.get("runtime", {}).get("nextTarget", multiplier_config["threshold"])),
                    active_until=float(STATE.get("runtime", {}).get("activeUntil", 0)),
                    apply_fill=multiplier_config.get("applyFill", True) is True,
                    apply_tnt=multiplier_config.get("applyTnt", True) is True,
                    apply_win=multiplier_config.get("applyWin", True) is True),
)


def public_state():
    with STATE_LOCK:
        config = json.loads(json.dumps(STATE))
    config["rcon"]["password"] = "" if not config["rcon"].get("password") else "••••••••"
    config["winBridge"]["token"] = "" if not config["winBridge"].get("token") else "••••••••"
    return {"version": APP_VERSION, "config": config, "game": ENGINE.snapshot(), "status": status_snapshot(),
            "localServer": LOCAL_SERVER.status()}


def status_snapshot():
    return {**STATUS, "queuedCommands": COMMAND_QUEUE.qsize(), "pendingWin": WIN_QUEUE.qsize()}


def save_state():
    with STATE_LOCK:
        STATE["runtime"] = {
            "totalCoins": ENGINE.multiplier.total_coins,
            "nextTarget": ENGINE.multiplier.next_target,
            "activeUntil": ENGINE.multiplier.active_until,
        }
        data = json.dumps(STATE, ensure_ascii=False, separators=(",", ":"))
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    temporary = STATE_FILE.with_suffix(".tmp")
    temporary.write_text(data, "utf-8")
    temporary.replace(STATE_FILE)


def queue_commands(commands):
    for command in commands:
        COMMAND_QUEUE.put_nowait(command)


def classify_server_software(*responses: str) -> str:
    text = " ".join(str(x or "") for x in responses).lower()
    if any(name in text for name in ("paper", "purpur", "folia", "pufferfish")):
        return "Paper系"
    if any(name in text for name in ("spigot", "bukkit", "craftbukkit")):
        return "Spigot系"
    if "neoforge" in text:
        return "NeoForge"
    if "forge" in text:
        return "Forge"
    if "fabric" in text or "quilt" in text:
        return "Fabric系"
    return "バニラ／判定不能"


def detect_server_software(rcon):
    responses = []
    with RconClient(rcon["host"], int(rcon["port"]), rcon["password"]) as client:
        for command in ("version", "plugins", "forge tps"):
            try:
                responses.append(client.command(command))
            except Exception as exc:
                responses.append(str(exc))
    return classify_server_software(*responses), " / ".join(x for x in responses if x)[:1000]


def command_worker():
    while True:
        try:
            first = COMMAND_QUEUE.get(timeout=1)
        except Empty:
            continue
        completed = [first]
        try:
            with STATE_LOCK:
                rcon = dict(STATE["rcon"])
                delay = int(clamp(STATE.get("commandDelayMs", 35), 10, 2000, 35)) / 1000
            if not rcon.get("password"):
                raise RuntimeError("RCONパスワードが未設定です")
            with RconClient(rcon["host"], int(rcon["port"]), rcon["password"]) as client:
                client.command(first)
                while True:
                    time.sleep(delay)
                    try:
                        command = COMMAND_QUEUE.get_nowait()
                    except Empty:
                        break
                    completed.append(command)
                    client.command(command)
            STATUS.update(rcon="接続中", lastError="")
        except Exception as exc:
            STATUS.update(rcon="エラー", lastError=str(exc)[:300])
        finally:
            for _ in completed:
                COMMAND_QUEUE.task_done()


def win_worker():
    while True:
        try:
            event = WIN_QUEUE.get(timeout=1)
        except Empty:
            continue
        delivered = False
        try:
            with STATE_LOCK:
                bridge = dict(STATE["winBridge"])
            if not bridge.get("enabled"):
                delivered = True
            else:
                body = json.dumps(event, ensure_ascii=False).encode("utf-8")
                request = urllib.request.Request(bridge["url"], data=body,
                                                 headers={"Content-Type": "application/json",
                                                          "X-Live-Minecraft-Token": bridge.get("token", "")},
                                                 method="POST")
                with urllib.request.urlopen(request, timeout=4) as response:
                    delivered = 200 <= response.status < 300
        except Exception as exc:
            STATUS["lastError"] = "WIN連携: " + str(exc)[:260]
        finally:
            if not delivered:
                time.sleep(2)
                try:
                    WIN_QUEUE.put_nowait(event)
                except Exception:
                    pass
            WIN_QUEUE.task_done()


def game_timer_worker():
    while True:
        try:
            result = ENGINE.tick()
            if result:
                queue_commands(result.get("commands", []))
                if result.get("win"):
                    WIN_QUEUE.put_nowait({"eventId": result["eventId"], "amount": result["win"],
                                         "reason": result["message"], "senderName": ""})
                save_state()
        except Exception as exc:
            STATUS["lastError"] = "ゲーム判定: " + str(exc)[:260]
        time.sleep(0.25)


class Handler(SimpleHTTPRequestHandler):
    def translate_path(self, path):
        clean = urlparse(path).path.lstrip("/") or "index.html"
        candidate = (ROOT / clean).resolve()
        return str(candidate if candidate == ROOT or ROOT in candidate.parents else ROOT / "index.html")

    def log_message(self, fmt, *args):
        return

    def _json(self, body, status=200):
        encoded = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _body(self):
        length = int(self.headers.get("Content-Length", 0))
        if length > 2_000_000:
            raise ValueError("リクエストが大きすぎます")
        return json.loads(self.rfile.read(length) or b"{}")

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/state":
            return self._json(public_state())
        if path == "/api/overlay":
            game = ENGINE.snapshot()
            with STATE_LOCK:
                effects = list(STATE["effects"].values())
            return self._json({"game": game, "effects": effects, "version": APP_VERSION})
        if path == "/api/gift-catalog":
            try:
                with urllib.request.urlopen("http://127.0.0.1:8765/api/tiktok/gifts", timeout=3) as response:
                    catalog = json.load(response)
                return self._json(catalog)
            except Exception as exc:
                return self._json({"gifts": [], "message": f"Live Overlay Studioから取得できません: {exc}"}, 503)
        return super().do_GET()

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            body = self._body()
            if path == "/api/config":
                self._update_config(body)
                return self._json({"ok": True, "state": public_state()})
            if path == "/api/local-server/prepare":
                result = LOCAL_SERVER.prepare(body.get("eulaAccepted") is True)
                with STATE_LOCK:
                    STATE["rcon"].update({"host": "127.0.0.1", "port": 25575,
                                          "password": result["password"],
                                          "serverSoftware": "Paper 1.21.1"})
                save_state()
                return self._json({"ok": True, "message": "準備が完了しました", "state": public_state()})
            if path == "/api/local-server/start":
                result = LOCAL_SERVER.start()
                STATUS.update(rcon="接続中" if result.get("running") else "未接続", lastError="")
                return self._json({"ok": True, "message": result.get("message"), "state": public_state()})
            if path == "/api/local-server/stop":
                with STATE_LOCK:
                    rcon = dict(STATE["rcon"])
                result = LOCAL_SERVER.stop(rcon)
                STATUS.update(rcon="未接続", lastError="")
                return self._json({"ok": True, "message": result.get("message"), "state": public_state()})
            if path == "/api/rcon/test":
                with STATE_LOCK:
                    rcon = dict(STATE["rcon"])
                with RconClient(rcon["host"], int(rcon["port"]), rcon["password"]) as client:
                    reply = client.command("list")
                STATUS.update(rcon="接続中", lastError="")
                return self._json({"ok": True, "message": reply or "接続できました"})
            if path == "/api/rcon/detect":
                with STATE_LOCK:
                    rcon = dict(STATE["rcon"])
                software, detail = detect_server_software(rcon)
                with STATE_LOCK:
                    STATE["rcon"]["serverSoftware"] = software
                    STATE["rcon"]["serverVersionText"] = detail
                save_state()
                STATUS.update(rcon="接続中", lastError="")
                return self._json({"ok": True, "software": software, "detail": detail})
            if path == "/api/arena/build":
                commands = ENGINE.frame_commands()
                queue_commands(commands)
                return self._json({"ok": True, "queued": len(commands)})
            if path == "/api/gift":
                result = ENGINE.receive(body, STATE["effects"])
                queue_commands(result.get("commands", []))
                if result.get("win"):
                    WIN_QUEUE.put_nowait({"eventId": result["eventId"], "amount": result["win"],
                                         "reason": result.get("message", "Minecraft効果"),
                                         "senderName": str(body.get("senderName") or "")[:80]})
                save_state()
                return self._json(result, 200 if result.get("ok") else 404)
            if path == "/api/test-effect":
                gift_id = str(body.get("giftId") or "")
                payload = {"eventId": "test-" + secrets.token_hex(8), "giftId": gift_id,
                           "senderName": "テスト", "coins": body.get("coins", 0), "repeatCount": 1}
                result = ENGINE.receive(payload, STATE["effects"])
                queue_commands(result.get("commands", []))
                return self._json(result)
            return self._json({"ok": False, "message": "見つかりません"}, 404)
        except Exception as exc:
            STATUS["lastError"] = str(exc)[:300]
            return self._json({"ok": False, "message": str(exc)}, 400)

    def _update_config(self, body):
        with STATE_LOCK:
            incoming_rcon = body.get("rcon", {}) if isinstance(body.get("rcon"), dict) else {}
            for key in ("host", "port", "password", "serverSoftware", "serverVersionText"):
                if key in incoming_rcon and incoming_rcon[key] != "••••••••":
                    STATE["rcon"][key] = incoming_rcon[key]
            incoming_bridge = body.get("winBridge", {}) if isinstance(body.get("winBridge"), dict) else {}
            for key in ("enabled", "url", "token"):
                if key in incoming_bridge and incoming_bridge[key] != "••••••••":
                    STATE["winBridge"][key] = incoming_bridge[key]
            if "commandDelayMs" in body:
                STATE["commandDelayMs"] = int(clamp(body["commandDelayMs"], 10, 2000, 35))
            if isinstance(body.get("arena"), dict):
                STATE["arena"].update(body["arena"])
                config = STATE["arena"]
                a = ENGINE.arena
                for key in ("x", "y", "z", "width", "depth", "height", "holdSeconds", "holdWin"):
                    if key in config:
                        attr = {"holdSeconds": "hold_seconds", "holdWin": "hold_win"}.get(key, key)
                        setattr(a, attr, int(config[key]))
                a.frame_block = str(config.get("frameBlock", a.frame_block))
                a.fill_block = str(config.get("fillBlock", a.fill_block))
                a.max_health = int(config.get("maxHealth", a.max_health))
                a.clear_after_success = config.get("clearAfterSuccess", True) is True
                a.health = min(a.health, a.max_health)
                a.normalize()
            if isinstance(body.get("multiplier"), dict):
                STATE["multiplier"].update(body["multiplier"])
                config = STATE["multiplier"]
                m = ENGINE.multiplier
                m.threshold = int(clamp(config["threshold"], 1, 10**9, 5000))
                m.duration_seconds = int(clamp(config["durationSeconds"], 1, 86400, 300))
                m.multiplier = clamp(config["multiplier"], 1, 100, 2)
                m.apply_fill = config.get("applyFill", True) is True
                m.apply_tnt = config.get("applyTnt", True) is True
                m.apply_win = config.get("applyWin", True) is True
                if m.next_target <= m.total_coins:
                    m.next_target = (m.total_coins // m.threshold + 1) * m.threshold
            if isinstance(body.get("effects"), dict):
                STATE["effects"] = body["effects"]
        save_state()


def make_server():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    Thread(target=command_worker, daemon=True).start()
    Thread(target=win_worker, daemon=True).start()
    Thread(target=game_timer_worker, daemon=True).start()
    return ThreadingHTTPServer((HOST, PORT), Handler)


def main():
    server = make_server()
    print(f"Live Minecraft Studio v{APP_VERSION}: http://{HOST}:{PORT}/")
    Thread(target=lambda: (time.sleep(0.5), webbrowser.open(f"http://{HOST}:{PORT}/")), daemon=True).start()
    server.serve_forever()


if __name__ == "__main__":
    main()

