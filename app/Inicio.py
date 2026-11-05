"""Página de inicio de la aplicación.

Se ejecuta con `streamlit run app/Inicio.py` desde la raíz del proyecto.
"""

import streamlit as st
from utilidades import (
    cargar_datos,
    cargar_paquete_modelo,
    configurar_pagina,
    largos_con_ventana_7d,
    numero,
)

configurar_pagina("Puro Balompié · Previsión de vídeos")

maestra, panel = cargar_datos()
paquete = cargar_paquete_modelo()
largos = largos_con_ventana_7d(maestra)

st.title("Puro Balompié: previsión de rendimiento de vídeos largos")
st.write(
    "Herramienta para el equipo del canal. Con los datos de los dos primeros días de un vídeo largo "
    "estima cuántos minutos acumulará en sus primeros 7 días, con un rango de valores razonables, y "
    "permite situarlo frente al histórico reciente del canal."
)

col1, col2, col3 = st.columns(3)
col1.metric("Vídeos analizados", numero(len(maestra)))
col2.metric("Vídeos largos con 7 días completos", numero(len(largos)))
col3.metric("Datos hasta", panel["day"].max().strftime("%d/%m/%Y"))

st.subheader("Qué se puede hacer")
st.page_link(
    "pages/1_Analizar_un_video.py",
    label="Analizar un vídeo",
    help="Introduce las horas (minutos) de los dos primeros días y obtén la previsión a 7 días.",
)
st.caption("Introduce los minutos de los dos primeros días de un vídeo y obtén la previsión a 7 días con su rango.")
st.page_link(
    "pages/2_Panel_del_canal.py",
    label="Panel del canal",
    help="Evolución del canal, curva típica de acumulación y rendimiento reciente.",
)
st.caption("Evolución mensual, curva típica de acumulación y comparación de los últimos vídeos con lo habitual.")
st.page_link(
    "pages/3_Metodologia.py",
    label="Metodología y limitaciones",
    help="Datos, decisiones, métricas del modelo y límites de la herramienta.",
)
st.caption("De dónde salen los datos, cómo se construye el modelo, cuánto acierta y qué no puede hacer.")

st.divider()
st.caption(
    f"Modelo entrenado con {numero(paquete['videos_entrenamiento'])} vídeos largos publicados entre "
    f"{paquete['primera_publicacion']} y {paquete['ultima_publicacion']}. "
    "Los datos proceden de la API de YouTube Analytics y la API de datos de YouTube."
)
