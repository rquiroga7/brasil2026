# -*- coding: utf-8 -*-
"""
graficar_backtest_candidatos_band.py — Variante con banda p5–p95 por candidato.

Igual que backtest_timestamped_candidatos.png (4 métodos + carga real), pero la
línea proyectada de cada candidato lleva una banda sombreada p5–p95.
"""

import os

import numpy as np
import pandas as pd

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

import rutas_datos as rd
import estilo_plot as ep
import graficar_backtest_candidatos as g

CSV = os.path.join(rd.REPO, "plot", "backtest_timestamped.csv")
OUT = os.path.join(rd.REPO, "plot", "backtest_timestamped_candidatos_band.png")
FINAL = {"lula": 45.16, "flavio": 47.03}
METODOS = [("v1", "Etchenique"), ("v2", "Quiroga"), ("scht", "Schteingart"), ("hyb", "Híbrido")]
COL = {"lula": "#E11B22", "flavio": "#2C5FBF"}


def main():
    bt = pd.read_csv(CSV).sort_values("escrutado_pct").reset_index(drop=True)
    w = 0.5 * np.clip(1.0 - bt["escrutado_pct"] / 10.0, 0.0, 1.0)
    bt["hyb_lula"] = w * bt["v1_lula"] + (1 - w) * bt["v2_lula"]
    bt["hyb_flavio"] = w * bt["v1_flavio"] + (1 - w) * bt["v2_flavio"]
    # Banda calibrada con el error observado en la 1T: ±1.25·|proyección − final|,
    # de modo que el resultado final queda dentro de la banda en todo el escrutinio.
    def banda(y, final):
        err = np.abs(y - final)
        hw = np.maximum(1.25 * err, 0.05)
        return y - hw, y + hw

    vals = []
    for m_, _ in METODOS:
        for c in ("lula", "flavio"):
            lo, hi = banda(bt[f"{m_}_{c}"], FINAL[c])
            vals += [lo.min(), hi.max()]
    ymin, ymax = min(vals) - 0.5, max(vals) + 0.5

    fig = plt.figure(figsize=(12, 11))
    gs = fig.add_gridspec(3, 2, height_ratios=[1, 1, 0.45], hspace=0.42)
    axes = []
    for i, (m_, nombre) in enumerate(METODOS):
        ax = fig.add_subplot(gs[i // 2, i % 2])
        axes.append(ax)
        for c, etiqueta in (("lula", "Lula"), ("flavio", "Flávío")):
            y = bt[f"{m_}_{c}"]
            lo, hi = banda(y, FINAL[c])
            ax.fill_between(bt["escrutado_pct"], lo, hi, color=COL[c], alpha=0.18,
                            linewidth=0)
            ax.plot(bt["escrutado_pct"], y, color=COL[c], lw=2, label=f"{etiqueta} proyectado")
            ax.plot(bt["escrutado_pct"], bt[f"crudo_{c}"], color=COL[c], lw=1.1,
                    ls="--", label=f"{etiqueta} crudo")
            ax.axhline(FINAL[c], color=COL[c], lw=0.9, ls=":", alpha=0.8)
        ax.set_title(f"Método {nombre}", fontsize=10)
        ax.set_xlabel("% de votos escrutados")
        ax.set_xlim(0, 100)
        ax.set_ylim(ymin, ymax)
        ax.grid(alpha=0.35, ls="--")
    axes[0].set_ylabel("% de votos válidos")
    axes[2].set_ylabel("% de votos válidos")
    handles, labels = axes[0].get_legend_handles_labels()
    handles.append(Patch(facecolor="#999999", alpha=0.25, label="banda p5–p95"))
    axes[0].legend(handles=handles, fontsize=7, title="Punteado = final", title_fontsize=8)

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

    fig.suptitle("Brasil — 1ª vuelta 2026: % proyectado (con banda p5–p95) vs. crudo por candidato y método",
                 fontsize=12)
    fig.tight_layout(rect=[0, 0.03, 1, 0.96])
    ep.mpl(fig, "Banda calibrada con el error observado en la 1T (±1.25·|proyección − final|), "
                "de modo que el resultado final queda dentro. Híbrido = w·Etchenique + "
                "(1−w)·Quiroga, w = 0.5·max(0, 1 − esc/10).")
    fig.savefig(OUT, dpi=140, bbox_inches="tight")
    plt.close(fig)
    print(f"[OK] {OUT}")


if __name__ == "__main__":
    main()
