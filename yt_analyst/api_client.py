"""Construcción de los servicios de Google y ejecución de peticiones con reintentos."""

from __future__ import annotations

import json
import logging
import random
import time
from typing import Any

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from .errors import ApiRequestError, AuthenticationError, QuotaExceededError

log = logging.getLogger(__name__)

RETRYABLE_STATUSES = {429, 500, 502, 503, 504}
RATE_LIMIT_REASONS = {"rateLimitExceeded", "userRateLimitExceeded"}
DAILY_QUOTA_REASONS = {"quotaExceeded", "dailyLimitExceeded"}


def build_data_service(credentials: Credentials) -> Any:
    """Crea el cliente de YouTube Data API v3."""
    return build("youtube", "v3", credentials=credentials, cache_discovery=False)


def build_analytics_service(credentials: Credentials) -> Any:
    """Crea el cliente de YouTube Analytics API v2."""
    return build("youtubeAnalytics", "v2", credentials=credentials, cache_discovery=False)


def _parse_http_error(exc: HttpError) -> tuple[str, str]:
    """Extrae (motivo, mensaje) del cuerpo JSON de un HttpError de Google."""
    try:
        error = json.loads(exc.content.decode("utf-8")).get("error", {})
    except (ValueError, AttributeError):
        return "", str(exc)
    errors = error.get("errors") or []
    reason = errors[0].get("reason", "") if errors else error.get("status", "")
    return reason, error.get("message", str(exc))


def execute_with_retry(
    request: Any,
    *,
    pause: float = 0.0,
    max_retries: int = 5,
    base_delay: float = 2.0,
) -> dict:
    """Ejecuta una petición con backoff exponencial ante errores transitorios.

    Args:
        request: objeto de petición del cliente de Google (tiene `.execute()`).
        pause: pausa en segundos tras una llamada correcta (limita el ritmo).
        max_retries: reintentos máximos ante errores transitorios.
        base_delay: retardo base del backoff exponencial (2s, 4s, 8s...).

    Returns:
        La respuesta JSON de la API como diccionario.

    Raises:
        AuthenticationError: ante un 401 (credenciales inválidas).
        QuotaExceededError: si se agotó la cuota diaria.
        ApiRequestError: si la petición falla de forma definitiva.
    """
    for attempt in range(max_retries + 1):
        try:
            response = request.execute()
            if pause:
                time.sleep(pause)
            return response
        except HttpError as exc:
            status = exc.resp.status
            reason, message = _parse_http_error(exc)

            if status == 401:
                raise AuthenticationError(f"Credenciales rechazadas: {message}") from exc
            if status == 403 and reason in DAILY_QUOTA_REASONS:
                raise QuotaExceededError(f"Cuota agotada ({reason}): {message}") from exc

            retryable = status in RETRYABLE_STATUSES or (
                status == 403 and reason in RATE_LIMIT_REASONS
            )
            if not retryable or attempt == max_retries:
                raise ApiRequestError(status, reason, message) from exc
            error_summary = f"HTTP {status} ({reason})"
        except (TimeoutError, ConnectionError) as exc:
            if attempt == max_retries:
                raise ApiRequestError(0, "network", str(exc)) from exc
            error_summary = f"error de red: {exc}"

        delay = base_delay * (2**attempt) + random.uniform(0, 1)
        log.warning(
            "%s; reintento %d/%d en %.1fs", error_summary, attempt + 1, max_retries, delay
        )
        time.sleep(delay)

    raise AssertionError("Inalcanzable: el bucle siempre retorna o lanza.")