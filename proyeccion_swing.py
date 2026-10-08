# -*- coding: utf-8 -*-
"""
proyeccion_swing.py — Segunda extrapolación (modelo de swing) 2026.

Mantiene el método v1 intacto (extrapolador10B_rodri.py) y añade una segunda
proyección, más robusta:

  * Denominador de VOTOS VÁLIDOS (excluye nulos Y blancos), que es el que rige
    el umbral del 50% en primera vuelta.
  * Prior de la elección 2022 a nivel de ZONA y swing observado por estado:
        proj_share_zona = share_2022_zona + swing_estado_observado
    El swing se mide sobre las MISMAS zonas ya escrutadas (pesos 2022), evitando
    el sesgo de composición. Si un estado tiene pocas zonas escrutadas, se usa
    el swing nacional.
  * Incertidumbre: Monte Carlo sobre la dispersión del swing por zona, para
    obtener intervalos p5–p95 de Lula y Flavio.
  * Fallback automático: si no existe 'escrutinio_zonas_2022.csv', la salida
    replica exactamente el método v1.

Salida: datos_proyeccion_swing_2026.json (nacional + por estado, v1 y swing).
"""

import os
import sys
import csv
import json
from datetime import datetime

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import numpy as np
import pandas as pd

import rutas_datos as rd

# Reutilizamos la carga de datos del v1 para que la semántica coincida.
from extrapolador10B_rodri import (
    normalizar_codigo,
    cargar_linea_base_2022,
    cargar_electores_habilitados_2026,
    calcular_fallbacks_jerarquicos,
    inicializar_log_salida,
    graficar_desde_historico,
    graficar_simulacion_swing,
    ARCHIVO_HISTORICO,
    ARCHIVO_HIST_SWING,
)

ARCHIVO_ZONAS_2022 = rd.ruta("escrutinio_zonas_2022.csv")
ARCHIVO_VIVO_2026 = rd.ruta("escrutinio_zonas_2026.csv")
ARCHIVO_JSON_SWING = rd.ruta("datos_proyeccion_swing_2026.json")

N_SIM = 300
MIN_ZONAS_ESTADO = 5          # zonas escrutadas mínimas para usar swing propio
MIN_VALIDOS_ESTADO = 20000.0  # válidos 2022 mínimos para usar swing propio

NOMBRES_UF = {
    "AC": "Acre", "AL": "Alagoas", "AM": "Amazonas", "AP": "Amapá",
    "BA": "Bahía", "CE": "Ceará", "DF": "Distrito Federal", "ES": "Espírito Santo",
    "GO": "Goiás", "MA": "Maranhão", "MG": "Minas Gerais", "MS": "Mato Grosso do Sul",
    "MT": "Mato Grosso", "PA": "Pará", "PB": "Paraíba", "PE": "Pernambuco",
    "PI": "Piauí", "PR": "Paraná", "RJ": "Río de Janeiro", "RN": "Rio Grande do Norte",
    "RO": "Rondônia", "RR": "Roraima", "RS": "Rio Grande do Sul", "SC": "Santa Catarina",
    "SE": "Sergipe", "SP": "São Paulo", "TO": "Tocantins", "ZZ": "Exterior",
}


def num(valor):
    try:
        return float(str(valor).replace(",", "."))
    except (TypeError, ValueError):
        return 0.0


def normalizar(M):
    M = np.clip(np.asarray(M, dtype=float), 0.0, None)
    s = M.sum(axis=1, keepdims=True)
    s = np.where(s <= 0, 1.0, s)
    return M / s


# --------------------------------------------------------------------------
# Carga de datos
# --------------------------------------------------------------------------
def cargar_zonas_2022():
    """{(municipio, zona): {uf,l,f,o,valid}} de escrutinio_zonas_2022.csv."""
    if not os.path.exists(ARCHIVO_ZONAS_2022):
        return {}
    df = pd.read_csv(ARCHIVO_ZONAS_2022, dtype=str)
    if "turno" in df.columns:
        df = df[df["turno"].astype(str).str.strip().isin(["1", "1.0"])]
    col_lula = next((c for c in df.columns if c.startswith("13_")), None)
    col_flav = next((c for c in df.columns if c.startswith("22_")), None)
    if not col_lula or not col_flav:
        return {}
    cand_cols = [c for c in df.columns if c[:2].isdigit()]
    out = {}
    for _, r in df.iterrows():
        # Votos válidos = suma de votos nominales por candidato. (El campo
        # "votos_totales" del detalhe 2022 quedó mal parseado: ~mitad del real.)
        valid = sum(num(r.get(c)) for c in cand_cols)
        if valid <= 0:
            continue
        l = num(r.get(col_lula))
        f = num(r.get(col_flav))
        out[(normalizar_codigo(r["codigo_municipio"]),
             normalizar_codigo(r["zona"]))] = {
            "uf": str(r["uf"]).upper(), "l": l, "f": f,
            "o": max(0.0, valid - l - f), "valid": valid,
        }
    return out


