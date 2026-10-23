"""Transformación del JSON crudo a CSV listos para analizar."""

from __future__ import annotations

import logging

import pandas as pd

from .config import Settings
from .data_api import load_video_resources
from .dates import parse_rfc3339
from .reports import CHANNEL_REPORTS, VIDEO_REPORTS
from .shorts import classify_format, parse_iso8601_duration
from .storage import RawStore, write_csv

log = logging.getLogger(__name__)

_META_COLUMNS = ["report", "scope", "start_date", "end_date"]


def response_to_frame(response: dict) -> pd.DataFrame:
    """Convierte una respuesta de Analytics (columnHeaders + rows) en DataFrame."""
    columns = [header["name"] for header in response.get("columnHeaders", [])]
    return pd.DataFrame(response.get("rows", []), columns=columns)


def load_report(store: RawStore, *dir_parts: str) -> pd.DataFrame:
    """Concatena todos los JSON de una carpeta de informe en un único DataFrame.

    Cada fila recibe como columnas los metadatos del sobre (video_id, fechas...).
    """
    frames: list[pd.DataFrame] = []
    for path in store.list_files(*dir_parts):
        payload = RawStore.read_file(path)
        frame = response_to_frame(payload["response"])
        for key, value in payload["meta"].items():
            frame[key] = value
        frames.append(frame)
    frames = [f for f in frames if not f.empty]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def _flatten_video(item: dict, probe_result: bool | None) -> dict:
    """Aplana un recurso de vídeo a una fila con campos útiles para el análisis."""
    snippet = item.get("snippet", {})
    details = item.get("contentDetails", {})
    stats = item.get("statistics", {})
    status = item.get("status", {})
    published = parse_rfc3339(snippet["publishedAt"])
    video_format, format_source = classify_format(item, probe_result)
    tags = snippet.get("tags", [])
    title = snippet.get("title", "")

    return {
        "video_id": item["id"],
        "title": title,
        "published_at": published.isoformat(),
        "publish_weekday_utc": published.strftime("%A"),
        "publish_hour_utc": published.hour,
        "duration_seconds": parse_iso8601_duration(details.get("duration", "PT0S")),
        "format": video_format,
        "format_source": format_source,
        "title_length": len(title),
        "description_length": len(snippet.get("description", "")),
        "tags_count": len(tags),
        "tags": "|".join(tags),
        "category_id": snippet.get("categoryId"),
        "default_language": snippet.get("defaultLanguage"),
        "default_audio_language": snippet.get("defaultAudioLanguage"),
        "definition": details.get("definition"),
        "has_captions": details.get("caption"),
        "privacy_status": status.get("privacyStatus"),
        "is_public": status.get("privacyStatus") == "public",
        "made_for_kids": status.get("madeForKids"),
        "view_count": stats.get("viewCount"),
        "like_count": stats.get("likeCount"),
        "comment_count": stats.get("commentCount"),
    }


def build_videos_frame(store: RawStore) -> pd.DataFrame:
    """Construye la tabla de vídeos (metadatos + clasificación long/short/live)."""
    videos = load_video_resources(store)
    probe = store.read("shorts_probe") if store.exists("shorts_probe") else {}
    frame = pd.DataFrame([_flatten_video(v, probe.get(v["id"])) for v in videos])
    for column in ("view_count", "like_count", "comment_count"):
        if column in frame:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame


def build_video_performance(
    videos: pd.DataFrame, totals: pd.DataFrame, revenue: pd.DataFrame
) -> pd.DataFrame:
    """Une metadatos, totales de Analytics e ingresos y añade ratios derivados."""
    frame = videos.copy()
    for extra in (totals, revenue):
        if not extra.empty:
            frame = frame.merge(
                extra.drop(columns=_META_COLUMNS, errors="ignore"),
                on="video_id",
                how="left",
            )
    if "views" in frame:
        views = frame["views"].where(frame["views"] > 0)  # evita dividir por cero
        frame["watch_time_hours"] = frame["estimatedMinutesWatched"] / 60
        frame["likes_per_1k_views"] = frame["likes"] / views * 1000
        frame["comments_per_1k_views"] = frame["comments"] / views * 1000
        frame["shares_per_1k_views"] = frame["shares"] / views * 1000
        frame["net_subs_per_1k_views"] = (
            (frame["subscribersGained"] - frame["subscribersLost"]) / views * 1000
        )
    return frame


def run_transform(settings: Settings) -> None:
    """Genera todos los CSV a partir del JSON crudo existente (sin llamar a la API)."""
    store = RawStore(settings.raw_dir)
    csv_dir = settings.csv_dir

    if store.exists("data_api", "channel"):
        item = store.read("data_api", "channel")["items"][0]
        snippet, stats = item.get("snippet", {}), item.get("statistics", {})
        channel = pd.DataFrame(
            [
                {
                    "channel_id": item["id"],
                    "title": snippet.get("title"),
                    "custom_url": snippet.get("customUrl"),
                    "published_at": snippet.get("publishedAt"),
                    "country": snippet.get("country"),
                    "subscriber_count": stats.get("subscriberCount"),
                    "view_count": stats.get("viewCount"),
                    "video_count": stats.get("videoCount"),
                    "hidden_subscriber_count": stats.get("hiddenSubscriberCount"),
                }
            ]
        )
        write_csv(channel, csv_dir / "channel.csv")

    videos = build_videos_frame(store)
    if videos.empty:
        log.warning("No hay vídeos en el crudo; ¿se ejecutó 'extract'?")
    else:
        write_csv(videos, csv_dir / "videos.csv")
        log.info("videos.csv: %d filas", len(videos))

    reports = {
        **{("channel", s.name): s for s in CHANNEL_REPORTS},
        **{("video", s.name): s for s in VIDEO_REPORTS},
    }
    frames: dict[tuple[str, str], pd.DataFrame] = {}
    for (scope, name), _spec in reports.items():
        frame = load_report(store, "analytics", f"{scope}_{name}")
        if frame.empty:
            log.warning("Sin datos para analytics_%s_%s", scope, name)
            continue
        if "day" in frame:
            sort_cols = ["video_id", "day"] if "video_id" in frame else ["day"]
            frame = frame.sort_values(sort_cols).reset_index(drop=True)
        frames[(scope, name)] = frame
        write_csv(frame, csv_dir / f"analytics_{scope}_{name}.csv")
        log.info("analytics_%s_%s.csv: %d filas", scope, name, len(frame))

    if not videos.empty:
        performance = build_video_performance(
            videos,
            frames.get(("video", "totals"), pd.DataFrame()),
            frames.get(("video", "revenue_totals"), pd.DataFrame()),
        )
        write_csv(performance, csv_dir / "video_performance.csv")
        log.info("video_performance.csv: %d filas", len(performance))