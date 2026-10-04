import csv
import os
import time
from datetime import datetime
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# === CONFIGURACIÓN OFICIAL TSE 2026 ===
ARCHIVO_CSV = "escrutinio_zonas_2026.csv"
# DOMINIO CORRECTO DE LA CDN DE RESULTADOS
DOMINIO_BASE = "https://resultados.tse.jus.br"
ANO_ELECCION = "ele2026"
CODIGO_ELEICAO = "6257"
CODIGO_ELEICAO_6D = "006257"

ESTADOS = [
    "ac",
    "al",
    "am",
    "ap",
    "ba",
    "ce",
    "df",
    "es",
    "go",
    "ma",
    "mg",
    "ms",
    "mt",
    "pa",
    "pb",
    "pe",
    "pi",
    "pr",
    "rj",
    "rn",
    "ro",
    "rr",
    "rs",
    "sc",
    "se",
    "sp",
    "to",
]

CANDIDATOS = {
    "lula": "Lula",
    "flavio bolsonaro": "Flavio_Bolsonaro",
    "augusto cury": "Augusto_Cury",
    "caiado": "Ronaldo_Caiado",
    "zema": "Romeu_Zema",
    "renan santos": "Renan_Santos",
    "hertz dias": "Hertz_Dias",
    "edmilson costa": "Edmilson_Costa",
    "clariana": "Clariana_Barao",
    "avalanche": "Avalanche_Marçal",
    "marçal": "Avalanche_Marçal",
    "pimenta": "Rui_Costa_Pimenta",
    "grassi": "Wilson_Grassi",
    "samara": "Samara_Martins",
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML,"
        " like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "pt-BR,pt;q=0.9,es;q=0.8",
    "Referer": "https://resultados.tse.jus.br/",
    "Origin": "https://resultados.tse.jus.br",
}

LIMITE_REQ_POR_SEGUNDO = 20
peticiones_este_segundo = 0
segundo_actual = int(time.time())


def crear_session_resistente():
  """Crea una sesión HTTP con reintentos automáticos para evitar errores por congestión de red."""
  session = requests.Session()
  retries = Retry(
      total=3, backoff_factor=0.3, status_forcelist=[429, 500, 502, 503, 504]
  )
  adapter = HTTPAdapter(max_retries=retries)
  session.mount("https://", adapter)
  session.mount("http://", adapter)
  return session


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


# Inicialización del archivo CSV con cabecera estándar
if not os.path.exists(ARCHIVO_CSV):
  print(f"[*] Creando base de datos por Zonas Electorales: {ARCHIVO_CSV}")
  with open(ARCHIVO_CSV, mode="w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow([
        "hora_local",
        "hora_tse",
        "codigo_municipio",
        "zona_electoral",
        "electores_totales",
        "votos_totales",
        "Lula",
        "Flavio_Bolsonaro",
        "Augusto_Cury",
        "Ronaldo_Caiado",
        "Romeu_Zema",
        "Renan_Santos",
        "Hertz_Dias",
        "Edmilson_Costa",
        "Clariana_Barao",
        "Avalanche_Marçal",
        "Rui_Costa_Pimenta",
        "Wilson_Grassi",
        "Samara_Martins",
        "votos_blancos",
        "votos_nulos",
        "estado_uf",
        "numero_pasada",
    ])

control_versiones = {}