def cargar_vivo_2026():
    if not os.path.exists(ARCHIVO_VIVO_2026):
        return None
    try:
        df = pd.read_csv(ARCHIVO_VIVO_2026, encoding="utf-8")
    except (pd.errors.ParserError, OSError, ValueError):
        print("[!] CSV en escritura por el raspador; se reintenta en el próximo ciclo.")
        return None
    df["codigo_municipio"] = df["codigo_municipio"].map(normalizar_codigo)
    df["zona_electoral"] = df["zona_electoral"].map(normalizar_codigo)
    return df.sort_values("hora_local").drop_duplicates(
        subset=["codigo_municipio", "zona_electoral"], keep="last"
    )


def construir_live(df_vivo):
    live = {}
    for _, r in df_vivo.iterrows():
        tot = num(r.get("votos_totales"))
        nu = num(r.get("votos_nulos"))
        br = num(r.get("votos_blancos"))
        valid = max(0.0, tot - nu - br)
        l = num(r.get("Lula"))
        f = num(r.get("Flavio_Bolsonaro"))
        clave = (r["codigo_municipio"], r["zona_electoral"])
        live[clave] = {
            "uf": str(r.get("estado_uf") or "").upper(),
            "total": tot, "nulos": nu, "blancos": br, "valid": valid,
            "l": l, "f": f, "o": max(0.0, valid - l - f),
            "st": num(r.get("secoes_totalizadas")),
        }
    return live


def calcular_fallbacks_valid(df_vivo):
    """Fallback jerárquico con denominador de válidos (excluye blancos y nulos)."""
    def props(g):
        d = g["votos_totales"].sum() - g["votos_nulos"].sum() - g["votos_blancos"].sum()
        if d <= 0:
            return None   # grupo sin votos: no generar fallback
        l = g["Lula"].sum()
        f = g["Flavio_Bolsonaro"].sum()
        return {"Lula": l/d, "Flavio": f/d, "Otros": (d - l - f)/d}

    out = {"nacional": props(df_vivo) or {"Lula": 1/3, "Flavio": 1/3, "Otros": 1/3},
           "estado": {}, "municipio": {}}
    for uf, g in df_vivo.groupby("estado_uf"):
        p = props(g)
        if p is not None:
            out["estado"][uf] = p
    for m, g in df_vivo.groupby("codigo_municipio"):
        p = props(g)
        if p is not None:
            out["municipio"][m] = p
    return out


# --------------------------------------------------------------------------
# Swing observado
# --------------------------------------------------------------------------
def calcular_swings(live, dict22):
    """Swing por estado y nacional + error estándar, medido sobre zonas comunes."""
    obs = []  # (uf, peso_2022, cur[3], pri[3])
    for clave, lv in live.items():
        p = dict22.get(clave)
        if not p or lv["valid"] <= 0 or p["valid"] <= 0:
            continue
        uf = lv["uf"] or p["uf"]
        cur = np.array([lv["l"]/lv["valid"], lv["f"]/lv["valid"], lv["o"]/lv["valid"]])
        pri = np.array([p["l"]/p["valid"], p["f"]/p["valid"], p["o"]/p["valid"]])
        obs.append((uf, lv["valid"], cur, pri))

    if not obs:
        return {}, {}, np.zeros(3), np.zeros(3)

    def resumen(rows):
        W = np.array([r[1] for r in rows])
        C = np.array([r[2] for r in rows])
        P = np.array([r[3] for r in rows])
        sw = (W[:, None] * (C - P)).sum(0) / W.sum()
        se = (C - P).std(0, ddof=1) / np.sqrt(len(rows)) if len(rows) >= 2 else np.zeros(3)
        return sw, se

    swings, errores = {}, {}
    for uf in set(r[0] for r in obs):
        filas = [r for r in obs if r[0] == uf]
        validos = sum(r[1] for r in filas)
        if len(filas) >= MIN_ZONAS_ESTADO and validos >= MIN_VALIDOS_ESTADO:
            swings[uf], errores[uf] = resumen(filas)
    nat_swing, nat_se = resumen(obs)
    return swings, errores, nat_swing, nat_se


