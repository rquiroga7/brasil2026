import csv
import os
import time
from datetime import datetime
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import pandas as pd

import rutas_datos as rd

# === ARCHIVOS DE ENTRADA Y SALIDA ===
ARCHIVO_BASE_2022 = rd.ruta("padron_y_asistencia_2022.csv")
ARCHIVO_PADRON_2026 = rd.ruta("padron_2026.csv")    # electores habilitados 2026 por zona
ARCHIVO_VIVO_2026 = rd.ruta("escrutinio_zonas_2026.csv")
ARCHIVO_LOG_PROYECCIONES = rd.ruta("historico_proyecciones_2026.csv")
ARCHIVO_IMAGEN_WEB = rd.ruta("grafico_vivo_2026.png")

# === SALIDA WEB ===
# La publicación del gráfico se hace desde GitHub Actions (rama gh-pages o
# carpeta /docs) usando el GITHUB_TOKEN automático del workflow. No se
# requieren credenciales embebidas en el código.

# Control de tiempo para subida a la web (cada 30 segundos)
ultima_subida_web = 0
INTERVALO_SUBIDA_WEB = 30

# Listas de almacenamiento en memoria
historial_pasos = []
historial_horas = []

# Datos RAW (TSE)
historial_raw_lula = []
historial_raw_flavio = []
historial_raw_otros = []

# Datos PROYECTADOS (Extrapolados)
historial_ext_lula = []
historial_ext_flavio = []
historial_ext_otros = []

# Variables globales para la figura
fig = None
ax_raw = None
ax_ext = None
contador_iteracion = 0


def obtener_hora_local_str():
  return datetime.now().astimezone().strftime("%H:%M:%S")


def obtener_fecha_hora_local_str():
  return datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")


def inicializar_grafico():
  global fig, ax_raw, ax_ext
  plt.ion()
  fig, (ax_raw, ax_ext) = plt.subplots(2, 1, figsize=(10, 8), sharex=True)
  fig.canvas.manager.set_window_title(
      "Evolución Escrutinio Brasil 2026 - RAW vs Proyectado"
  )
  plt.show(block=False)


