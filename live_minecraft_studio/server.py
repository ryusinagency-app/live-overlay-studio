from __future__ import annotations

from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from queue import Queue, Empty
from threading import Thread, Lock
from urllib.parse import urlparse
import json
import base64
import binascii
import mimetypes
import os
import secrets
import time
import urllib.request
import webbrowser

from game_engine import Arena, GameEngine, MultiplierState, clamp, resolve_effect
from rcon import RconClient
from local_server import LocalMinecraftServer


APP_VERSION = "0.3.2"
ROOT = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("LOCALAPPDATA", ROOT)) / "LiveMinecraftStudio"
SOUNDS_DIR = DATA_DIR / "sounds"
STATE_FILE = DATA_DIR / "state.json"
HOST, PORT = "127.0.0.1", 8775

DEFAULT = {
    "rcon": {"host": "127.0.0.1", "port": 25575, "password": "", "serverSoftware": "未判定", "serverVersionText": ""},
    "arena": {"x": 0, "y": 64, "z": 0, "width": 9, "depth": 9, "height": 12,
              "frameBlock": "minecraft:glass", "fillBlock": "minecraft:diamond_block", "maxHealth": 100,
              "floorEnabled": False, "floorDamage": 10, "floorPenalty": 1,
              "minWidth": 3, "maxWidth": 64, "minHeight": 3, "maxHeight": 64,
              "holdSeconds": 10, "holdWin": 1, "clearAfterSuccess": True,
              "daylightFixed": True, "clearWeather": True},
    "overlay": {"successText": "WIN！", "effectListStyle": {
        "columns": 5, "cardWidth": 180, "cardHeight": 180, "gap": 8, "borderRadius": 14,
        "backgroundColor": "#61294f", "borderColor": "#ef334e", "textColor": "#ffffff",
        "accentColor": "#a4f4bf", "feverGlowColor": "#ffd34e", "nameFontSize": 18, "effectFontSize": 20,
        "descriptionFontSize": 13, "imageSize": 74
    }},
    "multiplier": {"threshold": 5000, "durationSeconds": 300, "multiplier": 2,
                   "applyFill": True, "applyTnt": True, "applyWin": True, "applyRepair": True,
                   "applyItems": True, "applyResize": False, "applyCountdown": False, "applyPlayer": False, "stackingMode": "extend"},
    "commandDelayMs": 35,
    "winBridge": {"enabled": False, "url": "http://127.0.0.1:8765/api/minecraft-studio/win", "token": ""},
    "effects": {
        "demo-fill": {"name": "10ブロック埋め", "kind": "fill", "amount": 10, "win": 0,
                      "description": "埋め立てブロックを10個追加します"},
        "demo-tnt": {"name": "TNT", "kind": "tnt", "amount": 1,
                     "win": 0, "description": "TNTを1個落とし、枠内のブロックを爆破します。枠は壊れません"},
        "demo-shield": {"name": "シールド", "kind": "shield", "amount": 1, "win": 0,
                        "description": "次のブロック破壊を1回無効化します"},
        "demo-time-plus": {"name": "カウント＋5秒", "kind": "countdown", "countdownMode": "add",
                           "seconds": 5, "win": 0, "description": "カウントの残り時間を5秒増やします"},
        "demo-time-minus": {"name": "カウント－3秒", "kind": "countdown", "countdownMode": "add",
                            "seconds": -3, "win": 0, "description": "カウントの残り時間を3秒短くします"},
        "demo-all": {"name": "全埋め", "kind": "fill_all", "amount": 1, "win": 0,
                     "description": "枠内を埋める救済です。カウント完了でWINになります"},
        "demo-bomb": {"name": "全埋めボム補充", "kind": "bomb", "amount": 1, "win": 0, "description": "全埋めボムを1回補充。プレイヤーが右クリックで使用します"},
        "demo-chain": {"name": "連鎖ブロック補充", "kind": "chain", "amount": 1, "spreadBlocks": 27, "win": 0, "description": "連鎖ブロックを1回補充。置いた場所から27個へ広がります"},
        "demo-piercing": {"name": "貫通TNT", "kind": "tnt", "tntType": "piercing", "amount": 1, "win": 0, "description": "着弾した縦一列を破壊します"},
        "demo-timed": {"name": "時限TNT", "kind": "tnt", "tntType": "timed", "fuseSeconds": 5, "amount": 1, "win": 0, "description": "5秒後に爆発します"},
        "demo-giant": {"name": "巨大TNT", "kind": "tnt", "tntType": "giant", "amount": 1, "win": 0, "description": "広範囲を爆破。露出した底へのダメージは通常の4倍です"},
        "demo-expand": {"name": "横を拡大", "kind": "resize", "resizeAxis": "horizontal", "resizeDelta": 1, "amount": 1, "win": 0, "description": "幅と奥行を1ブロック拡大します"},
        "demo-shrink": {"name": "高さを縮小", "kind": "resize", "resizeAxis": "height", "resizeDelta": -1, "amount": 1, "win": 0, "description": "高さを1ブロック縮めます"},
        "demo-freeze": {"name": "移動停止", "kind": "freeze", "amount": 1, "seconds": 5, "win": 0, "description": "プレイヤーを5秒間動けなくします"},
        "demo-launch": {"name": "上へ吹き飛ばす", "kind": "launch", "amount": 1, "strength": 2, "win": 0, "description": "TNT演出でプレイヤーを上へ吹き飛ばします"},
        "demo-clear-all": {"name": "全消し", "kind": "clear_all", "amount": 1, "win": 0, "description": "枠を残して中のブロックを全消しします"},
    },
}

