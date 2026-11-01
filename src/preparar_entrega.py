"""Genera los CSV que se entregan a partir de la extracción completa.

Deja fuera los vídeos no públicos (privados y no listados) de todos los ficheros
que tienen la columna video_id. El resto de ficheros se copia sin cambios.
Se ejecuta una sola vez, desde la raíz del proyecto.
"""

import shutil
from pathlib import Path

import pandas as pd

# El script vive en src/, así que la raíz del proyecto es la carpeta superior
RAIZ = Path(__file__).resolve().parents[1]
ORIGEN = RAIZ / "data" / "extraction" / "csv"
DESTINO = RAIZ / "data" / "csv"


def leer_como_texto(ruta: Path) -> pd.DataFrame:
    """Lee un CSV sin interpretar tipos, para escribirlo exactamente igual."""
    return pd.read_csv(ruta, dtype=str, keep_default_na=False, encoding="utf-8-sig")


def main() -> None:
    if not ORIGEN.is_dir():
        raise SystemExit(f"No existe la carpeta de origen: {ORIGEN}")
    DESTINO.mkdir(parents=True, exist_ok=True)

    videos = leer_como_texto(ORIGEN / "videos.csv")
    excluidos = set(videos.loc[videos["privacy_status"] != "public", "video_id"])
    print(f"Vídeos no públicos excluidos: {len(excluidos)}\n")
    if not excluidos:
        print("AVISO: no se ha encontrado ningún vídeo no público; revisa el origen.\n")

    for ruta in sorted(ORIGEN.glob("*.csv")):
        tabla = leer_como_texto(ruta)
        filas_origen = len(tabla)

        if "video_id" in tabla.columns:
            tabla = tabla[~tabla["video_id"].isin(excluidos)]
            tabla.to_csv(DESTINO / ruta.name, index=False, encoding="utf-8")
        else:
            shutil.copyfile(ruta, DESTINO / ruta.name)

        print(f"{ruta.name:45s} {filas_origen:>7d} -> {len(tabla):>7d} filas")


if __name__ == "__main__":
    main()