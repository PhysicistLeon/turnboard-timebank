from __future__ import annotations


def format_mm_ss(value: float) -> str:
    sign = "-" if value < 0 else ""
    total = int(abs(value))
    minutes = total // 60
    seconds = total % 60
    return f"{sign}{minutes:02d}:{seconds:02d}"
