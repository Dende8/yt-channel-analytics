"""Descripción de los datos, el método, las métricas y las limitaciones de la herramienta."""

import sys
from math import exp
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utilidades import (  # noqa: E402
    COBERTURA_PRUEBA,
    MEJORA_PRUEBA,
    RESULTADOS_PRUEBA,
    cargar_paquete_modelo,
    configurar_pagina,
    porcentaje,
)

configurar_pagina("Metodología y limitaciones")
paquete = cargar_paquete_modelo()

st.title("Metodología y limitaciones")

st.header("Datos")
st.write(
    "Los datos se descargaron del propio canal con la API de YouTube Analytics y la API de datos de YouTube "
    "(paquete `yt_analyst`). Se trabaja con el detalle diario de cada vídeo. YouTube Analytics agrupa los días "
    "según el calendario del Pacífico, por lo que el día 1 de un vídeo es el día natural de su publicación en esa "
    "zona horaria: cubre entre 0 y 24 horas desde que se publica. Las visualizaciones anteriores a la publicación "
    "(unos pocos minutos como mucho) se guardan aparte y no cuentan en el día 1."
)

st.header("Qué predice el modelo")
st.write(
    "Minutos visualizados en los 7 primeros días de un vídeo largo, usando solo lo ocurrido en los 2 primeros. "
    "El modelo no predice el total directamente, sino el crecimiento (en logaritmo) respecto a lo ya observado. "
    "Usa tres variables: los minutos acumulados en los dos días, el cociente entre el día 2 y el día 1, y las "
    "horas que quedaban del día 1 cuando se publicó el vídeo."
)
st.write(
    f"Algoritmo: `GradientBoostingRegressor` con pérdida de Huber, árboles de profundidad 2 y 150 iteraciones. "
    f"Se entrenó con {paquete['videos_entrenamiento']} vídeos largos publicados entre "
    f"{paquete['primera_publicacion']} y {paquete['ultima_publicacion']}."
)

st.header("Cómo se evaluó")
st.write(
    "Los vídeos se ordenaron por fecha de publicación: el 75 % más antiguo (189 vídeos) sirvió para elegir y "
    "entrenar el modelo, con validación cruzada temporal, y el 25 % más reciente (64 vídeos) se reservó para "
    "evaluarlo una sola vez. La referencia con la que se compara es la más sencilla posible: aplicar a todos los "
    "vídeos el crecimiento mediano del entrenamiento."
)
tabla = RESULTADOS_PRUEBA.copy()
tabla.index.name = "Métrica"
st.dataframe(
    tabla.style.format("{:.3f}"),
)
inferior, superior = MEJORA_PRUEBA["intervalo_90"]
st.write(
    f"El error medio del modelo es un {porcentaje(MEJORA_PRUEBA['reduccion'])} menor que el de la referencia "
    f"(intervalo al 90 % por remuestreo: {porcentaje(inferior)} a {porcentaje(superior)}), y acierta mejor que "
    f"la referencia en {MEJORA_PRUEBA['videos_mejor']} de los {MEJORA_PRUEBA['videos_prueba']} vídeos de prueba."
)

st.header("Rango de la previsión")
st.write(
    "El rango se obtiene sumando al crecimiento previsto los cuantiles 10 y 90 del error que el modelo cometió con "
    f"vídeos que no había visto. Equivale, aproximadamente, a multiplicar la estimación por {exp(paquete['cuantil_inferior']):.2f} "
    f"y por {exp(paquete['cuantil_superior']):.2f}. El límite inferior nunca baja de los minutos ya observados. "
    f"En la prueba, el {porcentaje(COBERTURA_PRUEBA)} de los vídeos cayó dentro del rango: ninguno quedó por debajo "
    "y el resto lo superó por arriba."
)

st.header("Limitaciones")
st.markdown(
    """
- **Un único canal.** El modelo aprende los patrones de Puro Balompié y no es aplicable a otros canales.
- **Pocos vídeos de prueba.** Con 64 vídeos, la mejora medida tiene un margen de incertidumbre considerable.
- **Cambio del 24/08/2026.** Desde esa fecha cambió la definición de visualización en YouTube. No se ha podido
  corregir. Los vídeos posteriores tienen un error absoluto mayor, tanto en el modelo como en la referencia.
- **Día 1 parcial.** Depende de la hora de publicación, y de ahí que el modelo incluya las horas que quedan del día 1.
- **Formato.** Se modelan vídeos largos. Hay 7 vídeos largos de duración breve que se mantienen con una marca,
  y no se dispone de datos para distinguir formatos verticales.
- **Datos que no están disponibles** y que mejorarían la previsión: impresiones, porcentaje de clics, audiencia por
  horas y diferencia entre espectadores nuevos y recurrentes.
- **Sin causalidad.** El modelo anticipa un volumen de minutos, no explica por qué un vídeo funciona mejor.
"""
)
