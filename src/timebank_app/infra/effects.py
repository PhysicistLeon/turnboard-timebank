from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class EffectSink:
    played_sounds: list[str] = field(default_factory=list)
    vibrations: int = 0
    keep_awake: bool = False
    errors: list[str] = field(default_factory=list)

    def play_sound(self, path: Path | None) -> None:
        if path is None:
            self.errors.append("sound_unavailable")
            return
        self.played_sounds.append(path.name)

    def vibrate(self) -> None:
        self.vibrations += 1

    def set_keep_awake(self, enabled: bool) -> None:
        self.keep_awake = enabled


class SoundRepo:
    def __init__(self, sound_dir: Path):
        self.sound_dir = sound_dir

    def list_files(self) -> list[str]:
        if not self.sound_dir.exists() or not self.sound_dir.is_dir():
            return []
        return sorted(path.name for path in self.sound_dir.iterdir() if path.is_file())

    def resolve(self, file_name: str) -> Path | None:
        if not file_name:
            return None
        candidate = self.sound_dir / file_name
        if candidate.exists() and candidate.is_file():
            return candidate
        return None
