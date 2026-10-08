# -*- coding: utf-8 -*-
"""
backtest_timestamped.py — Backtest usando la CARGA REAL de datos.

En lugar de muestrear el CSV raspado (que hereda el sesgo de nuestro raspado),
reconstruye la carga nacional real del escrutinio 2026 ordenando las SECCIONES
por la marca de tiempo del TSE `DT_RECEBIMENTO_BU_HOR_TSE` (cuándo el TSE recibió
cada BU/mesa; respaldo: `DT_PRIM_TOT_PARCIAL_HOR_TSE`, primera totalización
parcial). En cada umbral de % escrutado arma una foto en formato "vivo" (por
zona) y corre cada método de proyección, midiendo el error contra el final.

Productos (en <repo>\\plot\\):
  carga_nacional_2026.csv            curva de carga real
  backtest_timestamped.csv / .png    error por método y % escrutado
  backtest_timestamped.json          mejor método por tramo temprano
"""

import os
import io
import sys
import json
import contextlib

import numpy as np
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import rutas_datos as rd
import estilo_plot as ep

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# Reutilizamos los módulos de proyección y las extracciones del backtest.
import backtest as bt

SEC = rd.ruta_dir("secciones")
OUT = os.path.join(rd.REPO, "plot")
os.makedirs(OUT, exist_ok=True)
SNAP = rd.ruta_dir("backtest_timestamped")

CAND_COLS = {"13": "Lula", "22": "Flavio_Bolsonaro", "70": "Augusto_Cury",
             "55": "Ronaldo_Caiado", "30": "Romeu_Zema", "14": "Renan_Santos",
             "16": "Hertz_Dias", "21": "Edmilson_Costa", "27": "Clariana_Barao",
             "29": "Rui_Costa_Pimenta", "35": "Wilson_Grassi", "80": "Samara_Martins"}
HEADER = (["hora_local", "hora_tse", "estado_uf", "codigo_municipio", "municipio",
           "zona_electoral", "secoes_totalizadas", "electores", "votos_totales"]
          + list(CAND_COLS.values()) + ["votos_blancos", "votos_nulos", "numero_pasada"])
UMBRALES = [0.01, 0.02, 0.05, 0.10, 0.15, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70,
            0.80, 0.90, 1.0]

# Nombres de los métodos para mostrar (v1 = Etchenique, v2 = Quiroga, scht = Schteingart)
NOMBRES_METODO = {"crudo": "Conteo crudo", "v1": "Etchenique", "v2": "Quiroga",
                  "scht": "Schteingart", "scht_ng": "Schteingart (sin gate)", "v4": "v4"}


def cargar_secciones():
    d = pd.read_csv(os.path.join(SEC, "secciones_presidente_2026_1t.csv"), dtype=str)
    det = pd.read_csv(os.path.join(SEC, "secciones_detalle_2026.csv"), dtype=str)
    clave = ["uf", "mun", "zona", "secao"]
    cands = [c for c in d.columns if c not in clave + ["branco", "nulo", "total"]]
    for c in cands + ["branco", "nulo"]:
        d[c] = pd.to_numeric(d[c], errors="coerce").fillna(0)
    d["_total"] = d[cands + ["branco", "nulo"]].sum(axis=1)
    det["ts_bu"] = pd.to_datetime(det["recebimento_bu"], format="%d/%m/%Y %H:%M:%S",
                                  errors="coerce")
    det["ts_pp"] = pd.to_datetime(det["prim_parcial"], format="%d/%m/%Y %H:%M:%S",
                                  errors="coerce")
    # Orden de carga: recepción del BU/mesa en el TSE; si falta, primera totalización.
    det["ts"] = det["ts_bu"].fillna(det["ts_pp"])
    det["aptos"] = pd.to_numeric(det["aptos"], errors="coerce").fillna(0)
    m = d.merge(det[clave + ["ts", "aptos"]], on=clave, how="inner")
    m = m.dropna(subset=["ts"]).sort_values("ts").reset_index(drop=True)
    # electores totales por zona (todas las secciones)
    ztot = m.groupby(["uf", "mun", "zona"], as_index=False)["aptos"].sum().rename(
        columns={"aptos": "electores_zona"})
    return m, cands, ztot