# --------------------------------------------------------------------------
# Proyección
# --------------------------------------------------------------------------
def proyectar():
    df_base = cargar_linea_base_2022()
    if df_base is None:
        return None
    df_vivo = cargar_vivo_2026()
    if df_vivo is None or df_vivo.empty:
        print("[-] No hay escrutinio 2026 todavía.")
        return None

    electores_2026 = cargar_electores_habilitados_2026(df_vivo)
    dict22 = cargar_zonas_2022()
    swing_disponible = bool(dict22)

    fb_v1 = calcular_fallbacks_jerarquicos(df_vivo)      # v1: excluye nulos
    fb_val = calcular_fallbacks_valid(df_vivo)           # v2: excluye nulos+blancos
    live = construir_live(df_vivo)

    # Escrutado CRUDO (sin proyectar), agregado por UF y nacional.
    crudo_uf = {}
    for lv in live.values():
        uf = lv["uf"]
        if not uf:
            continue
        d = crudo_uf.setdefault(uf, {"l": 0.0, "f": 0.0, "o": 0.0, "valid": 0.0,
                                     "total": 0.0, "blancos": 0.0, "nulos": 0.0})
        d["l"] += lv["l"]; d["f"] += lv["f"]; d["o"] += lv["o"]
        d["valid"] += lv["valid"]; d["total"] += lv["total"]
        d["blancos"] += lv["blancos"]; d["nulos"] += lv["nulos"]

    swings, errores, nat_swing, nat_se = ({}, {}, np.zeros(3), np.zeros(3))
    if swing_disponible:
        swings, errores, nat_swing, nat_se = calcular_swings(live, dict22)

    ufs = sorted(df_base["estado_uf"].unique())
    uf_idx = {u: i for i, u in enumerate(ufs)}
    n_uf = len(ufs)
    nat_g = n_uf  # grupo "nacional" para el swing
    n_g = n_uf + 1

    n = len(df_base)
    A = np.zeros(n)                 # asistencia estimada 2026
    H = np.zeros(n)                 # electores habilitados 2026
    state_idx = np.zeros(n, int)
    swing_src = np.zeros(n, int)
    mode = np.zeros(n, int)         # 0=escrutado, 1=prior+swing, 2=fallback
    obs = np.zeros((n, 3))
    prior = np.zeros((n, 3))
    fb2 = np.zeros((n, 3))
    v1sh = np.zeros((n, 3))
    live_total = np.zeros(n)

    for i, (_, r) in enumerate(df_base.iterrows()):
        uf = r["estado_uf"]
        m = r["codigo_municipio"]
        z = r["zona_electoral"]
        clave = (m, z)
        hab22 = int(r["electores_habilitados"])
        try:
            pct22 = float(r["porcentaje_asistencia"]) / 100.0
        except (TypeError, ValueError):
            pct22 = (int(r["electores_asistieron"]) / hab22) if hab22 else 0.0
        hab2026 = electores_2026.get(clave, hab22)
        H[i] = hab2026
        A[i] = hab2026 * pct22
        state_idx[i] = uf_idx.get(uf, 0)

        lv = live.get(clave)
        # --- v1 shares (denominador: válidos = total - nulos - blancos) ---
        if lv and lv["total"] - lv["nulos"] - lv["blancos"] > 0:
            d = lv["total"] - lv["nulos"] - lv["blancos"]
            v1sh[i] = [lv["l"]/d, lv["f"]/d, (d - lv["l"] - lv["f"])/d]
        elif m in fb_v1["municipio"]:
            v1sh[i] = [fb_v1["municipio"][m]["Lula"], fb_v1["municipio"][m]["Flavio"],
                       fb_v1["municipio"][m]["Otros"]]
        elif uf in fb_v1["estado"]:
            v1sh[i] = [fb_v1["estado"][uf]["Lula"], fb_v1["estado"][uf]["Flavio"],
                       fb_v1["estado"][uf]["Otros"]]
        else:
            v1sh[i] = [fb_v1["nacional"]["Lula"], fb_v1["nacional"]["Flavio"],
                       fb_v1["nacional"]["Otros"]]

        # --- v2: escrutado directo ---
        if lv and lv["valid"] > 0:
            mode[i] = 0
            obs[i] = [lv["l"]/lv["valid"], lv["f"]/lv["valid"], lv["o"]/lv["valid"]]
            live_total[i] = lv["total"]
            continue

        # --- v2: prior 2022 + swing ---
        p22 = dict22.get(clave)
        if swing_disponible and p22 and p22["valid"] > 0:
            mode[i] = 1
            prior[i] = [p22["l"]/p22["valid"], p22["f"]/p22["valid"], p22["o"]/p22["valid"]]
            # v2 = swing UNIFORME NACIONAL (un único swing para todo el país)
            swing_src[i] = nat_g
        else:
            mode[i] = 2
            if m in fb_val["municipio"]:
                s = fb_val["municipio"][m]
            elif uf in fb_val["estado"]:
                s = fb_val["estado"][uf]
            else:
                s = fb_val["nacional"]
            fb2[i] = [s["Lula"], s["Flavio"], s["Otros"]]

    # Medias y errores por grupo de swing
    grupo_mu = np.zeros((n_g, 3))
    grupo_sd = np.zeros((n_g, 3))
    for uf, i in uf_idx.items():
        if uf in swings:
            grupo_mu[i] = swings[uf]
            grupo_sd[i] = errores.get(uf, np.zeros(3))
        else:
            grupo_mu[i] = nat_swing
            grupo_sd[i] = nat_se
    grupo_mu[nat_g] = nat_swing
    grupo_sd[nat_g] = nat_se

    # Votos fijos (escrutados + fallback)
    fijos = np.zeros((n, 3))
    fijos[mode == 0] = A[mode == 0, None] * obs[mode == 0]
    fijos[mode == 2] = A[mode == 2, None] * fb2[mode == 2]

    valid_uf = np.zeros(n_uf)
    np.add.at(valid_uf, state_idx, A)

    def acumular(votos_zona):
        l = np.zeros(n_uf); f = np.zeros(n_uf); o = np.zeros(n_uf)
        np.add.at(l, state_idx, votos_zona[:, 0])
        np.add.at(f, state_idx, votos_zona[:, 1])
        np.add.at(o, state_idx, votos_zona[:, 2])
        return l, f, o

    # v1 (votos proyectados)
    v1_l, v1_f, v1_o = acumular(A[:, None] * v1sh)

    # v2 punto (swing medio)
    if swing_disponible:
        m1 = mode == 1
        sh1 = normalizar(prior[m1] + grupo_mu[swing_src[m1]])
        votos_v2 = fijos.copy()
        votos_v2[m1] = A[m1, None] * sh1
    else:
        votos_v2 = A[:, None] * v1sh
    v2_l, v2_f, v2_o = acumular(votos_v2)

    # Monte Carlo
    p5_l = p95_l = p5_f = p95_f = np.zeros(n_uf)
    if swing_disponible:
        rng = np.random.default_rng(42)
        m1 = mode == 1
        sims_l = np.zeros((N_SIM, n_uf))
        sims_f = np.zeros((N_SIM, n_uf))
        for s in range(N_SIM):
            sw = rng.normal(grupo_mu, grupo_sd)          # (n_g, 3)
            sh = normalizar(prior[m1] + sw[swing_src[m1]])
            v = fijos.copy()
            v[m1] = A[m1, None] * sh
            l, f, _ = acumular(v)
            sims_l[s] = l; sims_f[s] = f
        p5_l = np.percentile(sims_l, 5, axis=0)
        p95_l = np.percentile(sims_l, 95, axis=0)
        p5_f = np.percentile(sims_f, 5, axis=0)
        p95_f = np.percentile(sims_f, 95, axis=0)

    def pct(parte, total):
        return round(parte / total * 100, 2) if total > 0 else 0.0

    def bloque(l, f, o, total, il=None, if_=None):
        d = {"lula": {"votos": int(l), "pct": pct(l, total)},
             "flavio": {"votos": int(f), "pct": pct(f, total)},
             "otros": {"votos": int(o), "pct": pct(o, total)}}
        if il is not None:
            d["lula"]["p5"] = pct(il[0], total)
            d["lula"]["p95"] = pct(il[1], total)
            d["flavio"]["p5"] = pct(if_[0], total)
            d["flavio"]["p95"] = pct(if_[1], total)
        return d

    def bloque_crudo(d):
        """Escrutado real (sin proyectar), porcentajes sobre votos válidos."""
        return {
            "lula": {"votos": int(d["l"]), "pct": pct(d["l"], d["valid"])},
            "flavio": {"votos": int(d["f"]), "pct": pct(d["f"], d["valid"])},
            "otros": {"votos": int(d["o"]), "pct": pct(d["o"], d["valid"])},
            "validos": int(d["valid"]), "total": int(d["total"]),
            "blancos": int(d["blancos"]), "nulos": int(d["nulos"]),
        }

    # Nacional
    nat_total = float(valid_uf.sum())
    nat_v1 = bloque(v1_l.sum(), v1_f.sum(), v1_o.sum(), nat_total)
    if swing_disponible:
        nat_sw = bloque(v2_l.sum(), v2_f.sum(), v2_o.sum(), nat_total,
                        (p5_l.sum(), p95_l.sum()), (p5_f.sum(), p95_f.sum()))
    else:
        nat_sw = nat_v1
    escrutado_nat = pct(float(live_total.sum()), nat_total)

    crudo_nat = {"l": 0.0, "f": 0.0, "o": 0.0, "valid": 0.0,
                 "total": 0.0, "blancos": 0.0, "nulos": 0.0}
    for d in crudo_uf.values():
        for k in crudo_nat:
            crudo_nat[k] += d[k]
    crudo_nacional = bloque_crudo(crudo_nat)

    # Por estado
    estados = []
    for uf, i in uf_idx.items():
        total = float(valid_uf[i])
        esc = pct(float(live_total[state_idx == i].sum()), total)
        est = {
            "uf": uf,
            "nombre": NOMBRES_UF.get(uf, uf),
            "escrutado": esc,
            "electores": int(A[state_idx == i].sum()),
            "electores_habilitados": int(H[state_idx == i].sum()),
            "validos_proyectados": int(total),
            "crudo": bloque_crudo(crudo_uf.get(uf, {
                "l": 0.0, "f": 0.0, "o": 0.0, "valid": 0.0,
                "total": 0.0, "blancos": 0.0, "nulos": 0.0})),
            "v1": bloque(v1_l[i], v1_f[i], v1_o[i], total),
        }
        if swing_disponible:
            est["swing"] = bloque(v2_l[i], v2_f[i], v2_o[i], total,
                                  (p5_l[i], p95_l[i]), (p5_f[i], p95_f[i]))
        else:
            est["swing"] = est["v1"]
        estados.append(est)
    estados.sort(key=lambda e: -e["electores"])

    return {
        "actualizado": datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"),
        "swing_disponible": swing_disponible,
        "metodo_principal": "swing" if swing_disponible else "v1",
        "escrutado_pct": escrutado_nat,
        "nacional": {"escrutado": escrutado_nat, "crudo": crudo_nacional,
                     "v1": nat_v1, "swing": nat_sw},
        "estados": estados,
    }


