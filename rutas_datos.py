# -*- coding: utf-8 -*-
"""
rutas_datos.py — Dónde viven los datos del proyecto.

Todos los datos crudos y derivados se guardan en D:\\brasil2026_data porque el
disco C: está lleno. La raíz es configurable con la variable de entorno
BRASIL2026_DATA.

Uso desde otro script:

    import rutas_datos as rd
    archivo = rd.ruta("escrutinio_zonas_2026.csv")   # D:\\brasil2026_data\\...
    carpeta = rd.ruta_dir("secciones")               # crea y devuelve la carpeta

Migración (una vez):  python rutas_datos.py --migrar
  - Mueve los archivos de datos del repo a D:.
  - Deja los directorios grandes como junctions de NTFS apuntando a D: para
    que los scripts viejos que los referencian por ruta relativa sigan andando.
"""

import os
import shutil
import subprocess
import sys

REPO = os.path.dirname(os.path.abspath(__file__))
DATA_ROOT = os.environ.get("BRASIL2026_DATA", r"D:\brasil2026_data")

# Carpeta de datos derivados por tema (se crean al usarlas).
SUBCARPETAS = {
    "raw": "descargas crudas del TSE",
    "secciones": "votación por sección electoral 2022/2026",
    "lanzamiento": "reconstrucción de la publicación en vivo",
    "ei": "inferencia ecológica (migración de votos)",
    "backtest": "backtest de métodos",
}

# Archivos sueltos que deben vivir en D: (mismo nombre que en el repo).
ARCHIVOS_DATOS = [
    "escrutinio_zonas_2022.csv",
    "escrutinio_zonas_2026.csv",
    "escrutinio_zonas_2026maquinalabo.csv",
    "escrutinio_zonas_2026maquinarafa.csv",
    "serie_temporal_2026.csv",
    "control_versiones_2026.json",
    "padron_y_asistencia_2022.csv",
    "padron_2026.csv",
    "historico_proyecciones_2026.csv",
    "historico_swing_2026.csv",
    "historico_nacional_2022_1t.csv",
    "historico_nacional_2022_2t.csv",
    "candidatos_2022.csv",
    "datos_proyeccion_2026.json",
    "datos_proyeccion_schteingart_2026.json",
    "datos_proyeccion_swing_2026.json",
    "datos_proyeccion_v3_2026.json",
    "datos_proyeccion_v4_2026.json",
    "datos_web.json",
    "grafico_vivo_2026.png",
    "simulacion_swing_2026.png",
    "backtest_estados_2026.png",
    "backtest_metodos_2026.png",
]

# Directorios grandes que se mueven a D: y se enlazan con junctions.
DIRECTORIOS_DATOS = ["dados_tse_2022", "backtest_snapshots", "backtest_resultados"]


def asegurar_raiz():
    os.makedirs(DATA_ROOT, exist_ok=True)
    return DATA_ROOT


def ruta(nombre):
    """Ruta absoluta de un archivo de datos (no lo crea)."""
    if os.path.isabs(nombre):
        return nombre
    asegurar_raiz()
    return os.path.join(DATA_ROOT, nombre)


def ruta_dir(nombre):
    """Ruta de una subcarpeta de datos; la crea si no existe."""
    asegurar_raiz()
    p = os.path.join(DATA_ROOT, nombre)
    os.makedirs(p, exist_ok=True)
    return p


def _es_junction(path):
    try:
        out = subprocess.run(["cmd", "/c", "fsutil", "reparsepoint", "query", path],
                             capture_output=True, text=True)
        return out.returncode == 0
    except OSError:
        return False


def _crear_junction(link, target):
    if os.path.exists(link) or _es_junction(link):
        return False
    out = subprocess.run(["cmd", "/c", "mklink", "/J", link, target],
                         capture_output=True, text=True)
    return out.returncode == 0


def migrar():
    """Mueve los datos del repo a D: (idempotente)."""
    asegurar_raiz()
    movidos = 0
    for nombre in ARCHIVOS_DATOS:
        origen = os.path.join(REPO, nombre)
        destino = os.path.join(DATA_ROOT, nombre)
        if os.path.exists(origen) and not os.path.islink(origen):
            if not os.path.exists(destino):
                shutil.move(origen, destino)
                movidos += 1
            else:
                os.remove(origen)
    for nombre in DIRECTORIOS_DATOS:
        origen = os.path.join(REPO, nombre)
        destino = os.path.join(DATA_ROOT, nombre)
        if os.path.isdir(origen) and not _es_junction(origen):
            if not os.path.exists(destino):
                shutil.move(origen, destino)
            else:
                shutil.rmtree(origen)
            if _crear_junction(origen, destino):
                print(f"[junction] {origen} -> {destino}")
            movidos += 1
        elif not os.path.exists(destino) and os.path.exists(origen):
            _crear_junction(origen, destino)
    for sub in SUBCARPETAS:
        ruta_dir(sub)
    print(f"[OK] Migración terminada. {movidos} elementos movidos a {DATA_ROOT}")


if __name__ == "__main__":
    if "--migrar" in sys.argv:
        migrar()
    else:
        print(f"DATA_ROOT = {DATA_ROOT}")
        for nombre in ARCHIVOS_DATOS:
            p = os.path.join(DATA_ROOT, nombre)
            print(f"  {'OK ' if os.path.exists(p) else '   '} {nombre}")
        for nombre in DIRECTORIOS_DATOS:
            p = os.path.join(DATA_ROOT, nombre)
            print(f"  {'OK ' if os.path.exists(p) else '   '} {nombre}\\")
