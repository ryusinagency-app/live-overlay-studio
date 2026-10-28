from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock
from time import time
from typing import Any
import hashlib
import math


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

    def active(self, now: float | None = None) -> bool:
        return (now if now is not None else time()) < self.active_until

    def add_coins(self, coins: int, now: float | None = None) -> int:
        now = now if now is not None else time()
        self.total_coins += max(0, int(coins))
        activations = 0
        while self.total_coins >= self.next_target:
            activations += 1
            self.next_target += max(1, self.threshold)
        if activations:
            base = max(now, self.active_until)
            self.active_until = base + activations * self.duration_seconds
        return activations

    def factor(self, category: str, now: float | None = None) -> float:
        if not self.active(now):
            return 1.0
        enabled = {
            "fill": self.apply_fill,
            "tnt": self.apply_tnt,
            "win": self.apply_win,
        }.get(category, False)
        return self.multiplier if enabled else 1.0

    def snapshot(self, now: float | None = None) -> dict[str, Any]:
        now = now if now is not None else time()
        return {
            "threshold": self.threshold,
            "durationSeconds": self.duration_seconds,
            "multiplier": self.multiplier,
            "totalCoins": self.total_coins,
            "nextTarget": self.next_target,
            "progress": self.total_coins % max(1, self.threshold),
            "active": self.active(now),
            "remainingSeconds": max(0, math.ceil(self.active_until - now)),
            "applyFill": self.apply_fill,
            "applyTnt": self.apply_tnt,
            "applyWin": self.apply_win,
        }


@dataclass
class Arena:
    x: int = 0
    y: int = 64
    z: int = 0
    width: int = 9
    depth: int = 9
    height: int = 12
    frame_block: str = "minecraft:obsidian"
    fill_block: str = "minecraft:stone"
    max_health: int = 100
    health: int = 100
    hold_seconds: int = 10
    hold_win: int = 1
    clear_after_success: bool = True
    full_since: float = 0.0
    shield_charges: int = 0
    completed_rounds: int = 0
    filled: set[tuple[int, int, int]] = field(default_factory=set)

    def normalize(self) -> None:
        self.width = int(clamp(self.width, 3, 64, 9))
        self.depth = int(clamp(self.depth, 3, 64, 9))
        self.height = int(clamp(self.height, 3, 64, 12))
        self.max_health = int(clamp(self.max_health, 1, 100000, 100))
        self.health = int(clamp(self.health, 0, self.max_health, self.max_health))
        self.hold_seconds = int(clamp(self.hold_seconds, 1, 3600, 10))
        self.hold_win = int(clamp(self.hold_win, 0, 1000000, 1))

    @property
    def capacity(self) -> int:
        return self.width * self.depth * self.height

    def interior_positions(self):
        for dy in range(self.height):
            for dz in range(self.depth):
                for dx in range(self.width):
                    yield self.x + dx, self.y + dy, self.z + dz

    def unfilled_positions(self):
        for pos in self.interior_positions():
            if pos not in self.filled:
                yield pos


