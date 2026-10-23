"""Ejecución de un informe de YouTube Analytics API."""

from __future__ import annotations

from datetime import date
from typing import Any

from .api_client import execute_with_retry
from .reports import ReportSpec


def build_query_params(
    spec: ReportSpec,
    start: date,
    end: date,
    *,
    video_id: str | None = None,
    currency: str | None = None,
) -> dict[str, str]:
    """Traduce un ReportSpec a los parámetros de `reports().query()`.

    Solo incluye los parámetros que aplican (nunca valores None).
    """
    params = {
        "ids": "channel==MINE",
        "startDate": start.isoformat(),
        "endDate": end.isoformat(),
        "metrics": ",".join(spec.metrics),
    }
    if spec.dimensions:
        params["dimensions"] = ",".join(spec.dimensions)
    if spec.sort:
        params["sort"] = spec.sort
    if video_id:
        params["filters"] = f"video=={video_id}"
    if currency and spec.is_revenue:
        params["currency"] = currency
    return params


def query_report(
    service: Any,
    spec: ReportSpec,
    start: date,
    end: date,
    *,
    video_id: str | None = None,
    currency: str | None = None,
    pause: float = 0.0,
) -> dict:
    """Ejecuta un informe y devuelve un sobre con metadatos, petición y respuesta.

    Guardar la petición junto a la respuesta permite auditar después qué se pidió.
    """
    params = build_query_params(spec, start, end, video_id=video_id, currency=currency)
    response = execute_with_retry(service.reports().query(**params), pause=pause)

    meta = {
        "report": spec.name,
        "scope": spec.scope,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
    }
    if video_id:
        meta["video_id"] = video_id
    return {"meta": meta, "request": params, "response": response}