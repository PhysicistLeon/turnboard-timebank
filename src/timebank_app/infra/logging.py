from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from timebank_app.domain.events import Event


@dataclass(slots=True)
class LogWriter:
    path: Path
    seq: int = 0

    def __post_init__(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text("LOG_FORMAT v=1\n", encoding="utf-8")

    def append(self, game_id: str, event: Event) -> str:
        self.seq += 1
        stamp = datetime.now(tz=UTC).isoformat(timespec="milliseconds")
        pairs = " ".join(f"{key}={self._safe(value)}" for key, value in sorted(event.data.items()))
        line = (
            f"{stamp} SEQ={self.seq} G={game_id or '-'} EVENT={event.event_type} {pairs}".rstrip()
        )
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
        return line

    @staticmethod
    def _safe(value: object) -> str:
        if isinstance(value, list):
            return '"' + ",".join(str(item) for item in value) + '"'
        if isinstance(value, dict):
            packed = ",".join(f"{key}:{val}" for key, val in sorted(value.items()))
            return '"' + packed + '"'
        text = str(value)
        return f'"{text}"' if " " in text else text
