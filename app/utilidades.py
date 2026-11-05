"""Funciones comunes de la aplicación: rutas, carga de datos y formato."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from src.modelo import cargar_modelo  # noqa: E402

RUTA_MAESTRA = RAIZ / "data" / "processed" / "videos_maestra.csv"
RUTA_PANEL = RAIZ / "data" / "processed" / "panel_diario.csv"

# Desde esta fecha YouTube cuenta como visualización la reproducción desde el primer fotograma
FECHA_CAMBIO_VISUALIZACION = pd.Timestamp("2026-08-24")

# Población del modelo: los dos vídeos de 2017 son casos aislados y quedan fuera, como en el cuaderno 03
FECHA_INICIO_MODELO = pd.Timestamp("2025-01-01", tz="UTC")

# Resultados del cuaderno 03_modelo (sección 17), evaluados con los 64 vídeos más recientes
RESULTADOS_PRUEBA = pd.DataFrame(
    {
        "Referencia": [0.184, 0.128, 0.913, 0.779],
        "Modelo": [0.156, 0.106, 0.944, 0.673],
    },
    index=[
        "Error medio en logaritmo (7 días)",
        "Error relativo mediano",
        "R² en logaritmo",
        "Error en los minutos que llegan después de los 2 días",
    ],
)
MEJORA_PRUEBA = {"reduccion": 0.152, "intervalo_90": (0.088, 0.203), "videos_mejor": 43, "videos_prueba": 64}
COBERTURA_PRUEBA = 0.875


def configurar_pagina(titulo: str) -> None:
    """Configuración común de cada página."""
    st.set_page_config(page_title=titulo, layout="wide")


def numero(valor: float, decimales: int = 0) -> str:
    """Formatea un número con el separador de miles y decimales del español."""
    texto = f"{valor:,.{decimales}f}"
    return texto.replace(",", "X").replace(".", ",").replace("X", ".")


def porcentaje(valor: float, decimales: int = 1) -> str:
    """Formatea una proporción como porcentaje con el formato del español."""
    return numero(valor * 100, decimales) + " %"


@st.cache_data(show_spinner=False)
def _leer_datos() -> tuple[pd.DataFrame, pd.DataFrame]:
    maestra = pd.read_csv(RUTA_MAESTRA, parse_dates=["primer_dia"])
    maestra["published_at"] = pd.to_datetime(maestra["published_at"], utc=True)
    panel = pd.read_csv(RUTA_PANEL, parse_dates=["day"])
    return maestra, panel


def cargar_datos() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Devuelve la tabla maestra y el panel diario, o detiene la página con un mensaje si faltan."""
    try:
        return _leer_datos()
    except FileNotFoundError:
        st.error(
            "No se encuentran los datos procesados en `data/processed/`. "
            "Ejecuta el cuaderno `notebooks/01_preprocesamiento.ipynb` para generarlos."
        )
        st.stop()


@st.cache_resource(show_spinner=False)
def _leer_modelo() -> dict:
    return cargar_modelo()


def cargar_paquete_modelo() -> dict:
    """Devuelve el modelo guardado, o detiene la página con un mensaje si no existe."""
    try:
        return _leer_modelo()
    except FileNotFoundError:
        st.error(
            "No se encuentra el modelo en `models/`. "
            "Ejecuta el cuaderno `notebooks/03_modelo.ipynb` para generarlo."
        )
        st.stop()


def largos_con_ventana_7d(maestra: pd.DataFrame) -> pd.DataFrame:
    """Vídeos largos con los 7 primeros días completos publicados desde 2025, ordenados por fecha."""
    largos = maestra[
        (maestra["formato"] == "long")
        & maestra["minutos_7d"].notna()
        & (maestra["published_at"] >= FECHA_INICIO_MODELO)
    ]
    return largos.sort_values("published_at").reset_index(drop=True)