def procesar_municipio_por_zonas(session, uf, cod_mun_raw, hora_tse, n_pasada):
  # Formateo estricto del código de municipio a 5 dígitos (ejemplo: '01007')
  cod_mun = str(cod_mun_raw).zfill(5)

  url_mun = f"{DOMINIO_BASE}/oficial/{ANO_ELECCION}/{CODIGO_ELEICAO}/dados/{uf.lower()}/{uf.lower()}-m{cod_mun}-c0001-e{CODIGO_ELEICAO_6D}-v.json"
  registrar_peticion_y_controlar_trafico()

  try:
    res = session.get(url_mun, headers=HEADERS, timeout=6)
    if res.status_code != 200:
      return False

    data = res.json()
    zonas_internas = data.get("zns", [])
    if not zonas_internas:
      return False

    filas_a_escribir = []
    hora_local = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for zona_data in zonas_internas:
      num_zona = str(zona_data.get("cd", "")).lstrip("0")
      if not num_zona:
        num_zona = "0"

      electores_zona = str(zona_data.get("e", "0"))
      votos_totales_zona = str(zona_data.get("t", "0"))
      votos_blancos_zona = str(zona_data.get("vb", "0"))
      votos_nulos_zona = str(zona_data.get("vn", "0"))

      conteo_cand_zona = {nombre_col: "0" for nombre_col in CANDIDATOS.values()}

      # Mapeo de candidatos
      for c in zona_data.get("cand", []):
        nombre_tse = str(c.get("nm", "")).lower()
        votos_candidato = str(c.get("vap", "0"))

        for clave_busqueda, nombre_columna in CANDIDATOS.items():
          if clave_busqueda in nombre_tse:
            conteo_cand_zona[nombre_columna] = votos_candidato

      fila = [
          hora_local,
          hora_tse,
          cod_mun,
          num_zona,
          electores_zona,
          votos_totales_zona,
          conteo_cand_zona["Lula"],
          conteo_cand_zona["Flavio_Bolsonaro"],
          conteo_cand_zona["Augusto_Cury"],
          conteo_cand_zona["Ronaldo_Caiado"],
          conteo_cand_zona["Romeu_Zema"],
          conteo_cand_zona["Renan_Santos"],
          conteo_cand_zona["Hertz_Dias"],
          conteo_cand_zona["Edmilson_Costa"],
          conteo_cand_zona["Clariana_Barao"],
          conteo_cand_zona["Avalanche_Marçal"],
          conteo_cand_zona["Rui_Costa_Pimenta"],
          conteo_cand_zona["Wilson_Grassi"],
          conteo_cand_zona["Samara_Martins"],
          votos_blancos_zona,
          votos_nulos_zona,
          uf.upper(),
          n_pasada,
      ]
      filas_a_escribir.append(fila)

    if filas_a_escribir:
      with open(ARCHIVO_CSV, mode="a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerows(filas_a_escribir)
      return True
    return False

  except Exception:
    return False


def realizar_barrido_inteligente(session, n_pasada):
  print(
      f"\n[+] Ciclo de verificación iniciado | PASADA N° {n_pasada} |"
      f" {datetime.now().strftime('%H:%M:%S')}"
  )
  municipios_modificados = 0

  for uf in ESTADOS:
    print(f" -> Escaneando índice del estado: {uf.upper()}...", end="\r")
    registrar_peticion_y_controlar_trafico()

    url_estado = f"{DOMINIO_BASE}/oficial/{ANO_ELECCION}/{CODIGO_ELEICAO}/dados/{uf.lower()}/{uf.lower()}-e{CODIGO_ELEICAO_6D}-i.json"
    try:
      response = session.get(url_estado, headers=HEADERS, timeout=6)
      if response.status_code != 200:
        continue

      data_estado = response.json()
      for mu in data_estado.get("muns", []):
        cod_mun = mu.get("cd")
        hora_tse = f"{mu.get('dg', '')} {mu.get('hg', '')}".strip()

        if control_versiones.get(cod_mun) != hora_tse:
          exito = procesar_municipio_por_zonas(
              session, uf, cod_mun, hora_tse, n_pasada
          )
          if exito:
            control_versiones[cod_mun] = hora_tse
            municipios_modificados += 1
    except Exception:
      pass

  print(
      f"\n[✓] Pasada N° {n_pasada} terminada. Municipios con zonas actualizadas:"
      f" {municipios_modificados}"
  )


if __name__ == "__main__":
  print(
      "[*] Iniciando raspador por Zonas con conexión optimizada al CDN del TSE."
  )

  contador_pasadas_global = 1

  with crear_session_resistente() as s:
    while True:
      realizar_barrido_inteligente(s, contador_pasadas_global)
      print("Esperando 45 segundos para el próximo barrido...")
      time.sleep(45)
      contador_pasadas_global += 1
