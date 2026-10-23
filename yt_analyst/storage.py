"""Persistencia: JSON crudo (escritura atómica) y exportación a CSV."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pandas as pd


def atomic_write_text(path: Path, text: str) -> None:
    """Escribe un fichero de forma atómica (temporal + reemplazo).

    Evita que un corte a mitad de escritura deje un fichero corrupto.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(text, encoding="utf-8")
    os.replace(tmp_path, path)


class RawStore:
    """Almacén de respuestas JSON crudas organizado en subcarpetas.

    Las rutas se expresan como partes: ("analytics", "video_totals", "abc123")
    equivale a <raw_dir>/analytics/video_totals/abc123.json
    """

    def __init__(self, root: Path) -> None:
        self.root = root

    def _path(self, *parts: str) -> Path:
        """Resuelve las partes a la ruta física del fichero .json."""
        return self.root.joinpath(*parts[:-1], f"{parts[-1]}.json")

    def write(self, payload: Any, *parts: str) -> Path:
        """Guarda un objeto serializable como JSON y devuelve su ruta."""
        path = self._path(*parts)
        atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2))
        return path

    def read(self, *parts: str) -> Any:
        """Lee y deserializa un JSON guardado."""
        return self.read_file(self._path(*parts))

    def exists(self, *parts: str) -> bool:
        """Indica si existe el JSON correspondiente a esas partes."""
        return self._path(*parts).exists()

    def list_files(self, *dir_parts: str) -> list[Path]:
        """Lista (ordenados) los .json de una subcarpeta; vacío si no existe."""
        directory = self.root.joinpath(*dir_parts)
        return sorted(directory.glob("*.json")) if directory.is_dir() else []

    @staticmethod
    def read_file(path: Path) -> Any:
        """Lee un JSON a partir de su ruta física."""
        return json.loads(path.read_text(encoding="utf-8"))


def write_csv(frame: pd.DataFrame, path: Path) -> None:
    """Exporta un DataFrame a CSV con UTF-8 con BOM (se abre bien en Excel)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, encoding="utf-8-sig")