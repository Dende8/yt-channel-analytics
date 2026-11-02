"""Previsión a 7 días de un vídeo largo a partir de los minutos de sus dos primeros días."""

import sys
from datetime import datetime, time
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utilidades import (  # noqa: E402
    FECHA_CAMBIO_VISUALIZACION,
    cargar_datos,
    cargar_paquete_modelo,
    configurar_pagina,
    largos_con_ventana_7d,
    numero,
    porcentaje,
)

from src.modelo import ZONA_DIA_ANALYTICS, ZONA_USUARIO, predecir  # noqa: E402

VIDEOS_HISTORICO = 50
MINUTOS_POR_HORA = 60


def en_horas(minutos: float, decimales: int = 1) -> str:
    """Convierte minutos a horas y las da formateadas."""
    return numero(minutos / MINUTOS_POR_HORA, decimales)


configurar_pagina("Analizar un vídeo")
maestra, _ = cargar_datos()
paquete = cargar_paquete_modelo()
largos = largos_con_ventana_7d(maestra)
historico = largos.tail(VIDEOS_HISTORICO)

st.title("Analizar un vídeo")
st.write(
    "Introduce la fecha de publicación y las horas de visualización de cada uno de los dos primeros días, "
    "tal como aparecen en YouTube Studio («Tiempo de visualización (horas)»). El día 1 es el día natural de la "
    "publicación, en el calendario del Pacífico (el que usa YouTube Analytics), y el día 2 es el siguiente."
)

ahora = pd.Timestamp.now(tz=ZONA_USUARIO)

with st.form("formulario"):
    col_fecha, col_hora = st.columns(2)
    fecha = col_fecha.date_input("Fecha de publicación (hora de Madrid)", value=ahora.date() - pd.Timedelta(days=3))
    hora = col_hora.time_input("Hora de publicación (hora de Madrid)", value=time(18, 0), step=300)
    col_d1, col_d2 = st.columns(2)
    horas_dia1 = col_d1.number_input(
        "Horas de visualización del día 1", min_value=0.0, value=0.0, step=0.1, format="%.2f"
    )
    horas_dia2 = col_d2.number_input(
        "Horas de visualización del día 2", min_value=0.0, value=0.0, step=0.1, format="%.2f"
    )
    st.caption(
        "Introduce las horas de cada día por separado, no el acumulado. Si en YouTube Studio consultas el rango "
        "de los dos días, el día 2 es ese total menos las horas del día 1."
    )
    enviado = st.form_submit_button("Calcular previsión")

if not enviado:
    st.info("Rellena los datos y pulsa «Calcular previsión».")
    st.stop()

min_dia1 = horas_dia1 * MINUTOS_POR_HORA
min_dia2 = horas_dia2 * MINUTOS_POR_HORA

publicado = pd.Timestamp(datetime.combine(fecha, hora)).tz_localize(ZONA_USUARIO)
dia1_pacifico = publicado.tz_convert(ZONA_DIA_ANALYTICS).normalize()
fin_dia2 = dia1_pacifico + pd.Timedelta(days=2)

if publicado > ahora:
    st.error("La fecha de publicación es posterior al momento actual.")
    st.stop()
if ahora.tz_convert(ZONA_DIA_ANALYTICS).tz_localize(None) < fin_dia2.tz_localize(None):
    st.error(
        "Los dos primeros días todavía no han terminado en el calendario del Pacífico "
        f"({fin_dia2.strftime('%d/%m/%Y %H:%M')} hora del Pacífico). "
        "La previsión necesita los dos días completos."
    )
    st.stop()
if horas_dia1 + horas_dia2 <= 0:
    st.error("Hacen falta horas de visualización en alguno de los dos días.")
    st.stop()

prevision = predecir(paquete, min_dia1, min_dia2, publicado.to_pydatetime())

st.subheader("Previsión de horas de visualización a 7 días")
col1, col2, col3 = st.columns(3)
col1.metric("Estimación (horas)", en_horas(prevision.estimacion))
col2.metric(
    f"Rango al {int(prevision.nivel * 100)} % (horas)",
    f"{en_horas(prevision.inferior)} – {en_horas(prevision.superior)}",
)
col3.metric("Horas ya observadas (2 días)", en_horas(prevision.minutos_observados))
st.caption(
    f"Se espera que el vídeo multiplique por {numero(prevision.estimacion / prevision.minutos_observados, 2)} "
    "las horas de los dos primeros días. El rango recoge el error que ha tenido el modelo con vídeos que "
    "no había visto durante el entrenamiento."
)

st.subheader("Comparación con los últimos vídeos largos")
reales = historico["minutos_7d"] / MINUTOS_POR_HORA
estimacion_horas = prevision.estimacion / MINUTOS_POR_HORA
posicion = (reales < estimacion_horas).mean()
st.write(
    f"La estimación sería superior a la de {porcentaje(posicion, 0)} de los últimos {len(historico)} vídeos "
    f"largos con 7 días completos (mediana: {numero(reales.median(), 1)} horas)."
)

figura = go.Figure()
figura.add_histogram(x=reales, nbinsx=20, name="Últimos vídeos", marker_color="#8da0b8")
figura.add_vrect(
    x0=prevision.inferior / MINUTOS_POR_HORA,
    x1=prevision.superior / MINUTOS_POR_HORA,
    fillcolor="#d95f02",
    opacity=0.15,
    line_width=0,
)
figura.add_vline(x=estimacion_horas, line_color="#d95f02", line_width=3)
figura.update_layout(
    xaxis_title="Horas de visualización en los 7 primeros días",
    yaxis_title="Vídeos",
    showlegend=False,
    margin=dict(l=10, r=10, t=10, b=10),
    height=320,
)
st.plotly_chart(figura)
st.caption("La banda naranja es el rango de la previsión y la línea, la estimación.")

avisos = []
if (publicado + pd.Timedelta(days=7)).tz_localize(None) > FECHA_CAMBIO_VISUALIZACION and publicado.tz_localize(
    None
) < FECHA_CAMBIO_VISUALIZACION + pd.Timedelta(days=7):
    avisos.append("La ventana de 7 días incluye el 24/08/2026, fecha en la que cambió la definición de visualización.")
if publicado.tz_localize(None) >= FECHA_CAMBIO_VISUALIZACION:
    avisos.append(
        "El vídeo se publicó después del 24/08/2026. En los vídeos de esa etapa el error absoluto fue mayor, "
        "tanto para el modelo como para la referencia, y hay pocos ejemplos para evaluarlo."
    )
minimo, maximo = largos["minutos_2d"].min(), largos["minutos_2d"].max()
if not minimo <= prevision.minutos_observados <= maximo:
    avisos.append(
        f"Las horas de los dos primeros días ({en_horas(prevision.minutos_observados)}) quedan fuera del rango "
        f"visto en los datos ({en_horas(minimo)} a {en_horas(maximo)}). La previsión extrapola."
    )
if prevision.horas_dia1 < 3:
    avisos.append(
        f"El vídeo se publicó con solo {numero(prevision.horas_dia1, 1)} h por delante hasta el final del día 1 "
        "en el calendario del Pacífico, así que el día 1 es casi un día vacío."
    )
if horas_dia1 == 0 or horas_dia2 == 0:
    avisos.append("Uno de los dos días tiene 0 horas; comprueba que los datos son correctos.")

if avisos:
    st.subheader("Avisos")
    for aviso in avisos:
        st.warning(aviso)
