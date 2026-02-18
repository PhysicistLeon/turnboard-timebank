from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Mode(str, Enum):
    SETUP = "setup"
    RUNNING = "running"
    TECH_PAUSE = "tech_pause"


class TurnPhase(str, Enum):
    COOLDOWN = "cooldown"
    COUNTDOWN = "countdown"


class OrderDir(str, Enum):
    CLOCKWISE = "clockwise"
    COUNTERCLOCKWISE = "counterclockwise"


@dataclass(slots=True)
class PlayerConfig:
    name: str
    color: str = "#FFFFFF"
    sound_tap: str = ""
    sound_warn: str = ""


@dataclass(slots=True)
class Rules:
    bank_initial: float = 600.0
    cooldown: float = 5.0
    warn_every: int = 60
    warn_sound: str = ""
    blink_min_hz: float = 1.0 / 60.0
    blink_max_hz: float = 1.0


@dataclass(slots=True)
class TurnRuntime:
    turn_started_mono: float = 0.0
    phase_started_mono: float = 0.0
    phase: TurnPhase = TurnPhase.COOLDOWN
    elapsed_no_cooldown: float = 0.0
    warn_count: int = 0


@dataclass(slots=True)
class GameState:
    game_id: str = ""
    mode: Mode = Mode.SETUP
    players: list[PlayerConfig] = field(default_factory=list)
    order: list[str] = field(default_factory=list)
    order_dir: OrderDir = OrderDir.CLOCKWISE
    rules: Rules = field(default_factory=Rules)
    bank: dict[str, float] = field(default_factory=dict)
    current_player: str | None = None
    turn: TurnRuntime = field(default_factory=TurnRuntime)
    admin_mode: bool = False
    game_started: bool = False
    last_turn_end: dict[str, Any] | None = None

    def player_names(self) -> list[str]:
        return [player.name for player in self.players]

    def ensure_bank_initialized(self) -> None:
        for name in self.order:
            self.bank.setdefault(name, self.rules.bank_initial)
