"""Carga y validación de la configuración desde variables de entorno / .env."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

from .errors import ConfigError

_REQUIRED_CREDENTIALS = ("YT_CLIENT_ID", "YT_CLIENT_SECRET", "YT_REFRESH_TOKEN")


@dataclass(frozen=True)
class Settings:
    """Configuración inmutable de la aplicación."""

    client_id: str
    client_secret: str
    refresh_token: str
    output_dir: Path
    end_date_lag_days: int
    request_pause_seconds: float
    analytics_start_date: date | None
    currency: str | None

    @property
    def raw_dir(self) -> Path:
        """Carpeta con las respuestas JSON crudas de las APIs."""
        return self.output_dir / "raw"

    @property
    def csv_dir(self) -> Path:
        """Carpeta con los CSV consolidados."""
        return self.output_dir / "csv"

    @property
    def checkpoint_path(self) -> Path:
        """Fichero donde se guarda el progreso para poder reanudar."""
        return self.output_dir / "checkpoint.json"


def load_settings(require_credentials: bool = True) -> Settings:
    """Lee la configuración del entorno (y de .env) y la valida.

    Args:
        require_credentials: si es True, exige las tres credenciales OAuth.
            Los comandos que no llaman a la API (transform, status) pasan False.

    Raises:
        ConfigError: si faltan credenciales o algún valor tiene formato inválido.
    """
    load_dotenv()

    credentials = {name: os.getenv(name, "").strip() for name in _REQUIRED_CREDENTIALS}
    missing = [name for name, value in credentials.items() if not value]
    if require_credentials and missing:
        raise ConfigError(f"Faltan variables en .env: {', '.join(missing)}")

    try:
        start_raw = os.getenv("ANALYTICS_START_DATE", "").strip()
        return Settings(
            client_id=credentials["YT_CLIENT_ID"],
            client_secret=credentials["YT_CLIENT_SECRET"],
            refresh_token=credentials["YT_REFRESH_TOKEN"],
            output_dir=Path(os.getenv("OUTPUT_DIR", "data")),
            end_date_lag_days=int(os.getenv("END_DATE_LAG_DAYS", "3")),
            request_pause_seconds=float(os.getenv("REQUEST_PAUSE_SECONDS", "0.3")),
            analytics_start_date=date.fromisoformat(start_raw) if start_raw else None,
            currency=os.getenv("REVENUE_CURRENCY", "").strip() or None,
        )
    except ValueError as exc:
        raise ConfigError(f"Valor inválido en la configuración: {exc}") from exc