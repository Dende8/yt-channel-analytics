"""Interfaz de línea de comandos."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from .checkpoint import Checkpoint
from .config import load_settings
from .errors import (
    AuthenticationError,
    ConfigError,
    QuotaExceededError,
    YtAnalystError,
)
from .extract import run_extraction
from .transform import run_transform


def build_parser() -> argparse.ArgumentParser:
    """Define los subcomandos y sus opciones."""
    parser = argparse.ArgumentParser(
        prog="yt_analyst", description="Descarga y organiza datos de un canal de YouTube."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    for name, help_text in (
        ("extract", "Descarga datos de las APIs (JSON crudo, reanudable)."),
        ("run", "Ejecuta extract y después transform."),
    ):
        command = sub.add_parser(name, help=help_text)
        command.add_argument(
            "--verify-shorts", action="store_true",
            help="Sondea /shorts/<id> para clasificar Shorts con más precisión (no oficial).",
        )
        command.add_argument(
            "--limit-videos", type=int, default=None,
            help="Procesa solo los N vídeos más recientes (útil para pruebas).",
        )
        command.add_argument(
            "--retry-failed", action="store_true",
            help="Reintenta también los fallos permanentes registrados.",
        )

    sub.add_parser("transform", help="Genera los CSV desde el JSON crudo (sin API).")
    sub.add_parser("status", help="Muestra el resumen del checkpoint.")
    return parser


def configure_logging(output_dir: Path) -> None:
    """Configura el log hacia consola y hacia <output_dir>/run.log."""
    output_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(output_dir / "run.log", encoding="utf-8"),
        ],
    )


def main(argv: list[str] | None = None) -> int:
    """Punto de entrada. Devuelve el código de salida del proceso."""
    args = build_parser().parse_args(argv)
    needs_api = args.command in {"extract", "run"}

    try:
        settings = load_settings(require_credentials=needs_api)
        configure_logging(settings.output_dir)
        log = logging.getLogger("yt_analyst")

        if args.command == "status":
            print(json.dumps(Checkpoint(settings.checkpoint_path).summary(), indent=2))
            return 0

        if needs_api:
            run_extraction(
                settings,
                verify_shorts=args.verify_shorts,
                limit_videos=args.limit_videos,
                retry_failed=args.retry_failed,
            )
        if args.command in {"run", "transform"}:
            run_transform(settings)
        return 0

    except ConfigError as exc:
        print(f"Error de configuración: {exc}", file=sys.stderr)
        return 2
    except AuthenticationError as exc:
        log.error("Autenticación: %s", exc)
        return 3
    except QuotaExceededError as exc:
        log.error("%s Progreso guardado: relanza el mismo comando más tarde.", exc)
        return 4
    except YtAnalystError as exc:
        log.error("%s", exc)
        return 1
    except KeyboardInterrupt:
        log.warning("Interrumpido. El progreso queda guardado; relanza para continuar.")
        return 130