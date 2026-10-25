# -*- coding: utf-8 -*-
"""
graficar_backtest_probabilidad.py — Probabilidad de victoria implícita por método
(Etchenique, Quiroga, Schteingart, Híbrido), con la carga real debajo.

Híbrido: w_v1 = max(0, 1 - esc/10); proj = w_v1*v1 + (1-w_v1)*v2.
"""

import os
import json

import numpy as np
import pandas as pd
from scipy.stats import norm

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import rutas_datos as rd
import estilo_plot as ep
import graficar_backtest_candidatos as g

CSV = os.path.join(rd.REPO, "plot", "backtest_timestamped.csv")
MODEL = os.path.join(rd.REPO, "data", "error_model_1t.json")
OUT = os.path.join(rd.REPO, "plot", "backtest_timestamped_probabilidad.png")
METODOS = [("v1", "Etchenique"), ("v2", "Quiroga"), ("scht", "Schteingart"), ("hyb", "Híbrido")]
COL = {"lula": "#E11B22", "flavio": "#2C5FBF"}


def main():
    bt = pd.read_csv(CSV).sort_values("escrutado_pct").reset_index(drop=True)
    w = np.clip(1.0 - bt["escrutado_pct"] / 10.0, 0.0, 1.0)
    bt["hyb_lula"] = w * bt["v1_lula"] + (1 - w) * bt["v2_lula"]
    bt["hyb_flavio"] = w * bt["v1_flavio"] + (1 - w) * bt["v2_flavio"]

    cal = json.load(open(MODEL, encoding="utf-8"))["puntos"]
    xs = np.array([p["esc"] / 100.0 for p in cal])
    ms = np.array([p["margen_p90"] for p in cal])

    fig = plt.figure(figsize=(12, 11))
    gs = fig.add_gridspec(3, 2, height_ratios=[1, 1, 0.45], hspace=0.42)
    axes = []
    for i, (m_, nombre) in enumerate(METODOS):
        ax = fig.add_subplot(gs[i // 2, i % 2])
        axes.append(ax)
        margen = np.interp(bt["escrutado_pct"] / 100.0, xs, ms)
        sd = np.maximum(margen / 1.645, 0.05)
        for c, etiqueta in (("lula", "Lula"), ("flavio", "Flávio")):
            marg = (bt[f"{m_}_lula"] - bt[f"{m_}_flavio"]) if c == "lula" else \
                (bt[f"{m_}_flavio"] - bt[f"{m_}_lula"])
            p = norm.cdf(marg / sd)
            ax.plot(bt["escrutado_pct"], 100 * p, color=COL[c], lw=2, label=f"P({etiqueta})")
        ax.axhline(50, color="#999", lw=0.8, ls="--")
        ax.set_title(f"Método {nombre}", fontsize=10)
        ax.set_xlabel("% de votos escrutados")
        ax.set_xlim(0, 100)
        ax.set_ylim(0, 100)
        ax.grid(alpha=0.35, ls="--")
    axes[0].set_ylabel("Probabilidad de ganar (%)")
    axes[2].set_ylabel("Probabilidad de ganar (%)")
    axes[0].legend(fontsize=8)

    m, total = g.carga_real()
    ts_arr, pct_arr = m["ts"].to_numpy(), m["pct"].to_numpy()

    def pct_en(t):
        i = np.searchsorted(ts_arr, np.datetime64(pd.Timestamp(t)), side="right")
        return 0.0 if i == 0 else float(pct_arr[i - 1])

    carga = m.groupby(m["ts"].dt.floor("5min"))["_total"].sum()
    x0 = np.array([pct_en(t) for t in carga.index])
    x1 = np.array([pct_en(t + pd.Timedelta(minutes=5)) for t in carga.index])
    ancho = np.clip(x1 - x0, 0.08, None)
    ax2 = fig.add_subplot(gs[2, :])
    ax2.bar(x0, 100 * carga.values / total, width=ancho, align="edge", color="#2C5FBF")
    ax2.set_xlim(0, 100)
    ax2.set_ylabel("% del total\npor bin de 5 min", fontsize=8)
    ax2.set_title("Brasil: carga real del escrutinio 2026 (eje x = % escrutado; etiquetas = hora TSE)",
                  fontsize=9)

    def t_en(p):
        i = min(int(np.searchsorted(pct_arr, p, side="left")), len(m) - 1)
        return m["ts"].iloc[i]

    ticks = list(range(0, 101, 10))
    ax2.set_xticks(ticks)
    ax2.set_xticklabels([t_en(p).strftime("%H:%M") for p in ticks], fontsize=8)
    ax2.grid(alpha=0.3, axis="y", ls="--")

    fig.suptitle("Brasil — 1ª vuelta 2026: probabilidad de victoria según método y % escrutado",
                 fontsize=12)
    fig.tight_layout(rect=[0, 0.03, 1, 0.96])
    ep.mpl(fig, "Probabilidad implícita = normal sobre el margen proyectado, con el error p90 "
                "del margen calibrado en la 1T (modelo de error). Híbrido = w·Etchenique + "
                "(1−w)·Quiroga, w = max(0, 1 − esc/10).")
    fig.savefig(OUT, dpi=140, bbox_inches="tight")
    plt.close(fig)
    print(f"[OK] {OUT}")


if __name__ == "__main__":
    main()
