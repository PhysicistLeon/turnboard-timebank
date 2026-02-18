from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict

from .commands import (
    CmdAdminAuth,
    CmdAdminEdit,
    CmdAdminModeOff,
    CmdBackground,
    CmdPauseOff,
    CmdPauseOn,
    CmdResume,
    CmdStartGame,
    CmdTap,
    CmdTick,
    Command,
)
from .events import Event, ev
from .models import GameState, Mode, OrderDir, PlayerConfig, Rules, TurnPhase


class CommandError(ValueError):
    """Raised when command cannot be applied in current state."""


class Decider:
    def __init__(self, admin_password: str):
        self.admin_password = admin_password

    @staticmethod
    def _next_player(order: list[str], current: str, order_dir: OrderDir) -> str:
        idx = order.index(current)
        shift = 1 if order_dir == OrderDir.CLOCKWISE else -1
        return order[(idx + shift) % len(order)]

    @staticmethod
    def _advance_runtime(state: GameState, now_mono: float) -> list[Event]:
        if state.mode != Mode.RUNNING or state.current_player is None:
            return []

        events: list[Event] = []
        elapsed_since_phase = max(0.0, now_mono - state.turn.phase_started_mono)

        if state.turn.phase == TurnPhase.COOLDOWN and elapsed_since_phase >= state.rules.cooldown:
            state.turn.phase = TurnPhase.COUNTDOWN
            state.turn.phase_started_mono += state.rules.cooldown
            events.append(ev("COOLDOWN_END", player=state.current_player))
            elapsed_since_phase = max(0.0, now_mono - state.turn.phase_started_mono)

        if state.turn.phase == TurnPhase.COUNTDOWN:
            spent = elapsed_since_phase
            state.turn.elapsed_no_cooldown = spent
            bank_before = state.bank[state.current_player]
            state.bank[state.current_player] = bank_before - spent
            state.turn.phase_started_mono = now_mono
            warn_every = max(1, state.rules.warn_every)
            warn_count = int(state.turn.elapsed_no_cooldown // warn_every)
            while state.turn.warn_count < warn_count:
                state.turn.warn_count += 1
                events.append(
                    ev(
                        "WARN_LONG_TURN",
                        player=state.current_player,
                        warn_no=state.turn.warn_count,
                        elapsed_no_cooldown=round(
                            state.turn.warn_count * warn_every,
                            3,
                        ),
                    )
                )
        return events

    @staticmethod
    def _runtime_sync_event(state: GameState, shadow: GameState, now_mono: float) -> Event | None:
        if state.mode != Mode.RUNNING or state.current_player is None:
            return None

        if (
            shadow.bank.get(state.current_player) == state.bank.get(state.current_player)
            and shadow.turn.phase == state.turn.phase
            and shadow.turn.phase_started_mono == state.turn.phase_started_mono
            and shadow.turn.elapsed_no_cooldown == state.turn.elapsed_no_cooldown
            and shadow.turn.warn_count == state.turn.warn_count
        ):
            return None

        return ev(
            "RUNTIME_SYNC",
            player=state.current_player,
            bank_after=shadow.bank[state.current_player],
            phase=shadow.turn.phase.value,
            phase_started_mono=shadow.turn.phase_started_mono,
            elapsed_no_cooldown=shadow.turn.elapsed_no_cooldown,
            warn_count=shadow.turn.warn_count,
            now_mono=now_mono,
        )

    def decide(self, state: GameState, command: Command) -> list[Event]:
        shadow = deepcopy(state)
        pre_events = self._advance_runtime(shadow, command.now_mono)
        runtime_sync = self._runtime_sync_event(state, shadow, command.now_mono)
        if runtime_sync is not None:
            pre_events.append(runtime_sync)

        if isinstance(command, CmdStartGame):
            return self._decide_start(command)
        if isinstance(command, CmdTap):
            return self._decide_tap(shadow, command, pre_events)
        if isinstance(command, CmdTick):
            return pre_events
        if isinstance(command, (CmdPauseOn, CmdBackground)):
            return self._decide_pause_on(state, command, pre_events)
        if isinstance(command, (CmdPauseOff, CmdResume)):
            return self._decide_pause_off(state, command, pre_events)
        if isinstance(command, CmdAdminAuth):
            event_name = (
                "ADMIN_AUTH_OK" if command.password == self.admin_password else "ADMIN_AUTH_FAIL"
            )
            return [ev(event_name)]
        if isinstance(command, CmdAdminModeOff):
            return pre_events + [ev("ADMIN_MODE_OFF")] if state.admin_mode else pre_events
        if isinstance(command, CmdAdminEdit):
            return self._decide_admin_edit(state, command, pre_events)

        raise CommandError(f"Unsupported command {type(command)!r}")

    @staticmethod
    def _decide_start(command: CmdStartGame) -> list[Event]:
        names = [player.name for player in command.players]
        if len(set(names)) != len(names):
            raise CommandError("Player names must be unique")
        if set(command.order) != set(names):
            raise CommandError("Order must include all players")

        return [
            ev(
                "GAME_START",
                game_id=command.game_id,
                order=command.order,
                order_dir=command.order_dir.value,
                rules=asdict(command.rules),
                players=[asdict(player) for player in command.players],
                now_mono=command.now_mono,
            ),
            ev(
                "TURN_START",
                player=command.order[0],
                phase=TurnPhase.COOLDOWN.value,
                now_mono=command.now_mono,
            ),
        ]

    def _decide_tap(
        self,
        runtime_state: GameState,
        command: CmdTap,
        pre_events: list[Event],
    ) -> list[Event]:
        if runtime_state.mode != Mode.RUNNING or runtime_state.current_player is None:
            raise CommandError("Tap available only in running mode")

        current = runtime_state.current_player
        next_player = self._next_player(runtime_state.order, current, runtime_state.order_dir)
        return pre_events + [
            ev(
                "TURN_END",
                player=current,
                bank_after=runtime_state.bank[current],
                spent_no_cooldown=runtime_state.turn.elapsed_no_cooldown,
                now_mono=command.now_mono,
            ),
            ev(
                "TURN_START",
                player=next_player,
                phase=TurnPhase.COOLDOWN.value,
                now_mono=command.now_mono,
            ),
        ]

    @staticmethod
    def _decide_pause_on(
        state: GameState,
        command: CmdPauseOn | CmdBackground,
        pre_events: list[Event],
    ) -> list[Event]:
        if state.mode != Mode.RUNNING:
            return pre_events
        cause = command.cause if isinstance(command, CmdPauseOn) else "background"
        return pre_events + [ev("TECH_PAUSE_ON", cause=cause, now_mono=command.now_mono)]

    @staticmethod
    def _decide_pause_off(
        state: GameState,
        command: CmdPauseOff | CmdResume,
        pre_events: list[Event],
    ) -> list[Event]:
        if state.mode != Mode.TECH_PAUSE:
            return pre_events
        cause = "resume" if isinstance(command, CmdResume) else "continue"
        return pre_events + [ev("TECH_PAUSE_OFF", cause=cause, now_mono=command.now_mono)]

    @staticmethod
    def _decide_admin_edit(
        state: GameState,
        command: CmdAdminEdit,
        pre_events: list[Event],
    ) -> list[Event]:
        if not state.game_started:
            return [
                ev(
                    "SETUP_EDIT",
                    edit_type=command.edit_type,
                    payload=command.payload,
                )
            ]
        if not state.admin_mode:
            raise CommandError("Admin mode is required")
        return pre_events + [
            ev(
                "ADMIN_EDIT",
                edit_type=command.edit_type,
                payload=command.payload,
            )
        ]


def _apply_edit(state: GameState, etype: str, payload: dict) -> None:
    if etype == "reorder":
        state.order = payload["new_order"]
    elif etype == "reverse":
        state.order_dir = (
            OrderDir.COUNTERCLOCKWISE
            if state.order_dir == OrderDir.CLOCKWISE
            else OrderDir.CLOCKWISE
        )
    elif etype == "set_bank":
        state.bank[payload["player"]] = float(payload["value"])
    elif etype == "set_rules":
        for key, value in payload.items():
            setattr(state.rules, key, value)
    elif etype == "rename_player":
        old = payload["old"]
        new = payload["new"]
        if old in state.bank:
            state.bank[new] = state.bank.pop(old)
        state.order = [new if value == old else value for value in state.order]
        if state.current_player == old:
            state.current_player = new
        for player in state.players:
            if player.name == old:
                player.name = new
    elif etype == "set_color":
        for player in state.players:
            if player.name == payload["player"]:
                player.color = payload["value"]
    elif etype == "set_sound_tap":
        for player in state.players:
            if player.name == payload["player"]:
                player.sound_tap = payload["value"]
    elif etype == "remove_player":
        target = payload["player"]
        if target not in state.order or len(state.order) <= 1:
            return

        idx = state.order.index(target)
        state.order = [name for name in state.order if name != target]
        state.bank.pop(target, None)
        state.players = [player for player in state.players if player.name != target]

        if state.current_player == target:
            state.current_player = state.order[idx % len(state.order)] if state.order else None
    elif etype == "new_game":
        state.game_id = payload["game_id"]
        state.bank = {name: state.rules.bank_initial for name in state.order}
        state.current_player = state.order[0] if state.order else None
        state.turn.phase = TurnPhase.COOLDOWN
        state.turn.elapsed_no_cooldown = 0.0
        state.turn.warn_count = 0
    elif etype == "undo" and state.last_turn_end:
        state.current_player = state.last_turn_end["player"]
        state.bank[state.current_player] = state.last_turn_end["bank_after"]
        state.turn.phase = TurnPhase.COUNTDOWN
        state.turn.elapsed_no_cooldown = state.last_turn_end.get("spent_no_cooldown", 0.0)
        warn_every = max(1, state.rules.warn_every)
        state.turn.warn_count = int(state.turn.elapsed_no_cooldown // warn_every)


def apply_event(state: GameState, event: Event) -> GameState:
    if event.event_type == "GAME_START":
        state.game_id = event.data["game_id"]
        state.mode = Mode.RUNNING
        state.game_started = True
        state.players = [PlayerConfig(**item) for item in event.data["players"]]
        state.order = list(event.data["order"])
        state.order_dir = OrderDir(event.data["order_dir"])
        state.rules = Rules(**event.data["rules"])
        state.bank = {name: state.rules.bank_initial for name in state.order}

    elif event.event_type == "TURN_START":
        state.current_player = event.data["player"]
        state.turn.phase = TurnPhase(event.data["phase"])
        state.turn.turn_started_mono = event.data["now_mono"]
        state.turn.phase_started_mono = event.data["now_mono"]
        state.turn.elapsed_no_cooldown = 0.0
        state.turn.warn_count = 0

    elif event.event_type == "COOLDOWN_END":
        state.turn.phase = TurnPhase.COUNTDOWN

    elif event.event_type == "TURN_END":
        player = event.data["player"]
        state.bank[player] = event.data["bank_after"]
        state.last_turn_end = dict(event.data)

    elif event.event_type == "RUNTIME_SYNC":
        player = event.data["player"]
        state.bank[player] = event.data["bank_after"]
        state.turn.phase = TurnPhase(event.data["phase"])
        state.turn.phase_started_mono = event.data["phase_started_mono"]
        state.turn.elapsed_no_cooldown = event.data["elapsed_no_cooldown"]
        state.turn.warn_count = event.data["warn_count"]

    elif event.event_type == "TECH_PAUSE_ON":
        state.mode = Mode.TECH_PAUSE

    elif event.event_type == "TECH_PAUSE_OFF":
        state.mode = Mode.RUNNING
        state.turn.phase_started_mono = event.data["now_mono"]

    elif event.event_type == "ADMIN_AUTH_OK":
        state.admin_mode = True

    elif event.event_type in {"ADMIN_AUTH_FAIL", "ADMIN_MODE_OFF"}:
        state.admin_mode = False

    elif event.event_type in {"SETUP_EDIT", "ADMIN_EDIT"}:
        _apply_edit(state, event.data["edit_type"], event.data["payload"])

    return state
