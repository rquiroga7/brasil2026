# -*- coding: utf-8 -*-
"""
extrapolador10B_rodri.py — Proyección de la elección presidencial 2026.

Versión limpia (sin tokens ni subida por API de GitHub) y apta para GitHub
Actions. Genera:
  * historico_proyecciones_2026.csv  (se acumula en cada pasada)
  * grafico_vivo_2026.png            (RAW vs PROYECTADO)
  * datos_proyeccion_2026.json       (para la página web)

Método de proyección (matricial por zona):
  1. Para cada zona del padrón 2022 se estima la asistencia final 2026 como
         electores_habilitados_2026 * (% asistencia 2022 de la zona).
     El padrón 2026 se toma de padron_2026.csv (o de la columna 'electores'
     del fichero en vivo).
  2. Se asigna a cada zona una proporción Lula / Flavio / Otros:
       - si la zona ya tiene votos  -> su proporción observada;
       - si no                      -> promedio del municipio (▲);
       - si no                      -> promedio del estado (▲▲);
       - si no                      -> promedio nacional (▲▲▲).
  3. La proyección es la suma de asistencia_estimada * proporción.

Denominador: candidatos + blancos (se excluyen los nulos).
"""

import os
import csv
import sys
import json
import time
import argparse
from datetime import datetime

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import matplotlib
if "--mostrar" not in sys.argv:
    matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import pandas as pd
import requests  # noqa: F401  (se mantiene por si se amplía con descargas TSE)

# === ARCHIVOS ===
ARCHIVO_BASE_2022 = "padron_y_asistencia_2022.csv"
ARCHIVO_PADRON_2026 = "padron_2026.csv"
ARCHIVO_VIVO_2026 = "escrutinio_zonas_2026.csv"
ARCHIVO_HISTORICO = "historico_proyecciones_2026.csv"
ARCHIVO_IMAGEN = "grafico_vivo_2026.png"
ARCHIVO_JSON = "datos_proyeccion_2026.json"

CABECERA_HISTORICO = [
    "fecha_hora", "ambito", "codigo_ambito", "tipo", "escrutado_pct",
    "lula_votos", "lula_pct", "bolsonaro_votos", "bolsonaro_pct",
    "otros_blancos_votos", "otros_blancos_pct",
]


def obtener_hora_local_str():
  return datetime.now().astimezone().strftime("%H:%M:%S")


def obtener_fecha_hora_local_str():
  return datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")


# === NORMALIZACIÓN DE CÓDIGOS (2022 sin ceros a la izquierda vs 2026 con relleno) ===
def normalizar_codigo(valor):
  s = str(valor).strip()
  return str(int(s)) if s.isdigit() else s


def clave_zona(codigo_municipio, zona_electoral):
  return normalizar_codigo(codigo_municipio), normalizar_codigo(zona_electoral)


def cargar_electores_habilitados_2026(df_vivo_2026):
  """Mapa {(municipio, zona): electores_habilitados_2026}."""
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
    print(f"[-] Error crítico: No se encuentra '{ARCHIVO_BASE_2022}'.")
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
    denominador = v_totales - v_nulos

    if denominador == 0:
      return {"Lula": 0.35, "Flavio": 0.35, "OtrosBlancos": 0.30}

    v_otros_blancos = denominador - v_lula - v_bols
    return {
        "Lula": v_lula / denominador,
        "Flavio": v_bols / denominador,
        "OtrosBlancos": v_otros_blancos / denominador,
    }

  dict_fallbacks["nacional"] = extraer_proporciones(df_2026_actual)
  for uf, grupo in df_2026_actual.groupby("estado_uf"):
    dict_fallbacks["estado"][uf] = extraer_proporciones(grupo)
  for mun, grupo in df_2026_actual.groupby("codigo_municipio"):
    dict_fallbacks["municipio"][mun] = extraer_proporciones(grupo)
  return dict_fallbacks


def inicializar_log_salida():
  if not os.path.exists(ARCHIVO_HISTORICO):
    with open(ARCHIVO_HISTORICO, mode="w", newline="", encoding="utf-8") as f:
      csv.writer(f).writerow(CABECERA_HISTORICO)


