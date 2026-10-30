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
import random
import secrets
import time
import urllib.request
import webbrowser

from game_engine import Arena, GameEngine, MultiplierState, clamp, resolve_effect, resolve_effects
from rcon import RconClient
from local_server import LocalMinecraftServer


APP_VERSION = "0.4.8"
ROOT = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("LOCALAPPDATA", ROOT)) / "LiveMinecraftStudio"
SOUNDS_DIR = DATA_DIR / "sounds"
IMAGES_DIR = DATA_DIR / "images"
STATE_FILE = DATA_DIR / "state.json"
HOST, PORT = "127.0.0.1", 8775

DEFAULT = {
    "rcon": {"host": "127.0.0.1", "port": 25575, "password": "", "serverSoftware": "未判定", "serverVersionText": ""},
    "arena": {"x": 0, "y": 64, "z": 0, "width": 9, "depth": 9, "height": 12,
              "frameBlock": "minecraft:glass", "fillBlock": "minecraft:diamond_block", "maxHealth": 100,
              "floorEnabled": False, "floorDamage": 10, "floorPenalty": 1,
              "floorBreakSoundUrl": "", "floorBreakSoundVolume": 100, "floorBreakSoundSeconds": 0,
              "minWidth": 3, "maxWidth": 64, "minHeight": 3, "maxHeight": 64,
              "holdSeconds": 10, "holdWin": 1, "clearAfterSuccess": True,
              "topLayerWin": False, "gravityFill": False,
              "daylightFixed": True, "clearWeather": True},
    "overlay": {"successText": "WIN！",
        "arenaStyle": {"width": 620, "padding": 18, "borderRadius": 20, "backgroundOpacity": 88,
                       "titleFontSize": 26, "textFontSize": 16, "backgroundColor": "#080a0f",
                       "borderColor": "#ef334e", "textColor": "#ffffff", "accentColor": "#35bc75"},
        "feverStyle": {"width": 600, "padding": 22, "borderRadius": 18, "backgroundOpacity": 91,
                        "titleFontSize": 40, "timerFontSize": 42, "textFontSize": 22,
                        "backgroundColor": "#111521", "borderColor": "#ffd34e",
                        "textColor": "#ffffff", "accentColor": "#ffd34e"},
        "gachaStyle": {"width": 920, "padding": 24, "borderRadius": 24, "backgroundOpacity": 96,
                        "titleFontSize": 42, "senderFontSize": 25, "reelFontSize": 34,
                        "resultFontSize": 34, "continueFontSize": 29, "backgroundColor": "#1d0d28",
                        "borderColor": "#ef334e", "textColor": "#ffffff", "accentColor": "#ffd34e"},
        "effectListStyle": {
        "columns": 5, "cardWidth": 180, "cardHeight": 180, "gap": 8, "borderRadius": 14,
        "backgroundColor": "#61294f", "borderColor": "#ef334e", "textColor": "#ffffff",
        "accentColor": "#a4f4bf", "feverGlowColor": "#ffd34e", "nameFontSize": 18, "effectFontSize": 20,
        "descriptionFontSize": 13, "imageSize": 74
    }},
    "multiplier": {"enabled": True, "waitingText": "次のフィーバーまで", "threshold": 5000, "durationSeconds": 300, "multiplier": 2,
                   "applyFill": True, "applyTnt": True, "applyWin": True, "applyRepair": True,
                   "applyItems": True, "applyResize": False, "applyCountdown": False, "applyPlayer": False, "stackingMode": "extend",
                   "feverStartSoundUrl": "", "feverStartSoundVolume": 100, "feverStartSoundSeconds": 0,
                   "feverEndSoundUrl": "", "feverEndSoundVolume": 100, "feverEndSoundSeconds": 0,
                   "feverLevelSoundUrl": "", "feverLevelSoundVolume": 100, "feverLevelSoundSeconds": 0},
    "commandDelayMs": 35,
    "gachas": {},
    "social": {"followEnabled": False, "followTarget": "", "individualLikeEnabled": False,
               "individualLikeEvery": 100, "individualLikeTarget": "", "totalLikeEnabled": False,
               "totalLikeEvery": 1000, "totalLikeTarget": ""},
    "socialRuntime": {"followedUsers": [], "individualLikes": {}, "totalLikes": 0},
    "winBridge": {"enabled": False, "url": "http://127.0.0.1:8765/api/minecraft-studio/win", "token": ""},
    # Effects are user-managed. Never repopulate deleted sample cards on startup.
    "effects": {},
}

