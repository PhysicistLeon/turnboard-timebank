from __future__ import annotations

from pathlib import Path

from timebank_app.app.controller import GameController
from timebank_app.domain.commands import CmdPauseOn, CmdStartGame, CmdTap
from timebank_app.domain.engine import Decider
from timebank_app.domain.models import OrderDir, PlayerConfig, Rules
from timebank_app.infra.effects import EffectSink, SoundRepo
from timebank_app.infra.logging import LogWriter
from timebank_app.infra.storage import ConfigStore
from timebank_app.ui.main import _format_mmss


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
    assert cfg.get_password() is None
    cfg.save_password("secret")
    assert cfg.get_password() == "secret"


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


def test_game_config_store_roundtrip(tmp_path: Path):
    cfg = ConfigStore(tmp_path / "config.ini")
    players = [
        PlayerConfig(name="A", color="#112233", sound_tap="tap.wav"),
        PlayerConfig(name="B", color="#445566", sound_tap="b.wav"),
    ]
    rules = Rules(bank_initial=300, cooldown=4, warn_every=50)
    cfg.save_game_config(players, ["B", "A"], OrderDir.COUNTERCLOCKWISE, rules)

    loaded = cfg.load_game_config()
    assert loaded is not None
    loaded_players, order, order_dir, loaded_rules = loaded
    assert [p.name for p in loaded_players] == ["A", "B"]
    assert loaded_players[0].color == "#112233"
    assert loaded_players[1].sound_tap == "b.wav"
    assert order == ["B", "A"]
    assert order_dir == OrderDir.COUNTERCLOCKWISE
    assert loaded_rules.bank_initial == 300
    assert loaded_rules.cooldown == 4
    assert loaded_rules.warn_every == 50


def test_format_mmss_supports_negative_and_large_minutes():
    assert _format_mmss(0) == "00:00"
    assert _format_mmss(65) == "01:05"
    assert _format_mmss(-65) == "-01:05"
    assert _format_mmss(6059) == "100:59"
