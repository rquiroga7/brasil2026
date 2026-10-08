# -*- coding: utf-8 -*-
"""
Raspador del escrutinio TSE 2026 (1er turno) - granularidad de ZONA ELECTORAL.

Fuente oficial: https://resultados.tse.jus.br/oficial
Antes el script apuntaba a "tse.jus.br" (403) y usaba rutas obsoletas
("-i.json" / "-v.json"). La API vigente del sitio es:

  config/mun-e<codigo6>-cm.json                       -> lista de municipios y zonas
  dados/<uf>/<uf>-e<codigo6>-ab.json                  -> avance por municipio
  dados/<uf>/<uf>-m<mun5>-z<zona4>-c<cargo4>-e<codigo6>-u.json -> resultado unificado

Los candidatos se identifican por su NUMERO del TSE (campo "n"), que es estable
y no depende de como este escrito el nombre.
"""

import os
import csv
import sys
import json
import time
import argparse
import requests
from datetime import datetime

# === CONFIGURACIÓN OFICIAL TSE 2026 ===
DOMINIO_BASE   = "https://resultados.tse.jus.br"
AMBIENTE       = "oficial"
ANO_ELECCION   = "ele2026"     # ciclo
CODIGO_ELEICAO = "6257"        # Elección Ordinaria Federal 2026 - 1er turno
CODIGO_6D      = "006257"
CARGO          = "0001"        # Presidente
CARGO_NOMBRE   = "Presidente"

import rutas_datos as rd

ARCHIVO_CSV    = rd.ruta("escrutinio_zonas_2026.csv")
ARCHIVO_ESTADO = rd.ruta("control_versiones_2026.json")
ARCHIVO_SERIE  = rd.ruta("serie_temporal_2026.csv")   # snapshots nacionales/estatales

ESTADOS = ["ac", "al", "am", "ap", "ba", "ce", "df", "es", "go", "ma", "mg", "ms", "mt",
           "pa", "pb", "pe", "pi", "pr", "rj", "rn", "ro", "rr", "rs", "sc", "se", "sp", "to"]

# Columna CSV -> número TSE del candidato (verificado en ele-c / archivos -u.json)
CANDIDATOS = {
    "13": "Lula",
    "22": "Flavio_Bolsonaro",
    "70": "Augusto_Cury",
    "55": "Ronaldo_Caiado",
    "30": "Romeu_Zema",
    "14": "Renan_Santos",
    "16": "Hertz_Dias",
    "21": "Edmilson_Costa",
    "27": "Clariana_Barao",
    "29": "Rui_Costa_Pimenta",
    "35": "Wilson_Grassi",
    "80": "Samara_Martins",
}

CABECERA = ([
    "hora_local", "hora_tse", "uf", "codigo_municipio", "municipio", "zona",
    "secoes_totalizadas", "electores", "votos_totales",
] + list(CANDIDATOS.values()) + ["votos_blancos", "votos_nulos"])

# Snapshot agregado (nacional o por estado) para reconstruir la evolucion temporal
CABECERA_SERIE = ([
    "hora_local", "hora_tse", "ambito", "secoes_total", "secoes_totalizadas",
    "pe_secoes_pct", "electores", "votos_totales",
] + list(CANDIDATOS.values()) + ["votos_blancos", "votos_nulos"])

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
}

# === GOBERNADOR DE TRÁFICO ANTI-BANEO ===
LIMITE_REQ_POR_SEGUNDO = 20  # el TSE tolera ~100/s; nos mantenemos conservadores
_peticiones_segundo = 0
_segundo_actual = int(time.time())


def limitar_trafico():
    global _peticiones_segundo, _segundo_actual
    ahora = int(time.time())
    if ahora != _segundo_actual:
        _segundo_actual = ahora
        _peticiones_segundo = 0
    _peticiones_segundo += 1
    if _peticiones_segundo > LIMITE_REQ_POR_SEGUNDO:
        time.sleep(1.0 - (time.time() % 1))


def obtener_json(session, url, intentos=3):
    """GET con reintentos. Devuelve el JSON, o None si 404 o fallo definitivo."""
    for i in range(intentos):
        limitar_trafico()
        try:
            r = session.get(url, headers=HEADERS, timeout=10)
            if r.status_code == 200:
                try:
                    return r.json()
                except ValueError:
                    return None
            if r.status_code == 404:
                return None
            # 429 / 5xx -> espera progresiva
            time.sleep(0.5 * (i + 1))
        except requests.RequestException:
            time.sleep(0.5 * (i + 1))
    return None


# === CONSTRUCTORES DE URL ===
def url_config_municipios():
    return (f"{DOMINIO_BASE}/{AMBIENTE}/{ANO_ELECCION}/{CODIGO_ELEICAO}"
            f"/config/mun-e{CODIGO_6D}-cm.json")


def url_abrangencia(uf):
    return (f"{DOMINIO_BASE}/{AMBIENTE}/{ANO_ELECCION}/{CODIGO_ELEICAO}"
            f"/dados/{uf}/{uf}-e{CODIGO_6D}-ab.json")