STATE_LOCK = Lock()
SAVE_LOCK = Lock()
COMMAND_QUEUE: Queue[str] = Queue(maxsize=100000)
WIN_QUEUE: Queue[dict] = Queue(maxsize=10000)
STATUS = {"rcon": "未接続", "lastError": "", "worldBridge": "未確認", "queuedCommands": 0, "pendingWin": 0}
GACHA_EVENTS: list[dict] = []
GACHA_LOCK = Lock()


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
    # User-managed collections must not be merged with bundled samples on restart.
    if isinstance(raw.get("effects"), dict):
        state["effects"] = raw["effects"]
    if isinstance(raw.get("gachas"), dict):
        state["gachas"] = raw["gachas"]
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
          clear_after_success=arena_config.get("clearAfterSuccess", True) is True,
          top_layer_win=arena_config.get("topLayerWin", False) is True,
          gravity_fill=arena_config.get("gravityFill", False) is True),
    MultiplierState(enabled=multiplier_config.get("enabled", True) is True,
                    threshold=int(multiplier_config["threshold"]),
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
FEVER_WAS_ACTIVE = ENGINE.multiplier.active()
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
        previews = {}
        for key, effect in config["effects"].items():
            actions = resolve_effects(effect, 1, ENGINE.multiplier)
            preview = dict(actions[0])
            preview["effectiveLabel"] = effect_preview_label(effect, actions)
            preview["feverApplied"] = ENGINE.multiplier.active() and effect.get("useMultiplier", True) is not False
            preview["resolvedEffects"] = actions
            previews[key] = preview
    return {"version": APP_VERSION, "config": config, "effectPreviews": previews, "game": ENGINE.snapshot(), "status": status_snapshot(),
            "localServer": LOCAL_SERVER.status()}


def status_snapshot():
    return {**STATUS, "queuedCommands": COMMAND_QUEUE.qsize(), "pendingWin": WIN_QUEUE.qsize()}


def effect_preview_label(effect, actions):
    combined = " ＋ ".join(action["effectiveLabel"] for action in actions)
    text = str(effect.get("displayText") or "").strip()
    if not text or not actions:
        return combined
    first = actions[0]
    replacements = {"amount": first.get("amount", 0), "seconds": first.get("seconds", 0),
                    "strength": f'{first.get("strength", 0):g}', "size": first.get("resizeDelta", 0),
                    "effects": combined, "name": "ギフター名",
                    "gift": effect.get("giftName") or effect.get("name") or "ギフト"}
    for key, value in replacements.items():
        text = text.replace("{" + key + "}", str(value))
    return text[:200]


def effect_image_url(effect):
    mode = str(effect.get("imageMode") or "gift")
    if mode == "none":
        return ""
    if mode == "custom":
        return str(effect.get("customImageUrl") or "")[:1000]
    return str(effect.get("giftImageUrl") or "")[:1000]


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


def queue_system_sound(config, prefix):
    url = str(config.get(prefix + "SoundUrl") or "")[:500]
    if not url.startswith("/user-sounds/"):
        return
    notice = {"eventId": prefix + "-" + secrets.token_hex(10), "at": time.time(), "text": "", "sender": "",
              "duration": 1, "display": False, "soundUrl": url,
              "soundVolume": int(clamp(config.get(prefix + "SoundVolume", 100), 0, 100, 100)),
              "soundSeconds": float(clamp(config.get(prefix + "SoundSeconds", 0), 0, 600, 0))}
    with ENGINE.lock:
        ENGINE.announcements.append(notice)
        ENGINE.announcements = ENGINE.announcements[-50:]


def handle_multiplier_sounds(result):
    if result.get("multiplierActivations", 0):
        queue_system_sound(STATE.get("multiplier", {}), "feverStart")
    if result.get("multiplierLevelUps", 0):
        queue_system_sound(STATE.get("multiplier", {}), "feverLevel")


def minecraft_announcement(text, sender, duration=4):
    notice = {"text": str(text)[:200], "sender": str(sender)[:80], "duration": int(clamp(duration, 1, 30, 4))}
    encoded = base64.b64encode(json.dumps(notice, ensure_ascii=False).encode()).decode()
    return "lmsarena announce " + encoded


def dispatch_effect(result, sender_name=""):
    queue_commands(result.get("commands", []))
    if result.get("win"):
        queue_win({"eventId": result["eventId"], "amount": result["win"],
                   "reason": result.get("message", "Minecraft効果"), "senderName": str(sender_name)[:80]})
    for action in result.get("effects", []):
        if action.get("kind") == "gacha" and action.get("gachaId"):
            start_gacha(str(action["gachaId"]), sender_name, result["eventId"])


def weighted_index(entries):
    weights = [max(0.0, float(item.get("weight", 0))) for item in entries]
    total = sum(weights)
    if total <= 0:
        return random.randrange(len(entries))
    pick = random.random() * total
    for index, weight in enumerate(weights):
        pick -= weight
        if pick <= 0:
            return index
    return len(entries) - 1


def start_gacha(gacha_id, sender_name, parent_event=None):
    with STATE_LOCK:
        config = json.loads(json.dumps(STATE.get("gachas", {}).get(gacha_id, {})))
    if not config or config.get("enabled", True) is False:
        return False
    entries = [item for item in config.get("entries", []) if item.get("effectId") in STATE.get("effects", {})
               and STATE["effects"][item["effectId"]].get("enabled", True) is not False]
    if not entries:
        return False
    event_base = str(parent_event or ("gacha-" + secrets.token_hex(8)))

    def run():
        max_spins = int(clamp(config.get("maxSpins", 20), 1, 100, 20))
        for spin in range(max_spins):
            index = weighted_index(entries)
            selected = entries[index]
            effect_id = str(selected["effectId"])
            effect = STATE.get("effects", {}).get(effect_id, {})
            continued = (config.get("continueEnabled") is True and spin + 1 < max_spins and
                         random.random() * 100 < float(clamp(config.get("continueRate", 70), 0, 100, 70)))
            event_id = f"{event_base}-spin-{spin+1}"
            event = {"eventId": event_id, "at": time.time(), "gachaId": gacha_id,
                     "gachaName": str(config.get("name") or "スピナーガチャ")[:100],
                     "sender": str(sender_name)[:80], "items": [str(item.get("label") or STATE["effects"].get(item.get("effectId"), {}).get("name") or "効果")[:80] for item in entries],
                     "resultIndex": index, "resultLabel": str(selected.get("label") or effect.get("name") or "効果")[:100],
                     "spinSeconds": float(clamp(config.get("spinSeconds", 5), 1, 30, 5)), "continued": continued,
                     "continueEnabled": config.get("continueEnabled") is True,
                     "giftSoundUrl": str(config.get("giftSoundUrl") or "") if spin == 0 else "",
                     "spinSoundUrl": str(config.get("spinSoundUrl") or ""), "resultSoundUrl": str(config.get("resultSoundUrl") or ""),
                     "giftSoundVolume": int(clamp(config.get("giftSoundVolume", config.get("soundVolume", 100)), 0, 100, 100)),
                     "giftSoundSeconds": float(clamp(config.get("giftSoundSeconds", 0), 0, 600, 0)),
                     "spinSoundVolume": int(clamp(config.get("spinSoundVolume", config.get("soundVolume", 100)), 0, 100, 100)),
                     "spinSoundSeconds": float(clamp(config.get("spinSoundSeconds", 0), 0, 600, 0)),
                     "resultSoundVolume": int(clamp(config.get("resultSoundVolume", config.get("soundVolume", 100)), 0, 100, 100)),
                     "resultSoundSeconds": float(clamp(config.get("resultSoundSeconds", 0), 0, 600, 0))}
            with GACHA_LOCK:
                GACHA_EVENTS.append(event); del GACHA_EVENTS[:-100]
            queue_commands([minecraft_announcement(event["gachaName"], event["sender"], max(3, int(event["spinSeconds"])))])
            time.sleep(event["spinSeconds"])
            continuation_text = " ＋ 継続！" if continued else " ／ 継続終了" if config.get("continueEnabled") is True else ""
            queue_commands([minecraft_announcement(event["resultLabel"] + continuation_text, event["sender"], 4)])
            payload = {"eventId": event_id + "-effect", "giftId": effect_id, "giftName": effect.get("name", ""),
                       "senderName": sender_name, "repeatCount": 1, "coins": 0, "source": "gacha"}
            result = ENGINE.receive(payload, STATE["effects"])
            dispatch_effect(result, sender_name)
            save_state()
            if not continued:
                break
            time.sleep(float(clamp(config.get("continueDelaySeconds", 2), .2, 10, 2)))
    Thread(target=run, daemon=True).start()
    return True


def trigger_target(target, sender_name, event_id):
    target = str(target or "")
    if target.startswith("gacha:"):
        return start_gacha(target.split(":", 1)[1], sender_name, event_id)
    effect_id = target.split(":", 1)[1] if target.startswith("effect:") else target
    if effect_id not in STATE.get("effects", {}):
        return False
    result = ENGINE.receive({"eventId": event_id, "giftId": effect_id, "senderName": sender_name,
                             "repeatCount": 1, "coins": 0, "source": "social"}, STATE["effects"])
    dispatch_effect(result, sender_name)
    return True


def trigger_gachas_for_gift(body, event_id, already_triggered=None):
    gift_id = str(body.get("giftId") or "")
    gift_name = str(body.get("giftName") or "")
    sender = str(body.get("senderName") or "")[:80]
    skipped = set(already_triggered or [])
    with STATE_LOCK:
        matches = [(gacha_id, dict(gacha)) for gacha_id, gacha in STATE.get("gachas", {}).items()
                   if gacha.get("enabled", True) is not False and gacha_id not in skipped and
                   ((gift_id and str(gacha.get("triggerGiftId") or "") == gift_id) or
                    (gift_name and str(gacha.get("triggerGiftName") or "") == gift_name))]
    started = 0
    for gacha_id, _ in matches:
        if start_gacha(gacha_id, sender, f"{event_id}-direct-{gacha_id}"):
            started += 1
    return started


def _social_kind(body):
    raw = str(body.get("type") or body.get("eventType") or body.get("event") or
              body.get("eventName") or body.get("name") or "").lower().replace("-", "_")
    if "follow" in raw:
        return "follow"
    if "like" in raw:
        return "like"
    return raw


def receive_social(body):
    kind = _social_kind(body)
    user = body.get("user") if isinstance(body.get("user"), dict) else {}
    sender = body.get("sender") if isinstance(body.get("sender"), dict) else {}
    user_id = str(body.get("userId") or body.get("uniqueId") or body.get("senderId") or
                  user.get("uniqueId") or user.get("userId") or user.get("id") or
                  sender.get("uniqueId") or sender.get("userId") or sender.get("id") or
                  body.get("userName") or user.get("nickname") or sender.get("nickname") or "")[:160]
    user_name = str(body.get("userName") or body.get("senderName") or body.get("nickname") or
                    user.get("nickname") or user.get("displayName") or user.get("uniqueId") or
                    sender.get("nickname") or sender.get("displayName") or sender.get("uniqueId") or user_id)[:80]
    with STATE_LOCK:
        runtime = STATE.setdefault("socialRuntime", {"followedUsers": [], "individualLikes": {}, "totalLikes": 0})
        targets = [("effect:" + item_id, item) for item_id, item in STATE.get("effects", {}).items()
                   if item.get("enabled", True) is not False]
        targets += [("gacha:" + item_id, item) for item_id, item in STATE.get("gachas", {}).items()
                    if item.get("enabled", True) is not False]
        triggers = []
        if kind == "follow":
            followed = set(runtime.get("followedUsers", []))
            if user_id and user_id not in followed:
                followed.add(user_id); runtime["followedUsers"] = list(followed)[-100000:]
                triggers += [(target, "follow") for target, item in targets if item.get("followTriggerEnabled") is True]
        elif kind == "like":
            count = int(clamp(body.get("count", body.get("likeCount", body.get("repeatCount", 1))), 1, 1000000, 1))
            likes = runtime.setdefault("individualLikes", {}); before = int(likes.get(user_id, 0)); likes[user_id] = before + count
            total_before = int(runtime.get("totalLikes", 0)); runtime["totalLikes"] = total_before + count
            for target, item in targets:
                if item.get("individualLikeTriggerEnabled") is True and user_id:
                    every = int(clamp(item.get("individualLikeEvery", 100), 1, 100000000, 100))
                    triggers += [(target, "individual-like")] * min(20, likes[user_id] // every - before // every)
                if item.get("totalLikeTriggerEnabled") is True:
                    every = int(clamp(item.get("totalLikeEvery", 1000), 1, 100000000, 1000))
                    triggers += [(target, "total-like")] * min(20, runtime["totalLikes"] // every - total_before // every)
        else:
            raise ValueError("typeはfollowまたはlikeを指定してください")
    for index, (target, label) in enumerate(triggers):
        trigger_target(target, user_name, f"social-{label}-{secrets.token_hex(8)}-{index}")
    save_state()
    return {"ok": True, "triggered": len(triggers), "newFollow": kind == "follow" and bool(triggers),
            "totalLikes": STATE.get("socialRuntime", {}).get("totalLikes", 0)}


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
    global FEVER_WAS_ACTIVE
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
                        if result.get("message") == "底の耐久ゼロ":
                            queue_system_sound(STATE.get("arena", {}), "floorBreak")
                    if results or revision_changed:
                        save_state()
                    for event in world.get("wins", []):
                        bridge_command(client, "lmsarena ack " + event["eventId"])
                STATUS.update(rcon="接続中", worldBridge="監視中" if world.get("ready") else ("枠を準備中" if world.get("active") else "枠を生成してください"))
        except Exception as exc:
            STATUS["worldBridge"] = str(exc)[:260]
            ENGINE.world_state = {}
        fever_active = ENGINE.multiplier.active()
        if FEVER_WAS_ACTIVE and not fever_active:
            queue_system_sound(STATE.get("multiplier", {}), "feverEnd")
            save_state()
        FEVER_WAS_ACTIVE = fever_active
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
        if path.startswith("/user-images/"):
            name = Path(path.removeprefix("/user-images/")).name
            target = IMAGES_DIR / name
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
                effects = []
                for effect in STATE["effects"].values():
                    if effect.get("enabled", True) is False or effect.get("overlayVisible", True) is False:
                        continue
                    actions = resolve_effects(effect, 1, ENGINE.multiplier)
                    preview = dict(actions[0])
                    preview["effectiveLabel"] = effect_preview_label(effect, actions)
                    preview["feverApplied"] = ENGINE.multiplier.active() and effect.get("useMultiplier", True) is not False
                    preview["name"] = str(effect.get("name", ""))[:100]
                    preview["giftImageUrl"] = effect_image_url(effect)
                    effects.append(preview)
                for gacha_id, gacha in STATE.get("gachas", {}).items():
                    if gacha.get("enabled", True) is False or gacha.get("showInEffectList", True) is False:
                        continue
                    entries = [entry for entry in gacha.get("entries", []) if entry.get("effectId") in STATE["effects"]]
                    total = sum(max(0, float(entry.get("weight", 0))) for entry in entries) or 1
                    details = [f'{entry.get("label") or STATE["effects"][entry["effectId"]].get("name", "効果")} {max(0,float(entry.get("weight",0)))/total*100:.1f}%'
                               for entry in entries]
                    gacha_name = str(gacha.get("name") or "スピナーガチャ")
                    effects.append({"name": "", "effectiveLabel": gacha_name,
                                    "description": "", "overlayVisible": True,
                                    "useCustomStyle": False, "kind": "gacha-card", "feverApplied": ENGINE.multiplier.active(),
                                    "giftImageUrl": gacha.get("triggerGiftImageUrl", "")})
                overlay = dict(STATE.get("overlay", {}))
                multiplier_config = {"waitingText": STATE.get("multiplier", {}).get("waitingText", "次のフィーバーまで")}
            with GACHA_LOCK:
                gacha_events = list(GACHA_EVENTS)
            return self._json({"game": game, "effects": effects, "overlay": overlay, "multiplierConfig": multiplier_config,
                               "gachaEvents": gacha_events, "version": APP_VERSION})
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
            body = self._body(28_000_000 if path == "/api/sound-upload" else 8_000_000 if path == "/api/image-upload" else 2_000_000)
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
            if path == "/api/image-upload":
                original = Path(str(body.get("name") or "image")).name
                extension = Path(original).suffix.lower()
                allowed = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
                if extension not in allowed:
                    raise ValueError("PNG・JPG・GIF・WebPを選んでください")
                try:
                    data = base64.b64decode(str(body.get("data") or ""), validate=True)
                except (binascii.Error, ValueError):
                    raise ValueError("画像ファイルを読み込めませんでした")
                if not data or len(data) > 5_000_000:
                    raise ValueError("画像ファイルは5MB以内にしてください")
                IMAGES_DIR.mkdir(parents=True, exist_ok=True)
                stored = secrets.token_hex(16) + extension
                (IMAGES_DIR / stored).write_bytes(data)
                return self._json({"ok": True, "url": "/user-images/" + stored, "name": original})
            if path == "/api/config":
                self._update_config(body)
                return self._json({"ok": True, "state": public_state()})
            if path == "/api/social":
                return self._json(receive_social(body))
            if path == "/api/test-gacha":
                if not ENGINE.world_state.get("ready"):
                    raise RuntimeError("先にサーバーへ接続して枠を生成してください")
                gacha_id = str(body.get("gachaId") or "")
                if not start_gacha(gacha_id, "テスト", "test-gacha-" + secrets.token_hex(8)):
                    raise ValueError("ガチャの中身を1つ以上設定してください")
                return self._json({"ok": True, "message": "ガチャテストを開始しました"})
            if path == "/api/reset-social":
                with STATE_LOCK:
                    STATE["socialRuntime"] = {"followedUsers": [], "individualLikes": {}, "totalLikes": 0}
                save_state()
                return self._json({"ok": True, "message": "フォロー・いいね履歴をリセットしました", "state": public_state()})
            if path == "/api/reset-all":
                with ENGINE.lock:
                    m = ENGINE.multiplier
                    m.total_coins = 0
                    m.next_target = max(1, m.threshold)
                    m.active_until = 0
                    m.bonus = 0
                    m.queued = 0
                commands = ENGINE.frame_commands()
                success = base64.b64encode(STATE["overlay"]["successText"].encode("utf-8")).decode("ascii")
                commands.append(f"lmsarena success_text {success}")
                commands.append(f"lmsarena environment {str(STATE['arena'].get('daylightFixed', True)).lower()} {str(STATE['arena'].get('clearWeather', True)).lower()}")
                with STATE_LOCK:
                    rcon = dict(STATE["rcon"])
                with RconClient(rcon["host"], int(rcon["port"]), rcon["password"]) as client:
                    for command in commands:
                        bridge_command(client, command)
                save_state()
                return self._json({"ok": True, "message": "倍率・耐久・埋め立て・枠サイズをリセットしました", "state": public_state()})
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
                if str(body.get("eventType") or body.get("type") or "").lower() in {"follow", "like"}:
                    return self._json(receive_social(body))
                if _social_kind(body) in {"follow", "like"}:
                    return self._json(receive_social(body))
                if not ENGINE.world_state.get("ready"):
                    raise RuntimeError("先にサーバーへ接続して枠を生成してください")
                result = ENGINE.receive(body, STATE["effects"])
                handle_multiplier_sounds(result)
                dispatch_effect(result, body.get("senderName", ""))
                if not result.get("duplicate"):
                    action_gachas = {str(action.get("gachaId")) for action in result.get("effects", [])
                                     if action.get("kind") == "gacha" and action.get("gachaId")}
                    result["gachasStarted"] = trigger_gachas_for_gift(body, result["eventId"], action_gachas)
                save_state()
                return self._json(result, 200 if result.get("ok") else 404)
            if path == "/api/test-effect":
                if not ENGINE.world_state.get("ready"):
                    raise RuntimeError("先にサーバーへ接続して枠を生成してください")
                gift_id = str(body.get("giftId") or "")
                payload = {"eventId": "test-" + secrets.token_hex(8), "giftId": gift_id,
                           "senderName": "テスト", "coins": body.get("coins", 0), "repeatCount": 1, "source": "test"}
                result = ENGINE.receive(payload, STATE["effects"])
                dispatch_effect(result, "テスト")
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
                for style_key in ("arenaStyle", "feverStyle", "gachaStyle"):
                    if not isinstance(body["overlay"].get(style_key), dict):
                        continue
                    style = body["overlay"][style_key]
                    current = STATE["overlay"].setdefault(style_key, {})
                    numeric = {"width": (260, 1920), "padding": (0, 100), "borderRadius": (0, 100),
                               "backgroundOpacity": (0, 100), "titleFontSize": (10, 120),
                               "textFontSize": (8, 80), "timerFontSize": (10, 140),
                               "senderFontSize": (8, 100), "reelFontSize": (10, 120),
                               "resultFontSize": (10, 120), "continueFontSize": (10, 120)}
                    for key, bounds in numeric.items():
                        if key in style:
                            current[key] = int(clamp(style[key], bounds[0], bounds[1], current.get(key, bounds[0])))
                    for key in ("backgroundColor", "borderColor", "textColor", "accentColor"):
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
                config["floorBreakSoundUrl"] = str(config.get("floorBreakSoundUrl") or "")[:500]
                config["floorBreakSoundVolume"] = int(clamp(config.get("floorBreakSoundVolume", 100), 0, 100, 100))
                config["floorBreakSoundSeconds"] = float(clamp(config.get("floorBreakSoundSeconds", 0), 0, 600, 0))
                for key, attr in (("minWidth", "min_width"), ("maxWidth", "max_width"), ("minHeight", "min_height"), ("maxHeight", "max_height")):
                    setattr(a, attr, int(config.get(key, getattr(a, attr))))
                a.clear_after_success = config.get("clearAfterSuccess", True) is True
                a.top_layer_win = config.get("topLayerWin", False) is True
                a.gravity_fill = config.get("gravityFill", False) is True
                a.normalize()
            if isinstance(body.get("multiplier"), dict):
                old_threshold = ENGINE.multiplier.threshold
                STATE["multiplier"].update(body["multiplier"])
                config = STATE["multiplier"]
                m = ENGINE.multiplier
                m.enabled = config.get("enabled", True) is True
                config["waitingText"] = str(config.get("waitingText") or "次のフィーバーまで")[:100]
                if not m.enabled:
                    m.active_until = 0
                    m.bonus = 0
                    m.queued = 0
                m.threshold = int(clamp(config["threshold"], 1, 10**9, 5000))
                if m.threshold != old_threshold:
                    m.next_target = (m.total_coins // m.threshold + 1) * m.threshold
                m.duration_seconds = int(clamp(config["durationSeconds"], 1, 86400, 300))
                m.multiplier = clamp(config["multiplier"], 1, 100, 2)
                m.apply_fill = config.get("applyFill", True) is True
                m.apply_tnt = config.get("applyTnt", True) is True
                m.apply_win = config.get("applyWin", True) is True
                for name in ("repair", "items", "resize", "countdown", "player"):
                    setattr(m, "apply_" + name, config.get("apply" + name.title(), name in {"repair", "items"}) is True)
                mode = config.get("stackingMode", "extend")
                m.stacking_mode = mode if mode in {"extend", "increase", "queue", "overwrite"} else "extend"
                for prefix in ("feverStart", "feverEnd", "feverLevel"):
                    config[prefix + "SoundUrl"] = str(config.get(prefix + "SoundUrl") or "")[:500]
                    config[prefix + "SoundVolume"] = int(clamp(config.get(prefix + "SoundVolume", 100), 0, 100, 100))
                    config[prefix + "SoundSeconds"] = float(clamp(config.get(prefix + "SoundSeconds", 0), 0, 600, 0))
                if m.next_target <= m.total_coins:
                    m.next_target = (m.total_coins // m.threshold + 1) * m.threshold
            if isinstance(body.get("effects"), dict):
                STATE["effects"] = body["effects"]
            if isinstance(body.get("gachas"), dict):
                cleaned = {}
                for gacha_id, raw in list(body["gachas"].items())[:100]:
                    if not isinstance(raw, dict): continue
                    item = dict(raw); item["name"] = str(item.get("name") or "スピナーガチャ")[:100]
                    item["spinSeconds"] = float(clamp(item.get("spinSeconds", 5), 1, 30, 5))
                    item["continueRate"] = float(clamp(item.get("continueRate", 70), 0, 100, 70))
                    item["maxSpins"] = int(clamp(item.get("maxSpins", 20), 1, 100, 20))
                    item["continueDelaySeconds"] = float(clamp(item.get("continueDelaySeconds", 2), .2, 10, 2))
                    item["soundVolume"] = int(clamp(item.get("soundVolume", 100), 0, 100, 100))
                    for prefix in ("gift", "spin", "result"):
                        volume_key = prefix + "SoundVolume"; seconds_key = prefix + "SoundSeconds"
                        item[volume_key] = int(clamp(item.get(volume_key, item.get("soundVolume", 100)), 0, 100, 100))
                        item[seconds_key] = float(clamp(item.get(seconds_key, 0), 0, 600, 0))
                    item["triggerGiftId"] = str(item.get("triggerGiftId") or "")[:160]
                    item["triggerGiftName"] = str(item.get("triggerGiftName") or "")[:160]
                    item["triggerGiftImageUrl"] = str(item.get("triggerGiftImageUrl") or "")[:1000]
                    for key in ("followTriggerEnabled", "individualLikeTriggerEnabled", "totalLikeTriggerEnabled"):
                        item[key] = item.get(key) is True
                    item["individualLikeEvery"] = int(clamp(item.get("individualLikeEvery", 100), 1, 100000000, 100))
                    item["totalLikeEvery"] = int(clamp(item.get("totalLikeEvery", 1000), 1, 100000000, 1000))
                    item["entries"] = [dict(entry) for entry in item.get("entries", [])[:100] if isinstance(entry, dict)]
                    cleaned[str(gacha_id)[:160]] = item
                STATE["gachas"] = cleaned
            if isinstance(body.get("social"), dict):
                STATE["social"].update(body["social"])
                STATE["social"]["individualLikeEvery"] = int(clamp(STATE["social"].get("individualLikeEvery", 100), 1, 100000000, 100))
                STATE["social"]["totalLikeEvery"] = int(clamp(STATE["social"].get("totalLikeEvery", 1000), 1, 100000000, 1000))
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
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
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