class GameEngine:
    """Thread-safe game rules. RCON I/O is deliberately kept outside this class."""

    def __init__(self, arena: Arena | None = None, multiplier: MultiplierState | None = None):
        self.arena = arena or Arena()
        self.multiplier = multiplier or MultiplierState()
        self.lock = Lock()
        self.processed_events: set[str] = set()
        self.history: list[dict[str, Any]] = []

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
                return {"ok": False, "ignored": True, "eventId": event_id, "message": "未設定のギフトです"}

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
        kind = str(effect.get("kind") or "fill")
        amount = max(0, int(clamp(effect.get("amount", 1), 0, 1000000, 1))) * repeat
        win = int(clamp(effect.get("win", 0), -10**9, 10**9, 0)) * repeat
        commands: list[str] = []
        message = str(effect.get("name") or kind)

        if kind in {"fill", "fill_all"}:
            factor = self.multiplier.factor("fill")
            wanted = self.arena.capacity if kind == "fill_all" else int(math.ceil(amount * factor))
            added = list(self.arena.unfilled_positions())[:wanted]
            for pos in added:
                self.arena.filled.add(pos)
            commands.extend(self._block_commands(added, self.arena.fill_block))
        elif kind == "tnt":
            count = max(1, int(math.ceil(amount * self.multiplier.factor("tnt"))))
            center_x = self.arena.x + self.arena.width // 2
            center_z = self.arena.z + self.arena.depth // 2
            top_y = self.arena.y + self.arena.height + 2
            for index in range(count):
                ox = (index % 3) - 1
                oz = ((index // 3) % 3) - 1
                commands.append(f"summon tnt {center_x + ox} {top_y} {center_z + oz} {{Fuse:60}}")
            damage = max(0, int(clamp(effect.get("damage", amount), 0, 100000, amount)))
            if self.arena.shield_charges > 0:
                self.arena.shield_charges -= 1
                message += "／シールドで防御"
            else:
                self.arena.health = max(0, self.arena.health - damage * count)
                broken = min(len(self.arena.filled), max(1, int(clamp(effect.get("breakBlocks", count), 1, 100000, count))))
                for pos in list(self.arena.filled)[:broken]:
                    self.arena.filled.discard(pos)
                if broken:
                    self.arena.full_since = 0.0
        elif kind == "repair":
            self.arena.health = min(self.arena.max_health, self.arena.health + amount)
        elif kind == "shield":
            self.arena.shield_charges += max(1, amount)
        elif kind == "countdown":
            if self.arena.full_since:
                mode = str(effect.get("countdownMode") or "add")
                seconds = int(clamp(effect.get("seconds", amount), -3600, 3600, amount))
                now = time()
                if mode == "set":
                    remaining = int(clamp(seconds, 0, 3600, self.arena.hold_seconds))
                    self.arena.full_since = now - (self.arena.hold_seconds - remaining)
                else:
                    # Moving the start forward increases the remaining time;
                    # moving it backward decreases it.
                    self.arena.full_since += seconds
                message += f"／残り時間{'変更' if mode == 'set' else ('追加' if seconds >= 0 else '短縮')}"
            else:
                message += "／カウント開始前のため待機"
        elif kind == "clear":
            positions = list(self.arena.filled)[:amount or len(self.arena.filled)]
            for pos in positions:
                self.arena.filled.discard(pos)
            commands.extend(self._block_commands(positions, "air"))
            if positions:
                self.arena.full_since = 0.0

        if self.arena.health <= 0:
            win += int(clamp(effect.get("breakWin", -100), -10**9, 0, -100))
            self.arena.health = self.arena.max_health
            message += "／耐久ゲージ破壊"
        win = int(round(win * self.multiplier.factor("win")))
        if len(self.arena.filled) >= self.arena.capacity and not self.arena.full_since:
            self.arena.full_since = time()
        return {"commands": commands, "win": win, "message": message}

    @staticmethod
    def _block_commands(positions: list[tuple[int, int, int]], block: str) -> list[str]:
        """Compress adjacent X positions into /fill commands to avoid RCON floods."""
        rows: dict[tuple[int, int], list[int]] = {}
        for x, y, z in positions:
            rows.setdefault((y, z), []).append(x)
        commands: list[str] = []
        for (y, z), xs in rows.items():
            xs = sorted(set(xs)); start = previous = xs[0]
            for x in xs[1:] + [None]:
                if x is not None and x == previous + 1:
                    previous = x
                    continue
                if start == previous:
                    commands.append(f"setblock {start} {y} {z} {block}")
                else:
                    commands.append(f"fill {start} {y} {z} {previous} {y} {z} {block}")
                if x is not None:
                    start = previous = x
        return commands

    def tick(self, now: float | None = None) -> dict[str, Any] | None:
        """Complete one defended full-arena round. Called by a lightweight 4Hz timer."""
        now = now if now is not None else time()
        with self.lock:
            a = self.arena
            if len(a.filled) < a.capacity:
                a.full_since = 0.0
                return None
            if not a.full_since:
                a.full_since = now
                return None
            if now - a.full_since < a.hold_seconds:
                return None
            a.completed_rounds += 1
            event_id = f"arena-complete-{a.completed_rounds}-{int(now * 1000)}"
            commands: list[str] = []
            if a.clear_after_success:
                commands.append(
                    f"fill {a.x} {a.y} {a.z} {a.x + a.width - 1} {a.y + a.height - 1} {a.z + a.depth - 1} air"
                )
                a.filled.clear()
            a.full_since = 0.0
            win = int(round(a.hold_win * self.multiplier.factor("win", now)))
            self.history.append({"eventId": event_id, "effect": "全埋め防衛成功", "win": win, "at": now})
            self.history = self.history[-500:]
            return {"eventId": event_id, "commands": commands, "win": win, "message": "全埋めを守り切りました"}

    def frame_commands(self) -> list[str]:
        a = self.arena
        a.normalize()
        x1, y1, z1 = a.x - 1, a.y - 1, a.z - 1
        x2, y2, z2 = a.x + a.width, a.y + a.height, a.z + a.depth
        block = a.frame_block
        return [
            f"fill {x1} {y1} {z1} {x2} {y1} {z2} {block}",
            f"fill {x1} {y2} {z1} {x2} {y2} {z2} {block} outline",
            f"fill {x1} {y1} {z1} {x1} {y2} {z2} {block} outline",
            f"fill {x2} {y1} {z1} {x2} {y2} {z2} {block} outline",
            f"fill {x1} {y1} {z1} {x2} {y2} {z1} {block} outline",
            f"fill {x1} {y1} {z2} {x2} {y2} {z2} {block} outline",
            f"fill {a.x} {a.y} {a.z} {a.x + a.width - 1} {a.y + a.height - 1} {a.z + a.depth - 1} air",
        ]

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            return {
                "arena": {
                    "x": self.arena.x, "y": self.arena.y, "z": self.arena.z,
                    "width": self.arena.width, "depth": self.arena.depth, "height": self.arena.height,
                    "frameBlock": self.arena.frame_block, "fillBlock": self.arena.fill_block,
                    "health": self.arena.health, "maxHealth": self.arena.max_health,
                    "filled": len(self.arena.filled), "capacity": self.arena.capacity,
                    "holdSeconds": self.arena.hold_seconds,
                    "holdRemainingSeconds": max(0, math.ceil(self.arena.hold_seconds - (time() - self.arena.full_since))) if self.arena.full_since else 0,
                    "defending": bool(self.arena.full_since), "holdWin": self.arena.hold_win,
                    "clearAfterSuccess": self.arena.clear_after_success,
                    "shieldCharges": self.arena.shield_charges,
                    "completedRounds": self.arena.completed_rounds,
                },
                "multiplier": self.multiplier.snapshot(),
                "history": list(reversed(self.history[-20:])),
            }
