from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from time import time
from typing import Any
import hashlib
import math
import base64
import json


def clamp(value: Any, low: float, high: float, fallback: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = fallback
    return max(low, min(high, number))


@dataclass
class MultiplierState:
    threshold: int = 5000
    duration_seconds: int = 300
    multiplier: float = 2.0
    total_coins: int = 0
    next_target: int = 5000
    active_until: float = 0.0
    apply_fill: bool = True
    apply_tnt: bool = True
    apply_win: bool = True
    apply_repair: bool = True
    apply_items: bool = True
    apply_resize: bool = False
    apply_countdown: bool = False
    apply_player: bool = False
    stacking_mode: str = "extend"
    bonus: int = 0
    queued: int = 0

    def _advance(self, now: float):
        while self.active_until and now >= self.active_until and self.queued:
            self.active_until += self.duration_seconds
            self.queued -= 1
            self.bonus = 0
        if now >= self.active_until:
            self.bonus = 0

    def active(self, now: float | None = None) -> bool:
        now = time() if now is None else now
        self._advance(now)
        return now < self.active_until

    def add_coins(self, coins: int, now: float | None = None) -> int:
        now = time() if now is None else now
        self._advance(now)
        self.total_coins += max(0, int(coins))
        if self.total_coins < self.next_target:
            return 0
        activations = (self.total_coins - self.next_target) // max(1, self.threshold) + 1
        self.next_target += activations * max(1, self.threshold)
        remaining = activations
        if not self.active(now):
            self.active_until = now + self.duration_seconds
            self.bonus = 0
            remaining -= 1
        if self.stacking_mode == "increase":
            self.bonus = min(98, self.bonus + remaining)
        elif self.stacking_mode == "queue":
            self.queued += remaining
        elif self.stacking_mode == "overwrite":
            self.active_until = now + self.duration_seconds
        else:
            self.active_until += remaining * self.duration_seconds
        return activations

    def factor(self, category: str, now: float | None = None) -> float:
        enabled = getattr(self, "apply_" + category, False)
        return min(100, self.multiplier + self.bonus) if self.active(now) and enabled else 1.0

    def snapshot(self, now: float | None = None) -> dict[str, Any]:
        now = time() if now is None else now
        active = self.active(now)
        return {
            "threshold": self.threshold, "durationSeconds": self.duration_seconds,
            "multiplier": min(100, self.multiplier + self.bonus) if active else self.multiplier,
            "baseMultiplier": self.multiplier, "totalCoins": self.total_coins,
            "nextTarget": self.next_target, "progress": self.total_coins % max(1, self.threshold),
            "active": active, "remainingSeconds": max(0, math.ceil(self.active_until - now)),
            "stackingMode": self.stacking_mode, "queued": self.queued,
            **{"apply" + name.title(): getattr(self, "apply_" + name)
               for name in ("fill", "tnt", "win", "repair", "items", "resize", "countdown", "player")},
        }


def resolve_effect(effect: dict[str, Any], repeat: int, multiplier: MultiplierState) -> dict[str, Any]:
    """The sole gift scaling boundary, shared by execution and all previews."""
    e = dict(effect)
    kind = str(e.get("kind") or "fill")
    category = {"fill_all": "fill", "fill_layers": "fill", "fill_percent": "fill", "bomb": "items", "chain": "items", "shield": "items", "clear": "tnt", "freeze": "player", "launch": "player"}.get(kind, kind)
    enabled = e.get("useMultiplier", True) is not False
    now = time()
    factor = multiplier.factor(category, now) if enabled else 1.0
    amount = max(0, int(clamp(e.get("amount", 1), 0, 1000000, 1))) * repeat
    e["amount"] = math.ceil(amount * factor)
    if kind == "tnt": e["amount"] = min(256, max(0, e["amount"]))
    e["win"] = int(round(int(clamp(e.get("win", 0), -10**9, 10**9, 0)) * repeat *
                         (multiplier.factor("win", now) if enabled else 1)))
    e["seconds"] = int(round(int(clamp(e.get("seconds", effect.get("amount", 1)), -3600, 3600, 1)) * repeat * factor))
    if kind == "freeze": e["seconds"] = int(clamp(e["seconds"], 1, 600, 5))
    e["strength"] = clamp(clamp(e.get("strength", 2), .1, 10, 2) * factor, .1, 10, 2)
    delta = int(clamp(e.get("resizeDelta", 1), -64, 64, 1))
    e["resizeDelta"] = (1 if delta >= 0 else -1) * math.ceil(abs(delta) * repeat * factor)
    e["feverApplied"] = factor != 1
    e["resolvedAmount"] = e["amount"]
    labels = {"fill": "ブロック", "fill_layers": "段", "fill_percent": "%", "tnt": "個", "repair": "回復", "bomb": "回補充", "chain": "回補充", "clear": "ブロック"}
    e["effectiveLabel"] = (f'サイズ {e["resizeDelta"]:+}' if kind == "resize" else
                           f'規定カウント {e["seconds"]:+}秒' if kind == "countdown" else
                           f'移動停止 {e["seconds"]}秒' if kind == "freeze" else
                           f'吹き飛ばし 強さ{e["strength"]:g}' if kind == "launch" else
                           "全埋め" if kind == "fill_all" else "全消し" if kind == "clear_all" else f'{e["amount"]}{labels.get(kind, "回")}')
    return e


@dataclass
class Arena:
    x: int = 0
    y: int = 64
    z: int = 0
    width: int = 9
    depth: int = 9
    height: int = 12
    frame_block: str = "minecraft:glass"
    fill_block: str = "minecraft:diamond_block"
    max_health: int = 100
    floor_enabled: bool = False
    floor_damage: int = 10
    floor_penalty: int = 1
    min_width: int = 3
    max_width: int = 64
    min_height: int = 3
    max_height: int = 64
    hold_seconds: int = 10
    hold_win: int = 1
    clear_after_success: bool = True

    def normalize(self) -> None:
        self.min_width = int(clamp(self.min_width, 3, 64, 3))
        self.max_width = int(clamp(self.max_width, self.min_width, 64, 64))
        self.min_height = int(clamp(self.min_height, 3, 64, 3))
        self.max_height = int(clamp(self.max_height, self.min_height, 64, 64))
        self.width = int(clamp(self.width, 3, 64, 9))
        self.depth = int(clamp(self.depth, 3, 64, 9))
        self.height = int(clamp(self.height, 3, 64, 12))
        self.max_health = int(clamp(self.max_health, 1, 100000, 100))
        self.hold_seconds = int(clamp(self.hold_seconds, 1, 3600, 10))
        self.hold_win = int(clamp(self.hold_win, 0, 1000000, 1))

    @property
    def capacity(self) -> int:
        return self.width * self.depth * self.height

class GameEngine:
    """Thread-safe game rules. RCON I/O is deliberately kept outside this class."""

    def __init__(self, arena: Arena | None = None, multiplier: MultiplierState | None = None):
        self.arena = arena or Arena()
        self.world_state: dict[str, Any] = {}
        self.multiplier = multiplier or MultiplierState()
        self.lock = Lock()
        self.processed_events: set[str] = set()
        self.history: list[dict[str, Any]] = []
        self.announcements: list[dict[str, Any]] = []

    def _event_id(self, payload: dict[str, Any]) -> str:
        supplied = str(payload.get("eventId") or "").strip()
        if supplied:
            return supplied[:160]
        raw = "|".join(str(payload.get(k, "")) for k in ("giftId", "senderName", "coins", "timestamp"))
        return "gift-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]

    def receive(self, payload: dict[str, Any], effects: dict[str, dict[str, Any]]) -> dict[str, Any]:
        with self.lock:
            event_id = self._event_id(payload)
            if event_id in self.processed_events:
                return {"ok": True, "duplicate": True, "eventId": event_id, "commands": [], "win": 0}

            gift_id = str(payload.get("giftId") or "")
            gift_name = str(payload.get("giftName") or "")
            effect = effects.get(gift_id) or effects.get(gift_name)
            if not effect:
                effect = {"kind": "none", "name": gift_name or "コイン集計", "amount": 0}

            repeat = max(1, int(clamp(payload.get("repeatCount", 1), 1, 10000, 1)))
            coins = max(0, int(clamp(payload.get("coins", 0), 0, 10**9, 0))) * repeat
            activations = self.multiplier.add_coins(coins)
            result = self._apply_effect(effect, repeat)
            self.processed_events.add(event_id)
            entry = {
                "eventId": event_id,
                "giftId": gift_id,
                "senderName": str(payload.get("senderName") or "")[:80],
                "coins": coins,
                "effect": str(effect.get("name") or gift_id)[:100],
                "win": result["win"],
                "at": time(),
            }
            self.history.append(entry)
            self.history = self.history[-500:]
            resolved = result["resolved"]
            display_enabled = effect.get("displayEnabled", True) is not False and resolved.get("kind") != "none"
            sound_url = str(effect.get("soundUrl") or "")[:500]
            sound_enabled = effect.get("soundEnabled", False) is True and sound_url.startswith("/user-sounds/")
            if display_enabled or sound_enabled:
                text = str(effect.get("displayText") or resolved["effectiveLabel"])[:200]
                for key, val in {"amount": resolved["amount"], "seconds": resolved["seconds"], "strength": f'{resolved["strength"]:g}',
                                 "name": entry["senderName"], "gift": gift_name, "size": resolved["resizeDelta"]}.items():
                    text = text.replace("{" + key + "}", str(val))
                notice = {"eventId": event_id, "at": time(), "text": text,
                          "sender": entry["senderName"] if effect.get("showSender", True) is not False else "",
                          "duration": int(clamp(effect.get("displaySeconds", 4), 1, 30, 4)),
                          "display": display_enabled,
                          "soundUrl": sound_url if sound_enabled else "",
                          "soundVolume": int(clamp(effect.get("soundVolume", 100), 0, 100, 100)),
                          "soundSeconds": float(clamp(effect.get("soundSeconds", 0), 0, 600, 0))}
                self.announcements.append(notice)
                self.announcements = self.announcements[-50:]
                if display_enabled:
                    encoded = base64.b64encode(json.dumps(notice, ensure_ascii=False).encode()).decode()
                    result["commands"].append("lmsarena announce " + encoded)
            return {
                "ok": True,
                "duplicate": False,
                "eventId": event_id,
                "commands": result["commands"],
                "win": result["win"],
                "message": result["message"],
                "multiplierActivations": activations,
            }

    def _apply_effect(self, effect: dict[str, Any], repeat: int) -> dict[str, Any]:
        """Send intent to the server; never invent block counts or explosion damage."""
        kind = str(effect.get("kind") or "fill")
        effect = resolve_effect(effect, repeat, self.multiplier)
        amount = effect["amount"]
        win = effect["win"]
        commands: list[str] = []
        message = str(effect.get("name") or kind)
        if kind == "fill":
            commands = [f"lmsarena fill {min(amount, self.arena.capacity)}"]
        elif kind == "fill_all":
            commands = ["lmsarena fill_all"]
        elif kind == "fill_layers":
            commands = [f"lmsarena fill_layers {min(amount, self.arena.height)}"]
        elif kind == "fill_percent":
            commands = [f"lmsarena fill_percent {min(amount, 100)}"]
        elif kind == "tnt":
            count = min(256, max(1, amount))
            mode = effect.get("tntType", "normal")
            if mode not in {"normal", "piercing", "timed", "giant"}: mode = "normal"
            fuse = int(clamp(effect.get("fuseSeconds", 3), 1, 60, 3)) * 20
            commands = [f"lmsarena tnt {count} {mode} {fuse}"]
        elif kind == "shield":
            commands = [f"lmsarena shield {max(1, amount)}"]
        elif kind == "countdown":
            mode = "set" if effect.get("countdownMode") == "set" else "add"
            seconds = effect["seconds"]
            commands = [f"lmsarena countdown {mode} {seconds}"]
        elif kind == "clear":
            commands = [f"lmsarena clear {min(amount or self.arena.capacity, self.arena.capacity)}"]
        elif kind == "repair":
            commands = [f"lmsarena repair {amount}"]
        elif kind == "bomb":
            commands = [f"lmsarena bomb {amount}"]
        elif kind == "chain":
            spread = int(clamp(effect.get("spreadBlocks", 27), 1, 10000, 27))
            commands = [f"lmsarena chain {amount} {spread}"]
        elif kind == "resize":
            axis = effect.get("resizeAxis", "both")
            if axis not in {"horizontal", "height", "both"}: axis = "both"
            commands = [f"lmsarena resize {axis} {effect['resizeDelta']}"]
        elif kind == "clear_all":
            commands = ["lmsarena clear_all"]
        elif kind == "freeze":
            commands = [f"lmsarena freeze {effect['seconds']}"]
        elif kind == "launch":
            commands = [f"lmsarena launch {effect['strength']:g}"]
        return {"commands": commands, "win": win, "message": message, "resolved": effect}

    def sync_world(self, state: dict[str, Any]) -> list[dict[str, Any]]:
        """Only server-confirmed completion events can award WIN."""
        with self.lock:
            previous_revision = self.world_state.get("resizeRevision")
            self.world_state = dict(state)
            if state.get("active") and state.get("resizeRevision") != previous_revision:
                for key in ("width", "depth", "height"):
                    if state.get(key): setattr(self.arena, key, int(state[key]))
                if state.get("holdSeconds"): self.arena.hold_seconds = int(state["holdSeconds"])
            results = []
            for event in state.get("wins", []):
                event_id = str(event["eventId"])
                if event_id in self.processed_events:
                    continue
                self.processed_events.add(event_id)
                win = int(round(int(event["win"]) * self.multiplier.factor("win")))
                reason = str(event.get("reason") or "WIN")
                entry = {"eventId": event_id, "effect": reason, "win": win, "at": time()}
                self.history.append(entry)
                self.history = self.history[-500:]
                results.append({**entry, "message": reason, "commands": []})
            return results

    def tick(self, now: float | None = None):
        # Countdown and success run on the Minecraft main thread, including manual placements.
        return None

    def frame_commands(self) -> list[str]:
        a = self.arena
        a.normalize()
        return [
            f"lmsarena generate world {a.x} {a.y} {a.z} {a.width} {a.depth} {a.height} "
            f"{a.frame_block} {a.fill_block} {a.hold_seconds} {a.hold_win} {str(a.clear_after_success).lower()} "
            f"{str(a.floor_enabled).lower()} {a.max_health} {a.floor_damage} {a.floor_penalty} "
            f"{a.min_width} {a.max_width} {a.min_height} {a.max_height}",
        ]

    def settings_command(self) -> str:
        a = self.arena
        a.normalize()
        return (f"lmsarena settings {a.hold_seconds} {a.hold_win} {str(a.clear_after_success).lower()} "
                f"{str(a.floor_enabled).lower()} {a.max_health} {a.floor_damage} {a.floor_penalty} "
                f"{a.min_width} {a.max_width} {a.min_height} {a.max_height}")

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            s = self.world_state
            return {
                "arena": {
                    "x": self.arena.x, "y": self.arena.y, "z": self.arena.z,
                    "width": self.arena.width, "depth": self.arena.depth, "height": self.arena.height,
                    "frameBlock": self.arena.frame_block, "fillBlock": self.arena.fill_block,
                    "bombCharges": s.get("bombCharges", 0), "chainCharges": s.get("chainCharges", 0),
                    "actualWidth": s.get("width", self.arena.width), "actualDepth": s.get("depth", self.arena.depth), "actualHeight": s.get("height", self.arena.height),
                    "filled": s.get("filled", 0), "capacity": s.get("capacity") or self.arena.capacity,
                    "holdSeconds": s.get("holdSeconds", self.arena.hold_seconds),
                    "holdRemainingSeconds": s.get("holdRemainingSeconds", 0),
                    "defending": bool(s.get("defending")), "holdWin": self.arena.hold_win,
                    "clearAfterSuccess": self.arena.clear_after_success,
                    "shieldCharges": s.get("shieldCharges", 0),
                    "floorEnabled": s.get("floorEnabled", self.arena.floor_enabled),
                    "health": s.get("health", self.arena.max_health), "maxHealth": s.get("maxHealth", self.arena.max_health),
                    "completedRounds": s.get("completedRounds", 0),
                    "worldReady": s.get("ready", False), "active": s.get("active", False),
                },
                "multiplier": self.multiplier.snapshot(),
                "history": list(reversed(self.history[-20:])),
                "announcements": list(self.announcements),
            }