def actualizar_grafico(
    hora_str,
    pct_l_raw,
    pct_f_raw,
    pct_o_raw,
    pct_l_ext,
    pct_f_ext,
    pct_o_ext,
    pct_escrutado,
):
  global fig, ax_raw, ax_ext, contador_iteracion, ultima_subida_web

  contador_iteracion += 1

  historial_pasos.append(contador_iteracion)
  historial_horas.append(hora_str)

  historial_raw_lula.append(pct_l_raw)
  historial_raw_flavio.append(pct_f_raw)
  historial_raw_otros.append(pct_o_raw)

  historial_ext_lula.append(pct_l_ext)
  historial_ext_flavio.append(pct_f_ext)
  historial_ext_otros.append(pct_o_ext)

  try:
    ax_raw.clear()
    ax_ext.clear()

    # --- SUBPLOT 1: RAW / TSE (SUPERIOR) ---
    label_lula_raw = f"Lula: {pct_l_raw:.2f}%"
    label_flavio_raw = f"Bolsonaro: {pct_f_raw:.2f}%"
    label_otros_raw = f"Otros + Blancos: {pct_o_raw:.2f}%"

    ax_raw.plot(
        historial_pasos,
        historial_raw_lula,
        linestyle="-",
        color="#E11B22",
        label=label_lula_raw,
        linewidth=2,
    )
    ax_raw.plot(
        historial_pasos,
        historial_raw_flavio,
        linestyle="-",
        color="#002B7F",
        label=label_flavio_raw,
        linewidth=2,
    )
    ax_raw.plot(
        historial_pasos,
        historial_raw_otros,
        linestyle="-",
        color="#7F7F7F",
        label=label_otros_raw,
        linewidth=2,
    )

    ax_raw.set_title(
        f"VOTOS RAW EN VIVO - TSE (Última lect.: {hora_str})",
        fontsize=11,
        fontweight="bold",
    )
    ax_raw.set_ylabel("Porcentaje (%)", fontsize=10)
    ax_raw.set_ylim(-2, 102)
    ax_raw.grid(True, linestyle="--", alpha=0.5)
    ax_raw.legend(loc="upper right", fontsize=10, framealpha=0.8)

    # Indicador visual destacado con el % de escrutinio/votos analizados
    ax_raw.text(
        0.02,
        0.88,
        f"Estimacion: {pct_escrutado:.2f}%",
        transform=ax_raw.transAxes,
        fontsize=10,
        fontweight="bold",
        color="#155724",
        bbox=dict(
            boxstyle="round,pad=0.3",
            facecolor="#d4edda",
            edgecolor="#c3e6cb",
            alpha=0.9,
        ),
    )

    # --- SUBPLOT 2: EXTRAPOLADO (INFERIOR) ---
    label_lula_ext = f"Lula: {pct_l_ext:.2f}%"
    label_flavio_ext = f"Bolsonaro: {pct_f_ext:.2f}%"
    label_otros_ext = f"Otros + Blancos: {pct_o_ext:.2f}%"

    ax_ext.plot(
        historial_pasos,
        historial_ext_lula,
        linestyle="-",
        color="#E11B22",
        label=label_lula_ext,
        linewidth=2,
    )
    ax_ext.plot(
        historial_pasos,
        historial_ext_flavio,
        linestyle="-",
        color="#002B7F",
        label=label_flavio_ext,
        linewidth=2,
    )
    ax_ext.plot(
        historial_pasos,
        historial_ext_otros,
        linestyle="-",
        color="#7F7F7F",
        label=label_otros_ext,
        linewidth=2,
    )

    ax_ext.set_title(
        "PROYECCIÓN MATRICIAL EXTRAPOLADA (Excluye Nulos)",
        fontsize=11,
        fontweight="bold",
    )
    ax_ext.set_xlabel("Hora Local (Sistema)", fontsize=10)
    ax_ext.set_ylabel("Porcentaje (%)", fontsize=10)
    ax_ext.set_ylim(-2, 102)
    ax_ext.grid(True, linestyle="--", alpha=0.5)
    ax_ext.legend(loc="upper right", fontsize=10, framealpha=0.8)

    # Control inteligente de marcas en eje X
    ax_ext.xaxis.set_major_locator(ticker.MaxNLocator(nbins=8, integer=True))

    def formatear_hora(x, pos):
      idx = int(x) - 1
      if 0 <= idx < len(historial_horas):
        return historial_horas[idx]
      return ""

    ax_ext.xaxis.set_major_formatter(ticker.FuncFormatter(formatear_hora))
    plt.setp(ax_ext.get_xticklabels(), rotation=30, ha="right")

    fig.tight_layout()
    fig.canvas.draw_idle()
    plt.pause(0.1)

    # --- EXPORTACIÓN DEL GRÁFICO ---
    tiempo_actual = time.time()
    if tiempo_actual - ultima_subida_web >= INTERVALO_SUBIDA_WEB:
      fig.savefig(ARCHIVO_IMAGEN_WEB, dpi=120, bbox_inches="tight")
      print(
          f"[i] Gráfico local actualizado para web: {ARCHIVO_IMAGEN_WEB}"
          f" ({hora_str})"
      )
      ultima_subida_web = tiempo_actual

  except Exception as e:
    print(f"[!] Error actualizando gráfico: {e}")


def inicializar_log_salida():
  if not os.path.exists(ARCHIVO_LOG_PROYECCIONES):
    with open(ARCHIVO_LOG_PROYECCIONES, mode="w", encoding="utf-8") as f:
      f.write(
          "hora_local,ambito,codigo_ambito,tipo,lula_votos,lula_pct,bolsonaro_votos,bolsonaro_pct,otros_blancos_votos,otros_blancos_pct\n"
      )


def normalizar_codigo(valor):
  """Devuelve el código sin ceros a la izquierda ('04014' -> '4014')."""
  s = str(valor).strip()
  return str(int(s)) if s.isdigit() else s