def snapshot(m, idx, t, ztot):
    sub = m.iloc[:idx]
    agg = {name: (num, "sum") for num, name in CAND_COLS.items()}
    g = sub.groupby(["uf", "mun", "zona"], as_index=False).agg(
        votos_totales=("_total", "sum"), votos_blancos=("branco", "sum"),
        votos_nulos=("nulo", "sum"), secoes_totalizadas=("secao", "size"), **agg)
    g = g.merge(ztot, on=["uf", "mun", "zona"], how="left")
    g["electores"] = g["electores_zona"].fillna(0)
    g["hora_local"] = t.strftime("%Y-%m-%d %H:%M:%S")
    g["hora_tse"] = t.strftime("%d/%m/%Y %H:%M:%S")
    g["estado_uf"] = g["uf"].str.upper()
    g["codigo_municipio"] = g["mun"]
    g["municipio"] = ""
    g["zona_electoral"] = g["zona"]
    g["numero_pasada"] = 1
    return g[HEADER]


def correr_metodos(path):
    bt.sw.ARCHIVO_VIVO_2026 = path
    out = {}
    with contextlib.redirect_stdout(io.StringIO()):
        try:
            out.update(bt._extract_sw(bt.sw.proyectar())[0])
        except Exception:
            pass
        try:
            out.update(bt._extract_v4(bt.v4.proyectar_v4())[0])
        except Exception:
            pass
        try:
            out.update(bt._extract_scht(bt.sc.proyectar())[0])
        except Exception:
            pass
    out.pop("scht_ng", None)   # casi idéntico a scht; se omite
    out.pop("v4", None)        # el usuario pidió quitarlo
    return out


