# -*- coding: utf-8 -*-
"""
zonpasG_rodri.py — Raspador consolidado del escrutinio TSE 2026 (por ZONA).

Rutas vigentes (EA20), verificadas contra el front-end oficial:
  config/mun-e<cod6>-cm.json
  dados/<uf>/<uf>-e<cod6>-ab.json
  dados/<uf>/<uf><mun5>-z<zona4>-c<cargo4>-e<cod6>-u.json   (zona)
  dados/<ambito>/<ambito>-c<cargo4>-e<cod6>-u.json          (br | zz | uf)

Concurrencia: las zonas se descargan con un pool de hilos (sesiones por hilo)
bajo un limitador de tráfico global, para cubrir todos los estados en poco
tiempo sin exceder el límite del TSE (~100 req/s).
"""

import os
import csv
import sys
import json
import time
import argparse
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from datetime import datetime

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# === CONFIGURACIÓN OFICIAL TSE 2026 ===
DOMINIO_BASE   = "https://resultados.tse.jus.br"
AMBIENTE       = "oficial"
CICLO          = "ele2026"
CODIGO_ELEICAO = "6257"
CODIGO_6D      = "006257"
PLEITO         = "3220"
CARGO          = "0001"

ARCHIVO_CSV    = "escrutinio_zonas_2026.csv"
ARCHIVO_ESTADO = "control_versiones_2026.json"
ARCHIVO_SERIE  = "serie_temporal_2026.csv"
ARCHIVO_PADRON = "padron_2026.csv"

ESTADOS = ["ac", "al", "am", "ap", "ba", "ce", "df", "es", "go", "ma", "mg", "ms", "mt",
           "pa", "pb", "pe", "pi", "pr", "rj", "rn", "ro", "rr", "rs", "sc", "se", "sp",
           "to", "zz"]

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

# === GOBERNADOR DE TRÁFICO GLOBAL (thread-safe) ===
LIMITE_REQ_POR_SEGUNDO = 60


class _Limitador:
    """Token bucket compartido entre hilos."""

    def __init__(self, por_segundo):
        self.por_segundo = float(por_segundo)
        self.lock = threading.Lock()
        self.tokens = float(por_segundo)
        self.ultimo = time.time()

    def adquirir(self):
        while True:
            with self.lock:
                ahora = time.time()
                self.tokens = min(self.por_segundo,
                                  self.tokens + (ahora - self.ultimo) * self.por_segundo)
                self.ultimo = ahora
                if self.tokens >= 1.0:
                    self.tokens -= 1.0
                    return
                espera = (1.0 - self.tokens) / self.por_segundo
            time.sleep(espera)


LIMITADOR = _Limitador(LIMITE_REQ_POR_SEGUNDO)

_hilo_local = threading.local()


def get_session():
    """Una requests.Session por hilo (Session no es thread-safe)."""
    s = getattr(_hilo_local, "session", None)
    if s is None:
        s = requests.Session()
        _hilo_local.session = s
    return s


def obtener_json(url, intentos=3):
    for i in range(intentos):
        LIMITADOR.adquirir()
        try:
            r = get_session().get(url, headers=HEADERS, timeout=15)
            if r.status_code == 200:
                try:
                    return r.json()
                except ValueError:
                    return None
            if r.status_code == 404:
                return None
            time.sleep(0.5 * (i + 1))
        except requests.RequestException:
            time.sleep(0.5 * (i + 1))
    return None


# === CONSTRUCTORES DE URL ===
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
    return (f"{DOMINIO_BASE}/{AMBIENTE}/{CICLO}/{CODIGO_ELEICAO}"
            f"/dados/{ambito}/{ambito}-c{CARGO}-e{CODIGO_6D}-u.json")


# === UTILIDADES ===
def entero(valor):
    try:
        return int(float(str(valor).replace(".", "").replace(",", ".")))
    except (TypeError, ValueError):
        return 0


def extraer_votos_candidatos(data):
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
def cargar_municipios():
    data = obtener_json(url_config_municipios())
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


def versiones_abrangencia(uf):
    data = obtener_json(url_abrangencia(uf))
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


def leer_zona(uf, municipio, zona):
    data = obtener_json(url_zona(uf, municipio["cd"], zona))
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


def procesar_municipio(uf, municipio, version, n_pasada):
    """Descarga todas las zonas de un municipio. Se ejecuta en un hilo."""
    filas = []
    for zona in (municipio["zonas"] or [""]):
        leido = leer_zona(uf, municipio, zona)
        if not leido:
            continue
        data, votos = leido
        filas.append(fila_zona(uf, municipio, zona, data, votos, version, n_pasada))
    return filas


def registrar_snapshot(ambito):
    data = obtener_json(url_unificado(ambito))
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


