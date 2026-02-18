from __future__ import annotations

from pathlib import Path

from timebank_app.app.controller import GameController
from timebank_app.domain.commands import CmdPauseOn, CmdStartGame, CmdTap
from timebank_app.domain.engine import Decider
from timebank_app.domain.models import OrderDir, PlayerConfig, Rules
from timebank_app.infra.effects import EffectSink, SoundRepo
from timebank_app.infra.logging import LogWriter
from timebank_app.infra.storage import ConfigStore


def make_controller(tmp_path: Path) -> GameController:
    sounds = tmp_path / "sounds"
    sounds.mkdir()
    (sounds / "tap.wav").write_text("dummy", encoding="utf-8")
    return GameController(
        decider=Decider("pw"),
        log_writer=LogWriter(tmp_path / "events.log"),
        effects=EffectSink(),
        sound_repo=SoundRepo(sounds),
    )


def start(controller: GameController) -> None:
    controller.dispatch(
        CmdStartGame(
            now_mono=0.0,
            game_id="g1",
            players=[PlayerConfig(name="A", sound_tap="tap.wav"), PlayerConfig(name="B")],
            order=["A", "B"],
            order_dir=OrderDir.CLOCKWISE,
            rules=Rules(bank_initial=30, cooldown=1, warn_every=5),
        )
    )


def test_logging_and_effects_on_tap(tmp_path: Path):
    controller = make_controller(tmp_path)
    start(controller)
    result = controller.dispatch(CmdTap(now_mono=3.0))
    assert any("TURN_END" in line for line in result.log_lines)
    assert controller.effects.vibrations == 1
    assert "tap.wav" in controller.effects.played_sounds


def test_keep_awake_toggles_with_pause(tmp_path: Path):
    controller = make_controller(tmp_path)
    start(controller)
    assert controller.effects.keep_awake is True
    controller.dispatch(CmdPauseOn(now_mono=2.0, cause="manual"))
    assert controller.effects.keep_awake is False


def test_config_store_roundtrip(tmp_path: Path):
    cfg = ConfigStore(tmp_path / "config.ini")
    payload_players = [
        PlayerConfig(name="A", color="#112233", sound_tap="tap.wav"),
        PlayerConfig(name="B", color="#445566", sound_tap=""),
    ]
    payload_rules = Rules(bank_initial=90, cooldown=3, warn_every=15)
    cfg.save_game_config(
        players=payload_players,
        order=["A", "B"],
        order_dir=OrderDir.COUNTERCLOCKWISE,
        rules=payload_rules,
    )

    loaded = cfg.load_game_config()
    assert loaded is not None
    assert loaded["order"] == ["A", "B"]
    assert loaded["order_dir"] == OrderDir.COUNTERCLOCKWISE
    assert loaded["rules"].bank_initial == 90
    assert [player.name for player in loaded["players"]] == ["A", "B"]


def test_sound_repo_empty(tmp_path: Path):
    repo = SoundRepo(tmp_path / "missing")
    assert repo.list_files() == []
    assert repo.resolve("anything.wav") is None


def test_log_file_has_header(tmp_path: Path):
    writer = LogWriter(tmp_path / "l.log")
    text = (tmp_path / "l.log").read_text(encoding="utf-8")
    assert "LOG_FORMAT v=1" in text
    writer.append("g", type("Evt", (), {"event_type": "X", "data": {}})())
    text2 = (tmp_path / "l.log").read_text(encoding="utf-8")
    assert "EVENT=X" in text2
