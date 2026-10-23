"""Clasificación de vídeos en 'long', 'short' o 'live'.

La Data API v3 NO expone un campo que indique si un vídeo es un Short, así que
se usan dos métodos, de menor a mayor fiabilidad:

1. Heurística por duración (siempre disponible, aproximada).
2. Sondeo opcional de la URL /shorts/<id> (NO oficial: se basa en el
   comportamiento actual de YouTube y podría dejar de funcionar).

La columna `format_source` de los CSV indica qué método decidió cada vídeo.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

import requests

from .dates import parse_rfc3339

_DURATION_RE = re.compile(r"^P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?$")

# Hasta esta fecha los Shorts duraban como máximo 60 s; desde ella, hasta 180 s.
# (Dato de memoria: verifícalo si la precisión de la clasificación es crítica.)
SHORTS_LIMIT_CHANGE = datetime(2024, 10, 15, tzinfo=timezone.utc)
SHORTS_MAX_SECONDS_BEFORE = 60
SHORTS_MAX_SECONDS_AFTER = 180


def parse_iso8601_duration(value: str) -> int:
    """Convierte una duración ISO 8601 de YouTube (p. ej. 'PT1H2M3S') en segundos.

    Raises:
        ValueError: si el texto no tiene el formato esperado.
    """
    match = _DURATION_RE.match(value or "")
    if not match:
        raise ValueError(f"Duración con formato inesperado: {value!r}")
    days, hours, minutes, seconds = (int(group or 0) for group in match.groups())
    return days * 86400 + hours * 3600 + minutes * 60 + seconds


def probe_is_short(
    video_id: str, session: requests.Session, timeout: float = 10.0
) -> bool | None:
    """Sondea https://www.youtube.com/shorts/<id> para decidir si es un Short.

    Returns:
        True si es Short (HTTP 200), False si redirige a /watch (vídeo normal),
        None si el resultado no es concluyente (red, página de consentimiento...).
    """
    try:
        response = session.head(
            f"https://www.youtube.com/shorts/{video_id}",
            allow_redirects=False,
            timeout=timeout,
        )
    except requests.RequestException:
        return None
    if response.status_code == 200:
        return True
    redirects = {301, 302, 303, 307, 308}
    if response.status_code in redirects and "/watch" in response.headers.get("Location", ""):
        return False
    return None


def classify_format(video: dict, probe_result: bool | None = None) -> tuple[str, str]:
    """Clasifica un vídeo (recurso de videos.list) como 'live', 'short' o 'long'.

    El sondeo de /shorts/<id> solo se tiene en cuenta en vídeos públicos: en los
    privados devolvió resultados incoherentes (p. ej. Shorts de 8 minutos), así
    que en vídeos no públicos se recurre siempre a la duración.

    Args:
        video: recurso de vídeo con snippet, contentDetails, status y
            liveStreamingDetails.
        probe_result: resultado de `probe_is_short` si se ejecutó el sondeo.

    Returns:
        Tupla (formato, método) donde método es 'live_streaming_details',
        'shorts_url_probe', 'duration_heuristic' o 'duration_heuristic_nonpublic'.
    """
    snippet = video.get("snippet", {})
    if "liveStreamingDetails" in video or snippet.get("liveBroadcastContent") in {
        "live",
        "upcoming",
    }:
        return "live", "live_streaming_details"

    is_public = video.get("status", {}).get("privacyStatus") == "public"

    # El sondeo solo es fiable en vídeos públicos
    if is_public and probe_result is True:
        return "short", "shorts_url_probe"
    if is_public and probe_result is False:
        return "long", "shorts_url_probe"

    duration = parse_iso8601_duration(video.get("contentDetails", {}).get("duration", "PT0S"))
    published = parse_rfc3339(snippet["publishedAt"])
    limit = (
        SHORTS_MAX_SECONDS_AFTER
        if published >= SHORTS_LIMIT_CHANGE
        else SHORTS_MAX_SECONDS_BEFORE
    )
    method = "duration_heuristic" if is_public else "duration_heuristic_nonpublic"
    return ("short" if duration <= limit else "long"), method