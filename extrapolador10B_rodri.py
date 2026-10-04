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

Denominador: votos válidos (se excluyen nulos y blancos).
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
from matplotlib.lines import Line2D
import numpy as np
import pandas as pd
import requests  # noqa: F401  (se mantiene por si se amplía con descargas TSE)

# === ARCHIVOS ===
ARCHIVO_BASE_2022 = "padron_y_asistencia_2022.csv"
ARCHIVO_PADRON_2026 = "padron_2026.csv"
ARCHIVO_VIVO_2026 = "escrutinio_zonas_2026.csv"
ARCHIVO_HISTORICO = "historico_proyecciones_2026.csv"
ARCHIVO_IMAGEN = "grafico_vivo_2026.png"
ARCHIVO_JSON = "datos_proyeccion_2026.json"
ARCHIVO_HIST_SWING = "historico_swing_2026.csv"
ARCHIVO_IMG_SWING = "simulacion_swing_2026.png"

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
      "nacional": {"Lula": 0.50, "Flavio": 0.40, "Otros": 0.10},
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
    v_blancos = (
        df_grupo["votos_blancos"].sum()
        if "votos_blancos" in df_grupo.columns
        else 0
    )
    v_totales = df_grupo["votos_totales"].sum()
    # Válidos = total - nulos - blancos (comparable con el swing v2).
    denominador = v_totales - v_nulos - v_blancos

    if denominador == 0:
      return {"Lula": 0.35, "Flavio": 0.35, "Otros": 0.30}

    v_otros = denominador - v_lula - v_bols
    return {
        "Lula": v_lula / denominador,
        "Flavio": v_bols / denominador,
        "Otros": v_otros / denominador,
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
  total_lula_crudo = total_bols_crudo = total_nulos_crudo = total_blancos_crudo = 0
  total_votos_totales_crudo = 0

  for _, fila in df_2026_ultimos.iterrows():
    m = str(fila["codigo_municipio"])
    z = str(fila["zona_electoral"])
    tot = int(fila["votos_totales"])
    l = int(fila["Lula"])
    b = int(fila["Flavio_Bolsonaro"])
    n = int(fila["votos_nulos"]) if "votos_nulos" in fila else 0
    bl = int(fila["votos_blancos"]) if "votos_blancos" in fila else 0
    dict_vivo_2026[(m, z)] = {
        "votos_totales": tot, "Lula": l, "Flavio": b,
        "votos_nulos": n, "votos_blancos": bl,
    }
    total_lula_crudo += l
    total_bols_crudo += b
    total_nulos_crudo += n
    total_blancos_crudo += bl
    total_votos_totales_crudo += tot

  total_validos_crudo = (
      total_votos_totales_crudo - total_nulos_crudo - total_blancos_crudo
  )
  total_otros_crudo = total_validos_crudo - total_lula_crudo - total_bols_crudo

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
      v_bl = dict_vivo_2026[llave]["votos_blancos"]
      denominador_zona = v_tot - v_nul - v_bl
      if denominador_zona > 0:
        prop_lula = dict_vivo_2026[llave]["Lula"] / denominador_zona
        prop_flavio = dict_vivo_2026[llave]["Flavio"] / denominador_zona
        prop_otros = (
            denominador_zona - dict_vivo_2026[llave]["Lula"]
            - dict_vivo_2026[llave]["Flavio"]
        ) / denominador_zona
      else:
        prop_lula, prop_flavio, prop_otros = 0, 0, 0
      zonas_nivel_directo += 1
    elif m in fallbacks["municipio"]:
      prop_lula = fallbacks["municipio"][m]["Lula"]
      prop_flavio = fallbacks["municipio"][m]["Flavio"]
      prop_otros = fallbacks["municipio"][m]["Otros"]
      zonas_nivel_municipio += 1
    elif uf in fallbacks["estado"]:
      prop_lula = fallbacks["estado"][uf]["Lula"]
      prop_flavio = fallbacks["estado"][uf]["Flavio"]
      prop_otros = fallbacks["estado"][uf]["Otros"]
      zonas_nivel_estado += 1
    else:
      prop_lula = fallbacks["nacional"]["Lula"]
      prop_flavio = fallbacks["nacional"]["Flavio"]
      prop_otros = fallbacks["nacional"]["Otros"]
      zonas_nivel_nacional += 1

    proyecciones_zonales.append({
        "estado_uf": uf,
        "codigo_municipio": m,
        "proj_lula": asistencia_estimada_2026 * prop_lula,
        "proj_flavio": asistencia_estimada_2026 * prop_flavio,
        "proj_otros": asistencia_estimada_2026 * prop_otros,
        "peso_asistencia": asistencia_estimada_2026,
    })

  df_proj = pd.DataFrame(proyecciones_zonales)

  total_lula_ext = df_proj["proj_lula"].sum()
  total_flavio_ext = df_proj["proj_flavio"].sum()
  total_otros_ext = df_proj["proj_otros"].sum()
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

  pct_l_crudo = pct(total_lula_crudo, total_validos_crudo)
  pct_f_crudo = pct(total_bols_crudo, total_validos_crudo)
  pct_o_crudo = pct(total_otros_crudo, total_validos_crudo)
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
        total_otros_crudo, round(pct_o_crudo, 4),
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
          "otros": {"votos": total_otros_crudo, "pct": round(pct_o_crudo, 2)},
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
  print(        f"   * Denominador = Candidatos (nulos y blancos excluidos) | "
        f"ESCRUTADO: {pct_escrutado:.2f}%")
  print("=" * 74)
  print(f"RAW (TSE)   | {total_lula_crudo:>10,} ({pct_l_crudo:5.2f}%) |"
        f" {total_bols_crudo:>10,} ({pct_f_crudo:5.2f}%) |"
        f" {total_otros_crudo:>10,} ({pct_o_crudo:5.2f}%)")
  print(f"PROYECTADO  | {int(total_lula_ext):>10,} ({pct_l_ext:5.2f}%) |"
        f" {int(total_flavio_ext):>10,} ({pct_f_ext:5.2f}%) |"
        f" {int(total_otros_ext):>10,} ({pct_o_ext:5.2f}%)")
  print("=" * 74)
  print(f"ESTADO DE CONTROL: {leyenda_estabilidad}")
  print(f"Zonas -> directas:{zonas_nivel_directo:,} municipio:{zonas_nivel_municipio:,} "
        f"estado:{zonas_nivel_estado:,} nacional:{zonas_nivel_nacional:,}")

  return resultado


def graficar_desde_historico():
  """Reconstruye el gráfico (RAW, v1, swing y votos contados) desde el historial."""
  if not os.path.exists(ARCHIVO_HISTORICO):
    return
  df = pd.read_csv(ARCHIVO_HISTORICO)
  if df.empty:
    return

  df_crudo = df[df["tipo"] == "crudo"].reset_index(drop=True)
  df_ext = df[df["tipo"] == "extrapolado"].reset_index(drop=True)
  df_swing = df[df["tipo"] == "swing"].reset_index(drop=True)

  paneles = []
  if not df_crudo.empty:
    paneles.append(("pct", df_crudo,
                    f"VOTOS RAW EN VIVO - TSE (última: {df_crudo['fecha_hora'].iloc[-1]}, "
                    f"escrutado {df_crudo['escrutado_pct'].iloc[-1]:.2f}%)"))
  if not df_ext.empty:
    paneles.append(("pct", df_ext,
                    "PROYECCIÓN v1 ESTRATIFICADA (votos válidos, excluye nulos y blancos)"))
  if not df_swing.empty:
    paneles.append(("pct", df_swing,
                    "PROYECCIÓN SWING v2 (2022 + swing observado, votos válidos)"))
  if not df_crudo.empty:
    paneles.append(("votos", df_crudo, "VOTOS CONTADOS ACUMULADOS (TSE)"))
  if not paneles:
    return

  fig, axes = plt.subplots(len(paneles), 1, figsize=(11, 3.3 * len(paneles)))
  if len(paneles) == 1:
    axes = [axes]

  for ax, (tipo, d, titulo) in zip(axes, paneles):
    x = list(range(1, len(d) + 1))
    if tipo == "pct":
      ax.plot(x, d["lula_pct"], "-", color="#E11B22", linewidth=2,
              label=f"Lula: {d['lula_pct'].iloc[-1]:.2f}%")
      ax.plot(x, d["bolsonaro_pct"], "-", color="#4C8DFF", linewidth=2,
              label=f"Flavio: {d['bolsonaro_pct'].iloc[-1]:.2f}%")
      ax.plot(x, d["otros_blancos_pct"], "-", color="#7F7F7F", linewidth=2,
              label=f"Otros: {d['otros_blancos_pct'].iloc[-1]:.2f}%")
      ax.set_ylabel("Porcentaje (%)", fontsize=10)
      ax.set_ylim(0, 65)
      ax.set_yticks([0, 25, 50, 65])
    else:
      votos = (pd.to_numeric(d["lula_votos"], errors="coerce").fillna(0)
               + pd.to_numeric(d["bolsonaro_votos"], errors="coerce").fillna(0)
               + pd.to_numeric(d["otros_blancos_votos"], errors="coerce").fillna(0))
      ax.plot(x, votos, "-", color="#2E7D32", linewidth=2,
              label=f"Contados: {int(votos.iloc[-1]):,}".replace(",", "."))
      ax.fill_between(x, votos, color="#2E7D32", alpha=0.15)
      ax.set_ylabel("Votos contados", fontsize=10)
      ax.yaxis.set_major_formatter(
          ticker.FuncFormatter(
              lambda v, p: f"{v/1e6:.1f}M" if v >= 1e6 else f"{int(v):,}".replace(",", ".")))
      ax.set_ylim(0, max(float(votos.max()) * 1.1, 1.0))
    ax.set_title(titulo, fontsize=11, fontweight="bold")
    ax.grid(True, linestyle="--", alpha=0.5)
    ax.legend(loc="upper left", fontsize=9, framealpha=0.8)
    ax.xaxis.set_major_locator(ticker.MaxNLocator(nbins=8, integer=True))
    etiquetas = d["fecha_hora"].tolist()
    ax.xaxis.set_major_formatter(
        ticker.FuncFormatter(
            lambda v, p, e=etiquetas: e[int(v) - 1] if 0 <= int(v) - 1 < len(e) else ""
        )
    )
    plt.setp(ax.get_xticklabels(), rotation=30, ha="right")

  axes[-1].set_xlabel("Hora local (sistema)", fontsize=10)
  fig.tight_layout()
  fig.savefig(ARCHIVO_IMAGEN, dpi=120, bbox_inches="tight")
  plt.close(fig)
  print(f"[i] Gráfico actualizado: {ARCHIVO_IMAGEN}")


def _curva_proyeccion(x0, y0, fin, pendiente):
  """Curva de convergencia (no lineal) desde el último punto contado hasta el final."""
  if fin is None or pd.isna(fin) or x0 >= 100:
    return None, None
  fin = float(fin)
  if abs(y0 - fin) < 1e-9:
    return np.array([x0, 100.0]), np.array([y0, fin])
  # exponente según la pendiente reciente observada (mejor que lineal)
  p = -pendiente * (100.0 - x0) / (y0 - fin)
  p = min(max(p, 0.5), 3.0)
  xs = np.linspace(x0, 100.0, 120)
  t = (xs - x0) / (100.0 - x0)
  ys = fin + (y0 - fin) * (1.0 - t) ** p
  return xs, ys


def graficar_simulacion_swing():
  """% CONTADO (raw) vs % escrutado + proyección no lineal al final swing (100%)."""
  if not os.path.exists(ARCHIVO_HISTORICO):
    return
  df = pd.read_csv(ARCHIVO_HISTORICO)
  crudo = df[df["tipo"] == "crudo"].copy()
  if crudo.empty:
    return
  x = pd.to_numeric(crudo["escrutado_pct"], errors="coerce")

  finales, bandas = {}, {}
  if os.path.exists(ARCHIVO_HIST_SWING):
    sw = pd.read_csv(ARCHIVO_HIST_SWING)
    if not sw.empty:
      last = sw.iloc[-1]
      finales = {"lula": last.get("lula_pct"), "flavio": last.get("flavio_pct"),
                 "otros": last.get("otros_pct")}
      bandas = {"lula": (last.get("lula_p5"), last.get("lula_p95")),
                "flavio": (last.get("flavio_p5"), last.get("flavio_p95"))}

  fig, ax = plt.subplots(figsize=(10, 7.5))
  series = [("lula", "lula", "Lula", "#E11B22"),
            ("bolsonaro", "flavio", "Flavio", "#4C8DFF"),
            ("otros_blancos", "otros", "Otros", "#7F7F7F")]

  for col, key, nombre, color in series:
    yv = pd.to_numeric(crudo[f"{col}_pct"], errors="coerce")
    mask = x.notna() & yv.notna()
    xv = x[mask].to_numpy(dtype=float)
    yvv = yv[mask].to_numpy(dtype=float)
    if len(xv) == 0:
      continue
    ax.plot(xv, yvv, "-", color=color, linewidth=2,
            label=f"{nombre} (contado): {yvv[-1]:.2f}%")

    fin = finales.get(key)
    if fin is None or pd.isna(fin):
      continue
    fin = float(fin)
    pendiente = 0.0
    if len(xv) >= 3:
      n = min(len(xv), 8)
      pendiente = float(np.polyfit(xv[-n:], yvv[-n:], 1)[0])
    cx, cy = _curva_proyeccion(xv[-1], yvv[-1], fin, pendiente)
    if cx is not None:
      ax.plot(cx, cy, "--", color=color, linewidth=1.8)
      ax.plot([100], [fin], "o", color=color, markersize=5)
      ax.text(101.5, fin, f"{fin:.1f}%", color=color, va="center", fontsize=9)
    # referencia lineal tenue
    ax.plot([xv[-1], 100], [yvv[-1], fin], ":", color=color, linewidth=1, alpha=0.45)
    if key in bandas:
      lo, hi = bandas[key]
      try:
        ax.plot([100, 100], [float(lo), float(hi)], color=color, linewidth=2)
      except (TypeError, ValueError):
        pass

  ax.set_xlim(0, 106)
  ax.set_ylim(0, 65)
  ax.set_yticks([0, 25, 50, 65])
  ax.set_xlabel("% escrutado", fontsize=10)
  ax.set_ylabel("Porcentaje (%)", fontsize=10)
  ax.set_title("Simulación: % contado (raw) y proyección al final swing a 100% "
               f"(última: {x.iloc[-1]:.2f}% contado)", fontsize=11, fontweight="bold")
  ax.grid(True, linestyle="--", alpha=0.5)

  # Leyenda 1 (arriba-izquierda): series contadas + total contado
  lastc = crudo.iloc[-1]

  def _v(col):
    val = lastc.get(col)
    try:
      return 0.0 if pd.isna(val) else float(val)
    except (TypeError, ValueError):
      return 0.0

  votos_contados = int(_v("lula_votos") + _v("bolsonaro_votos") + _v("otros_blancos_votos"))
  leg1 = ax.legend(loc="upper left", fontsize=9, framealpha=0.85,
                   title=f"Contados: {votos_contados:,}".replace(",", ".") + " votos",
                   title_fontsize=9)
  ax.add_artist(leg1)

  # Leyenda 2 (arriba-derecha): resultados proyectados a 100%
  handles2 = []
  for key, nombre, color in [("lula", "Lula", "#E11B22"),
                             ("flavio", "Flavio", "#4C8DFF"),
                             ("otros", "Otros", "#7F7F7F")]:
    fin = finales.get(key)
    if fin is None or pd.isna(fin):
      continue
    handles2.append(Line2D([], [], color=color, marker="o", linestyle="none",
                           markersize=7, label=f"{nombre}: {float(fin):.2f}%"))
  if handles2:
    ax.legend(handles=handles2, loc="upper right", fontsize=9, framealpha=0.85,
              title="Proyección a 100%", title_fontsize=9)

  fig.tight_layout()
  fig.savefig(ARCHIVO_IMG_SWING, dpi=120, bbox_inches="tight")
  plt.close(fig)
  print(f"[i] Simulación swing: {ARCHIVO_IMG_SWING}")


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