def clave_zona(codigo_municipio, zona_electoral):
  """Normaliza la llave (municipio, zona) para empatar 2022 con 2026.

  El padrón 2022 guarda los códigos sin ceros a la izquierda ('4014') y las
  zonas sin relleno ('157'), mientras que la API 2026 de la TSE los rellena
  ('04014', '0157'). Se normalizan ambos lados para que la unión funcione."""
  return normalizar_codigo(codigo_municipio), normalizar_codigo(zona_electoral)


def cargar_electores_habilitados_2026(df_vivo_2026):
  """Mapa {(municipio, zona): electores_habilitados_2026}.

  Fuente preferida: padron_2026.csv (barrido completo del padrón 2026 del TSE).
  Respaldo: la columna 'electores' del fichero en vivo 2026 (atributo e.te)."""
  electores = {}

  if os.path.exists(ARCHIVO_PADRON_2026):
    df_padron = pd.read_csv(ARCHIVO_PADRON_2026, dtype=str)
    for _, fila in df_padron.iterrows():
      clave = clave_zona(fila["codigo_municipio"], fila["zona_electoral"])
      electores[clave] = int(float(fila["electores_habilitados"]))

  if "electores" in df_vivo_2026.columns:
    for _, fila in df_vivo_2026.iterrows():
      clave = clave_zona(fila["codigo_municipio"], fila["zona_electoral"])
      valor = pd.to_numeric(fila["electores"], errors="coerce")
      if pd.notna(valor) and valor > 0:
        electores[clave] = int(valor)

  return electores


def cargar_linea_base_2022():
  if not os.path.exists(ARCHIVO_BASE_2022):
    print(
        f"[-] Error crítico: No se encuentra '{ARCHIVO_BASE_2022}' en la"
        " carpeta."
    )
    return None
  df_2022 = pd.read_csv(ARCHIVO_BASE_2022, encoding="utf-8")
  df_2022["codigo_municipio"] = df_2022["codigo_municipio"].map(normalizar_codigo)
  df_2022["zona_electoral"] = df_2022["zona_electoral"].map(normalizar_codigo)
  return df_2022


def calcular_fallbacks_jerarquicos(df_2026_actual):
  dict_fallbacks = {
      "nacional": {"Lula": 0.50, "Flavio": 0.40, "OtrosBlancos": 0.10},
      "estado": {},
      "municipio": {},
  }

  if df_2026_actual.empty:
    return dict_fallbacks

  def extraer_proporciones(df_grupo):
    v_lula = df_grupo["Lula"].sum()
    v_bols = df_grupo["Flavio_Bolsonaro"].sum()
    v_nulos = (
        df_grupo["votos_nulos"].sum()
        if "votos_nulos" in df_grupo.columns
        else 0
    )
    v_totales = df_grupo["votos_totales"].sum()

    denominador_validos_blancos = v_totales - v_nulos

    if denominador_validos_blancos == 0:
      return {"Lula": 0.35, "Flavio": 0.35, "OtrosBlancos": 0.30}

    v_otros_blancos = denominador_validos_blancos - v_lula - v_bols
    return {
        "Lula": v_lula / denominador_validos_blancos,
        "Flavio": v_bols / denominador_validos_blancos,
        "OtrosBlancos": v_otros_blancos / denominador_validos_blancos,
    }

  dict_fallbacks["nacional"] = extraer_proporciones(df_2026_actual)

  for uf, grupo in df_2026_actual.groupby("estado_uf"):
    dict_fallbacks["estado"][uf] = extraer_proporciones(grupo)

  for mun, grupo in df_2026_actual.groupby("codigo_municipio"):
    dict_fallbacks["municipio"][mun] = extraer_proporciones(grupo)

  return dict_fallbacks