def main():
    print("[*] Reconstruyendo la carga real (secciones por hora TSE)...")
    m, cands, ztot = cargar_secciones()
    print(f"    secciones con timestamp: {len(m)}")
    total_votos = m["_total"].sum()
    m["cum_votos"] = m["_total"].cumsum()
    m["cum_secciones"] = np.arange(1, len(m) + 1)
    m["pct_votos"] = 100 * m["cum_votos"] / total_votos
    m["pct_secciones"] = 100 * m["cum_secciones"] / len(m)

    # Resultado final nacional
    valid = m[cands].sum().sum()
    final_lula = 100 * m["13"].sum() / valid
    final_flavio = 100 * m["22"].sum() / valid
    print(f"[i] Final nacional: Lula {final_lula:.2f}% | Flávio {final_flavio:.2f}%")

    carga = m[["ts", "pct_secciones", "pct_votos"]].copy()
    carga.to_csv(os.path.join(OUT, "carga_nacional_2026.csv"), index=False)

    filas = []
    for frac in UMBRALES:
        objetivo = frac * total_votos
        idx = int(np.searchsorted(m["cum_votos"].to_numpy(), objetivo, side="left")) + 1
        idx = min(idx, len(m))
        t = m["ts"].iloc[idx - 1]
        esc_votos = 100 * m["cum_votos"].iloc[idx - 1] / total_votos
        snap = snapshot(m, idx, t, ztot)
        path = os.path.join(SNAP, f"snap_{int(frac*1000):04d}.csv")
        snap.to_csv(path, index=False)
        met = correr_metodos(path)
        fila = {"escrutado_pct": esc_votos, "frac": frac, "hora_tse": t}
        for nombre, val in met.items():
            if val:
                fila[nombre] = abs(val[0] - final_lula) + abs(val[1] - final_flavio)
                fila[nombre + "_lula"] = val[0]
                fila[nombre + "_flavio"] = val[1]
        filas.append(fila)
        def _v(k):
            return (f"{fila.get(k+'_lula', float('nan')):.1f}/"
                    f"{fila.get(k+'_flavio', float('nan')):.1f}")
        print(f"    {esc_votos:5.1f}% escrutado  | crudo {_v('crudo')} | "
              f"Etchenique {_v('v1')} | Quiroga {_v('v2')} | Schteingart {_v('scht')}")

    res = pd.DataFrame(filas)
    res.to_csv(os.path.join(OUT, "backtest_timestamped.csv"), index=False)

    metodos = [k for k in bt.METODOS if k in res.columns]
    # mejor método en tramos tempranos (se agrupa por el umbral nominal, no por el % realizado)
    mejor = {}
    medias_tramo = {}
    for corte in (2, 5, 10, 20):
        sub = res[res["frac"] <= corte / 100.0 + 1e-9]
        if len(sub):
            medias = {NOMBRES_METODO.get(k, k): float(sub[k].mean())
                      for k in metodos if sub[k].notna().any()}
            medias_tramo[f"hasta_{corte}pct"] = {k: round(v, 2) for k, v in
                                                 sorted(medias.items(), key=lambda x: x[1])}
            mejor[f"hasta_{corte}pct"] = min(medias, key=medias.get)
    print(f"\n[i] Mejor método por tramo: {mejor}")
    print(f"[i] Error medio por método en cada tramo: {medias_tramo}")
    json.dump({"final_lula": final_lula, "final_flavio": final_flavio,
               "mejor_por_tramo": mejor, "error_medio_por_tramo": medias_tramo},
              open(os.path.join(OUT, "backtest_timestamped.json"), "w"),
              ensure_ascii=False, indent=2)

    # Gráfico: error de los métodos arriba; carga real abajo como barra fina
    m["bin5"] = m["ts"].dt.floor("5min")
    carga_bin = m.groupby("bin5")["_total"].sum()
    carga_bin_pct = 100 * carga_bin / total_votos

    # La carga real dura ~4 h; unas pocas secciones con marca tardía estiran el eje.
    # Recortamos el eje hasta donde ya se cargó el 99.9% de los votos.
    t_ini = m["ts"].min()
    t_999 = m.loc[m["pct_votos"] >= 99.9, "ts"].iloc[0] if (m["pct_votos"] >= 99.9).any() else m["ts"].max()
    print(f"[i] Carga: {t_ini} -> 99.9% en {t_999} | cola hasta {m['ts'].max()} "
          f"({int((m['ts'] > t_999).sum())} secciones)")

    fig = plt.figure(figsize=(10, 8))
    gs = fig.add_gridspec(2, 1, height_ratios=[4, 1], hspace=0.35)

    ax = fig.add_subplot(gs[0])
    for k in metodos:
        ax.plot(res["escrutado_pct"], res[k], "o-", label=NOMBRES_METODO.get(k, k))
    ax.set_xlabel("% de votos escrutados")
    ax.set_ylabel("Error |ΔLula| + |ΔFlávio| (puntos)")
    ax.set_title("Brasil: Error de cada método de proyección de resultado según % escrutado")
    ax.set_xlim(0, 100)
    ax.set_xticks(range(0, 101, 10))
    ax.set_ylim(0, max(10, res[metodos].max().max() * 1.1))
    ax.grid(alpha=0.35, ls="--")
    ax.legend(fontsize=8)

    # Carga real: se dibuja contra el % escrutado (mismo eje que arriba), con las
    # etiquetas del eje x en hora local (17:00, 18:00, ...).
    ax2 = fig.add_subplot(gs[1])
    ts_arr = m["ts"].to_numpy()
    pct_arr = m["pct_votos"].to_numpy()

    def pct_en(t):
        i = np.searchsorted(ts_arr, np.datetime64(pd.Timestamp(t)), side="right")
        return 0.0 if i == 0 else float(pct_arr[i - 1])

    idx = carga_bin.index
    x0 = np.array([pct_en(t) for t in idx])
    x1 = np.array([pct_en(t + pd.Timedelta(minutes=5)) for t in idx])
    ancho = np.clip(x1 - x0, 0.08, None)
    ax2.bar(x0, carga_bin_pct.values, width=ancho, align="edge", color="#2C5FBF")
    ax2.set_xlim(0, 100)
    ax2.set_ylabel("% del total\npor bin de 5 min", fontsize=8)
    ax2.set_title("Brasil: carga real del escrutinio 2026 (eje x = % escrutado; etiquetas = hora TSE)",
                  fontsize=9)
    # Etiquetas cada 10 unidades del eje (% escrutado) con la hora TSE a la que se llegó.
    def t_en(p):
        i = min(int(np.searchsorted(pct_arr, p, side="left")), len(m) - 1)
        return m["ts"].iloc[i]

    ticks = list(range(0, 101, 10))
    labels = [t_en(p).strftime("%H:%M") for p in ticks]
    ax2.set_xticks(ticks)
    ax2.set_xticklabels(labels, fontsize=8)
    ax2.grid(alpha=0.3, axis="y", ls="--")

    fig.tight_layout()
    ep.mpl(fig, "Backtest con la carga real reconstruida a partir de marcas de tiempo del TSE; "
                "error |ΔLula|+|ΔFlávio| por método y % escrutado.")
    fig.savefig(os.path.join(OUT, "backtest_timestamped.png"), dpi=140, bbox_inches="tight")
    plt.close(fig)

    print("\n=== Error por método y % escrutado ===")
    ren = {}
    for k in metodos:
        ren[k] = NOMBRES_METODO.get(k, k)
        ren[k + "_lula"] = NOMBRES_METODO.get(k, k) + "_Lula"
        ren[k + "_flavio"] = NOMBRES_METODO.get(k, k) + "_Flávio"
    print(res.rename(columns=ren).round(2).to_string(index=False))
    print(f"\n[OK] Salidas en {OUT}")


if __name__ == "__main__":
    main()
