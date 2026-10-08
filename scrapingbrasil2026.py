# -*- coding: utf-8 -*-
"""
Raspador consolidado del escrutinio TSE 2026 (1er turno) - granularidad de ZONA.

Fusiona los arreglos de "scrapingbrasil2026d_rodri.py" (API vigente correcta)
con las funcionalidades de "scrapingbrasil2026zonpasG.py" (columnas de estado,
numero de pasada e inclusion del voto exterior).

Fuente oficial: https://resultados.tse.jus.br  (documentacion EA10..EA20 del TSE)

Rutas vigentes verificadas contra el propio front-end del TSE:

  config/mun-e<codigo6>-cm.json
      -> lista de UFs, municipios y zonas (incluye la abrangencia "zz").

  dados/<uf>/<uf>-e<codigo6>-ab.json
      -> avance/version por municipio (para saber que cambio).

  dados/<uf>/<uf><mun5>-c<cargo4>-e<codigo6>-u.json          (EA20 municipal)
  dados/<uf>/<uf><mun5>-z<zona4>-c<cargo4>-e<codigo6>-u.json (EA20 por zona)
      -> resultado unificado. OJO: NO existe el prefijo "-m" que usaba
         la version vieja (sp-m61018-... daba 404; lo correcto es sp61018-...).

  dados/<ambito>/<ambito>-c<cargo4>-e<codigo6>-u.json
      -> "br" (nacional), "zz" (exterior) o una UF.

Los candidatos se identifican por su NUMERO del TSE (campo "n"), estable, en
lugar de por el nombre (que en zonpasG producia fallos por acentos/variantes).

Exterior: la abrangencia "zz" (EXTERIOR) contiene 186 ciudades en 134 paises.
El total del exterior es dados/zz/zz-c0001-e006257-u.json y cada ciudad
dados/zz/zz<codigo>-z<zona>-c0001-e006257-u.json.

NOTA: la divulgacion oficial (EA20) arranca a las 17:00 de Brasilia. Antes de
esa hora los ficheros -u.json estan a cero. Los medios obtienen resultados
anticipados del exterior leyendo los Boletines de Urna (BU) publicos en
/oficial/ele2026/arquivo-urna/3220/... (3220 = codigo del pleito 2026),
no de la totalizacion oficial.
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
CICLO          = "ele2026"     # ciclo
CODIGO_ELEICAO = "6257"        # Elección Ordinaria Federal 2026 - 1er turno
CODIGO_6D      = "006257"
PLEITO         = "3220"        # código del pleito (para los Boletines de Urna)
CARGO          = "0001"        # Presidente (4 dígitos)
CARGO_NOMBRE   = "Presidente"

import rutas_datos as rd

ARCHIVO_CSV    = rd.ruta("escrutinio_zonas_2026.csv")
ARCHIVO_ESTADO = rd.ruta("control_versiones_2026.json")
ARCHIVO_SERIE  = rd.ruta("serie_temporal_2026.csv")    # snapshots nacionales/estatales
ARCHIVO_PADRON = rd.ruta("padron_2026.csv")            # electores habilitados 2026

# "zz" = exterior (134 países, 186 ciudades). Se incluye como un ámbito más.
ESTADOS = ["ac", "al", "am", "ap", "ba", "ce", "df", "es", "go", "ma", "mg", "ms", "mt",
           "pa", "pb", "pe", "pi", "pr", "rj", "rn", "ro", "rr", "rs", "sc", "se", "sp",
           "to", "zz"]

# Columna CSV -> número TSE del candidato (verificado en los -u.json vigentes).
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
    "hora_local", "hora_tse", "estado_uf", "codigo_municipio", "municipio",
    "zona_electoral", "secoes_totalizadas", "electores", "votos_totales",
] + list(CANDIDATOS.values()) + ["votos_blancos", "votos_nulos", "numero_pasada"])

# Snapshot agregado (nacional, estatal o exterior) para la evolución temporal.
CABECERA_SERIE = ([
    "hora_local", "hora_tse", "ambito", "secoes_total", "secoes_totalizadas",
    "pe_secoes_pct", "electores", "votos_totales",
] + list(CANDIDATOS.values()) + ["votos_blancos", "votos_nulos"])

CABECERA_PADRON = [
    "estado_uf", "codigo_municipio", "municipio", "zona_electoral",
    "electores_habilitados",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
}

# === GOBERNADOR DE TRÁFICO ANTI-BANEO (TSE tolera ~100 req/s) ===
LIMITE_REQ_POR_SEGUNDO = 20
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
            r = session.get(url, headers=HEADERS, timeout=15)
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


# === CONSTRUCTORES DE URL (patrón real del front-end oficial) ===
def url_config_municipios():
    return (f"{DOMINIO_BASE}/{AMBIENTE}/{CICLO}/{CODIGO_ELEICAO}"
            f"/config/mun-e{CODIGO_6D}-cm.json")


def url_abrangencia(uf):
    return (f"{DOMINIO_BASE}/{AMBIENTE}/{CICLO}/{CODIGO_ELEICAO}"
            f"/dados/{uf}/{uf}-e{CODIGO_6D}-ab.json")


def url_zona(uf, mun5, zona4):
    return (f"{DOMINIO_BASE}/{AMBIENTE}/{CICLO}/{CODIGO_ELEICAO}"
            f"/dados/{uf}/{uf}{mun5}-z{zona4}-c{CARGO}-e{CODIGO_6D}-u.json")


def url_municipio(uf, mun5):
    return (f"{DOMINIO_BASE}/{AMBIENTE}/{CICLO}/{CODIGO_ELEICAO}"
            f"/dados/{uf}/{uf}{mun5}-c{CARGO}-e{CODIGO_6D}-u.json")


def url_unificado(ambito):
    """Agregado unificado: 'br' (nacional), 'zz' (exterior) o una UF."""
    return (f"{DOMINIO_BASE}/{AMBIENTE}/{CICLO}/{CODIGO_ELEICAO}"
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


def escribir_filas(filas, archivo=ARCHIVO_CSV, cabecera=CABECERA):
    if not filas:
        return
    asegurar_csv(archivo, cabecera)
    with open(archivo, mode="a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(filas)


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
    """Devuelve {uf: [{'cd','nm','zonas':[...]}, ...]} (incluye 'zz')."""
    data = obtener_json(session, url_config_municipios())
    if not data:
        return {}
    mapa = {}
    for uf_entry in data.get("abr", []):
        uf = str(uf_entry.get("cd", "")).lower()
        if uf not in ESTADOS:
            continue
        mapa[uf] = [
            {"cd": str(mu.get("cd")), "nm": mu.get("nm"), "zonas": mu.get("z", [])}
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


def hora_de(data, respaldo=""):
    return f"{data.get('dg', '')} {data.get('hg', '')}".strip() or respaldo


def leer_zona(session, uf, municipio, zona):
    """Devuelve (datos, votos) de una zona, o None."""
    data = obtener_json(session, url_zona(uf, municipio["cd"], zona))
    if not data:
        return None
    return data, extraer_votos_candidatos(data)


def fila_zona(uf, municipio, zona, data, votos, hora_tse_ab, n_pasada):
    e = data.get("e", {})
    v = data.get("v", {})
    s = data.get("s", {})
    fila = [
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        hora_de(data, hora_tse_ab),
        uf.upper(),
        municipio["cd"],
        municipio["nm"],
        zona,
        entero(s.get("st")),
        entero(e.get("te")),
        entero(v.get("tv")),
    ]
    fila += [votos.get(num, 0) for num in CANDIDATOS]
    fila += [entero(v.get("vb")), entero(v.get("vn")), n_pasada]
    return fila


def registrar_snapshot(session, ambito, n_pasada=None):
    """Guarda un snapshot agregado (br, zz o uf) con el % de secciones cargadas."""
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
        hora_de(data),
        ambito,
        entero(s.get("ts")),
        entero(s.get("st")),
        pe,
        entero(e.get("te")),
        entero(v.get("tv")),
    ]
    fila += [votos.get(num, 0) for num in CANDIDATOS]
    fila += [entero(v.get("vb")), entero(v.get("vn"))]
    escribir_filas([fila], ARCHIVO_SERIE, CABECERA_SERIE)
    return 1


def realizar_barrido(session, municipios, estado, args, n_pasada):
    print(f"\n[+] Ciclo N° {n_pasada} iniciado: {datetime.now().strftime('%H:%M:%S')}")
    zonas_nuevas = 0
    estados = [args.uf] if args.uf else ESTADOS

    if not args.sin_serie:
        snaps = registrar_snapshot(session, "br")
        if "zz" in estados or not args.uf:
            snaps += registrar_snapshot(session, "zz")
        for uf in estados:
            snaps += registrar_snapshot(session, uf)
        print(f"[i] Snapshots de la serie temporal registrados: {snaps}")

    for uf in estados:
        if uf not in municipios:
            continue
        muns_uf = municipios.get(uf, [])
        if not muns_uf:
            continue
        print(f" -> {uf.upper()}: consultando avance...", end="\r")
        versiones = versiones_abrangencia(session, uf)
        if not versiones:
            continue

        filas = []
        procesados = 0
        intentados = 0
        for municipio in muns_uf:
            clave = f"{uf}/{municipio['cd']}"
            version = versiones.get(municipio["cd"])
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
                leido = leer_zona(session, uf, municipio, zona)
                if not leido:
                    continue
                data, votos = leido
                filas.append(fila_zona(uf, municipio, zona, data, votos, version, n_pasada))
                zonas_nuevas += 1
                exito = True
            if exito:
                estado[clave] = version
                procesados += 1

        escribir_filas(filas)
        print(f" -> {uf.upper()}: {procesados} municipios actualizados.        ")

    print(f"[OK] Ciclo N° {n_pasada} terminado. Zonas nuevas escritas: {zonas_nuevas}")
    return zonas_nuevas


def construir_padron(session, municipios, args):
    """Barre todas las zonas y (re)escribe el padrón 2026 de electores."""
    print("[*] Construyendo padrón de electores 2026 (puede tardar unos minutos)...")
    estados = [args.uf] if args.uf else ESTADOS
    total = 0
    with open(ARCHIVO_PADRON, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(CABECERA_PADRON)
        for uf in estados:
            muns_uf = municipios.get(uf, [])
            if not muns_uf:
                continue
            for municipio in muns_uf:
                for zona in (municipio["zonas"] or [""]):
                    data = obtener_json(session, url_zona(uf, municipio["cd"], zona))
                    if not data:
                        continue
                    writer.writerow([uf.upper(), municipio["cd"], municipio["nm"],
                                     zona, entero(data.get("e", {}).get("te"))])
                    total += 1
                    if total % 500 == 0:
                        print(f"    ... {total} zonas procesadas ({uf.upper()})", end="\r")
            f.flush()
            print(f" -> {uf.upper()}: padrón actualizado.                      ")
    print(f"[OK] Padrón 2026 escrito en {ARCHIVO_PADRON} ({total} zonas)")


def probar(session, uf):
    """Valida el parseo contra archivos reales (nacional, uf y una zona)."""
    print(f"[*] Probando conectividad y parseo (uf={uf.upper()})...")
    for etiqueta, url in (
        ("NACIONAL", url_unificado("br")),
        ("EXTERIOR", url_unificado("zz")),
        (f"UF {uf.upper()}", url_unificado(uf)),
    ):
        data = obtener_json(session, url)
        if not data:
            print(f"[x] Sin respuesta para {url}")
            continue
        e, v, s = data.get("e", {}), data.get("v", {}), data.get("s", {})
        print(f"[OK] {etiqueta}: dg={data.get('dg')} hg={data.get('hg')} "
              f"secciones={entero(s.get('st'))}/{entero(s.get('ts'))} "
              f"electores={entero(e.get('te'))} votos={entero(v.get('tv'))}")
    # una zona concreta, si el config está disponible
    municipios = cargar_municipios(session)
    muns_uf = municipios.get(uf, [])
    if muns_uf:
        municipio = muns_uf[0]
        zona = (municipio["zonas"] or [""])[0]
        data = obtener_json(session, url_zona(uf, municipio["cd"], zona))
        if data:
            votos = extraer_votos_candidatos(data)
            print(f"[OK] Zona {uf.upper()} {municipio['nm']} z={zona}: "
                  f"electores={entero(data.get('e', {}).get('te'))}")
            for num, nombre in CANDIDATOS.items():
                print(f"     {num:>3} {nombre:<20} {votos.get(num, 0)}")
        else:
            print(f"[x] Sin respuesta para la zona {uf} {municipio['cd']} {zona}")


def main():
    parser = argparse.ArgumentParser(description="Raspador TSE 2026 (por zona).")
    parser.add_argument("--uf", help="Procesar una sola UF (ej. sp, zz para exterior).")
    parser.add_argument("--una-pasada", action="store_true", help="Un solo ciclo y salir.")
    parser.add_argument("--max-mun", type=int, help="Limite de municipios por UF (pruebas).")
    parser.add_argument("--intervalo", type=int, default=45, help="Segundos entre ciclos.")
    parser.add_argument("--probar", action="store_true", help="Validar conectividad y parseo.")
    parser.add_argument("--padron", action="store_true",
                        help="Solo construir padron_2026.csv (electores 2026) y salir.")
    parser.add_argument("--sin-serie", action="store_true",
                        help="No registrar snapshots nacionales/estatales/exterior.")
    args = parser.parse_args()

    with requests.Session() as session:
        if args.probar:
            probar(session, args.uf or "sp")
            return

        print("[*] Raspador consolidado TSE 2026 - escrutinio por zona electoral.")
        print(f"[*] Ámbitos: 26 estados + DF + exterior (zz).")
        print(f"[*] Archivo de salida: {ARCHIVO_CSV}")
        print("[i] Recuerde: la divulgación oficial (EA20) comienza a las 17:00 de Brasilia.")
        municipios = cargar_municipios(session)
        if not municipios:
            print("[x] No se pudo cargar la lista de municipios. Verifique la conexión.")
            sys.exit(1)
        total_muns = sum(len(v) for v in municipios.values())
        print(f"[*] Municipios/ciudades cargados: {total_muns}")

        if args.padron:
            construir_padron(session, municipios, args)
            return

        asegurar_csv()
        asegurar_csv(ARCHIVO_SERIE, CABECERA_SERIE)
        print(f"[*] Serie temporal: {ARCHIVO_SERIE}")
        print(f"[i] Para el padrón 2026 de electores use: --padron (genera {ARCHIVO_PADRON}).")
        estado = cargar_estado()

        n_pasada = 1
        try:
            while True:
                realizar_barrido(session, municipios, estado, args, n_pasada)
                guardar_estado(estado)
                if args.una_pasada:
                    break
                print(f"Esperando {args.intervalo} segundos para el próximo barrido...")
                time.sleep(args.intervalo)
                n_pasada += 1
        except KeyboardInterrupt:
            guardar_estado(estado)
            print("\n[!] Interrumpido por el usuario. Estado guardado.")


if __name__ == "__main__":
    main()