def ejecutar_extrapolacion():
  df_base = cargar_linea_base_2022()
  if df_base is None:
    return

  if not os.path.exists(ARCHIVO_VIVO_2026):
    print(f"[-] Esperando por el archivo dinámico '{ARCHIVO_VIVO_2026}'...")
    return

  df_2026 = pd.read_csv(ARCHIVO_VIVO_2026, encoding="utf-8")
  if df_2026.empty:
    print("[!] Archivo de 2026 detectado pero aún sin registros de mesas.")
    return

  df_2026["codigo_municipio"] = df_2026["codigo_municipio"].map(normalizar_codigo)
  df_2026["zona_electoral"] = df_2026["zona_electoral"].map(normalizar_codigo)

  df_2026_ultimos = df_2026.sort_values("hora_local").drop_duplicates(
      subset=["codigo_municipio", "zona_electoral"], keep="last"
  )

  mapeo_uf = df_base.set_index("codigo_municipio")["estado_uf"].to_dict()
  df_2026_ultimos["estado_uf"] = (
      df_2026_ultimos["codigo_municipio"].map(mapeo_uf).fillna("zz")
  )

  fallbacks = calcular_fallbacks_jerarquicos(df_2026_ultimos)

  # Electores habilitados 2026 por zona (padrón 2026 o fichero en vivo).
  electores_2026 = cargar_electores_habilitados_2026(df_2026_ultimos)

  dict_vivo_2026 = {}
  total_lula_crudo = 0
  total_bols_crudo = 0
  total_nulos_crudo = 0
  total_votos_totales_crudo = 0

  for _, fila in df_2026_ultimos.iterrows():
    m = str(fila["codigo_municipio"])
    z = str(fila["zona_electoral"])
    tot = int(fila["votos_totales"])
    l = int(fila["Lula"])
    b = int(fila["Flavio_Bolsonaro"])
    n = int(fila["votos_nulos"]) if "votos_nulos" in fila else 0

    dict_vivo_2026[(m, z)] = {
        "votos_totales": tot,
        "Lula": l,
        "Flavio": b,
        "votos_nulos": n,
    }
    total_lula_crudo += l
    total_bols_crudo += b
    total_nulos_crudo += n
    total_votos_totales_crudo += tot

  total_validos_blancos_crudo = (
      total_votos_totales_crudo - total_nulos_crudo
  )
  total_otros_blancos_crudo = (
      total_validos_blancos_crudo - total_lula_crudo - total_bols_crudo
  )

  proyecciones_zonales = []

  zonas_nivel_directo = 0
  zonas_nivel_municipio = 0
  zonas_nivel_estado = 0
  zonas_nivel_nacional = 0

  for _, fila_base in df_base.iterrows():
    uf = fila_base["estado_uf"]
    m = fila_base["codigo_municipio"]
    z = fila_base["zona_electoral"]

    # Padrón 2026 (número de electores habilitados) + % de asistencia 2022.
    hab_2022 = int(fila_base["electores_habilitados"])
    try:
      pct_asistencia_2022 = float(fila_base["porcentaje_asistencia"]) / 100.0
    except (TypeError, ValueError):
      pct_asistencia_2022 = (
          int(fila_base["electores_asistieron"]) / hab_2022 if hab_2022 else 0.0
      )
    hab_2026 = electores_2026.get((m, z), hab_2022)
    # Se estima la participación final 2026 aplicando el porcentaje de
    # asistencia de 2022 al número de electores habilitados de 2026.
    asistencia_estimada_2026 = hab_2026 * pct_asistencia_2022

    llave = (m, z)
    prop_lula, prop_flavio, prop_otros_blancos = 0, 0, 0

    if llave in dict_vivo_2026 and dict_vivo_2026[llave]["votos_totales"] > 0:
      v_tot = dict_vivo_2026[llave]["votos_totales"]
      v_nul = dict_vivo_2026[llave]["votos_nulos"]
      denominador_zona = v_tot - v_nul

      if denominador_zona > 0:
        prop_lula = dict_vivo_2026[llave]["Lula"] / denominador_zona
        prop_flavio = dict_vivo_2026[llave]["Flavio"] / denominador_zona
        prop_otros_blancos = (
            denominador_zona
            - dict_vivo_2026[llave]["Lula"]
            - dict_vivo_2026[llave]["Flavio"]
        ) / denominador_zona
      zonas_nivel_directo += 1
    elif m in fallbacks["municipio"]:
      prop_lula = fallbacks["municipio"][m]["Lula"]
      prop_flavio = fallbacks["municipio"][m]["Flavio"]
      prop_otros_blancos = fallbacks["municipio"][m]["OtrosBlancos"]
      zonas_nivel_municipio += 1
    elif uf in fallbacks["estado"]:
      prop_lula = fallbacks["estado"][uf]["Lula"]
      prop_flavio = fallbacks["estado"][uf]["Flavio"]
      prop_otros_blancos = fallbacks["estado"][uf]["OtrosBlancos"]
      zonas_nivel_estado += 1
    else:
      prop_lula = fallbacks["nacional"]["Lula"]
      prop_flavio = fallbacks["nacional"]["Flavio"]
      prop_otros_blancos = fallbacks["nacional"]["OtrosBlancos"]
      zonas_nivel_nacional += 1

    votos_proj_lula = asistencia_estimada_2026 * prop_lula
    votos_proj_flavio = asistencia_estimada_2026 * prop_flavio
    votos_proj_otros_blancos = asistencia_estimada_2026 * prop_otros_blancos

    proyecciones_zonales.append({
        "estado_uf": uf,
        "codigo_municipio": m,
        "proj_lula": votos_proj_lula,
        "proj_flavio": votos_proj_flavio,
        "proj_otros_blancos": votos_proj_otros_blancos,
        "peso_asistencia": asistencia_estimada_2026,
    })

  df_proj = pd.DataFrame(proyecciones_zonales)

  total_lula_extrapolado = df_proj["proj_lula"].sum()
  total_flavio_extrapolado = df_proj["proj_flavio"].sum()
  total_otros_blancos_extrapolado = df_proj["proj_otros_blancos"].sum()
  total_votos_validos_blancos_extrapolados = df_proj["peso_asistencia"].sum()

  # === CÁLCULO DEL PORCENTAJE DE VOTOS ANALIZADO (ESCRUTADO) ===
  pct_escrutado = (
      (
          total_votos_totales_crudo
          / total_votos_validos_blancos_extrapolados
          * 100
      )
      if total_votos_validos_blancos_extrapolados > 0
      else 0.0
  )

  total_zonas_mapeadas = (
      zonas_nivel_directo
      + zonas_nivel_municipio
      + zonas_nivel_estado
      + zonas_nivel_nacional
  )
  pct_zonas_superiores = (
      ((zonas_nivel_estado + zonas_nivel_nacional) / total_zonas_mapeadas * 100)
      if total_zonas_mapeadas > 0
      else 0
  )

  leyenda_estabilidad = "[✓] PROYECCIÓN ESTABILIZADA"
  if pct_zonas_superiores > 65.0:
    leyenda_estabilidad = (
        "[⚠] ALTA INCERTEZA (Faltan Estados / Municipios completos)"
    )

  hora_actual_local = obtener_hora_local_str()

  pct_l_crudo = (
      (total_lula_crudo / total_validos_blancos_crudo * 100)
      if total_validos_blancos_crudo > 0
      else 0.0
  )
  pct_f_crudo = (
      (total_bols_crudo / total_validos_blancos_crudo * 100)
      if total_validos_blancos_crudo > 0
      else 0.0
  )
  pct_o_crudo = (
      (total_otros_blancos_crudo / total_validos_blancos_crudo * 100)
      if total_validos_blancos_crudo > 0
      else 0.0
  )

  pct_l_ext = (
      (
          total_lula_extrapolado
          / total_votos_validos_blancos_extrapolados
          * 100
      )
      if total_votos_validos_blancos_extrapolados > 0
      else 0.0
  )
  pct_f_ext = (
      (
          total_flavio_extrapolado
          / total_votos_validos_blancos_extrapolados
          * 100
      )
      if total_votos_validos_blancos_extrapolados > 0
      else 0.0
  )
  pct_o_ext = (
      (
          total_otros_blancos_extrapolado
          / total_votos_validos_blancos_extrapolados
          * 100
      )
      if total_votos_validos_blancos_extrapolados > 0
      else 0.0
  )

  print(
      "\n=========================================================================="
  )
  print(
      "   MONITOR DE EXTRAPOLACIÓN MATRICIAL PRECOZ (PROYECCIÓN ZONAL) |"
      f" {hora_actual_local} "
  )
  print(
      "   * Nota: Denominador = Candidatos + Blancos (Nulos Excluidos) |"
      f" ESCRUTADO: {pct_escrutado:.2f}%"
  )
  print(
      "   * Proyección: electores habilitados 2026 (padrón 2026) x % de"
      " asistencia de 2022 por zona."
  )
  print(
      "=========================================================================="
  )
  print(
      "MÉTRICA     |"
      f" {'LULA (PT)':<20} |"
      f" {'FLÁVIO BOLSONARO (PL)':<20} |"
      f" {'OTROS + BLANCOS':<20}"
  )
  print(
      "--------------------------------------------------------------------------"
  )
  print(
      f"RAW (TSE)   | {total_lula_crudo:<10,} ({pct_l_crudo:.2f}%) |"
      f" {total_bols_crudo:<10,} ({pct_f_crudo:.2f}%) |"
      f" {total_otros_blancos_crudo:<10,} ({pct_o_crudo:.2f}%)"
  )
  print(
      f"PROYECTADO  | {int(total_lula_extrapolado):<10,} ({pct_l_ext:.2f}%) |"
      f" {int(total_flavio_extrapolado):<10,} ({pct_f_ext:.2f}%) |"
      f" {int(total_otros_blancos_extrapolado):<10,} ({pct_o_ext:.2f}%)"
  )
  print(
      "=========================================================================="
  )

  print(f"ESTADO DE CONTROL: {leyenda_estabilidad}")
  print("Desglose de Origen Zonal de Datos:")
  print(
      " -> [Nivel 1] Zonas con datos directos en vivo  :"
      f" {zonas_nivel_directo:,}"
  )
  print(
      " -> [Nivel 2] Zonas resueltas por Municipio (▲) :"
      f" {zonas_nivel_municipio:,}"
  )
  print(
      " -> [Nivel 3] Zonas resueltas por Estado (▲▲)   :"
      f" {zonas_nivel_estado:,}"
  )
  print(
      " -> [Nivel 4] Zonas resueltas por Nacional (▲▲▲):"
      f" {zonas_nivel_nacional:,}"
  )
  print(
      "=========================================================================="
  )

  fecha_hora_local = obtener_fecha_hora_local_str()
  with open(
      ARCHIVO_LOG_PROYECCIONES, mode="a", newline="", encoding="utf-8"
  ) as f:
    writer = csv.writer(f)
    writer.writerow([
        fecha_hora_local,
        "nacional",
        "BR",
        "extrapolado",
        int(total_lula_extrapolado),
        round(pct_l_ext, 4),
        int(total_flavio_extrapolado),
        round(pct_f_ext, 4),
        int(total_otros_blancos_extrapolado),
        round(pct_o_ext, 4),
    ])
    writer.writerow([
        fecha_hora_local,
        "nacional",
        "BR",
        "crudo",
        total_lula_crudo,
        round(pct_l_crudo, 4),
        total_bols_crudo,
        round(pct_f_crudo, 4),
        total_otros_blancos_crudo,
        round(pct_o_crudo, 4),
    ])

  actualizar_grafico(
      hora_actual_local,
      round(pct_l_crudo, 2),
      round(pct_f_crudo, 2),
      round(pct_o_crudo, 2),
      round(pct_l_ext, 2),
      round(pct_f_ext, 2),
      round(pct_o_ext, 2),
      round(pct_escrutado, 2),
  )


def esperar_manteniendo_gui(segundos=15):
  fin = time.time() + segundos
  while time.time() < fin:
    plt.pause(0.2)


if __name__ == "__main__":
  inicializar_log_salida()
  inicializar_grafico()
  while True:
    ejecutar_extrapolacion()
    esperar_manteniendo_gui(15)
