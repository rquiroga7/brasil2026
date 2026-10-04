# -*- coding: utf-8 -*-
"""
runner_local.py — Orquestador local (scraper continuo + proyección/publicación).

Problema que resuelve: si se lanza el raspador una pasada por ciclo con un tope
de tiempo, siempre reinicia por el primer estado (AC) y nunca llega a los
grandes (SP, MG, ...). Aquí el raspador corre CONTINUO en segundo plano (pasadas
completas) y, en paralelo, este proceso publica proyecciones cada minuto.

Variables de entorno:
  SCRAPER_INTERVAL   segundos entre pasadas completas del raspador (def. 20)
  PUBLISH_INTERVAL   segundos entre publicaciones (def. 60)
  PUBLISH_MODE       "git" para commit+push de datos_web.json (rama `data`)
                     (o PUBLISH_URL/PUBLISH_TOKEN para un endpoint HTTP)

Uso:
  python runner_local.py
  (Ctrl+C detiene el raspador y sale)
"""

import os
import sys
import time
import subprocess

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

PY = sys.executable
SCRAPER_INTERVAL = int(os.environ.get("SCRAPER_INTERVAL", "20"))
PUBLISH_INTERVAL = int(os.environ.get("PUBLISH_INTERVAL", "60"))


def correr(*args):
    print(f"\n$ {' '.join(args)}", flush=True)
    return subprocess.run([PY, *args]).returncode


def main():
    print(f"[*] Runner local | raspador continuo (pausa {SCRAPER_INTERVAL}s) | "
          f"publicación cada {PUBLISH_INTERVAL}s")
    print("[i] Para publicar en GitHub: define PUBLISH_MODE=git (y configura el remoto).")
    print("[i] Alternativa HTTP: define PUBLISH_URL (y PUBLISH_TOKEN).")

    # El raspador corre como proceso aparte, en pasadas completas.
    raspador = subprocess.Popen([PY, "zonpasG_rodri.py", "--intervalo", str(SCRAPER_INTERVAL)])
    print(f"[*] Raspador lanzado (pid {raspador.pid}).")
    try:
        while True:
            inicio = time.time()
            correr("extrapolador10B_rodri.py", "--una-pasada")
            correr("proyeccion_swing.py")
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
