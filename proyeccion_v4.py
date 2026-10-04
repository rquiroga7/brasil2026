# -*- coding: utf-8 -*-
"""
proyeccion_v4.py — Proyección v4: swing DIFERENCIAL (calibración 2022->2026).

Idea: en vez de un swing uniforme (v2: proj = 2022 + swing_estado, que equivale a
"media_2026 + (2022_zona - media_2022)"), se ajusta por estado una recta
ponderada

        cur_2026 = a + b * pri_2022

sobre las zonas ya escrutadas, y se predice cada zona no escrutada con

        proj(z) = a + b * pri(z).

* b = 1  -> swing uniforme (equivale a v2 con referencia de estado).
* b < 1  -> las diferencias entre zonas se comprimen (regresión a la media).
* b > 1  -> se amplifican.
Así v4 usa las DIFERENCIAS entre zonas y su nivel 2022 para estimar cada zona,
sin depender de la media bruta de la muestra ni de zonas "parecidas" (v3).

Respaldo: regresión del estado -> regresión nacional -> v2 (swing) -> fallback válido.
Salida: datos_proyeccion_v4_2026.json.
"""

import os
import sys
import json
from datetime import datetime

import numpy as np

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from extrapolador10B_rodri import (
    cargar_linea_base_2022,
    cargar_electores_habilitados_2026,
)
from proyeccion_swing import (
    cargar_zonas_2022,
    cargar_vivo_2026,
    construir_live,
    calcular_fallbacks_valid,
    normalizar,
    NOMBRES_UF,
)
from proyeccion_v3 import _bloque, _bloque_crudo, _pct

ARCHIVO_JSON_V4 = "datos_proyeccion_v4_2026.json"
MIN_N = 5          # zonas escrutadas mínimas para ajustar la recta
B_MIN, B_MAX = 0.3, 1.7


def _ajustar(X, Y, W):
    """OLS ponderado por candidato: cur = a + b*pri. Devuelve (a[3], b[3])."""
    a = np.zeros(3)
    b = np.ones(3)
    sw = W.sum()
    if sw <= 0:
        return a, b
    for c in range(3):
        x, y = X[:, c], Y[:, c]
        xm = (W * x).sum() / sw
        ym = (W * y).sum() / sw
        var = (W * (x - xm) ** 2).sum() / sw
        cov = (W * (x - xm) * (y - ym)).sum() / sw
        if var > 1e-9:
            b[c] = min(max(cov / var, B_MIN), B_MAX)
        else:
            b[c] = 1.0
        a[c] = ym - b[c] * xm
    return a, b


