# -*- coding: utf-8 -*-
"""
publicar_rodri.py — Construye el paquete web y lo publica en un endpoint sin caché.

Lee los resultados del extrapolador y arma un JSON compacto con:
  * el último estado (escrutado, control, crudo, proyectado, zonas)
  * la serie temporal completa (para dibujar la evolución en el navegador)

Siempre escribe 'datos_web.json' en local (sirve de respaldo/desarrollo) y,
si existe la variable de entorno PUBLISH_URL, lo sube por HTTP.

Variables de entorno (nada de secretos en el código):
  PUBLISH_URL     p.ej. https://escrutinio-2026.tu-subdominio.workers.dev/datos
  PUBLISH_TOKEN   token secreto (se envía como 'Authorization: Bearer ...')
  PUBLISH_METHOD  PUT (por defecto) o POST

Con GitHub Pages solo sirviendo el HTML/JS estático, el navegador consulta
PUBLISH_URL cada 60 s y obtiene datos siempre frescos (Cache-Control: no-store).
"""

import os
import csv
import json
import sys
from datetime import datetime

import requests

ARCHIVO_HISTORICO = "historico_proyecciones_2026.csv"
ARCHIVO_JSON = "datos_proyeccion_2026.json"
ARCHIVO_JSON_SWING = "datos_proyeccion_swing_2026.json"
ARCHIVO_WEB = "datos_web.json"


def construir_serie():
    """Convierte el histórico CSV en una lista de puntos para Chart.js."""
    if not os.path.exists(ARCHIVO_HISTORICO):
        return []
    serie = {}
    with open(ARCHIVO_HISTORICO, newline="", encoding="utf-8") as f:
        for fila in csv.DictReader(f):
            t = fila["fecha_hora"]
            entrada = serie.setdefault(t, {
                "t": t,
                "escrutado": _num(fila.get("escrutado_pct")),
            })
            punto = {
                "lula": _num(fila.get("lula_pct")),
                "flavio": _num(fila.get("bolsonaro_pct")),
                "otros": _num(fila.get("otros_blancos_pct")),
                "lula_votos": int(_num(fila.get("lula_votos"))),
                "flavio_votos": int(_num(fila.get("bolsonaro_votos"))),
                "otros_votos": int(_num(fila.get("otros_blancos_votos"))),
            }
            if fila.get("tipo") == "crudo":
                entrada["crudo"] = punto
            else:
                entrada["proyectado"] = punto
    return list(serie.values())


def _num(valor):
    try:
        return float(str(valor).replace(",", "."))
    except (TypeError, ValueError):
        return 0.0


def _leer_json(archivo):
    if os.path.exists(archivo):
        try:
            with open(archivo, encoding="utf-8") as f:
                return json.load(f)
        except (ValueError, OSError):
            return {}
    return {}


def construir_payload():
    """Une la salida v1 (extrapolador) con la salida swing (proyeccion_swing)."""
    v1 = _leer_json(ARCHIVO_JSON)
    swing = _leer_json(ARCHIVO_JSON_SWING)

    nacional = swing.get("nacional")
    if not nacional:
        # Sin proyección swing: reutilizamos la v1 como única serie.
        nacional = {"escrutado": v1.get("escrutado_pct"),
                    "v1": v1.get("proyectado"), "swing": v1.get("proyectado")}

    payload = {
        "actualizado": v1.get("actualizado") or swing.get("actualizado"),
        "escrutado_pct": v1.get("escrutado_pct", swing.get("escrutado_pct")),
        "estado_control": v1.get("estado_control", ""),
        "swing_disponible": swing.get("swing_disponible", False),
        "metodo_principal": swing.get("metodo_principal", "v1"),
        "crudo": v1.get("crudo"),
        "zonas": v1.get("zonas"),
        "nacional": nacional,
        "estados": swing.get("estados", []),
        "serie": construir_serie(),
        "publicado": datetime.now().astimezone().isoformat(),
    }
    return payload


def publicar(payload):
    url = os.environ.get("PUBLISH_URL", "").strip()
    with open(ARCHIVO_WEB, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
    print(f"[i] Paquete web local escrito: {ARCHIVO_WEB} "
          f"({len(payload.get('serie', []))} puntos de serie)")

    if not url:
        print("[i] PUBLISH_URL no definido: no se sube a Internet (modo local).")
        return True

    headers = {"Content-Type": "application/json", "Cache-Control": "no-store"}
    token = os.environ.get("PUBLISH_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    metodo = os.environ.get("PUBLISH_METHOD", "PUT").upper()

    try:
        r = requests.request(
            metodo, url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers=headers, timeout=20,
        )
        if r.status_code in (200, 201, 204):
            print(f"[✓] Publicado en {url} ({r.status_code})")
            return True
        print(f"[!] El endpoint respondió {r.status_code}: {r.text[:200]}")
    except requests.RequestException as e:
        print(f"[!] Error al publicar: {e}")
    return False


def main():
    payload = construir_payload()
    if not payload.get("actualizado"):
        print("[-] Todavía no hay datos de proyección (ejecuta antes el extrapolador).")
    ok = publicar(payload)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
