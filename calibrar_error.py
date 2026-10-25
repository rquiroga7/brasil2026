# -*- coding: utf-8 -*-
"""
calibrar_error.py — Modela el error de proyección (1ª vuelta 2026) en función del
% escrutado, para usarlo como banda de incertidumbre en el dashboard (1T y 2T).

Genera data/error_model_1t.json con, para cada % escrutado:
  cand_mean / cand_p90 / cand_max   error absoluto del % de candidato
  margen_p90 / margen_max           error absoluto del margen (Lula − Flávio)
y un ajuste de ley de potencia como respaldo.
"""

import os
import json

import numpy as np
import pandas as pd

import rutas_datos as rd

CSV = os.path.join(rd.REPO, "plot", "backtest_timestamped.csv")
OUT = os.path.join(rd.REPO, "data", "error_model_1t.json")
FINAL = {"lula": 45.16, "flavio": 47.03}
MET = ["v1", "v2", "scht", "hyb"]


def main():
    bt = pd.read_csv(CSV).sort_values("escrutado_pct").reset_index(drop=True)
    w = np.clip(1 - bt["escrutado_pct"] / 10, 0, 1)
    bt["hyb_lula"] = w * bt["v1_lula"] + (1 - w) * bt["v2_lula"]
    bt["hyb_flavio"] = w * bt["v1_flavio"] + (1 - w) * bt["v2_flavio"]

    puntos = []
    for _, r in bt.iterrows():
        ce = []
        me = []
        for m in MET:
            for c in ("lula", "flavio"):
                ce.append(abs(r[f"{m}_{c}"] - FINAL[c]))
            me.append(abs((r[f"{m}_lula"] - r[f"{m}_flavio"])
                          - (FINAL["lula"] - FINAL["flavio"])))
        ce = np.array(ce)
        me = np.array(me)
        puntos.append({
            "esc": round(float(r["escrutado_pct"]), 2),
            "cand_mean": round(float(ce.mean()), 3),
            "cand_p90": round(float(np.percentile(ce, 90)), 3),
            "cand_max": round(float(ce.max()), 3),
            "margen_p90": round(float(np.percentile(me, 90)), 3),
            "margen_max": round(float(me.max()), 3),
        })

    # respaldo: ley de potencia sobre el error de candidato (pooled)
    xs, ys = [], []
    for _, r in bt.iterrows():
        for m in MET:
            for c in ("lula", "flavio"):
                xs.append(max(r["escrutado_pct"] / 100.0, 0.01))
                ys.append(abs(r[f"{m}_{c}"] - FINAL[c]))
    xs, ys = np.array(xs), np.array(ys)
    b, lna = np.polyfit(np.log(xs), np.log(np.maximum(ys, 1e-3)), 1)
    powerlaw = {"a": round(float(np.exp(lna)), 4), "b": round(float(-b), 4)}

    data = {"puntos": puntos, "powerlaw": powerlaw,
            "nota": "Error observado en el backtest 1T 2026 (métodos v1/v2/scht/híbrido)."}
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"[OK] {OUT}")
    for p in puntos:
        print(f"  {p['esc']:5.1f}%  cand p90 {p['cand_p90']:.2f}  max {p['cand_max']:.2f}  "
              f"margen p90 {p['margen_p90']:.2f}")


if __name__ == "__main__":
    main()
