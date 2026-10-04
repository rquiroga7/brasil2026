import os
import csv
import time
import requests
from datetime import datetime

# === CONFIGURACIÓN OFICIAL TSE 2026 ===
# Cambios mínimos respecto a la versión vieja:
#   * host correcto: resultados.tse.jus.br (tse.jus.br daba 403)
#   * rutas vigentes EA20: config/mun-e<cod6>-cm.json y
#     dados/<uf>/<uf><mun>-z<zona>-c<cargo>-e<cod6>-u.json
#     (la vieja usaba -i.json de estado y -m...-v.json de municipio, que ya no existen)
ARCHIVO_CSV = "escrutinio_zonas_2026.csv"
DOMINIO_BASE = "https://resultados.tse.jus.br"
ANO_ELECCION = "ele2026"
CODIGO_ELEICAO = "6257"
CODIGO_ELEICAO_6D = "006257"
CARGO = "0001"

ESTADOS = ["ac", "al", "am", "ap", "ba", "ce", "df", "es", "go", "ma", "mg", "ms", "mt", 
           "pa", "pb", "pe", "pi", "pr", "rj", "rn", "ro", "rr", "rs", "sc", "se", "sp", "to"]

CANDIDATOS = {
    "lula": "Lula", "flavio bolsonaro": "Flavio_Bolsonaro", "augusto cury": "Augusto_Cury",
    "caiado": "Ronaldo_Caiado", "zema": "Romeu_Zema", "renan santos": "Renan_Santos",
    "hertz dias": "Hertz_Dias", "edmilson costa": "Edmilson_Costa", "clariana": "Clariana_Barao",
    "avalanche": "Avalanche_Marçal", "marçal": "Avalanche_Marçal",
    "pimenta": "Rui_Costa_Pimenta", "grassi": "Wilson_Grassi", "samara": "Samara_Martins"
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json"
}

LIMITE_REQ_POR_SEGUNDO = 25  
peticiones_este_segundo = 0
segundo_actual = int(time.time())

def registrar_peticion_y_controlar_trafico():
    global peticiones_este_segundo, segundo_actual
    ahora = int(time.time())
    if ahora == segundo_actual:
        peticiones_este_segundo += 1
        if peticiones_este_segundo >= LIMITE_REQ_POR_SEGUNDO:
            tiempo_espera = 1.0 - (time.time() % 1)
            if tiempo_espera > 0:
                time.sleep(tiempo_espera)
            segundo_actual = int(time.time())
            peticiones_este_segundo = 1
    else:
        segundo_actual = ahora
        peticiones_este_segundo = 1

# Inicialización local incorporando 'estado_uf' en la penúltima posición
if not os.path.exists(ARCHIVO_CSV):
    print(f"[*] Creando base de datos por Zonas Electorales: {ARCHIVO_CSV}")
    with open(ARCHIVO_CSV, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "hora_local", "hora_tse", "codigo_municipio", "zona_electoral", "electores_totales", "votos_totales",
            "Lula", "Flavio_Bolsonaro", "Augusto_Cury", "Ronaldo_Caiado", 
            "Romeu_Zema", "Renan_Santos", "Hertz_Dias", "Edmilson_Costa", 
            "Clariana_Barao", "Avalanche_Marçal", "Rui_Costa_Pimenta", 
            "Wilson_Grassi", "Samara_Martins", "votos_blancos", "votos_nulos",
            "estado_uf",     # <- PENÚLTIMA COLUMNA SOLICITADA
            "numero_pasada"  # <- ÚLTIMA COLUMNA
        ])

control_versiones = {}

# Municipios y zonas por UF, cargados una sola vez desde el config vigente.
municipios_por_uf = {}


def cargar_municipios(session):
    """Lista de municipios y sus zonas desde config/mun-e<cod6>-cm.json."""
    url = (f"{DOMINIO_BASE}/oficial/{ANO_ELECCION}/{CODIGO_ELEICAO}"
           f"/config/mun-e{CODIGO_ELEICAO_6D}-cm.json")
    registrar_peticion_y_controlar_trafico()
    res = session.get(url, headers=HEADERS, timeout=15)
    res.raise_for_status()
    data = res.json()
    mapa = {}
    for uf_entry in data.get("abr", []):
        uf = str(uf_entry.get("cd", "")).lower()
        if uf not in ESTADOS:
            continue
        mapa[uf] = [
            (str(mu.get("cd")), mu.get("nm"), [str(z) for z in (mu.get("z") or [])])
            for mu in uf_entry.get("mu", [])
        ]
    return mapa


def versiones_estado(session, uf):
    """{codigo_municipio: version} desde el avance -ab.json (reemplaza a -i.json)."""
    url = (f"{DOMINIO_BASE}/oficial/{ANO_ELECCION}/{CODIGO_ELEICAO}"
           f"/dados/{uf}/{uf}-e{CODIGO_ELEICAO_6D}-ab.json")
    registrar_peticion_y_controlar_trafico()
    try:
        res = session.get(url, headers=HEADERS, timeout=10)
        if res.status_code != 200:
            return {}
        data = res.json()
    except Exception:
        return {}
    dg, hg = data.get("dg", ""), data.get("hg", "")
    versiones = {}
    for ab in data.get("abr", []):
        cd = str(ab.get("cdabr", ""))
        est = str(ab.get("e", {}).get("est", ""))
        versiones[cd] = f"{ab.get('dt') or dg}|{ab.get('ht') or hg}|{est}"
    return versiones


