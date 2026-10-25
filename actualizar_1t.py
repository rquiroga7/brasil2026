# -*- coding: utf-8 -*-
"""
actualizar_1t.py — Corrige la serie de la 1ª vuelta en datos_web.json.

La serie publicada se generó cuando el swing se multiplicaba por 0.5 (atenuado).
Aquí se reconstruye la serie nacional del método Quiroga con la versión corregida,
usando el backtest con la carga real (plot/backtest_timestamped.csv), y se
republica en la rama `data`.
"""

import os
import json
import requests
import numpy as np
import pandas as pd

import rutas_datos as rd
import publicar_rodri as p

URL = "https://raw.githubusercontent.com/rquiroga7/brasil2026/data/datos_web.json"
CSV = os.path.join(rd.REPO, "plot", "backtest_timestamped.csv")


def main():
    d = requests.get(URL, timeout=30).json()
    bt = pd.read_csv(CSV).sort_values("escrutado_pct")
    x = bt["escrutado_pct"].to_numpy(float)
    xi = np.arange(1, 101, 1)

    def it(col):
        return np.interp(xi, x, bt[col].to_numpy(float))

    lc, fc = it("crudo_lula"), it("crudo_flavio")
    ls, fs = it("v2_lula"), it("v2_flavio")
    lp, fp = it("v1_lula"), it("v1_flavio")
    idxs = np.clip(np.searchsorted(x, xi), 0, len(x) - 1)
    times = bt["hora_tse"].astype(str).to_numpy()

    def blk(l, f):
        return {"lula": round(float(l), 2), "flavio": round(float(f), 2),
                "otros": round(float(100 - l - f), 2)}

    serie = []
    for k in range(len(xi)):
        serie.append({"t": times[idxs[k]], "escrutado": float(xi[k]),
                      "crudo": blk(lc[k], fc[k]), "swing": blk(ls[k], fs[k]),
                      "proyectado": blk(lp[k], fp[k])})
    d["serie"] = serie
    # nacional.swift corregido al 100% (último punto del backtest)
    d["nacional"]["swing"]["lula"]["pct"] = round(float(bt["v2_lula"].iloc[-1]), 2)
    d["nacional"]["swing"]["flavio"]["pct"] = round(float(bt["v2_flavio"].iloc[-1]), 2)

    archivo = rd.ruta("datos_web.json")
    with open(archivo, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False)
    print(f"[OK] serie 1T corregida ({len(serie)} puntos) -> {archivo}")
    p.publicar_git(archivo, branch="data")


if __name__ == "__main__":
    main()
