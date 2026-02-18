from __future__ import annotations

from configparser import ConfigParser
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

    def save_password(self, password: str) -> None:
        parser = self.load()
        if "auth" not in parser:
            parser["auth"] = {}
        parser["auth"]["password"] = password
        parser["meta"] = {"config_version": "1"}
        with self.path.open("w", encoding="utf-8") as handle:
            parser.write(handle)

    def get_password(self) -> str | None:
        parser = self.load()
        if "auth" not in parser:
            return None
        return parser["auth"].get("password")

    def save_game_config(
        self,
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
            "bank_initial": str(rules.bank_initial),
            "cooldown": str(rules.cooldown),
            "warn_every": str(rules.warn_every),
            "warn_sound": rules.warn_sound,
        }
        for index, player in enumerate(players, start=1):
            parser[f"player:{index}"] = {
                "name": player.name,
                "color": player.color,
                "sound_tap": player.sound_tap,
                "sound_warn": player.sound_warn,
            }
        player_sections = [
            name
            for name in parser.sections()
            if name.startswith("player:") and name.count(":") == 1
        ]
        for section in player_sections:
            try:
                idx = int(section.split(":", maxsplit=1)[1])
            except ValueError:
                continue
            if idx > len(players):
                parser.remove_section(section)

        with self.path.open("w", encoding="utf-8") as handle:
            parser.write(handle)

    def load_game_config(self) -> tuple[list[PlayerConfig], list[str], OrderDir, Rules] | None:
        parser = self.load()
        if "game" not in parser:
            return None

        game = parser["game"]
        players: list[PlayerConfig] = []
        player_sections = [
            name
            for name in parser.sections()
            if name.startswith("player:") and name.count(":") == 1
        ]
        for section in sorted(
            player_sections,
            key=lambda item: int(item.split(":", maxsplit=1)[1]),
        ):
            item = parser[section]
            name = item.get("name", "").strip()
            if not name:
                continue
            players.append(
                PlayerConfig(
                    name=name,
                    color=item.get("color", "#FFFFFF"),
                    sound_tap=item.get("sound_tap", ""),
                    sound_warn=item.get("sound_warn", ""),
                )
            )

        if not players:
            return None

        default_order = [player.name for player in players]
        order = [part.strip() for part in game.get("order", "").split(",") if part.strip()]
        if set(order) != set(default_order):
            order = default_order

        order_dir_value = game.get("order_dir", OrderDir.CLOCKWISE.value)
        order_dir = (
            OrderDir(order_dir_value)
            if order_dir_value in {OrderDir.CLOCKWISE.value, OrderDir.COUNTERCLOCKWISE.value}
            else OrderDir.CLOCKWISE
        )
        rules = Rules(
            bank_initial=float(game.get("bank_initial", "600")),
            cooldown=float(game.get("cooldown", "5")),
            warn_every=int(game.get("warn_every", "60")),
            warn_sound=game.get("warn_sound", ""),
        )
        return players, order, order_dir, rules