def url_zona(uf, mun5, zona4):
    return (f"{DOMINIO_BASE}/{AMBIENTE}/{ANO_ELECCION}/{CODIGO_ELEICAO}"
            f"/dados/{uf}/{uf}-m{mun5}-z{zona4}-c{CARGO}-e{CODIGO_6D}-u.json")


def url_municipio(uf, mun5):
    return (f"{DOMINIO_BASE}/{AMBIENTE}/{ANO_ELECCION}/{CODIGO_ELEICAO}"
            f"/dados/{uf}/{uf}-m{mun5}-c{CARGO}-e{CODIGO_6D}-u.json")


def url_unificado(ambito):
    """Agregado unificado: 'br' (nacional) o una UF (estatal)."""
    return (f"{DOMINIO_BASE}/{AMBIENTE}/{ANO_ELECCION}/{CODIGO_ELEICAO}"
            f"/dados/{ambito}/{ambito}-c{CARGO}-e{CODIGO_6D}-u.json")


# === UTILIDADES ===
def entero(valor):
    try:
        return int(float(str(valor).replace(".", "").replace(",", ".")))
    except (TypeError, ValueError):
        return 0


def extraer_votos_candidatos(data):
    """Recorre el árbol de cargos/agremiaciones y recoge {numero: vap}."""
    votos = {}

    def recorrer(obj):
        if isinstance(obj, dict):
            if "vap" in obj and "n" in obj:
                votos[str(obj["n"])] = entero(obj.get("vap"))
            for valor in obj.values():
                recorrer(valor)
        elif isinstance(obj, list):
            for valor in obj:
                recorrer(valor)

    recorrer(data.get("carg", []))
    return votos


