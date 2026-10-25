# -*- coding: utf-8 -*-
"""
graficar_backtest_candidatos.py — % proyectado vs. crudo por candidato y método
(Etchenique, Quiroga, Schteingart, Híbrido), con la carga real debajo.

Híbrido: w_v1 = max(0, 1 - esc/10); proj = w_v1*v1 + (1-w_v1)*v2.
"""

import os

import numpy as np
import pandas as pd

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import rutas_datos as rd
import estilo_plot as ep

CSV = os.path.join(rd.REPO, "plot", "backtest_timestamped.csv")
OUT = os.path.join(rd.REPO, "plot", "backtest_timestamped_candidatos.png")
FINAL = {"lula": 45.16, "flavio": 47.03}
METODOS = [("v1", "Etchenique"), ("v2", "Quiroga"), ("scht", "Schteingart"), ("hyb", "Híbrido")]
COL = {"lula": "#E11B22", "flavio": "#2C5FBF"}
CLAVE = ["uf", "mun", "zona", "secao"]


def carga_real():
    sec = rd.ruta_dir("secciones")
    d = pd.read_csv(os.path.join(sec, "secciones_presidente_2026_1t.csv"), dtype=str)
    det = pd.read_csv(os.path.join(sec, "secciones_detalle_2026.csv"), dtype=str)
    cands = [c for c in d.columns if c not in CLAVE + ["branco", "nulo", "total"]]
    for c in cands + ["branco", "nulo"]:
        d[c] = pd.to_numeric(d[c], errors="coerce").fillna(0)
    d["_total"] = d[cands + ["branco", "nulo"]].sum(axis=1)
    det["ts"] = pd.to_datetime(det["prim_parcial"], format="%d/%m/%Y %H:%M:%S", errors="coerce")
    m = d.merge(det[CLAVE + ["ts"]], on=CLAVE, how="inner").dropna(subset=["ts"])
    m = m.sort_values("ts").reset_index(drop=True)
    total = m["_total"].sum()
    m["pct"] = 100 * m["_total"].cumsum() / total
    return m, total


def main():
    bt = pd.read_csv(CSV).sort_values("escrutado_pct").reset_index(drop=True)
    w = np.clip(1.0 - bt["escrutado_pct"] / 10.0, 0.0, 1.0)
    bt["hyb_lula"] = w * bt["v1_lula"] + (1 - w) * bt["v2_lula"]
    bt["hyb_flavio"] = w * bt["v1_flavio"] + (1 - w) * bt["v2_flavio"]

    vals = []
    for m_, _ in METODOS:
        for c in ("lula", "flavio"):
            vals += [bt[f"{m_}_{c}"].min(), bt[f"{m_}_{c}"].max()]
    for c in ("lula", "flavio"):
        vals += [bt[f"crudo_{c}"].min(), bt[f"crudo_{c}"].max()]
    ymin, ymax = min(vals) - 1.0, max(vals) + 1.0

    fig = plt.figure(figsize=(12, 11))
    gs = fig.add_gridspec(3, 2, height_ratios=[1, 1, 0.45], hspace=0.42)
    axes = []
    for i, (m_, nombre) in enumerate(METODOS):
        ax = fig.add_subplot(gs[i // 2, i % 2])
        axes.append(ax)
        for c, etiqueta in (("lula", "Lula"), ("flavio", "Flavío")):
            ax.plot(bt["escrutado_pct"], bt[f"{m_}_{c}"], color=COL[c], lw=2,
                    label=f"{etiqueta} proyectado")
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
    axes[0].legend(fontsize=7, title="Punteado = final", title_fontsize=8)

    m, total = carga_real()
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

    fig.suptitle("Brasil — 1ª vuelta 2026: % proyectado vs. crudo por candidato y método",
                 fontsize=12)
    fig.tight_layout(rect=[0, 0.03, 1, 0.96])
    ep.mpl(fig, "Híbrido = w·Etchenique + (1−w)·Quiroga, con w = max(0, 1 − esc/10). "
                "Backtest con la carga real (marcas de tiempo del TSE).")
    fig.savefig(OUT, dpi=140, bbox_inches="tight")
    plt.close(fig)
    print(f"[OK] {OUT}")


if __name__ == "__main__":
    main()
