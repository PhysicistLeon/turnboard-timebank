from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .models import OrderDir, PlayerConfig, Rules


@dataclass(slots=True)
class Command:
    now_mono: float


@dataclass(slots=True)
class CmdStartGame(Command):
    game_id: str
    players: list[PlayerConfig]
    order: list[str]
    order_dir: OrderDir
    rules: Rules


@dataclass(slots=True)
class CmdTap(Command):
    pass


@dataclass(slots=True)
class CmdTick(Command):
    pass


@dataclass(slots=True)
class CmdPauseOn(Command):
    cause: str


@dataclass(slots=True)
class CmdPauseOff(Command):
    pass


@dataclass(slots=True)
class CmdAdminAuth(Command):
    password: str


@dataclass(slots=True)
class CmdAdminModeOff(Command):
    pass


@dataclass(slots=True)
class CmdAdminEdit(Command):
    edit_type: Literal[
        "reorder",
        "reverse",
        "set_bank",
        "set_rules",
        "rename_player",
        "set_color",
        "set_sound_tap",
        "remove_player",
        "new_game",
        "undo",
    ]
    payload: dict


@dataclass(slots=True)
class CmdBackground(Command):
    pass


@dataclass(slots=True)
class CmdResume(Command):
    pass
