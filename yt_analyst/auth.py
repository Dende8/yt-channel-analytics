"""Autenticación OAuth 2.0 a partir de un refresh token ya obtenido."""

from __future__ import annotations

import logging

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

from .config import Settings
from .errors import AuthenticationError

log = logging.getLogger(__name__)

# Deben coincidir (o ser subconjunto) de los scopes que el propietario concedió
# al generar el refresh token.
SCOPES = [
    "https://www.googleapis.com/auth/yt-analytics.readonly",
    "https://www.googleapis.com/auth/yt-analytics-monetary.readonly",
    "https://www.googleapis.com/auth/youtube.readonly",
]

TOKEN_URI = "https://oauth2.googleapis.com/token"


def build_credentials(settings: Settings) -> Credentials:
    """Construye credenciales y obtiene un access token válido (~1 hora).

    Las librerías de Google renuevan el access token automáticamente cuando
    caduca durante una ejecución larga.

    Raises:
        AuthenticationError: si el refresh token no es válido (caducado en modo
            test tras 7 días, revocado, o scopes que no coinciden).
    """
    credentials = Credentials(
        token=None,  # aún no hay access token; lo genera refresh()
        refresh_token=settings.refresh_token,
        token_uri=TOKEN_URI,
        client_id=settings.client_id,
        client_secret=settings.client_secret,
        scopes=SCOPES,
    )
    try:
        credentials.refresh(Request())
    except RefreshError as exc:
        raise AuthenticationError(
            f"No se pudo renovar el access token: {exc}. "
            "En modo test el refresh token caduca a los 7 días; "
            "si es el caso, el propietario debe volver a autorizar."
        ) from exc
    log.info("Access token obtenido correctamente.")
    return credentials