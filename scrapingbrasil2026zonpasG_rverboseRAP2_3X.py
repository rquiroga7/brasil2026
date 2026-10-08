# -*- coding: utf-8 -*-
"""
scrapingbrasil2026zonpasG_rverboseRAP2.py — Raspador TSE 2026 por zona (RAP2).

Versión rápida del raspador verboso. Conserva su identidad (impresión detallada
por zona y ESCRITURA INMEDIATA en CSV, para no perder datos durante el vivo),
pero incorpora las optimizaciones de velocidad:

  * Token bucket global thread-safe y configurable (--limite, def. 120 req/s).
  * Muchos más hilos (--workers, def. 128) y una requests.Session por hilo
    (una Session compartida entre hilos no es segura).
  * El avance por municipio (abrangencia) de cada UF se pide EN PARALELO
    (antes era secuencial: 27 peticiones encadenadas por pasada).
  * Una tarea por ZONA (no por municipio), para repartir el paralelismo entre
    municipios grandes y chicos.
  * Tareas INTERCALADAS por estado (round-robin): ningún estado queda al final,
    así la hora de observación no hereda el orden alfabético.
  * Se SALTAN los municipios con progreso 0: al inicio del escrutinio casi
    ninguna zona existe y pedirlas genera miles de 404 inútiles.
  * Salida en D: (rutas_datos) y log de tiempos por pasada.

La escritura inmediata (abrir/cerrar el CSV por fila) es la principal limitante
restante; se mantiene a propósito para resistencia en vivo.
"""

import os
import csv
import sys
import time
import argparse
import threading
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

import rutas_datos as rd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# === CONFIGURACIÓN OFICIAL TSE 2026 ===
DOMINIO_BASE = "https://resultados.tse.jus.br"
ANO_ELECCION = "ele2026"
CODIGO_ELEICAO = "6257"
CODIGO_ELEICAO_6D = "006257"
CARGO = "0001"

ARCHIVO_CSV = rd.ruta("escrutinio_zonas_2026.csv")

MAX_WORKERS = 128

ESTADOS = ["ac", "al", "am", "ap", "ba", "ce", "df", "es", "go", "ma", "mg", "ms", "mt",
           "pa", "pb", "pe", "pi", "pr", "rj", "rn", "ro", "rr", "rs", "sc", "se", "sp",
           "to", "zz"]

CANDIDATOS = {
    "lula": "Lula", "flavio bolsonaro": "Flavio_Bolsonaro", "augusto cury": "Augusto_Cury",
    "caiado": "Ronaldo_Caiado", "zema": "Romeu_Zema", "renan santos": "Renan_Santos",
    "hertz dias": "Hertz_Dias", "edmilson costa": "Edmilson_Costa", "clariana": "Clariana_Barao",
    "avalanche": "Avalanche_Marçal", "marçal": "Avalanche_Marçal",
    "pimenta": "Rui_Costa_Pimenta", "grassi": "Wilson_Grassi", "samara": "Samara_Martins"
}

CABECERA = [
    "hora_local", "hora_tse", "codigo_municipio", "zona_electoral", "electores_totales",
    "votos_totales", "Lula", "Flavio_Bolsonaro", "Augusto_Cury", "Ronaldo_Caiado",
    "Romeu_Zema", "Renan_Santos", "Hertz_Dias", "Edmilson_Costa", "Clariana_Barao",
    "Avalanche_Marçal", "Rui_Costa_Pimenta", "Wilson_Grassi", "Samara_Martins",
    "votos_blancos", "votos_nulos", "estado_uf", "numero_pasada",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
}

LIMITE_REQ_POR_SEGUNDO = 80
VERBOSE = True


# === GOBERNADOR DE TRÁFICO GLOBAL (thread-safe y adaptativo) ===
# El TSE tolera ~100 req/s. Por defecto 80 (--limite) para no arriesgar
# throttling; ante 429/5xx/timeouts bajamos el ritmo y lo recuperamos de a poco.
LIMITE_MINIMO = 10


