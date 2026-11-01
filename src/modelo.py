"""Previsión de los minutos visualizados a 7 días de un vídeo largo a partir de sus 2 primeros días.

Este módulo lo usan el cuaderno `03_modelo` (entrenamiento y evaluación) y la aplicación, de modo que las
variables del modelo se construyen siempre con el mismo código.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from joblib import load

DIAS_ENTRADA = 2
HORIZONTE = 7
# Los días de la API de Analytics empiezan a las 00:00 hora del Pacífico (UTC-7 o UTC-8)
ZONA_DIA_ANALYTICS = "America/Los_Angeles"
ZONA_USUARIO = "Europe/Madrid"
RUTA_MODELO = Path(__file__).resolve().parents[1] / "models" / "modelo_prevision_2d.joblib"


@dataclass(frozen=True)
class Prevision:
    """Resultado de una previsión, en minutos acumulados a 7 días."""

    minutos_observados: float
    estimacion: float
    inferior: float
    superior: float
    crecimiento_log: float
    horas_dia1: float
    nivel: float


def horas_restantes_dia1(publicado: pd.Series) -> pd.Series:
    """Horas del día 1 (calendario del Pacífico) que quedan desde la publicación hasta la medianoche."""
    local = pd.to_datetime(publicado, utc=True).dt.tz_convert(ZONA_DIA_ANALYTICS)
    return 24 - (local.dt.hour + local.dt.minute / 60)


def construir_variables(entradas: pd.DataFrame, publicado: pd.Series) -> pd.DataFrame:
    """Transforma las entradas en las variables del modelo.

    Siempre calcula las tres variables base. Las ampliadas solo se calculan si `entradas` incluye las columnas
    que necesitan, de modo que la aplicación no tiene que pedir datos que el modelo final no usa.
    """
    min_1, min_2 = entradas["min_dia1"], entradas["min_dia2"]
    total = min_1 + min_2

    variables = pd.DataFrame(index=entradas.index)
    variables["log_min_2d"] = np.log1p(total)
    variables["log_cociente_d2_d1"] = np.log1p(min_2) - np.log1p(min_1)
    variables["horas_dia1"] = horas_restantes_dia1(publicado).to_numpy()

    columna_vistas = f"vistas_{DIAS_ENTRADA}d"
    columna_subs = f"subs_netos_{DIAS_ENTRADA}d"
    if columna_vistas in entradas:
        vistas = entradas[columna_vistas].clip(lower=1)
        variables["log_min_por_vista"] = np.log(total.clip(lower=1) / vistas)
        if columna_subs in entradas:
            variables["asinh_subs_por_mil"] = np.arcsinh(entradas[columna_subs] / vistas * 1000)
    if "duracion_min" in entradas:
        variables["log_duracion_min"] = np.log(entradas["duracion_min"])
    if "dia_semana" in entradas:
        variables["dia_semana"] = entradas["dia_semana"]
    return variables


def intervalo_minutos(observado, crecimiento, q_inf, q_sup):
    """Rango de minutos a 7 días. Los minutos acumulados no pueden bajar de lo ya observado."""
    inferior = np.maximum(np.expm1(np.log1p(observado) + crecimiento + q_inf), observado)
    superior = np.maximum(np.expm1(np.log1p(observado) + crecimiento + q_sup), observado)
    return inferior, superior


def cargar_modelo(ruta: Path = RUTA_MODELO) -> dict:
    """Carga el paquete guardado por el cuaderno `03_modelo` y avisa si cambian las versiones de las librerías."""
    if not Path(ruta).is_file():
        raise FileNotFoundError(
            f"No se encuentra el modelo en {ruta}. Ejecuta el cuaderno 03_modelo para generarlo."
        )
    paquete = load(ruta)

    import sklearn

    version_guardada = paquete.get("versiones", {}).get("scikit-learn")
    if version_guardada and version_guardada != sklearn.__version__:
        warnings.warn(
            f"El modelo se guardó con scikit-learn {version_guardada} y está instalada la {sklearn.__version__}. "
            "Si hay errores o resultados extraños, reinstala las versiones de requirements.txt.",
            stacklevel=2,
        )
    return paquete


def predecir(paquete: dict, min_dia1: float, min_dia2: float, publicado: datetime) -> Prevision:
    """Estima los minutos a 7 días de un vídeo a partir de sus 2 primeros días.

    `publicado` es la fecha y hora de publicación. Si no lleva zona horaria se interpreta como hora de Madrid.
    """
    if min_dia1 < 0 or min_dia2 < 0:
        raise ValueError("Los minutos de cada día no pueden ser negativos.")
    if min_dia1 + min_dia2 <= 0:
        raise ValueError("Hacen falta minutos visualizados en alguno de los dos primeros días.")

    momento = pd.Timestamp(publicado)
    if momento.tzinfo is None:
        momento = momento.tz_localize(ZONA_USUARIO)

    entradas = pd.DataFrame({"min_dia1": [float(min_dia1)], "min_dia2": [float(min_dia2)]})
    variables = construir_variables(entradas, pd.Series([momento]))

    columnas = paquete["columnas"]
    faltan = [c for c in columnas if c not in variables.columns]
    if faltan:
        raise ValueError(f"El modelo guardado necesita variables que no se han proporcionado: {faltan}")

    crecimiento = float(paquete["modelo"].predict(variables[columnas])[0])
    observado = float(min_dia1 + min_dia2)
    estimacion = float(np.expm1(np.log1p(observado) + crecimiento))
    inferior, superior = intervalo_minutos(
        observado, crecimiento, paquete["cuantil_inferior"], paquete["cuantil_superior"]
    )
    return Prevision(
        minutos_observados=observado,
        estimacion=estimacion,
        inferior=float(inferior),
        superior=float(superior),
        crecimiento_log=crecimiento,
        horas_dia1=float(variables["horas_dia1"].iloc[0]),
        nivel=float(paquete["nivel_intervalo"]),
    )