STATE_LOCK = Lock()
SAVE_LOCK = Lock()
COMMAND_QUEUE: Queue[str] = Queue(maxsize=100000)
WIN_QUEUE: Queue[dict] = Queue(maxsize=10000)
STATUS = {"rcon": "未接続", "lastError": "", "worldBridge": "未確認", "queuedCommands": 0, "pendingWin": 0}


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
    # Old bundled all-fill awarded WIN immediately, before the countdown.
    if raw.get("rulesVersion", 0) < 3:
        old_all = state.get("effects", {}).get("demo-all", {})
        if old_all.get("kind") == "fill_all" and old_all.get("win") == 100:
            old_all["win"] = 0
    state["rulesVersion"] = 3
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
          max_health=int(arena_config["maxHealth"]),
          floor_enabled=arena_config.get("floorEnabled", False) is True,
          floor_damage=int(arena_config.get("floorDamage", 10)), floor_penalty=int(arena_config.get("floorPenalty", 1)),
          min_width=int(arena_config.get("minWidth", 3)), max_width=int(arena_config.get("maxWidth", 64)),
          min_height=int(arena_config.get("minHeight", 3)), max_height=int(arena_config.get("maxHeight", 64)),
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
for name in ("repair", "items", "resize", "countdown", "player"):
    setattr(ENGINE.multiplier, "apply_" + name, multiplier_config.get("apply" + name.title(), name in {"repair", "items"}) is True)
ENGINE.multiplier.stacking_mode = multiplier_config.get("stackingMode", "extend")
ENGINE.multiplier.bonus = int(STATE.get("runtime", {}).get("feverBonus", 0))
ENGINE.multiplier.queued = int(STATE.get("runtime", {}).get("feverQueued", 0))
ENGINE.processed_events.update(STATE.get("runtime", {}).get("processedEvents", []))
WIN_OUTBOX = {event["eventId"]: event for event in STATE.get("runtime", {}).get("pendingWins", [])}
for event in WIN_OUTBOX.values():
    WIN_QUEUE.put_nowait(event)


def public_state():
    with STATE_LOCK:
        config = json.loads(json.dumps(STATE))
    config["rcon"]["password"] = "" if not config["rcon"].get("password") else "••••••••"
    config["winBridge"]["token"] = "" if not config["winBridge"].get("token") else "••••••••"
    with ENGINE.lock:
        previews = {key: resolve_effect(effect, 1, ENGINE.multiplier) for key, effect in config["effects"].items()}
    return {"version": APP_VERSION, "config": config, "effectPreviews": previews, "game": ENGINE.snapshot(), "status": status_snapshot(),
            "localServer": LOCAL_SERVER.status()}


def status_snapshot():
    return {**STATUS, "queuedCommands": COMMAND_QUEUE.qsize(), "pendingWin": WIN_QUEUE.qsize()}


def save_state():
    with SAVE_LOCK:
        with STATE_LOCK:
            STATE["runtime"] = {
                "totalCoins": ENGINE.multiplier.total_coins,
                "nextTarget": ENGINE.multiplier.next_target,
                "activeUntil": ENGINE.multiplier.active_until,
                "processedEvents": list(ENGINE.processed_events),
                "pendingWins": list(WIN_OUTBOX.values()),
                "feverBonus": ENGINE.multiplier.bonus, "feverQueued": ENGINE.multiplier.queued,
            }
            data = json.dumps(STATE, ensure_ascii=False, separators=(",", ":"))
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        temporary = STATE_FILE.with_suffix(".tmp")
        temporary.write_text(data, "utf-8")
        temporary.replace(STATE_FILE)