class _Limitador:
    """Token bucket compartido entre hilos, con penalización adaptativa."""

    def __init__(self, por_segundo, minimo=LIMITE_MINIMO):
        self.maximo = float(por_segundo)
        self.minimo = float(minimo)
        self.por_segundo = float(por_segundo)
        self.factor = 1.0
        self.recuperar_en = 0.0
        self.lock = threading.Lock()
        self.tokens = float(por_segundo)
        self.ultimo = time.time()

    def _recalcular(self):
        self.por_segundo = max(self.minimo, self.maximo * self.factor)

    def adquirir(self):
        while True:
            with self.lock:
                ahora = time.time()
                if self.factor < 1.0 and ahora >= self.recuperar_en:
                    self.factor = min(1.0, self.factor + 0.1)
                    self._recalcular()
                    self.recuperar_en = ahora + 5.0
                self.tokens = min(self.por_segundo,
                                  self.tokens + (ahora - self.ultimo) * self.por_segundo)
                self.ultimo = ahora
                if self.tokens >= 1.0:
                    self.tokens -= 1.0
                    return
                espera = (1.0 - self.tokens) / self.por_segundo
            time.sleep(min(espera, 0.5))

    def penalizar(self, factor=0.5, cooldown=10.0):
        with self.lock:
            self.factor = max(self.minimo / self.maximo, self.factor * factor)
            self._recalcular()
            self.tokens = min(self.tokens, self.por_segundo)
            self.recuperar_en = time.time() + cooldown


LIMITADOR = _Limitador(LIMITE_REQ_POR_SEGUNDO)


def configurar_limite(por_segundo):
    """Fija el techo de peticiones/segundo (se llama tras parsear argumentos)."""
    with LIMITADOR.lock:
        LIMITADOR.maximo = float(por_segundo)
        LIMITADOR.factor = 1.0
        LIMITADOR.por_segundo = float(por_segundo)
        LIMITADOR.tokens = float(por_segundo)
        LIMITADOR.ultimo = time.time()
        LIMITADOR.recuperar_en = 0.0


_hilo_local = threading.local()

# Candado para evitar colisiones al escribir concurrentemente en el CSV.
csv_lock = threading.Lock()

# Diagnóstico de respuestas HTTP (para detectar throttling del TSE).
_contadores = {}
_contadores_lock = threading.Lock()


def _contar(clave):
    with _contadores_lock:
        _contadores[clave] = _contadores.get(clave, 0) + 1


def get_session():
    """Una requests.Session por hilo (Session no es thread-safe)."""
    s = getattr(_hilo_local, "session", None)
    if s is None:
        s = requests.Session()
        adapter = requests.adapters.HTTPAdapter(pool_connections=8, pool_maxsize=8)
        s.mount("https://", adapter)
        s.mount("http://", adapter)
        _hilo_local.session = s
    return s


def registrar_peticion_y_controlar_trafico():
    """Se mantiene el nombre por compatibilidad; ahora usa el token bucket."""
    LIMITADOR.adquirir()


def obtener_json(url, intentos=3):
    """GET con reintentos y retroceso adaptativo ante throttling del TSE."""
    for i in range(intentos):
        LIMITADOR.adquirir()
        try:
            r = get_session().get(url, headers=HEADERS, timeout=15)
            if r.status_code == 200:
                try:
                    return r.json()
                except ValueError:
                    _contar("200_no_json")
                    return None
            if r.status_code == 404:
                _contar("404")
                return None
            _contar(f"http_{r.status_code}")
            if r.status_code == 429:
                retry = r.headers.get("Retry-After")
                try:
                    espera = max(1.0, float(retry))
                except (TypeError, ValueError):
                    espera = 2.0 * (i + 1)
                LIMITADOR.penalizar(factor=0.5, cooldown=espera + 5.0)
                time.sleep(espera)
            else:
                LIMITADOR.penalizar(factor=0.7, cooldown=5.0)
                time.sleep(0.5 * (i + 1))
        except requests.RequestException:
            _contar("timeout_o_conexion")
            LIMITADOR.penalizar(factor=0.7, cooldown=5.0)
            time.sleep(0.5 * (i + 1))
    return None


