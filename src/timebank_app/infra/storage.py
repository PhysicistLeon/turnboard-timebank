from __future__ import annotations

from configparser import ConfigParser
from dataclasses import asdict
from pathlib import Path

from timebank_app.domain.models import OrderDir, PlayerConfig, Rules


class ConfigStore:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> ConfigParser:
        parser = ConfigParser()
        if self.path.exists():
            parser.read(self.path, encoding="utf-8")
        return parser

    def save_game_config(
        self,
        *,
        players: list[PlayerConfig],
        order: list[str],
        order_dir: OrderDir,
        rules: Rules,
    ) -> None:
        parser = self.load()
        parser["meta"] = {"config_version": "2"}
        parser["game"] = {
            "order": ",".join(order),
            "order_dir": order_dir.value,
        }
        parser["rules"] = {key: str(value) for key, value in asdict(rules).items()}

        for section in list(parser.sections()):
            if section.startswith("player:"):
                parser.remove_section(section)

        for player in players:
            parser[f"player:{player.name}"] = {
                "name": player.name,
                "color": player.color,
                "sound_tap": player.sound_tap,
                "sound_warn": player.sound_warn,
            }

        with self.path.open("w", encoding="utf-8") as handle:
            parser.write(handle)

    def load_game_config(self) -> dict | None:
        parser = self.load()
        if "game" not in parser or "rules" not in parser:
            return None

        players: list[PlayerConfig] = []
        for section in parser.sections():
            if not section.startswith("player:"):
                continue
            block = parser[section]
            players.append(
                PlayerConfig(
                    name=block.get("name", section.removeprefix("player:")),
                    color=block.get("color", "#FFFFFF"),
                    sound_tap=block.get("sound_tap", ""),
                    sound_warn=block.get("sound_warn", ""),
                )
            )

        game = parser["game"]
        rules_block = parser["rules"]
        order = [item.strip() for item in game.get("order", "").split(",") if item.strip()]
        order_dir_raw = game.get("order_dir", OrderDir.CLOCKWISE.value)
        rules = Rules(
            bank_initial=rules_block.getfloat("bank_initial", fallback=600.0),
            cooldown=rules_block.getfloat("cooldown", fallback=5.0),
            warn_every=rules_block.getint("warn_every", fallback=60),
            warn_sound=rules_block.get("warn_sound", fallback=""),
            blink_min_hz=rules_block.getfloat("blink_min_hz", fallback=1.0 / 60.0),
            blink_max_hz=rules_block.getfloat("blink_max_hz", fallback=1.0),
        )

        try:
            order_dir = OrderDir(order_dir_raw)
        except ValueError:
            order_dir = OrderDir.CLOCKWISE

        return {
            "players": players,
            "order": order,
            "order_dir": order_dir,
            "rules": rules,
        }
