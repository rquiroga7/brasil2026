# -*- coding: utf-8 -*-
"""
runner_local.py — Orquestador local (scrape -> proyección -> publicación).

Pensado para correr en tu máquina el día de la elección: acota cada pasada del
raspador para que quepa en el intervalo y publica ~cada minuto en el endpoint
sin caché.

Variables de entorno:
  SCRAPE_SECONDS     segundos máximos por pasada de raspado (por defecto 45)
  PUBLISH_INTERVAL   segundos entre publicaciones (por defecto 60)
  PUBLISH_MODE       "git" para commit+push de datos_web.json cada ciclo
                     (o PUBLISH_URL/PUBLISH_TOKEN para un endpoint HTTP)

Uso:
  python runner_local.py
  (Ctrl+C para detener)
"""

import os
import sys
import time
import subprocess

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

PY = sys.executable
SCRAPE_SECONDS = int(os.environ.get("SCRAPE_SECONDS", "45"))
PUBLISH_INTERVAL = int(os.environ.get("PUBLISH_INTERVAL", "60"))


def correr(*args):
    print(f"\n$ {' '.join(args)}", flush=True)
    return subprocess.run([PY, *args]).returncode


def main():
    print(f"[*] Runner local | raspado <= {SCRAPE_SECONDS}s | "
          f"publicación cada {PUBLISH_INTERVAL}s")
    print("[i] Para publicar en GitHub: define PUBLISH_MODE=git (y configura el remoto).")
    print("[i] Alternativa HTTP: define PUBLISH_URL (y PUBLISH_TOKEN).")
    try:
        while True:
            inicio = time.time()
            correr("zonpasG_rodri.py", "--una-pasada",
                   "--max-segundos", str(SCRAPE_SECONDS))
            correr("extrapolador10B_rodri.py", "--una-pasada")
            correr("proyeccion_swing.py")
            correr("publicar_rodri.py")
            transcurrido = time.time() - inicio
            espera = max(0, PUBLISH_INTERVAL - transcurrido)
            print(f"[i] Ciclo en {transcurrido:.1f}s. Esperando {espera:.1f}s...")
            time.sleep(espera)
    except KeyboardInterrupt:
        print("\n[!] Detenido por el usuario.")


if __name__ == "__main__":
    main()
