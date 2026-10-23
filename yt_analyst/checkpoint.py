"""Registro de progreso para que la extracción sea reanudable."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .storage import atomic_write_text


def _now() -> str:
    """Marca temporal UTC en formato ISO 8601."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Checkpoint:
    """Guarda qué trabajos se completaron y cuáles fallaron.

    Cada trabajo se identifica con una clave de texto única. El estado se
    persiste en disco tras cada cambio.
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        self._state: dict[str, dict] = {"meta": {}, "done": {}, "failed": {}}
        if path.exists():
            self._state.update(json.loads(path.read_text(encoding="utf-8")))

    def _save(self) -> None:
        """Persiste el estado en disco de forma atómica."""
        atomic_write_text(
            self._path, json.dumps(self._state, ensure_ascii=False, indent=2)
        )

    def is_done(self, key: str) -> bool:
        """Indica si el trabajo ya se completó."""
        return key in self._state["done"]

    def is_blocked(self, key: str) -> bool:
        """Indica si el trabajo falló de forma permanente (p. ej. HTTP 400)."""
        entry = self._state["failed"].get(key)
        return bool(entry and entry.get("permanent"))

    def mark_done(self, key: str) -> None:
        """Marca el trabajo como completado y limpia cualquier fallo previo."""
        self._state["done"][key] = _now()
        self._state["failed"].pop(key, None)
        self._save()

    def mark_failed(self, key: str, error: str, *, permanent: bool) -> None:
        """Registra un fallo; si es permanente no se reintentará salvo petición expresa."""
        self._state["failed"][key] = {"error": error, "permanent": permanent, "at": _now()}
        self._save()

    def clear_permanent_failures(self) -> int:
        """Olvida los fallos permanentes para reintentarlos; devuelve cuántos eran."""
        blocked = [k for k in self._state["failed"] if self.is_blocked(k)]
        for key in blocked:
            del self._state["failed"][key]
        if blocked:
            self._save()
        return len(blocked)

    def get_meta(self, key: str, default: Any = None) -> Any:
        """Lee un valor auxiliar persistido (p. ej. el rango de fechas)."""
        return self._state["meta"].get(key, default)

    def set_meta(self, key: str, value: Any) -> None:
        """Guarda un valor auxiliar persistido."""
        self._state["meta"][key] = value
        self._save()

    def summary(self) -> dict[str, int]:
        """Resumen numérico del progreso."""
        permanent = sum(1 for k in self._state["failed"] if self.is_blocked(k))
        return {
            "done": len(self._state["done"]),
            "failed_permanent": permanent,
            "failed_transient": len(self._state["failed"]) - permanent,
        }