def escribir_fila_csv(fila):
    """Escritura inmediata de una fila (cierra el archivo en cada zona)."""
    with csv_lock:
        with open(ARCHIVO_CSV, mode="a", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(fila)


def asegurar_csv():
    if not os.path.exists(ARCHIVO_CSV):
        os.makedirs(os.path.dirname(ARCHIVO_CSV), exist_ok=True)
        with open(ARCHIVO_CSV, mode="w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(CABECERA)


# === DESCUBRIMIENTO ===
def cargar_municipios():
    url = f"{DOMINIO_BASE}/oficial/{ANO_ELECCION}/{CODIGO_ELEICAO}" \
          f"/config/mun-e{CODIGO_ELEICAO_6D}-cm.json"
    if VERBOSE:
        print(f"[Descargando Config General] {url}")
    data = obtener_json(url)
    if not data:
        return {}
    mapa = {}
    for uf_entry in data.get("abr", []):
        uf = str(uf_entry.get("cd", "")).lower()
        if uf not in ESTADOS:
            continue
        mapa[uf] = [
            {"cd": str(mu.get("cd")), "nm": mu.get("nm"),
             "zonas": [str(z) for z in (mu.get("z") or [])]}
            for mu in uf_entry.get("mu", [])
        ]
    return mapa


def versiones_estado(uf):
    url = f"{DOMINIO_BASE}/oficial/{ANO_ELECCION}/{CODIGO_ELEICAO}" \
          f"/dados/{uf}/{uf}-e{CODIGO_ELEICAO_6D}-ab.json"
    if VERBOSE:
        print(f"[Descargando Índice UF: {uf.upper()}] {url}")
    data = obtener_json(url)
    if not data:
        return {}
    dg, hg = data.get("dg", ""), data.get("hg", "")
    versiones = {}
    for ab in data.get("abr", []):
        cd = str(ab.get("cdabr", ""))
        est = str(ab.get("e", {}).get("est", ""))
        versiones[cd] = f"{ab.get('dt') or dg}|{ab.get('ht') or hg}|{est}"
    return versiones


def progreso_de_version(version):
    """Cuántas secciones/electores lleva contados un municipio ("dt|ht|est")."""
    try:
        est = version.rsplit("|", 1)[1]
        return int(float(str(est).replace(".", "").replace(",", ".")))
    except (ValueError, IndexError):
        return 0


def descargar_zona_individual(uf, cod_mun, nombre, zona, hora_tse, n_pasada):
    """Descarga UNA zona y devuelve (clave_municipio, fila) o None."""
    url_zona = (f"{DOMINIO_BASE}/oficial/{ANO_ELECCION}/{CODIGO_ELEICAO}"
                f"/dados/{uf}/{uf}{cod_mun}-z{zona}-c{CARGO}-e{CODIGO_ELEICAO_6D}-u.json")
    if VERBOSE:
        print(f"  └─► [Zona] {uf.upper()} | Mun {cod_mun} ({nombre}) | Zona {zona} | {url_zona}")

    data = obtener_json(url_zona)
    if not data:
        return None

    hora_local = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    e = data.get("e", {})
    v = data.get("v", {})

    num_zona = str(zona).lstrip("0") or "0"

    conteo = {col: "0" for col in CANDIDATOS.values()}
    for cargo in data.get("carg", []):
        for agr in cargo.get("agr", []):
            for par in agr.get("par", []):
                for c in par.get("cand", []):
                    nombre_tse = (c.get("nmu") or c.get("nm") or "").lower()
                    votos = c.get("vap", "0")
                    for clave, col in CANDIDATOS.items():
                        if clave in nombre_tse:
                            conteo[col] = votos

    fila = [
        hora_local, hora_tse, cod_mun, num_zona, e.get("te", "0"), v.get("tv", "0"),
        conteo["Lula"], conteo["Flavio_Bolsonaro"], conteo["Augusto_Cury"],
        conteo["Ronaldo_Caiado"], conteo["Romeu_Zema"], conteo["Renan_Santos"],
        conteo["Hertz_Dias"], conteo["Edmilson_Costa"], conteo["Clariana_Barao"],
        conteo["Avalanche_Marçal"], conteo["Rui_Costa_Pimenta"],
        conteo["Wilson_Grassi"], conteo["Samara_Martins"],
        v.get("vb", "0"), v.get("vn", "0"), uf.upper(), n_pasada,
    ]
    escribir_fila_csv(fila)
    return f"{uf}/{cod_mun}", hora_tse


def registrar_log_barrido(t0, n_pasada, municipios, zonas, args):
    try:
        ruta = os.path.join(rd.ruta_dir("lanzamiento"), "scrape_runs.csv")
        nuevo = not os.path.exists(ruta)
        with open(ruta, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if nuevo:
                w.writerow(["inicio", "fin", "duracion_s", "n_pasada",
                            "municipios", "zonas", "limite", "workers", "scraper"])
            w.writerow([
                datetime.fromtimestamp(t0).strftime("%Y-%m-%d %H:%M:%S"),
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                f"{time.time() - t0:.1f}", n_pasada, municipios, zonas,
                args.limite, args.workers, "RAP2",
            ])
    except OSError:
        pass


def realizar_barrido_inteligente(municipios, control_versiones, n_pasada, args):
    t0 = time.time()
    print(f"\n[+] Ciclo iniciado | PASADA N° {n_pasada} | {datetime.now().strftime('%H:%M:%S')}")
    estados = [args.uf] if args.uf else ESTADOS

    # 1) Abrangencia por UF EN PARALELO (antes: secuencial, 27 peticiones).
    ufs_con_muns = [uf for uf in estados if municipios.get(uf)]
    with ThreadPoolExecutor(max_workers=min(len(ufs_con_muns) or 1, args.workers)) as ex:
        versiones_por_uf = dict(zip(ufs_con_muns, ex.map(versiones_estado, ufs_con_muns)))

    # 2) Construir tareas a nivel ZONA, saltando municipios sin progreso.
    tareas = []
    muns_pend = 0
    for uf in ufs_con_muns:
        versiones = versiones_por_uf.get(uf) or {}
        if not versiones:
            continue
        intentados = 0
        for mu in municipios.get(uf, []):
            clave = f"{uf}/{mu['cd']}"
            version = versiones.get(mu["cd"])
            if not version or control_versiones.get(clave) == version:
                continue
            if progreso_de_version(version) <= 0:
                continue
            if args.max_mun and intentados >= args.max_mun:
                break
            intentados += 1
            muns_pend += 1
            for zona in (mu["zonas"] or [""]):
                tareas.append((uf, mu["cd"], mu["nm"], zona, version))
    print(f"[i] Tareas pendientes: {muns_pend} municipios / {len(tareas)} zonas.")
    if not tareas:
        print("[✓] Sin novedades o cambios en las zonas.")
        return 0

    # 3) Intercalar por estado (round-robin) para quitar el sesgo alfabético.
    deques = {}
    for t in tareas:
        deques.setdefault(t[0], []).append(t)
    tareas_inter = []
    while deques:
        for uf in list(deques):
            tareas_inter.append(deques[uf].pop(0))
            if not deques[uf]:
                del deques[uf]
    tareas = tareas_inter

    # 4) Descargar en un único pool global.
    municipios_actualizados = set()
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(descargar_zona_individual, uf, cod, nm, zona, ver, n_pasada):
                (uf, cod, ver)
            for uf, cod, nm, zona, ver in tareas
        }
        for future in as_completed(futures):
            uf, cod, ver = futures[future]
            try:
                resultado = future.result()
            except Exception:
                resultado = None
            if resultado:
                clave, _ = resultado
                control_versiones[clave] = ver
                municipios_actualizados.add(clave)

    registrar_log_barrido(t0, n_pasada, len(municipios_actualizados),
                          len(tareas), args)
    if _contadores:
        print(f"[i] Respuestas HTTP: {dict(sorted(_contadores.items()))}")
    print(f"\n[✓] Pasada N° {n_pasada} terminada. Municipios actualizados: "
          f"{len(municipios_actualizados)}")
    return len(municipios_actualizados)


def main():
    global VERBOSE, ARCHIVO_CSV
    parser = argparse.ArgumentParser(description="Raspador TSE 2026 RAP2 (rápido).")
    parser.add_argument("--uf", help="Procesar una sola UF (ej. sp, zz).")
    parser.add_argument("--una-pasada", action="store_true", help="Un ciclo y salir.")
    parser.add_argument("--workers", type=int, default=MAX_WORKERS, help="Hilos concurrentes.")
    parser.add_argument("--limite", type=int, default=LIMITE_REQ_POR_SEGUNDO,
                        help="Peticiones por segundo (token bucket). TSE ~100 máx.")
    parser.add_argument("--intervalo", type=int, default=20, help="Segundos entre ciclos.")
    parser.add_argument("--max-mun", type=int, help="Límite de municipios por UF (pruebas).")
    parser.add_argument("--salida", help="Archivo CSV de salida (def. en D:).")
    parser.add_argument("--silencioso", action="store_true",
                        help="Desactiva el registro verboso por zona.")
    args = parser.parse_args()

    VERBOSE = not args.silencioso
    if args.salida:
        ARCHIVO_CSV = args.salida
    configurar_limite(args.limite)

    print("[*] Iniciando raspador RAP2 (multithread + escritura inmediata).")
    print(f"[*] Hilos: {args.workers} | límite: {args.limite} req/s | salida: {ARCHIVO_CSV}")

    asegurar_csv()
    municipios = cargar_municipios()
    print(f"[*] Municipios cargados: {sum(len(v) for v in municipios.values())}")
    if not municipios:
        sys.exit(1)

    control_versiones = {}
    pasada = 1
    try:
        while True:
            realizar_barrido_inteligente(municipios, control_versiones, pasada, args)
            if args.una_pasada:
                break
            print(f"\nEsperando {args.intervalo} segundos para el próximo barrido...")
            time.sleep(args.intervalo)
            pasada += 1
    except KeyboardInterrupt:
        print("\n[!] Interrumpido por el usuario.")


if __name__ == "__main__":
    main()
