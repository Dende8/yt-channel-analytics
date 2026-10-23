"""Llamadas a YouTube Data API v3: canal, lista de subidas y metadatos de vídeos."""

from __future__ import annotations

import logging
from collections.abc import Iterator, Sequence
from typing import Any

from .api_client import execute_with_retry
from .storage import RawStore

log = logging.getLogger(__name__)

VIDEO_PARTS = "snippet,contentDetails,statistics,status,liveStreamingDetails"
BATCH_SIZE = 50  # máximo de IDs por llamada a videos.list


def chunked(items: Sequence[Any], size: int) -> Iterator[Sequence[Any]]:
    """Divide una secuencia en trozos consecutivos de como mucho `size` elementos."""
    for start in range(0, len(items), size):
        yield items[start : start + size]


def fetch_channel(service: Any) -> dict:
    """Obtiene el canal de la cuenta autorizada (mine=True) con sus estadísticas."""
    request = service.channels().list(part="snippet,contentDetails,statistics", mine=True)
    return execute_with_retry(request)


def fetch_uploads_playlist_items(service: Any, playlist_id: str) -> list[dict]:
    """Recorre toda la playlist de subidas (paginando) y devuelve sus elementos."""
    items: list[dict] = []
    page_token: str | None = None
    while True:
        request = service.playlistItems().list(
            part="contentDetails",
            playlistId=playlist_id,
            maxResults=50,
            pageToken=page_token,
        )
        response = execute_with_retry(request)
        items.extend(response.get("items", []))
        page_token = response.get("nextPageToken")
        log.info("Subidas listadas: %d", len(items))
        if not page_token:
            return items


def fetch_videos_batch(service: Any, video_ids: Sequence[str]) -> dict:
    """Obtiene metadatos y estadísticas de hasta 50 vídeos en una sola llamada."""
    request = service.videos().list(part=VIDEO_PARTS, id=",".join(video_ids))
    return execute_with_retry(request)


def load_video_resources(store: RawStore) -> list[dict]:
    """Reúne todos los recursos de vídeo guardados en los lotes crudos."""
    videos: list[dict] = []
    for path in store.list_files("data_api", "videos"):
        videos.extend(RawStore.read_file(path).get("items", []))
    return videos