from __future__ import annotations

from configparser import ConfigParser
from pathlib import Path


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