def proyectar_v4():
    df_base = cargar_linea_base_2022()
    if df_base is None:
        return None
    df_vivo = cargar_vivo_2026()
    if df_vivo is None or df_vivo.empty:
        print("[-] No hay escrutinio 2026 todavía.")
        return None

    electores_2026 = cargar_electores_habilitados_2026(df_vivo)
    dict22 = cargar_zonas_2022()
    live = construir_live(df_vivo)
    fb_val = calcular_fallbacks_valid(df_vivo)

    # --- zonas escrutadas por estado (2022 y 2026) ---
    est = {}
    for clave, lv in live.items():
        if lv["valid"] <= 0:
            continue
        p = dict22.get(clave)
        if not p or p["valid"] <= 0:
            continue
        uf = lv["uf"] or p["uf"]
        d = est.setdefault(uf, {"pri": [], "cur": [], "w": []})
        d["pri"].append([p["l"] / p["valid"], p["f"] / p["valid"], p["o"] / p["valid"]])
        d["cur"].append([lv["l"] / lv["valid"], lv["f"] / lv["valid"], lv["o"] / lv["valid"]])
        d["w"].append(p["valid"])

    coef = {}
    for uf, d in est.items():
        X = np.array(d["pri"]); Y = np.array(d["cur"]); W = np.array(d["w"], float)
        if len(X) >= MIN_N:
            coef[uf] = _ajustar(X, Y, W)
    # regresión nacional (respaldo)
    if est:
        Xn = np.vstack([np.array(d["pri"]) for d in est.values()])
        Yn = np.vstack([np.array(d["cur"]) for d in est.values()])
        Wn = np.concatenate([np.array(d["w"], float) for d in est.values()])
        coef_nat = _ajustar(Xn, Yn, Wn)
    else:
        coef_nat = (np.zeros(3), np.ones(3))

    # --- arrays por zona base ---
    ufs = sorted(df_base["estado_uf"].unique())
    uf_idx = {u: i for i, u in enumerate(ufs)}
    n = len(df_base)
    A = np.zeros(n); H = np.zeros(n); state_idx = np.zeros(n, int)
    v4sh = np.zeros((n, 3)); live_total = np.zeros(n)

    for i, (_, r) in enumerate(df_base.iterrows()):
        uf = r["estado_uf"]; m = r["codigo_municipio"]; z = r["zona_electoral"]
        clave = (m, z)
        hab22 = int(r["electores_habilitados"])
        try:
            pct22 = float(r["porcentaje_asistencia"]) / 100.0
        except (TypeError, ValueError):
            pct22 = (int(r["electores_asistieron"]) / hab22) if hab22 else 0.0
        hab26 = electores_2026.get(clave, hab22)
        H[i] = hab26; A[i] = hab26 * pct22
        state_idx[i] = uf_idx.get(uf, 0)

        lv = live.get(clave)
        if lv and lv["valid"] > 0:
            v4sh[i] = [lv["l"] / lv["valid"], lv["f"] / lv["valid"], lv["o"] / lv["valid"]]
            live_total[i] = lv["total"]
            continue
        p = dict22.get(clave)
        if p and p["valid"] > 0:
            pri = np.array([p["l"] / p["valid"], p["f"] / p["valid"], p["o"] / p["valid"]])
            a, b = coef.get(uf, coef_nat)
            v4sh[i] = normalizar((a + b * pri)[None, :])[0]
        else:
            if m in fb_val["municipio"]:
                s = fb_val["municipio"][m]
            elif uf in fb_val["estado"]:
                s = fb_val["estado"][uf]
            else:
                s = fb_val["nacional"]
            v4sh[i] = [s["Lula"], s["Flavio"], s["Otros"]]

    # --- agregación ---
    valid_uf = np.zeros(len(ufs)); np.add.at(valid_uf, state_idx, A)
    votes = A[:, None] * v4sh
    V = np.zeros((len(ufs), 3))
    for k in range(3):
        np.add.at(V[:, k], state_idx, votes[:, k])

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
    crudo_nat = {"l": 0.0, "f": 0.0, "o": 0.0, "valid": 0.0,
                 "total": 0.0, "blancos": 0.0, "nulos": 0.0}
    for d in crudo_uf.values():
        for k in crudo_nat:
            crudo_nat[k] += d[k]

    nat_total = float(valid_uf.sum())
    escrutado_nat = _pct(float(live_total.sum()), nat_total)

    estados = []
    for uf, i in uf_idx.items():
        total = float(valid_uf[i])
        esc = _pct(float(live_total[state_idx == i].sum()), total)
        estados.append({
            "uf": uf, "nombre": NOMBRES_UF.get(uf, uf), "escrutado": esc,
            "electores_habilitados": int(H[state_idx == i].sum()),
            "crudo": _bloque_crudo(crudo_uf.get(uf, {
                "l": 0.0, "f": 0.0, "o": 0.0, "valid": 0.0,
                "total": 0.0, "blancos": 0.0, "nulos": 0.0})),
            "v4": _bloque(V[i, 0], V[i, 1], V[i, 2], total),
        })
    estados.sort(key=lambda e: -e["electores_habilitados"])

    return {
        "actualizado": datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"),
        "metodo": "v4",
        "escrutado_pct": escrutado_nat,
        "nacional": {"escrutado": escrutado_nat, "crudo": _bloque_crudo(crudo_nat),
                     "v4": _bloque(V[:, 0].sum(), V[:, 1].sum(), V[:, 2].sum(), nat_total)},
        "estados": estados,
    }


def main():
    resultado = proyectar_v4()
    if resultado is None:
        return
    with open(ARCHIVO_JSON_V4, "w", encoding="utf-8") as f:
        json.dump(resultado, f, ensure_ascii=False, indent=2)
    print(f"[✓] Proyección v4 (swing diferencial) escrita en {ARCHIVO_JSON_V4} "
          f"(escrutado {resultado['escrutado_pct']:.2f}%)")


if __name__ == "__main__":
    main()