def queue_win(event):
    with STATE_LOCK:
        WIN_OUTBOX[event["eventId"]] = event
    WIN_QUEUE.put_nowait(event)


def queue_commands(commands):
    for command in commands:
        COMMAND_QUEUE.put_nowait(command)


def bridge_command(client, command):
    reply = client.command(command)
    try:
        result = json.loads(reply.strip())
    except (ValueError, AttributeError):
        raise RuntimeError("ゲーム連携プラグインが未起動です。サーバーを安全に停止してから起動し直してください")
    if not result.get("ok"):
        raise RuntimeError(result.get("message") or "Minecraft側で処理できませんでした")
    return result


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
                bridge_command(client, first)
                while True:
                    time.sleep(delay)
                    try:
                        command = COMMAND_QUEUE.get_nowait()
                    except Empty:
                        break
                    completed.append(command)
                    bridge_command(client, command)
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
            if delivered:
                with STATE_LOCK:
                    WIN_OUTBOX.pop(event["eventId"], None)
                save_state()
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
            with STATE_LOCK:
                rcon = dict(STATE["rcon"])
            if rcon.get("password"):
                with RconClient(rcon["host"], int(rcon["port"]), rcon["password"]) as client:
                    world = bridge_command(client, "lmsarena status")
                    revision_changed = world.get("active") and world.get("resizeRevision") != ENGINE.world_state.get("resizeRevision")
                    results = ENGINE.sync_world(world)
                    if revision_changed:
                        with STATE_LOCK:
                            for key in ("width", "depth", "height", "holdSeconds"):
                                STATE["arena"][key] = int(world[key])
                    for result in results:
                        if result["win"]:
                            queue_win({"eventId": result["eventId"], "amount": result["win"],
                                                 "reason": result["message"], "senderName": ""})
                    if results or revision_changed:
                        save_state()
                    for event in world.get("wins", []):
                        bridge_command(client, "lmsarena ack " + event["eventId"])
                STATUS.update(rcon="接続中", worldBridge="監視中" if world.get("ready") else ("枠を準備中" if world.get("active") else "枠を生成してください"))
        except Exception as exc:
            STATUS["worldBridge"] = str(exc)[:260]
            ENGINE.world_state = {}
        time.sleep(0.5)


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

    def _body(self, limit=2_000_000):
        length = int(self.headers.get("Content-Length", 0))
        if length > limit:
            raise ValueError("リクエストが大きすぎます")
        return json.loads(self.rfile.read(length) or b"{}")

    def do_GET(self):
        path = urlparse(self.path).path
        if path.startswith("/user-sounds/"):
            name = Path(path.removeprefix("/user-sounds/")).name
            target = SOUNDS_DIR / name
            if not name or not target.is_file():
                return self.send_error(404)
            data = target.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", mimetypes.guess_type(name)[0] or "application/octet-stream")
            self.send_header("Cache-Control", "public, max-age=31536000, immutable")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if path == "/api/state":
            return self._json(public_state())
        if path == "/api/overlay":
            game = ENGINE.snapshot()
            with STATE_LOCK:
                effects = [resolve_effect(e, 1, ENGINE.multiplier) for e in STATE["effects"].values()]
            with STATE_LOCK:
                overlay = dict(STATE.get("overlay", {}))
            return self._json({"game": game, "effects": effects, "overlay": overlay, "version": APP_VERSION})
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
            body = self._body(28_000_000 if path == "/api/sound-upload" else 2_000_000)
            if path == "/api/sound-upload":
                original = Path(str(body.get("name") or "sound")).name
                extension = Path(original).suffix.lower()
                allowed = {".mp3", ".wav", ".ogg", ".m4a", ".aac", ".webm", ".flac"}
                if extension not in allowed:
                    raise ValueError("MP3・WAV・OGG・M4A・AAC・WebM・FLACを選んでください")
                try:
                    data = base64.b64decode(str(body.get("data") or ""), validate=True)
                except (binascii.Error, ValueError):
                    raise ValueError("音声ファイルを読み込めませんでした")
                if not data or len(data) > 20_000_000:
                    raise ValueError("音声ファイルは20MB以内にしてください")
                SOUNDS_DIR.mkdir(parents=True, exist_ok=True)
                stored = secrets.token_hex(16) + extension
                (SOUNDS_DIR / stored).write_bytes(data)
                return self._json({"ok": True, "url": "/user-sounds/" + stored, "name": original})
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
                success = base64.b64encode(STATE["overlay"]["successText"].encode("utf-8")).decode("ascii")
                commands.append(f"lmsarena success_text {success}")
                commands.append(f"lmsarena environment {str(STATE['arena'].get('daylightFixed', True)).lower()} {str(STATE['arena'].get('clearWeather', True)).lower()}")
                with STATE_LOCK:
                    rcon = dict(STATE["rcon"])
                with RconClient(rcon["host"], int(rcon["port"]), rcon["password"]) as client:
                    for command in commands:
                        bridge_command(client, command)
                return self._json({"ok": True, "queued": len(commands)})
            if path == "/api/gift":
                if not ENGINE.world_state.get("ready"):
                    raise RuntimeError("先にサーバーへ接続して枠を生成してください")
                result = ENGINE.receive(body, STATE["effects"])
                queue_commands(result.get("commands", []))
                if result.get("win"):
                    queue_win({"eventId": result["eventId"], "amount": result["win"],
                                         "reason": result.get("message", "Minecraft効果"),
                                         "senderName": str(body.get("senderName") or "")[:80]})
                save_state()
                return self._json(result, 200 if result.get("ok") else 404)
            if path == "/api/test-effect":
                if not ENGINE.world_state.get("ready"):
                    raise RuntimeError("先にサーバーへ接続して枠を生成してください")
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
            if isinstance(body.get("overlay"), dict):
                if "successText" in body["overlay"]:
                    text = str(body["overlay"].get("successText", "WIN！")).strip()[:80]
                    STATE["overlay"]["successText"] = text or "WIN！"
                if isinstance(body["overlay"].get("effectListStyle"), dict):
                    style = body["overlay"]["effectListStyle"]
                    current = STATE["overlay"].setdefault("effectListStyle", {})
                    numeric = {"columns": (1, 10), "cardWidth": (100, 600), "cardHeight": (100, 600),
                               "gap": (0, 100), "borderRadius": (0, 100), "nameFontSize": (8, 80),
                               "effectFontSize": (8, 100), "descriptionFontSize": (8, 60), "imageSize": (0, 300)}
                    for key, bounds in numeric.items():
                        if key in style:
                            current[key] = int(clamp(style[key], bounds[0], bounds[1], current.get(key, bounds[0])))
                    for key in ("backgroundColor", "borderColor", "textColor", "accentColor", "feverGlowColor"):
                        value = str(style.get(key, current.get(key, ""))).strip()
                        if len(value) <= 40:
                            current[key] = value
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
                a.floor_enabled = config.get("floorEnabled", False) is True
                a.floor_damage = int(clamp(config.get("floorDamage", 10), 1, 1000000, 10))
                a.floor_penalty = int(clamp(config.get("floorPenalty", 1), 0, 1000000, 1))
                for key, attr in (("minWidth", "min_width"), ("maxWidth", "max_width"), ("minHeight", "min_height"), ("maxHeight", "max_height")):
                    setattr(a, attr, int(config.get(key, getattr(a, attr))))
                a.clear_after_success = config.get("clearAfterSuccess", True) is True
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
                for name in ("repair", "items", "resize", "countdown", "player"):
                    setattr(m, "apply_" + name, config.get("apply" + name.title(), name in {"repair", "items"}) is True)
                mode = config.get("stackingMode", "extend")
                m.stacking_mode = mode if mode in {"extend", "increase", "queue", "overwrite"} else "extend"
                if m.next_target <= m.total_coins:
                    m.next_target = (m.total_coins // m.threshold + 1) * m.threshold
            if isinstance(body.get("effects"), dict):
                STATE["effects"] = body["effects"]
        save_state()
        if ENGINE.world_state.get("active"):
            commands = []
            if isinstance(body.get("arena"), dict):
                commands.append(ENGINE.settings_command())
                commands.append(f"lmsarena environment {str(STATE['arena'].get('daylightFixed', True)).lower()} {str(STATE['arena'].get('clearWeather', True)).lower()}")
            if isinstance(body.get("overlay"), dict):
                encoded = base64.b64encode(STATE["overlay"]["successText"].encode("utf-8")).decode("ascii")
                commands.append(f"lmsarena success_text {encoded}")
            if commands:
                queue_commands(commands)


def make_server():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SOUNDS_DIR.mkdir(parents=True, exist_ok=True)
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

