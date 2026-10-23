"""Excepciones propias del proyecto."""


class YtAnalystError(Exception):
    """Clase base de todos los errores controlados del proyecto."""


class ConfigError(YtAnalystError):
    """Falta configuración obligatoria o tiene un formato inválido."""


class AuthenticationError(YtAnalystError):
    """El refresh token es inválido, ha caducado o ha sido revocado."""


class QuotaExceededError(YtAnalystError):
    """Se agotó la cuota diaria de la API; hay que reanudar más tarde."""


class ApiRequestError(YtAnalystError):
    """Una petición concreta falló de forma definitiva (tras los reintentos)."""

    def __init__(self, status: int, reason: str, message: str) -> None:
        super().__init__(f"HTTP {status} ({reason}): {message}")
        self.status = status
        self.reason = reason
        self.message = message