def procesar_municipio_por_zonas(session, uf, cod_mun, zonas, hora_tse, n_pasada):
    filas_a_escribir = []
    hora_local = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for zona in zonas:
        # Ruta vigente EA20 por zona (sin el prefijo "-m" y con sufijo -u.json).
        url_zona = (f"{DOMINIO_BASE}/oficial/{ANO_ELECCION}/{CODIGO_ELEICAO}"
                    f"/dados/{uf}/{uf}{cod_mun}-z{zona}-c{CARGO}-e{CODIGO_ELEICAO_6D}-u.json")
        registrar_peticion_y_controlar_trafico()
        try:
            time.sleep(0.04)
            res = session.get(url_zona, headers=HEADERS, timeout=5)
            if res.status_code != 200:
                continue
            data = res.json()
        except Exception:
            continue

        e = data.get("e", {})
        v = data.get("v", {})
        electores_zona = e.get("te", "0")
        votos_totales_zona = v.get("tv", "0")
        votos_blancos_zona = v.get("vb", "0")
        votos_nulos_zona = v.get("vn", "0")

        num_zona = str(zona).lstrip("0")
        if not num_zona:
            num_zona = "0"

        # Los candidatos ahora viven en carg[].agr[].par[].cand[] y se identifican
        # por su número ("n"); el nombre de urna ("nmu") conserva las claves viejas.
        conteo_cand_zona = {nombre_col: "0" for nombre_col in CANDIDATOS.values()}
        for cargo in data.get("carg", []):
            for agr in cargo.get("agr", []):
                for par in agr.get("par", []):
                    for c in par.get("cand", []):
                        nombre_tse = (c.get("nmu") or c.get("nm") or "").lower()
                        votos_candidato = c.get("vap", "0")
                        for clave_busqueda, nombre_columna in CANDIDATOS.items():
                            if clave_busqueda in nombre_tse:
                                conteo_cand_zona[nombre_columna] = votos_candidato

        fila = [
            hora_local, hora_tse, cod_mun, num_zona, electores_zona, votos_totales_zona,
            conteo_cand_zona["Lula"], conteo_cand_zona["Flavio_Bolsonaro"], conteo_cand_zona["Augusto_Cury"],
            conteo_cand_zona["Ronaldo_Caiado"], conteo_cand_zona["Romeu_Zema"], conteo_cand_zona["Renan_Santos"],
            conteo_cand_zona["Hertz_Dias"], conteo_cand_zona["Edmilson_Costa"], conteo_cand_zona["Clariana_Barao"],
            conteo_cand_zona["Avalanche_Marçal"], conteo_cand_zona["Rui_Costa_Pimenta"],
            conteo_cand_zona["Wilson_Grassi"], conteo_cand_zona["Samara_Martins"],
            votos_blancos_zona, votos_nulos_zona,
            uf.upper(),  # <- Guarda la sigla del Estado en mayúsculas (Ej: SP, RJ, BA)
            n_pasada
        ]
        filas_a_escribir.append(fila)

    if not filas_a_escribir:
        return False

    with open(ARCHIVO_CSV, mode="a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerows(filas_a_escribir)
    return True


def realizar_barrido_inteligente(session, n_pasada):
    print(f"\n[+] Ciclo de verificación iniciado | PASADA N° {n_pasada} | {datetime.now().strftime('%H:%M:%S')}")
    municipios_modificados = 0

    for uf in ESTADOS:
        print(f" -> Escaneando índice del estado: {uf.upper()}...", end="\r")
        versiones = versiones_estado(session, uf)
        for cod_mun, _nombre, zonas in municipios_por_uf.get(uf, []):
            version = versiones.get(cod_mun)
            if version is None:
                continue
            if control_versiones.get(cod_mun) == version:
                continue
            if not zonas:
                continue
            exito = procesar_municipio_por_zonas(session, uf, cod_mun, zonas, version, n_pasada)
            if exito:
                control_versiones[cod_mun] = version
                municipios_modificados += 1

    print(f"\n[✓] Pasada N° {n_pasada} terminada. Municipios con zonas actualizadas: {municipios_modificados}")


if __name__ == "__main__":
    print("[*] Iniciando raspador por Zonas con columnas de Estado y Pasadas activas.")

    contador_pasadas_global = 1

    with requests.Session() as s:
        municipios_por_uf = cargar_municipios(s)
        print(f"[*] Municipios cargados: {sum(len(v) for v in municipios_por_uf.values())}")
        while True:
            realizar_barrido_inteligente(s, contador_pasadas_global)
            print("Esperando 45 segundos para el próximo barrido...")
            time.sleep(45)
            contador_pasadas_global += 1
