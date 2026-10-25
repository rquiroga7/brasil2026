# -*- coding: utf-8 -*-
"""
runner_local.py — Orquestador local (scraper continuo + proyección/publicación).

Uso:
  python runner_local.py --turno 2     # 2ª vuelta (por defecto)
  python runner_local.py --turno 1     # 1ª vuelta (pipeline viejo)

2ª vuelta: lanza el raspador rápido RAP2 (_3X) con --turno 2, y en paralelo corre
proyeccion_2t.py (base 1ª vuelta 2026) y publicar_2t.py (rama `data2t`).

Variables de entorno:
  SCRAPER_INTERVAL   segundos entre pasadas completas del raspador (def. 20)
  PUBLISH_INTERVAL   segundos entre publicaciones (def. 60)
"""

import os
import sys
import time
import argparse
import subprocess

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

REPO = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
SCRAPER_INTERVAL = int(os.environ.get("SCRAPER_INTERVAL", "20"))
PUBLISH_INTERVAL = int(os.environ.get("PUBLISH_INTERVAL", "60"))


def correr(*args):
    print(f"\n$ {' '.join(args)}", flush=True)
    return subprocess.run([PY, *args], cwd=REPO).returncode


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--turno", default=os.environ.get("TURNO", "2"), choices=["1", "2"])
    args = ap.parse_args()
    turno = args.turno

    print(f"[*] Runner local | turno {turno} | raspador cada {SCRAPER_INTERVAL}s | "
          f"publicación cada {PUBLISH_INTERVAL}s")

    if turno == "2":
        raspador = subprocess.Popen(
            [PY, "scrapingbrasil2026zonpasG_rverboseRAP2_3X.py", "--turno", "2",
             "--intervalo", str(SCRAPER_INTERVAL), "--silencioso"], cwd=REPO)
    else:
        raspador = subprocess.Popen(
            [PY, "zonpasG_rodri.py", "--intervalo", str(SCRAPER_INTERVAL)], cwd=REPO)
    print(f"[*] Raspador lanzado (pid {raspador.pid}).")

    try:
        while True:
            inicio = time.time()
            if turno == "2":
                correr("proyeccion_2t.py")
                correr("publicar_2t.py")
            else:
                correr("extrapolador10B_rodri.py", "--una-pasada")
                correr("proyeccion_swing.py")
                correr("proyeccion_schteingart.py")
                correr("proyeccion_v4.py")
                correr("publicar_rodri.py")
            transcurrido = time.time() - inicio
            espera = max(0, PUBLISH_INTERVAL - transcurrido)
            print(f"[i] Publicación en {transcurrido:.1f}s. Esperando {espera:.1f}s...")
            time.sleep(espera)
    except KeyboardInterrupt:
        print("\n[!] Detenido por el usuario.")
    finally:
        raspador.terminate()
        try:
            raspador.wait(timeout=10)
        except Exception:
            raspador.kill()
        print("[i] Raspador detenido.")


if __name__ == "__main__":
    main()
