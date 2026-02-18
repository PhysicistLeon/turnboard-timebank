from __future__ import annotations

from dataclasses import dataclass, field

from timebank_app.domain.commands import CmdTap, Command
from timebank_app.domain.engine import Decider, apply_event
from timebank_app.domain.events import Event
from timebank_app.domain.models import GameState
from timebank_app.infra.effects import EffectSink, SoundRepo
from timebank_app.infra.logging import LogWriter


@dataclass(slots=True)
class DispatchResult:
    events: list[Event] = field(default_factory=list)
    log_lines: list[str] = field(default_factory=list)


class GameController:
    def __init__(
        self, decider: Decider, log_writer: LogWriter, effects: EffectSink, sound_repo: SoundRepo
    ):
        self.decider = decider
        self.log_writer = log_writer
        self.effects = effects
        self.sound_repo = sound_repo
        self.state = GameState()

    def dispatch(self, command: Command) -> DispatchResult:
        events = self.decider.decide(self.state, command)
        result = DispatchResult(events=list(events))

        for event in events:
            result.log_lines.append(self.log_writer.append(self.state.game_id, event))
            self.state = apply_event(self.state, event)
            self._run_effects(command, event)

        return result

    def _run_effects(self, command: Command, event: Event) -> None:
        if event.event_type == "GAME_START":
            self.effects.set_keep_awake(True)
        elif event.event_type == "TECH_PAUSE_ON":
            self.effects.set_keep_awake(False)
        elif event.event_type == "TECH_PAUSE_OFF":
            self.effects.set_keep_awake(True)

        if isinstance(command, CmdTap) and event.event_type == "TURN_END":
            player = event.data["player"]
            sound_name = ""
            for cfg in self.state.players:
                if cfg.name == player:
                    sound_name = cfg.sound_tap
                    break
            self.effects.play_sound(self.sound_repo.resolve(sound_name))
            self.effects.vibrate()

        if event.event_type == "WARN_LONG_TURN":
            warn = self.sound_repo.resolve(self.state.rules.warn_sound)
            self.effects.play_sound(warn)
