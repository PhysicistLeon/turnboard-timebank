from __future__ import annotations

from timebank_app.domain.commands import (
    CmdAdminAuth,
    CmdAdminEdit,
    CmdPauseOn,
    CmdStartGame,
    CmdTap,
    CmdTick,
)
from timebank_app.domain.engine import CommandError, Decider, apply_event
from timebank_app.domain.models import GameState, OrderDir, PlayerConfig, Rules, TurnPhase


def evolve(state: GameState, events):
    for event in events:
        state = apply_event(state, event)
    return state


def mk_start(now: float = 0.0):
    return CmdStartGame(
        now_mono=now,
        game_id="g1",
        players=[PlayerConfig(name="A"), PlayerConfig(name="B")],
        order=["A", "B"],
        order_dir=OrderDir.CLOCKWISE,
        rules=Rules(bank_initial=100, cooldown=5, warn_every=10),
    )


def test_start_game_and_turn_start():
    decider = Decider("pw")
    state = GameState()
    state = evolve(state, decider.decide(state, mk_start()))
    assert state.game_started is True
    assert state.mode.value == "running"
    assert state.current_player == "A"
    assert state.turn.phase == TurnPhase.COOLDOWN


def test_tap_switches_turn_and_spends_only_countdown():
    decider = Decider("pw")
    state = evolve(GameState(), decider.decide(GameState(), mk_start()))
    state = evolve(state, decider.decide(state, CmdTap(now_mono=3.0)))
    assert state.bank["A"] == 100
    assert state.current_player == "B"


def test_warn_events_generated_each_interval():
    decider = Decider("pw")
    state = evolve(GameState(), decider.decide(GameState(), mk_start()))
    events = decider.decide(state, CmdTap(now_mono=27.0))
    warn_events = [event for event in events if event.event_type == "WARN_LONG_TURN"]
    assert len(warn_events) == 2


def test_pause_command_enters_pause_mode():
    decider = Decider("pw")
    state = evolve(GameState(), decider.decide(GameState(), mk_start()))
    state = evolve(state, decider.decide(state, CmdPauseOn(now_mono=1.0, cause="manual")))
    assert state.mode.value == "tech_pause"


def test_admin_required_after_start():
    decider = Decider("pw")
    state = evolve(GameState(), decider.decide(GameState(), mk_start()))
    try:
        decider.decide(state, CmdAdminEdit(now_mono=1.0, edit_type="reverse", payload={}))
    except CommandError as exc:
        assert "Admin mode" in str(exc)
    else:
        raise AssertionError("CommandError expected")


def test_admin_auth_and_reverse_direction():
    decider = Decider("pw")
    state = evolve(GameState(), decider.decide(GameState(), mk_start()))
    state = evolve(state, decider.decide(state, CmdAdminAuth(now_mono=1.0, password="pw")))
    state = evolve(
        state, decider.decide(state, CmdAdminEdit(now_mono=2.0, edit_type="reverse", payload={}))
    )
    assert state.order_dir == OrderDir.COUNTERCLOCKWISE


def test_undo_restores_previous_player():
    decider = Decider("pw")
    state = evolve(GameState(), decider.decide(GameState(), mk_start()))
    state = evolve(state, decider.decide(state, CmdTap(now_mono=15.0)))
    state = evolve(state, decider.decide(state, CmdAdminAuth(now_mono=16.0, password="pw")))
    state = evolve(
        state, decider.decide(state, CmdAdminEdit(now_mono=17.0, edit_type="undo", payload={}))
    )
    assert state.current_player == "A"
    assert state.turn.phase == TurnPhase.COUNTDOWN


def test_setup_edit_without_admin_before_start():
    decider = Decider("pw")
    state = GameState()
    events = decider.decide(
        state, CmdAdminEdit(now_mono=1.0, edit_type="set_rules", payload={"cooldown": 1})
    )
    assert events[0].event_type == "SETUP_EDIT"


def test_tick_advances_runtime_without_tap():
    decider = Decider("pw")
    state = evolve(GameState(), decider.decide(GameState(), mk_start()))
    state = evolve(state, decider.decide(state, CmdTick(now_mono=27.0)))
    assert state.current_player == "A"
    assert state.turn.phase == TurnPhase.COUNTDOWN
    assert state.bank["A"] == 78

