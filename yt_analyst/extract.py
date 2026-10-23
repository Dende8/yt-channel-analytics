"""Orquestación de la descarga completa (reanudable)."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from datetime import date, timedelta
from functools import partial
from typing import Any

import requests

from .analytics_api import query_report
from .api_client import build_analytics_service, build_data_service
from .auth import build_credentials
from .checkpoint import Checkpoint
from .config import Settings
from .data_api import (
    BATCH_SIZE,
    chunked,
    fetch_channel,
    fetch_uploads_playlist_items,
    fetch_videos_batch,
    load_video_resources,
)
from .dates import parse_rfc3339, split_into_year_windows
from .errors import ApiRequestError, YtAnalystError
from .reports import CHANNEL_REPORTS, VIDEO_REPORTS, ReportSpec
from .shorts import probe_is_short
from .storage import RawStore

log = logging.getLogger(__name__)

# Errores que no se arreglan reintentando (petición inválida, sin permiso, no existe).
PERMANENT_STATUSES = {400, 403, 404}
# Tras N fallos seguidos de un mismo informe por vídeo, se desactiva en esta ejecución
# para no gastar cientos de llamadas en un informe mal definido.
CIRCUIT_BREAKER_THRESHOLD = 10

def _currency_tag(spec: ReportSpec, settings: Settings) -> str:
    """Devuelve un sufijo para la clave del trabajo en informes de ingresos.

    Si hay moneda configurada, la clave incluye la moneda: así los ingresos
    descargados antes sin moneda explícita se vuelven a pedir con ella, y un
    cambio posterior de moneda fuerza otra descarga en lugar de mezclarlas.
    """
    return f":cur={settings.currency}" if spec.is_revenue and settings.currency else ""

def _run_job(
    checkpoint: Checkpoint,
    key: str,
    action: Callable[[], Any],
    *,
    essential: bool = False,
) -> bool:
    """Ejecuta un trabajo solo si no está hecho ni bloqueado, y registra el resultado.

    Args:
        checkpoint: registro de progreso.
        key: clave única del trabajo.
        action: función sin argumentos que realiza la llamada y guarda el JSON.
        essential: si True, un fallo se propaga (la ejecución no puede continuar).

    Returns:
        True si el trabajo está completado; False si falló o está bloqueado.
    """
    if checkpoint.is_done(key):
        return True
    if checkpoint.is_blocked(key):
        log.debug("Omitido (fallo permanente previo): %s", key)
        return False
    try:
        action()
    except ApiRequestError as exc:
        if essential:
            raise
        checkpoint.mark_failed(key, str(exc), permanent=exc.status in PERMANENT_STATUSES)
        log.warning("Fallo en %s -> %s", key, exc)
        return False
    checkpoint.mark_done(key)
    return True


def _extract_channel(data_service: Any, store: RawStore, checkpoint: Checkpoint) -> dict:
    """Descarga (o reutiliza) los datos del canal y devuelve su recurso."""
    _run_job(
        checkpoint,
        "data_api:channel",
        lambda: store.write(fetch_channel(data_service), "data_api", "channel"),
        essential=True,
    )
    items = store.read("data_api", "channel").get("items", [])
    if not items:
        raise YtAnalystError("El token no devolvió ningún canal (mine=True).")
    return items[0]


def _extract_videos(
    data_service: Any, store: RawStore, checkpoint: Checkpoint, channel: dict
) -> list[dict]:
    """Descarga la lista de subidas y los metadatos de todos los vídeos."""
    uploads_id = channel["contentDetails"]["relatedPlaylists"]["uploads"]

    def fetch_playlist() -> None:
        items = fetch_uploads_playlist_items(data_service, uploads_id)
        store.write({"items": items}, "data_api", "uploads_playlist_items")

    _run_job(checkpoint, "data_api:uploads_playlist", fetch_playlist, essential=True)

    playlist_items = store.read("data_api", "uploads_playlist_items")["items"]
    # dict.fromkeys elimina duplicados conservando el orden
    video_ids = list(dict.fromkeys(i["contentDetails"]["videoId"] for i in playlist_items))
    log.info("Vídeos en la playlist de subidas: %d", len(video_ids))

    for number, batch in enumerate(chunked(video_ids, BATCH_SIZE), start=1):
        _run_job(
            checkpoint,
            f"data_api:videos:{number:04d}",
            lambda b=batch, n=number: store.write(
                fetch_videos_batch(data_service, b), "data_api", "videos", f"batch_{n:04d}"
            ),
            essential=True,
        )
    return load_video_resources(store)


def _probe_shorts(store: RawStore, videos: list[dict], pause: float = 0.2) -> None:
    """Sondea los vídeos públicos no resueltos con /shorts/<id> (caché reanudable).

    Los vídeos no públicos se omiten: el sondeo no es fiable con ellos y su
    formato se decide por duración en `classify_format`.
    """
    cache: dict[str, bool | None] = (
        store.read("shorts_probe") if store.exists("shorts_probe") else {}
    )
    pending = [
        v["id"]
        for v in videos
        if cache.get(v["id"]) is None
        and "liveStreamingDetails" not in v
        and v.get("status", {}).get("privacyStatus") == "public"
    ]
    log.info("Sondeo de Shorts: %d vídeos públicos pendientes", len(pending))
    with requests.Session() as session:
        for number, video_id in enumerate(pending, start=1):
            cache[video_id] = probe_is_short(video_id, session)
            if number % 50 == 0:
                store.write(cache, "shorts_probe")
            time.sleep(pause)
    store.write(cache, "shorts_probe")


def _resolve_date_range(
    settings: Settings, checkpoint: Checkpoint, channel: dict
) -> tuple[date, date]:
    """Determina (y congela) el rango de fechas para que todas las ejecuciones coincidan.

    El rango se guarda en el checkpoint en la primera ejecución; así los ficheros
    crudos y las claves de trabajo son coherentes al reanudar otro día.
    """
    stored = checkpoint.get_meta("date_range")
    if stored:
        return date.fromisoformat(stored["start"]), date.fromisoformat(stored["end"])

    channel_start = parse_rfc3339(channel["snippet"]["publishedAt"]).date()
    start = settings.analytics_start_date or channel_start
    end = date.today() - timedelta(days=settings.end_date_lag_days)
    checkpoint.set_meta("date_range", {"start": start.isoformat(), "end": end.isoformat()})
    log.info("Rango de fechas fijado: %s -> %s", start, end)
    return start, end


def _query_and_store(
    service: Any,
    store: RawStore,
    settings: Settings,
    spec: ReportSpec,
    start: date,
    end: date,
    video_id: str | None = None,
) -> None:
    """Ejecuta un informe de Analytics y guarda su respuesta cruda."""
    payload = query_report(
        service,
        spec,
        start,
        end,
        video_id=video_id,
        currency=settings.currency,
        pause=settings.request_pause_seconds,
    )
    if video_id:
        store.write(payload, "analytics", f"video_{spec.name}", video_id)
    else:
        file_name = f"{start}_{end}" if spec.windowed else "full"
        store.write(payload, "analytics", f"channel_{spec.name}", file_name)


def _extract_channel_reports(
    service: Any,
    store: RawStore,
    checkpoint: Checkpoint,
    settings: Settings,
    start: date,
    end: date,
) -> None:
    """Descarga todos los informes a nivel de canal."""
    for spec in CHANNEL_REPORTS:
        windows = split_into_year_windows(start, end) if spec.windowed else [(start, end)]
        for window_start, window_end in windows:
            key = (
                f"analytics:channel:{spec.name}:{window_start}_{window_end}"
                f"{_currency_tag(spec, settings)}"
            )
            log.info("Informe de canal: %s (%s -> %s)", spec.name, window_start, window_end)
            _run_job(
                checkpoint,
                key,
                partial(
                    _query_and_store, service, store, settings, spec, window_start, window_end
                ),
            )


def _extract_video_reports(
    service: Any,
    store: RawStore,
    checkpoint: Checkpoint,
    settings: Settings,
    videos: list[dict],
    end: date,
    limit_videos: int | None,
) -> None:
    """Descarga los informes por vídeo (los más recientes primero)."""
    eligible = [v for v in videos if parse_rfc3339(v["snippet"]["publishedAt"]).date() <= end]
    eligible.sort(key=lambda v: v["snippet"]["publishedAt"], reverse=True)
    skipped = len(videos) - len(eligible)
    if skipped:
        log.info("Vídeos omitidos por ser posteriores a %s: %d", end, skipped)
    if limit_videos:
        eligible = eligible[:limit_videos]

    failures = {spec.name: 0 for spec in VIDEO_REPORTS}
    disabled: set[str] = set()

    for number, video in enumerate(eligible, start=1):
        video_id = video["id"]
        published = parse_rfc3339(video["snippet"]["publishedAt"]).date()
        # Un día de margen por posibles diferencias de zona horaria
        video_start = published - timedelta(days=1)
        log.info("Vídeo %d/%d: %s", number, len(eligible), video_id)

        for spec in VIDEO_REPORTS:
            if spec.name in disabled:
                continue
            ok = _run_job(
                checkpoint,
                f"analytics:video:{spec.name}:{video_id}{_currency_tag(spec, settings)}",
                partial(
                    _query_and_store,
                    service, store, settings, spec, video_start, end,
                    video_id=video_id,
                ),
            )
            if ok:
                failures[spec.name] = 0
                continue
            failures[spec.name] += 1
            if failures[spec.name] >= CIRCUIT_BREAKER_THRESHOLD:
                disabled.add(spec.name)
                log.error(
                    "Informe de vídeo '%s' desactivado tras %d fallos seguidos. "
                    "Revisa los errores en checkpoint.json.",
                    spec.name,
                    CIRCUIT_BREAKER_THRESHOLD,
                )


def run_extraction(
    settings: Settings,
    *,
    verify_shorts: bool = False,
    limit_videos: int | None = None,
    retry_failed: bool = False,
) -> None:
    """Ejecuta la extracción completa y reanudable.

    Args:
        settings: configuración cargada.
        verify_shorts: sondear /shorts/<id> para clasificar con más precisión.
        limit_videos: procesar solo los N vídeos más recientes (para pruebas).
        retry_failed: reintentar también los fallos permanentes anteriores.

    Raises:
        AuthenticationError, QuotaExceededError, YtAnalystError: el progreso
            queda guardado y se puede relanzar el mismo comando.
    """
    store = RawStore(settings.raw_dir)
    checkpoint = Checkpoint(settings.checkpoint_path)
    if retry_failed:
        log.info("Fallos permanentes reabiertos: %d", checkpoint.clear_permanent_failures())

    credentials = build_credentials(settings)
    data_service = build_data_service(credentials)
    analytics_service = build_analytics_service(credentials)

    channel = _extract_channel(data_service, store, checkpoint)
    log.info("Canal: %s", channel["snippet"]["title"])
    videos = _extract_videos(data_service, store, checkpoint, channel)

    if verify_shorts:
        _probe_shorts(store, videos)

    start, end = _resolve_date_range(settings, checkpoint, channel)
    _extract_channel_reports(analytics_service, store, checkpoint, settings, start, end)
    _extract_video_reports(
        analytics_service, store, checkpoint, settings, videos, end, limit_videos
    )
    log.info("Extracción finalizada. Resumen: %s", checkpoint.summary())