def asegurar_csv(archivo=ARCHIVO_CSV, cabecera=CABECERA):
    if not os.path.exists(archivo):
        with open(archivo, mode="w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(cabecera)


def escribir_fila(fila, archivo=ARCHIVO_CSV):
    with open(archivo, mode="a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow(fila)


def cargar_estado():
    if os.path.exists(ARCHIVO_ESTADO):
        try:
            with open(ARCHIVO_ESTADO, encoding="utf-8") as f:
                return json.load(f)
        except (ValueError, OSError):
            return {}
    return {}


def guardar_estado(estado):
    tmp = ARCHIVO_ESTADO + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(estado, f, ensure_ascii=False)
    os.replace(tmp, ARCHIVO_ESTADO)


# === LÓGICA DE RASPA ===
def cargar_municipios(session):
    """Devuelve {uf: [{'cd','nm','zonas':[...]}, ...]}."""
    data = obtener_json(session, url_config_municipios())
    if not data:
        return {}
    mapa = {}
    for uf_entry in data.get("abr", []):
        uf = str(uf_entry.get("cd", "")).lower()
        if uf not in ESTADOS:
            continue
        mapa[uf] = [
            {"cd": mu.get("cd"), "nm": mu.get("nm"), "zonas": mu.get("z", [])}
            for mu in uf_entry.get("mu", [])
        ]
    return mapa


def versiones_abrangencia(session, uf):
    """{codigo_municipio5: version} usando el avance por municipio."""
    data = obtener_json(session, url_abrangencia(uf))
    if not data:
        return {}
    dg = data.get("dg", "")
    hg = data.get("hg", "")
    versiones = {}
    for ab in data.get("abr", []):
        cd = str(ab.get("cdabr", ""))
        est = str(ab.get("e", {}).get("est", ""))
        dt = ab.get("dt", "") or dg
        ht = ab.get("ht", "") or hg
        versiones[cd] = f"{dt}|{ht}|{est}"
    return versiones


def procesar_zona(session, uf, municipio, zona, hora_tse_ab):
    data = obtener_json(session, url_zona(uf, municipio["cd"], zona))
    if not data:
        return False

    votos = extraer_votos_candidatos(data)
    e = data.get("e", {})
    v = data.get("v", {})

    fila = [
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        f"{data.get('dg', '')} {data.get('hg', '')}".strip() or hora_tse_ab,
        uf,
        municipio["cd"],
        municipio["nm"],
        zona,
        entero(e.get("est")),
        entero(e.get("te")),
        entero(v.get("tv")),
    ]
    fila += [votos.get(num, 0) for num in CANDIDATOS]
    fila += [entero(v.get("vb")), entero(v.get("vn"))]

    escribir_fila(fila)
    return True


def registrar_snapshot(session, ambito):
    """Guarda un snapshot agregado (br o uf) con el % de secciones cargadas."""
    data = obtener_json(session, url_unificado(ambito))
    if not data:
        return 0
    s = data.get("s", {})
    e = data.get("e", {})
    v = data.get("v", {})
    votos = extraer_votos_candidatos(data)

    pe = str(s.get("pst", "")).strip()
    if pe:
        pe = pe.replace(".", "").replace(",", ".")
    else:
        total = entero(s.get("ts"))
        pe = f"{100.0 * entero(s.get('st')) / total:.2f}" if total else ""

    fila = [
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        f"{data.get('dg', '')} {data.get('hg', '')}".strip(),
        ambito,
        entero(s.get("ts")),
        entero(s.get("st")),
        pe,
        entero(e.get("te")),
        entero(v.get("tv")),
    ]
    fila += [votos.get(num, 0) for num in CANDIDATOS]
    fila += [entero(v.get("vb")), entero(v.get("vn"))]
    escribir_fila(fila, ARCHIVO_SERIE)
    return 1


def realizar_barrido(session, municipios, estado, args):
    print(f"\n[+] Ciclo iniciado: {datetime.now().strftime('%H:%M:%S')}")
    zonas_nuevas = 0
    estados = [args.uf] if args.uf else ESTADOS

    if not args.sin_serie:
        snaps = registrar_snapshot(session, "br")
        for uf in estados:
            snaps += registrar_snapshot(session, uf)
        print(f"[i] Snapshots de la serie temporal registrados: {snaps}")

    for uf in estados:
        muns_uf = municipios.get(uf, [])
        if not muns_uf:
            continue
        print(f" -> {uf.upper()}: consultando avance...", end="\r")
        versiones = versiones_abrangencia(session, uf)
        if not versiones:
            continue

        procesados = 0
        intentados = 0
        for municipio in muns_uf:
            clave = f"{uf}/{municipio['cd']}"
            version = versiones.get(str(municipio["cd"]))
            if version is None:
                continue
            if estado.get(clave) == version:
                continue
            if args.max_mun and intentados >= args.max_mun:
                break
            intentados += 1

            zonas = municipio["zonas"] or [""]
            exito = False
            for zona in zonas:
                if procesar_zona(session, uf, municipio, zona, version):
                    zonas_nuevas += 1
                    exito = True
            if exito:
                estado[clave] = version
                procesados += 1

        print(f" -> {uf.upper()}: {procesados} municipios actualizados.        ")

    print(f"[OK] Ciclo terminado. Zonas nuevas escritas: {zonas_nuevas}")
    return zonas_nuevas


def probar(session, uf):
    """Valida el parseo contra el archivo -u.json a nivel estado (no por zona)."""
    url = (f"{DOMINIO_BASE}/{AMBIENTE}/{ANO_ELECCION}/{CODIGO_ELEICAO}"
           f"/dados/{uf}/{uf}-c{CARGO}-e{CODIGO_6D}-u.json")
    data = obtener_json(session, url)
    if not data:
        print(f"[x] Sin respuesta para {url}")
        return
    e, v = data.get("e", {}), data.get("v", {})
    print(f"[OK] {uf.upper()} dg={data.get('dg')} hg={data.get('hg')}")
    print(f"     electores={entero(e.get('te'))} votos_totales={entero(v.get('tv'))} "
          f"blancos={entero(v.get('vb'))} nulos={entero(v.get('vn'))}")
    votos = extraer_votos_candidatos(data)
    for num, nombre in CANDIDATOS.items():
        print(f"     {num:>3} {nombre:<20} {votos.get(num, 0)}")


def main():
    parser = argparse.ArgumentParser(description="Raspador TSE 2026 (por zona).")
    parser.add_argument("--uf", help="Procesar una sola UF (ej. sp).")
    parser.add_argument("--una-pasada", action="store_true", help="Un solo ciclo y salir.")
    parser.add_argument("--max-mun", type=int, help="Limite de municipios por UF (pruebas).")
    parser.add_argument("--intervalo", type=int, default=45, help="Segundos entre ciclos.")
    parser.add_argument("--probar", action="store_true", help="Validar parseo y salir.")
    parser.add_argument("--sin-serie", action="store_true",
                        help="No registrar snapshots nacionales/estatales.")
    args = parser.parse_args()

    with requests.Session() as session:
        if args.probar:
            probar(session, args.uf or "sp")
            return

        print("[*] Raspador TSE 2026 - escrutinio por zona electoral.")
        print(f"[*] Archivo de salida: {ARCHIVO_CSV}")
        municipios = cargar_municipios(session)
        if not municipios:
            print("[x] No se pudo cargar la lista de municipios. Verifique la conexión.")
            sys.exit(1)
        total_muns = sum(len(v) for v in municipios.values())
        print(f"[*] Municipios cargados: {total_muns}")

        asegurar_csv()
        asegurar_csv(ARCHIVO_SERIE, CABECERA_SERIE)
        print(f"[*] Serie temporal: {ARCHIVO_SERIE}")
        estado = cargar_estado()

        try:
            while True:
                realizar_barrido(session, municipios, estado, args)
                guardar_estado(estado)
                if args.una_pasada:
                    break
                print(f"Esperando {args.intervalo} segundos para el próximo barrido...")
                time.sleep(args.intervalo)
        except KeyboardInterrupt:
            guardar_estado(estado)
            print("\n[!] Interrumpido por el usuario. Estado guardado.")


if __name__ == "__main__":
    main()
