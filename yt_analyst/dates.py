"""Utilidades de fechas."""

from __future__ import annotations

from datetime import date, datetime, timedelta


def parse_rfc3339(value: str) -> datetime:
    """Convierte una marca RFC 3339 de YouTube (acaba en 'Z') en datetime con zona."""
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def split_into_year_windows(start: date, end: date) -> list[tuple[date, date]]:
    """Divide [start, end] en ventanas que no cruzan el cambio de año.

    Evita pedir de golpe series diarias de muchos años en una sola llamada.
    """
    windows: list[tuple[date, date]] = []
    cursor = start
    while cursor <= end:
        window_end = min(date(cursor.year, 12, 31), end)
        windows.append((cursor, window_end))
        cursor = window_end + timedelta(days=1)
    return windows