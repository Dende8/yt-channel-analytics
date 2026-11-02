"""Panel con la evolución del canal y el rendimiento reciente de los vídeos largos."""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utilidades import (  # noqa: E402
    cargar_datos,
    cargar_paquete_modelo,
    configurar_pagina,
    largos_con_ventana_7d,
    numero,
)

from src.modelo import construir_variables, intervalo_minutos  # noqa: E402

configurar_pagina("Panel del canal")
maestra, _ = cargar_datos()
paquete = cargar_paquete_modelo()
largos = largos_con_ventana_7d(maestra)

st.title("Panel del canal")

# Evolución mensual
st.subheader("Evolución mensual de los vídeos largos")
largos["mes"] = largos["published_at"].dt.tz_localize(None).dt.to_period("M").dt.to_timestamp()
mensual = largos.groupby("mes").agg(videos=("video_id", "count"), minutos_7d=("minutos_7d", "sum")).reset_index()
mensual["mediana_por_video"] = largos.groupby("mes")["minutos_7d"].median().to_numpy()

figura = go.Figure()
figura.add_bar(x=mensual["mes"], y=mensual["minutos_7d"], name="Minutos en los 7 primeros días", marker_color="#8da0b8")
figura.add_scatter(
    x=mensual["mes"], y=mensual["mediana_por_video"], name="Mediana por vídeo", yaxis="y2", line=dict(color="#d95f02")
)
figura.update_layout(
    yaxis=dict(title="Minutos totales"),
    yaxis2=dict(title="Mediana por vídeo", overlaying="y", side="right"),
    legend=dict(orientation="h", y=1.12),
    margin=dict(l=10, r=10, t=10, b=10),
    height=360,
)
st.plotly_chart(figura)
st.caption("Solo vídeos largos con los 7 primeros días completos, agrupados por mes de publicación.")

# Curva típica de acumulación
st.subheader("Cómo se acumulan los minutos en la primera semana")
curva = pd.DataFrame(
    {dia: largos[f"minutos_{dia}d"] / largos["minutos_7d"] for dia in (1, 2, 3, 7)}
).dropna()
resumen = curva.quantile([0.25, 0.5, 0.75]).T
resumen.columns = ["p25", "mediana", "p75"]

figura = go.Figure()
figura.add_scatter(x=resumen.index, y=resumen["p75"], line=dict(width=0), showlegend=False, hoverinfo="skip")
figura.add_scatter(
    x=resumen.index,
    y=resumen["p25"],
    fill="tonexty",
    fillcolor="rgba(141,160,184,0.3)",
    line=dict(width=0),
    name="Entre el percentil 25 y el 75",
)
figura.add_scatter(x=resumen.index, y=resumen["mediana"], name="Mediana", line=dict(color="#d95f02", width=3))
figura.update_layout(
    xaxis=dict(title="Día desde la publicación", tickvals=[1, 2, 3, 7]),
    yaxis=dict(title="Parte de los minutos de 7 días", tickformat=".0%", range=[0, 1.02]),
    legend=dict(orientation="h", y=1.12),
    margin=dict(l=10, r=10, t=10, b=10),
    height=340,
)
st.plotly_chart(figura)
st.caption(
    f"Mediana acumulada: {resumen.loc[1, 'mediana']:.0%} el día 1, {resumen.loc[2, 'mediana']:.0%} el día 2 "
    f"y {resumen.loc[3, 'mediana']:.0%} el día 3. El día 1 es el natural de la publicación y suele estar incompleto."
)

# Rendimiento frente a lo esperado
st.subheader("Últimos vídeos frente a lo esperado")
entradas = pd.DataFrame(
    {"min_dia1": largos["minutos_1d"].to_numpy(), "min_dia2": (largos["minutos_2d"] - largos["minutos_1d"]).to_numpy()},
    index=largos.index,
)
variables = construir_variables(entradas, largos["published_at"])
crecimiento = paquete["modelo"].predict(variables[paquete["columnas"]])
observado = largos["minutos_2d"].to_numpy()
esperado = np.expm1(np.log1p(observado) + crecimiento)
inferior, superior = intervalo_minutos(observado, crecimiento, paquete["cuantil_inferior"], paquete["cuantil_superior"])

rendimiento = pd.DataFrame(
    {
        "Publicado": largos["published_at"].dt.tz_localize(None).dt.strftime("%d/%m/%Y"),
        "Título": largos["title"],
        "Minutos 2 días": observado,
        "Esperado 7 días": esperado,
        "Real 7 días": largos["minutos_7d"],
    }
)
rendimiento["Real / esperado"] = rendimiento["Real 7 días"] / rendimiento["Esperado 7 días"]
rendimiento["Situación"] = np.select(
    [largos["minutos_7d"].to_numpy() > superior, largos["minutos_7d"].to_numpy() < inferior],
    ["Por encima del rango", "Por debajo del rango"],
    default="Dentro del rango",
)

n_mostrar = st.slider("Vídeos a mostrar (los más recientes)", 5, min(50, len(rendimiento)), min(15, len(rendimiento)))
tabla = rendimiento.tail(n_mostrar).iloc[::-1]
st.dataframe(
    tabla,
    hide_index=True,
    column_config={
        "Minutos 2 días": st.column_config.NumberColumn(format="%d"),
        "Esperado 7 días": st.column_config.NumberColumn(format="%d"),
        "Real 7 días": st.column_config.NumberColumn(format="%d"),
        "Real / esperado": st.column_config.NumberColumn(format="%.2f"),
    },
)
st.caption(
    "Los vídeos de esta tabla forman parte de los datos con los que se entrenó el modelo, por lo que la "
    "comparación sirve para describir qué vídeos se alejaron de lo habitual, no para medir la precisión del "
    "modelo (esa medida está en la página de metodología). Total de vídeos largos con 7 días completos: "
    f"{numero(len(largos))}."
)