def realizar_barrido(municipios, estado, args, n_pasada, deadline=None):
    print(f"\n[+] Ciclo N° {n_pasada} iniciado: {datetime.now().strftime('%H:%M:%S')}")
    zonas_nuevas = 0
    estados = [args.uf] if args.uf else ESTADOS

    if not args.sin_serie:
        snaps = registrar_snapshot("br")
        if "zz" in estados or not args.uf:
            snaps += registrar_snapshot("zz")
        for uf in estados:
            snaps += registrar_snapshot(uf)
        print(f"[i] Snapshots de la serie temporal registrados: {snaps}")

    for uf in estados:
        if deadline and time.time() > deadline:
            print("[i] Tiempo máximo alcanzado; se corta el barrido.")
            break
        muns_uf = municipios.get(uf, [])
        if not muns_uf:
            continue
        print(f" -> {uf.upper()}: consultando avance...", end="\r")
        versiones = versiones_abrangencia(uf)
        if not versiones:
            continue

        tareas = []
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
            tareas.append((municipio, version))

        filas = []
        procesados = 0
        if tareas:
            with ThreadPoolExecutor(max_workers=args.workers) as ex:
                futuros = {
                    ex.submit(procesar_municipio, uf, mun, ver, n_pasada): (mun, ver)
                    for mun, ver in tareas
                }
                for fut in as_completed(futuros):
                    mun, ver = futuros[fut]
                    try:
                        resultado = fut.result()
                    except Exception:
                        resultado = []
                    if resultado:
                        filas.extend(resultado)
                        estado[f"{uf}/{mun['cd']}"] = ver
                        procesados += 1
        escribir_filas(filas)
        zonas_nuevas += len(filas)
        guardar_estado(estado)
        print(f" -> {uf.upper()}: {procesados} municipios actualizados.        ")

    print(f"[OK] Ciclo N° {n_pasada} terminado. Zonas nuevas escritas: {zonas_nuevas}")
    return zonas_nuevas


def construir_padron(municipios, args):
    print("[*] Construyendo padrón de electores 2026 (puede tardar unos minutos)...")
    estados = [args.uf] if args.uf else ESTADOS
    total = 0

    def tarea(mun):
        out = []
        for zona in (mun["zonas"] or [""]):
            data = obtener_json(url_zona(uf_actual, mun["cd"], zona))
            if data:
                out.append([uf_actual.upper(), mun["cd"], mun["nm"], zona,
                            entero(data.get("e", {}).get("te"))])
        return out

    with open(ARCHIVO_PADRON, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(CABECERA_PADRON)
        for uf_actual in estados:
            muns = municipios.get(uf_actual, [])
            with ThreadPoolExecutor(max_workers=args.workers) as ex:
                for res in ex.map(tarea, muns):
                    if res:
                        writer.writerows(res)
                        total += len(res)
            f.flush()
            print(f" -> {uf_actual.upper()}: padrón actualizado.                      ")
    print(f"[OK] Padrón 2026 escrito en {ARCHIVO_PADRON} ({total} zonas)")


def probar(uf):
    print(f"[*] Probando conectividad y parseo (uf={uf.upper()})...")
    for etiqueta, url in (
        ("NACIONAL", url_unificado("br")),
        ("EXTERIOR", url_unificado("zz")),
        (f"UF {uf.upper()}", url_unificado(uf)),
    ):
        data = obtener_json(url)
        if not data:
            print(f"[x] Sin respuesta para {url}")
            continue
        e, v, s = data.get("e", {}), data.get("v", {}), data.get("s", {})
        print(f"[OK] {etiqueta}: dg={data.get('dg')} hg={data.get('hg')} "
              f"secciones={entero(s.get('st'))}/{entero(s.get('ts'))} "
              f"electores={entero(e.get('te'))} votos={entero(v.get('tv'))}")
    municipios = cargar_municipios()
    muns_uf = municipios.get(uf, [])
    if muns_uf:
        municipio = muns_uf[0]
        zona = (municipio["zonas"] or [""])[0]
        data = obtener_json(url_zona(uf, municipio["cd"], zona))
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
    parser.add_argument("--max-segundos", type=int, help="Corta el barrido tras N segundos.")
    parser.add_argument("--workers", type=int, default=12, help="Hilos concurrentes.")
    parser.add_argument("--intervalo", type=int, default=20, help="Segundos entre ciclos.")
    parser.add_argument("--probar", action="store_true", help="Validar conectividad y parseo.")
    parser.add_argument("--padron", action="store_true",
                        help="Solo construir padron_2026.csv (electores 2026) y salir.")
    parser.add_argument("--sin-serie", action="store_true",
                        help="No registrar snapshots nacionales/estatales/exterior.")
    args = parser.parse_args()

    if args.probar:
        probar(args.uf or "sp")
        return

    print("[*] zonpasG_rodri — Raspador consolidado TSE 2026 por zona electoral.")
    print(f"[*] Ámbitos: 26 estados + DF + exterior (zz) | hilos: {args.workers}.")
    print(f"[*] Archivo de salida: {ARCHIVO_CSV}")
    municipios = cargar_municipios()
    if not municipios:
        print("[x] No se pudo cargar la lista de municipios. Verifique la conexión.")
        sys.exit(1)
    total_muns = sum(len(v) for v in municipios.values())
    print(f"[*] Municipios/ciudades cargados: {total_muns}")

    if args.padron:
        construir_padron(municipios, args)
        return

    asegurar_csv()
    asegurar_csv(ARCHIVO_SERIE, CABECERA_SERIE)
    estado = cargar_estado()

    n_pasada = 1
    try:
        while True:
            deadline = (time.time() + args.max_segundos) if args.max_segundos else None
            realizar_barrido(municipios, estado, args, n_pasada, deadline)
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