def registrar_historico(resultado):
    """Añade el resultado nacional del swing a los historiales (gráficos PNG)."""
    if not resultado.get("swing_disponible"):
        return
    inicializar_log_salida()
    nat = resultado["nacional"]["swing"]
    with open(ARCHIVO_HISTORICO, mode="a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow([
            resultado["actualizado"], "nacional", "BR", "swing",
            resultado["escrutado_pct"],
            nat["lula"]["votos"], nat["lula"]["pct"],
            nat["flavio"]["votos"], nat["flavio"]["pct"],
            nat["otros"]["votos"], nat["otros"]["pct"],
        ])
    # Historial propio del swing (con intervalos p5–p95) para el fan chart.
    cabecera = ["fecha_hora", "escrutado_pct", "lula_pct", "lula_p5", "lula_p95",
                "flavio_pct", "flavio_p5", "flavio_p95", "otros_pct"]
    nuevo = not os.path.exists(ARCHIVO_HIST_SWING)
    with open(ARCHIVO_HIST_SWING, mode="a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if nuevo:
            w.writerow(cabecera)
        w.writerow([
            resultado["actualizado"], resultado["escrutado_pct"],
            nat["lula"]["pct"], nat["lula"].get("p5", ""), nat["lula"].get("p95", ""),
            nat["flavio"]["pct"], nat["flavio"].get("p5", ""), nat["flavio"].get("p95", ""),
            nat["otros"]["pct"],
        ])


def main():
    resultado = proyectar()
    if resultado is None:
        return
    with open(ARCHIVO_JSON_SWING, "w", encoding="utf-8") as f:
        json.dump(resultado, f, ensure_ascii=False, indent=2)
    registrar_historico(resultado)
    try:
        graficar_desde_historico()
        graficar_simulacion_swing()
    except Exception as e:
        print(f"[!] No se pudo regenerar el gráfico: {e}")
    etiqueta = "SWING" if resultado["swing_disponible"] else "v1 (fallback, sin 2022)"
    print(f"[✓] Proyección {etiqueta} escrita en {ARCHIVO_JSON_SWING} "
          f"(escrutado {resultado['escrutado_pct']:.2f}%)")
    if not resultado["swing_disponible"]:
        print("[i] Genera escrutinio_zonas_2022.csv con: "
              "python scrapingbrasil2022.py --solo-zonas")


if __name__ == "__main__":
    main()
