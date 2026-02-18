from __future__ import annotations

import json
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
        *,
        players: list[PlayerConfig],
        order: list[str],
        rules: Rules,
        order_dir: OrderDir,
    ) -> None:
        parser = self.load()
        parser["game"] = {
            "players": json.dumps([asdict(player) for player in players], ensure_ascii=False),
            "order": json.dumps(order, ensure_ascii=False),
            "rules": json.dumps(asdict(rules), ensure_ascii=False),
            "order_dir": order_dir.value,
        }
        parser["meta"] = {"config_version": "2"}
        with self.path.open("w", encoding="utf-8") as handle:
            parser.write(handle)

    def load_game_config(self) -> tuple[list[PlayerConfig], list[str], Rules, OrderDir] | None:
        parser = self.load()
        if "game" not in parser:
            return None
        game = parser["game"]
        try:
            players_data = json.loads(game.get("players", "[]"))
            order = list(json.loads(game.get("order", "[]")))
            rules_data = json.loads(game.get("rules", "{}"))
            order_dir = OrderDir(game.get("order_dir", OrderDir.CLOCKWISE.value))
            players = [PlayerConfig(**item) for item in players_data]
            rules = Rules(**rules_data)
        except (TypeError, ValueError, json.JSONDecodeError):
            return None
        if not players or not order:
            return None
        return players, order, rules, order_dir
