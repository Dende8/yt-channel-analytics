"""Definición declarativa de los informes de YouTube Analytics.

Añadir un informe nuevo = añadir un ReportSpec a las tuplas de abajo.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ReportSpec:
    """Describe una consulta a la Analytics API.

    Attributes:
        name: identificador (nombre de carpeta y de CSV).
        scope: 'channel' (todo el canal) o 'video' (un vídeo concreto).
        metrics: métricas a pedir.
        dimensions: dimensiones de agrupación (vacío = un único total).
        sort: criterio de ordenación (obligatorio en algunos informes).
        windowed: si True, se trocea por años (series diarias largas).
        is_revenue: si True, usa métricas monetarias y admite `currency`.
    """

    name: str
    scope: str
    metrics: tuple[str, ...]
    dimensions: tuple[str, ...] = ()
    sort: str | None = None
    windowed: bool = False
    is_revenue: bool = False


CORE_METRICS = (
    "views",
    "estimatedMinutesWatched",
    "averageViewDuration",
    "averageViewPercentage",
    "likes",
    "dislikes",
    "comments",
    "shares",
    "subscribersGained",
    "subscribersLost",
    "videosAddedToPlaylists",
    "videosRemovedFromPlaylists",
)

REVENUE_METRICS = (
    "estimatedRevenue",
    "estimatedAdRevenue",
    "grossRevenue",
    "cpm",
    "playbackBasedCpm",
    "adImpressions",
    "monetizedPlaybacks",
)

# Subconjunto de métricas de ingresos para informes desglosados por dimensión
# (menos métricas = menos probabilidad de combinación no admitida por la API).
REVENUE_SLIM_METRICS = (
    "estimatedRevenue",
    "monetizedPlaybacks",
    "playbackBasedCpm",
)

VIDEO_DAILY_METRICS = (
    "views",
    "estimatedMinutesWatched",
    "averageViewDuration",
    "averageViewPercentage",
    "likes",
    "comments",
    "shares",
    "subscribersGained",
    "subscribersLost",
)

CHANNEL_REPORTS: tuple[ReportSpec, ...] = (
    ReportSpec("daily", "channel", CORE_METRICS, ("day",), "day", windowed=True),
    ReportSpec(
        "revenue_daily", "channel", REVENUE_METRICS, ("day",), "day",
        windowed=True, is_revenue=True,
    ),
    ReportSpec(
        "traffic_source", "channel", ("views", "estimatedMinutesWatched"),
        ("insightTrafficSourceType",), "-views",
    ),
    ReportSpec(
        "country", "channel", ("views", "estimatedMinutesWatched", "subscribersGained"),
        ("country",), "-views",
    ),
    ReportSpec(
        "device_type", "channel", ("views", "estimatedMinutesWatched"),
        ("deviceType",), "-views",
    ),
    ReportSpec(
        "operating_system", "channel", ("views", "estimatedMinutesWatched"),
        ("operatingSystem",), "-views",
    ),
    ReportSpec(
        "demographics", "channel", ("viewerPercentage",),
        ("ageGroup", "gender"), "gender,ageGroup",
    ),
    ReportSpec(
        "content_type", "channel", ("views", "estimatedMinutesWatched"),
        ("creatorContentType",), "-views",
    ),
    # Evolución diaria por tipo de contenido (Shorts / vídeo / directo) y año.
    ReportSpec(
        "content_type_daily", "channel", ("views", "estimatedMinutesWatched"),
        ("day", "creatorContentType"), "day", windowed=True,
    ),
    # Audiencia suscrita frente a no suscrita (nivel canal).
    ReportSpec(
        "subscribed_status", "channel", ("views", "estimatedMinutesWatched"),
        ("subscribedStatus",), "-views",
    ),
    # Ingresos por país (nivel canal).
    ReportSpec(
        "country_revenue", "channel", REVENUE_SLIM_METRICS,
        ("country",), "-estimatedRevenue", is_revenue=True,
    ),
)

VIDEO_REPORTS: tuple[ReportSpec, ...] = (
    ReportSpec("totals", "video", CORE_METRICS),
    ReportSpec("daily", "video", VIDEO_DAILY_METRICS, ("day",), "day"),
    ReportSpec(
        "traffic_source", "video", ("views", "estimatedMinutesWatched"),
        ("insightTrafficSourceType",), "-views",
    ),
    ReportSpec(
        "retention", "video", ("audienceWatchRatio", "relativeRetentionPerformance"),
        ("elapsedVideoTimeRatio",), "elapsedVideoTimeRatio",
    ),
    ReportSpec("revenue_totals", "video", REVENUE_METRICS, is_revenue=True),
    # --- Nuevos ---
    # Ingresos día a día por vídeo: permite medir los primeros 7/28 días de cada
    # vídeo y evita el sesgo de los publicados antes de la monetización.
    ReportSpec("revenue_daily", "video", REVENUE_METRICS, ("day",), "day", is_revenue=True),
    # Audiencia por país (vistas y minutos) y su ingreso, para contrastar la
    # hipótesis de que el RPM depende del origen de la audiencia.
    ReportSpec(
        "country", "video", ("views", "estimatedMinutesWatched"),
        ("country",), "-views",
    ),
    ReportSpec(
        "country_revenue", "video", REVENUE_SLIM_METRICS,
        ("country",), "-estimatedRevenue", is_revenue=True,
    ),
    # Audiencia suscrita frente a no suscrita por vídeo.
    ReportSpec(
        "subscribed_status", "video", ("views", "estimatedMinutesWatched"),
        ("subscribedStatus",), "-views",
    ),
)