def ejecutar_extrapolacion():
  """Calcula la proyección, acumula historial y escribe PNG + JSON."""
  df_base = cargar_linea_base_2022()
  if df_base is None:
    return None

  if not os.path.exists(ARCHIVO_VIVO_2026):
    print(f"[-] Esperando por el archivo dinámico '{ARCHIVO_VIVO_2026}'...")
    return None

  try:
    df_2026 = pd.read_csv(ARCHIVO_VIVO_2026, encoding="utf-8")
  except (pd.errors.ParserError, OSError, ValueError):
    print("[!] CSV en escritura por el raspador; se reintenta en el próximo ciclo.")
    return None
  if df_2026.empty:
    print("[!] Archivo de 2026 detectado pero aún sin registros de mesas.")
    return None

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
  electores_2026 = cargar_electores_habilitados_2026(df_2026_ultimos)

  dict_vivo_2026 = {}
  total_lula_crudo = total_bols_crudo = total_nulos_crudo = 0
  total_votos_totales_crudo = 0

  for _, fila in df_2026_ultimos.iterrows():
    m = str(fila["codigo_municipio"])
    z = str(fila["zona_electoral"])
    tot = int(fila["votos_totales"])
    l = int(fila["Lula"])
    b = int(fila["Flavio_Bolsonaro"])
    n = int(fila["votos_nulos"]) if "votos_nulos" in fila else 0
    dict_vivo_2026[(m, z)] = {
        "votos_totales": tot, "Lula": l, "Flavio": b, "votos_nulos": n,
    }
    total_lula_crudo += l
    total_bols_crudo += b
    total_nulos_crudo += n
    total_votos_totales_crudo += tot

  total_validos_blancos_crudo = total_votos_totales_crudo - total_nulos_crudo
  total_otros_blancos_crudo = (
      total_validos_blancos_crudo - total_lula_crudo - total_bols_crudo
  )

  proyecciones_zonales = []
  zonas_nivel_directo = zonas_nivel_municipio = 0
  zonas_nivel_estado = zonas_nivel_nacional = 0

  for _, fila_base in df_base.iterrows():
    uf = fila_base["estado_uf"]
    m = fila_base["codigo_municipio"]
    z = fila_base["zona_electoral"]

    hab_2022 = int(fila_base["electores_habilitados"])
    try:
      pct_asistencia_2022 = float(fila_base["porcentaje_asistencia"]) / 100.0
    except (TypeError, ValueError):
      pct_asistencia_2022 = (
          int(fila_base["electores_asistieron"]) / hab_2022 if hab_2022 else 0.0
      )
    hab_2026 = electores_2026.get((m, z), hab_2022)
    asistencia_estimada_2026 = hab_2026 * pct_asistencia_2022

    llave = (m, z)
    if llave in dict_vivo_2026 and dict_vivo_2026[llave]["votos_totales"] > 0:
      v_tot = dict_vivo_2026[llave]["votos_totales"]
      v_nul = dict_vivo_2026[llave]["votos_nulos"]
      denominador_zona = v_tot - v_nul
      if denominador_zona > 0:
        prop_lula = dict_vivo_2026[llave]["Lula"] / denominador_zona
        prop_flavio = dict_vivo_2026[llave]["Flavio"] / denominador_zona
        prop_otros_blancos = (
            denominador_zona - dict_vivo_2026[llave]["Lula"]
            - dict_vivo_2026[llave]["Flavio"]
        ) / denominador_zona
      else:
        prop_lula, prop_flavio, prop_otros_blancos = 0, 0, 0
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

    proyecciones_zonales.append({
        "estado_uf": uf,
        "codigo_municipio": m,
        "proj_lula": asistencia_estimada_2026 * prop_lula,
        "proj_flavio": asistencia_estimada_2026 * prop_flavio,
        "proj_otros_blancos": asistencia_estimada_2026 * prop_otros_blancos,
        "peso_asistencia": asistencia_estimada_2026,
    })

  df_proj = pd.DataFrame(proyecciones_zonales)

  total_lula_ext = df_proj["proj_lula"].sum()
  total_flavio_ext = df_proj["proj_flavio"].sum()
  total_otros_ext = df_proj["proj_otros_blancos"].sum()
  total_peso_ext = df_proj["peso_asistencia"].sum()

  pct_escrutado = (
      total_votos_totales_crudo / total_peso_ext * 100 if total_peso_ext else 0.0
  )

  total_zonas = (
      zonas_nivel_directo + zonas_nivel_municipio
      + zonas_nivel_estado + zonas_nivel_nacional
  )
  pct_zonas_superiores = (
      (zonas_nivel_estado + zonas_nivel_nacional) / total_zonas * 100
      if total_zonas else 0
  )
  leyenda_estabilidad = "[✓] PROYECCIÓN ESTABILIZADA"
  if pct_zonas_superiores > 65.0:
    leyenda_estabilidad = "[⚠] ALTA INCERTEZA (faltan estados/municipios completos)"

  def pct(parte, total):
    return parte / total * 100 if total else 0.0

  pct_l_crudo = pct(total_lula_crudo, total_validos_blancos_crudo)
  pct_f_crudo = pct(total_bols_crudo, total_validos_blancos_crudo)
  pct_o_crudo = pct(total_otros_blancos_crudo, total_validos_blancos_crudo)
  pct_l_ext = pct(total_lula_ext, total_peso_ext)
  pct_f_ext = pct(total_flavio_ext, total_peso_ext)
  pct_o_ext = pct(total_otros_ext, total_peso_ext)

  hora_actual_local = obtener_hora_local_str()
  fecha_hora_local = obtener_fecha_hora_local_str()

  # === HISTORIAL (se acumula entre ejecuciones) ===
  with open(ARCHIVO_HISTORICO, mode="a", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow([
        fecha_hora_local, "nacional", "BR", "extrapolado", round(pct_escrutado, 4),
        int(total_lula_ext), round(pct_l_ext, 4),
        int(total_flavio_ext), round(pct_f_ext, 4),
        int(total_otros_ext), round(pct_o_ext, 4),
    ])
    w.writerow([
        fecha_hora_local, "nacional", "BR", "crudo", round(pct_escrutado, 4),
        total_lula_crudo, round(pct_l_crudo, 4),
        total_bols_crudo, round(pct_f_crudo, 4),
        total_otros_blancos_crudo, round(pct_o_crudo, 4),
    ])

  resultado = {
      "actualizado": fecha_hora_local,
      "escrutado_pct": round(pct_escrutado, 2),
      "estado_control": leyenda_estabilidad,
      "zonas": {
          "directo": zonas_nivel_directo,
          "municipio": zonas_nivel_municipio,
          "estado": zonas_nivel_estado,
          "nacional": zonas_nivel_nacional,
          "total": total_zonas,
          "pct_superiores": round(pct_zonas_superiores, 2),
      },
      "crudo": {
          "lula": {"votos": total_lula_crudo, "pct": round(pct_l_crudo, 2)},
          "flavio": {"votos": total_bols_crudo, "pct": round(pct_f_crudo, 2)},
          "otros": {"votos": total_otros_blancos_crudo, "pct": round(pct_o_crudo, 2)},
      },
      "proyectado": {
          "lula": {"votos": int(total_lula_ext), "pct": round(pct_l_ext, 2)},
          "flavio": {"votos": int(total_flavio_ext), "pct": round(pct_f_ext, 2)},
          "otros": {"votos": int(total_otros_ext), "pct": round(pct_o_ext, 2)},
      },
  }
  with open(ARCHIVO_JSON, "w", encoding="utf-8") as f:
    json.dump(resultado, f, ensure_ascii=False, indent=2)

  # === CONSOLA ===
  print("\n" + "=" * 74)
  print(f"   MONITOR DE EXTRAPOLACIÓN MATRICIAL PRECOZ | {fecha_hora_local} ")
  print(f"   * Denominador = Candidatos + Blancos (nulos excluidos) | "
        f"ESCRUTADO: {pct_escrutado:.2f}%")
  print("=" * 74)
  print(f"RAW (TSE)   | {total_lula_crudo:>10,} ({pct_l_crudo:5.2f}%) |"
        f" {total_bols_crudo:>10,} ({pct_f_crudo:5.2f}%) |"
        f" {total_otros_blancos_crudo:>10,} ({pct_o_crudo:5.2f}%)")
  print(f"PROYECTADO  | {int(total_lula_ext):>10,} ({pct_l_ext:5.2f}%) |"
        f" {int(total_flavio_ext):>10,} ({pct_f_ext:5.2f}%) |"
        f" {int(total_otros_ext):>10,} ({pct_o_ext:5.2f}%)")
  print("=" * 74)
  print(f"ESTADO DE CONTROL: {leyenda_estabilidad}")
  print(f"Zonas -> directas:{zonas_nivel_directo:,} municipio:{zonas_nivel_municipio:,} "
        f"estado:{zonas_nivel_estado:,} nacional:{zonas_nivel_nacional:,}")

  return resultado


def graficar_desde_historico():
  """Reconstruye el gráfico RAW vs PROYECTADO a partir del historial CSV."""
  if not os.path.exists(ARCHIVO_HISTORICO):
    return
  df = pd.read_csv(ARCHIVO_HISTORICO)
  if df.empty:
    return

  df_crudo = df[df["tipo"] == "crudo"].reset_index(drop=True)
  df_ext = df[df["tipo"] == "extrapolado"].reset_index(drop=True)
  if df_crudo.empty or df_ext.empty:
    return

  x = list(range(1, len(df_crudo) + 1))
  etiquetas = df_crudo["fecha_hora"].tolist()

  fig, (ax_raw, ax_ext) = plt.subplots(2, 1, figsize=(11, 8), sharex=True)

  def dibujar(ax, d, titulo):
    ax.clear()
    ax.plot(x, d["lula_pct"], "-", color="#E11B22", linewidth=2,
            label=f"Lula: {d['lula_pct'].iloc[-1]:.2f}%")
    ax.plot(x, d["bolsonaro_pct"], "-", color="#002B7F", linewidth=2,
            label=f"Flavio: {d['bolsonaro_pct'].iloc[-1]:.2f}%")
    ax.plot(x, d["otros_blancos_pct"], "-", color="#7F7F7F", linewidth=2,
            label=f"Otros+Blancos: {d['otros_blancos_pct'].iloc[-1]:.2f}%")
    ax.set_title(titulo, fontsize=11, fontweight="bold")
    ax.set_ylabel("Porcentaje (%)", fontsize=10)
    ax.set_ylim(-2, 102)
    ax.grid(True, linestyle="--", alpha=0.5)
    ax.legend(loc="upper right", fontsize=9, framealpha=0.8)

  dibujar(ax_raw, df_crudo,
          f"VOTOS RAW EN VIVO - TSE (última: {etiquetas[-1]}, "
          f"escrutado {df_crudo['escrutado_pct'].iloc[-1]:.2f}%)")
  dibujar(ax_ext, df_ext,
          "PROYECCIÓN MATRICIAL EXTRAPOLADA (excluye nulos)")

  ax_ext.set_xlabel("Hora local (sistema)", fontsize=10)
  ax_ext.xaxis.set_major_locator(ticker.MaxNLocator(nbins=8, integer=True))
  ax_ext.xaxis.set_major_formatter(
      ticker.FuncFormatter(
          lambda v, p: etiquetas[int(v) - 1] if 0 <= int(v) - 1 < len(etiquetas) else ""
      )
  )
  plt.setp(ax_ext.get_xticklabels(), rotation=30, ha="right")
  fig.tight_layout()
  fig.savefig(ARCHIVO_IMAGEN, dpi=120, bbox_inches="tight")
  plt.close(fig)
  print(f"[i] Gráfico actualizado: {ARCHIVO_IMAGEN}")


def main():
  parser = argparse.ArgumentParser(description="Extrapolador 2026 (por zona).")
  parser.add_argument("--una-pasada", action="store_true",
                      help="Una sola pasada y salir (por defecto).")
  parser.add_argument("--bucle", action="store_true",
                      help="Repetir indefinidamente (uso local).")
  parser.add_argument("--intervalo", type=int, default=15,
                      help="Segundos entre pasadas con --bucle.")
  parser.add_argument("--mostrar", action="store_true",
                      help="Abrir ventana interactiva (requiere backend gráfico).")
  parser.add_argument("--sin-grafico", action="store_true",
                      help="No regenerar el PNG.")
  args = parser.parse_args()

  inicializar_log_salida()

  if not args.bucle:
    resultado = ejecutar_extrapolacion()
    if resultado and not args.sin_grafico:
      graficar_desde_historico()
    return

  if args.mostrar:
    plt.ion()
  while True:
    ejecutar_extrapolacion()
    if not args.sin_grafico:
      graficar_desde_historico()
    time.sleep(args.intervalo)


if __name__ == "__main__":
  main()
