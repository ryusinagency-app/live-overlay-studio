from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Course:
    world: str = "world"
    start_x: float = 0
    start_y: float = 64
    start_z: float = 0
    goal_x: float = 0
    goal_y: float = 160
    goal_z: float = 0
    goal_radius: float = 4
    checkpoint_rise: int = 20
    goal_win: int = 1


@dataclass
class MultiplierState:
    enabled: bool = True
    threshold: int = 5000
    duration_seconds: int = 300
    multiplier: int = 2
    progress: int = 0
    active_until: float = 0

    def add_coins(self, coins: int) -> bool:
        if not self.enabled or coins <= 0:
            return False
        self.progress += coins
        started = False
        while self.progress >= max(1, self.threshold):
            self.progress -= max(1, self.threshold)
            self.active_until = max(self.active_until, time.time()) + self.duration_seconds
            started = True
        return started

    def factor(self) -> int:
        return self.multiplier if self.enabled and self.active_until > time.time() else 1

    def snapshot(self) -> dict[str, Any]:
        remaining = max(0, int(self.active_until - time.time()))
        return {"enabled": self.enabled, "active": remaining > 0, "multiplier": self.factor(),
                "remainingSeconds": remaining, "progress": self.progress, "threshold": self.threshold}


@dataclass
class GameEngine:
    course: Course = field(default_factory=Course)
    multiplier: MultiplierState = field(default_factory=MultiplierState)
    world_state: dict[str, Any] = field(default_factory=dict)
    announcements: list[dict[str, Any]] = field(default_factory=list)

    def configure_command(self) -> str:
        c = self.course
        return (f"lmsmountain configure {c.world} {c.start_x:g} {c.start_y:g} {c.start_z:g} "
                f"{c.goal_x:g} {c.goal_y:g} {c.goal_z:g} {c.goal_radius:g} {c.checkpoint_rise} {c.goal_win}")

    def effect_command(self, action: dict[str, Any], factor: int = 1) -> str:
        kind = str(action.get("kind", "tnt"))
        amount = max(1, int(float(action.get("amount", 1))))
        if action.get("multiply", True):
            amount *= max(1, factor)
        return f"lmsmountain effect {kind} {amount}"

    def receive(self, effect: dict[str, Any], sender: str = "", coins: int = 0) -> dict[str, Any]:
        self.multiplier.add_coins(coins)
        factor = self.multiplier.factor() if effect.get("applyMultiplier", True) else 1
        actions = effect.get("actions") or [{"kind": effect.get("kind", "tnt"),
                                             "amount": effect.get("amount", 1), "multiply": True}]
        commands = [self.effect_command(a, factor) for a in actions]
        title = str(effect.get("displayText") or effect.get("name") or "効果発動")
        event = {"eventId": str(time.time_ns()), "at": time.time(), "title": title, "sender": sender,
                 "imageUrl": effect.get("imageUrl", ""), "soundUrl": effect.get("soundUrl", ""),
                 "soundVolume": effect.get("soundVolume", 100), "soundSeconds": effect.get("soundSeconds", 0)}
        self.announcements = (self.announcements + [event])[-100:]
        return {"commands": commands, "announcement": event}

    def update_world(self, state: dict[str, Any]) -> None:
        self.world_state = dict(state or {})

    def snapshot(self) -> dict[str, Any]:
        c = self.course
        return {"course": {"world": c.world, "startX": c.start_x, "startY": c.start_y, "startZ": c.start_z,
                           "goalX": c.goal_x, "goalY": c.goal_y, "goalZ": c.goal_z,
                           "goalRadius": c.goal_radius, "checkpointRise": c.checkpoint_rise,
                           "goalWin": c.goal_win, **self.world_state},
                "multiplier": self.multiplier.snapshot(), "announcements": list(self.announcements)}
