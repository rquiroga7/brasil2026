# -*- coding: utf-8 -*-
"""
proyeccion_v3.py — Proyección v3: imputación por zonas similares (k-NN intra-estado).

Idea: para cada zona NO escrutada, buscar las zonas YA escrutadas del MISMO estado
con perfil 2022 parecido (kernel gaussiano sobre el % de Lula 2022) y tomar un
promedio ponderado de sus shares 2026. Así v3 combina:
  * la estructura 2022 (como v2), y
  * la dinámica 2026 observada (como v1),
quedando entre ambas y más cerca del resultado final.

Cadena de respaldo:
  kNN intra-estado  ->  media del estado  ->  media nacional
  ->  fallback válido (municipio -> estado -> nacional)

Salida: datos_proyeccion_v3_2026.json (nacional + por estado).
"""

import os
import sys
import csv
import json
from datetime import datetime

import numpy as np
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from extrapolador10B_rodri import (
    cargar_linea_base_2022,
    cargar_electores_habilitados_2026,
    calcular_fallbacks_jerarquicos,
)
from proyeccion_swing import (
    cargar_zonas_2022,
    cargar_vivo_2026,
    construir_live,
    calcular_fallbacks_valid,
    normalizar,
    NOMBRES_UF,
)

ARCHIVO_JSON_V3 = "datos_proyeccion_v3_2026.json"
H_BANDA = 0.10      # ancho de banda del kernel sobre el % de Lula 2022
MIN_NEF = 8.0       # nº efectivo de vecinos para confiar plenamente en el kNN


def _pct(parte, total):
    return round(parte / total * 100, 2) if total > 0 else 0.0


def _bloque(l, f, o, total):
    return {"lula": {"votos": int(l), "pct": _pct(l, total)},
            "flavio": {"votos": int(f), "pct": _pct(f, total)},
            "otros": {"votos": int(o), "pct": _pct(o, total)}}


def _bloque_crudo(d):
    return {"lula": {"votos": int(d["l"]), "pct": _pct(d["l"], d["valid"])},
            "flavio": {"votos": int(d["f"]), "pct": _pct(d["f"], d["valid"])},
            "otros": {"votos": int(d["o"]), "pct": _pct(d["o"], d["valid"])},
            "validos": int(d["valid"]), "total": int(d["total"]),
            "blancos": int(d["blancos"]), "nulos": int(d["nulos"])}


def proyectar_v3():
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

    # --- zonas escrutadas por estado (con perfil 2022) ---
    est_counted = {}
    for clave, lv in live.items():
        if lv["valid"] <= 0:
            continue
        p = dict22.get(clave)
        if not p or p["valid"] <= 0:
            continue
        uf = lv["uf"] or p["uf"]
        est_counted.setdefault(uf, []).append(
            (p["l"] / p["valid"], lv["l"] / lv["valid"],
             lv["f"] / lv["valid"], lv["o"] / lv["valid"], p["valid"]))

    def media(rows):
        if not rows:
            return None
        W = np.array([r[4] for r in rows], dtype=float)
        C = np.array([r[1:4] for r in rows], dtype=float)
        return (W[:, None] * C).sum(0) / W.sum()

    est_mean = {uf: media(rows) for uf, rows in est_counted.items()}
    nat_mean = media([r for rows in est_counted.values() for r in rows])

    # --- arrays por zona base ---
    ufs = sorted(df_base["estado_uf"].unique())
    uf_idx = {u: i for i, u in enumerate(ufs)}
    n = len(df_base)
    A = np.zeros(n)
    H = np.zeros(n)
    state_idx = np.zeros(n, int)
    v3sh = np.zeros((n, 3))
    unc = {uf: [] for uf in ufs}

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
        hab26 = electores_2026.get(clave, hab22)
        H[i] = hab26
        A[i] = hab26 * pct22
        state_idx[i] = uf_idx.get(uf, 0)

        lv = live.get(clave)
        if lv and lv["valid"] > 0:
            v3sh[i] = [lv["l"] / lv["valid"], lv["f"] / lv["valid"], lv["o"] / lv["valid"]]
            continue
        p = dict22.get(clave)
        if p and p["valid"] > 0:
            unc[uf].append((i, p["l"] / p["valid"]))
        else:
            if m in fb_val["municipio"]:
                s = fb_val["municipio"][m]
            elif uf in fb_val["estado"]:
                s = fb_val["estado"][uf]
            else:
                s = fb_val["nacional"]
            v3sh[i] = [s["Lula"], s["Flavio"], s["Otros"]]

    # --- predicción kNN intra-estado ---
    for uf in ufs:
        lista = unc[uf]
        if not lista:
            continue
        idxs = [i for i, _ in lista]
        X = np.array([x for _, x in lista], dtype=float)[:, None]
        rows = est_counted.get(uf, [])
        if rows:
            Y = np.array([r[0] for r in rows], dtype=float)[None, :]
            C = np.array([r[1:4] for r in rows], dtype=float)
            W = np.exp(-0.5 * ((Y - X) / H_BANDA) ** 2)
            S = W.sum(1, keepdims=True)
            pred = (W @ C) / np.maximum(S, 1e-12)
            neff = (S[:, 0] ** 2) / np.maximum((W ** 2).sum(1), 1e-12)
            sm = est_mean.get(uf)
            if sm is None:
                sm = nat_mean
            if sm is not None:
                alpha = np.clip(neff / MIN_NEF, 0.0, 1.0)[:, None]
                pred = alpha * pred + (1.0 - alpha) * sm[None, :]
            v3sh[idxs] = normalizar(pred)
        else:
            sm = est_mean.get(uf, nat_mean)
            if sm is None:
                sm = np.array([0.4, 0.4, 0.2])
            v3sh[idxs] = normalizar(np.tile(sm, (len(idxs), 1)))

    # --- agregación ---
    valid_uf = np.zeros(len(ufs))
    np.add.at(valid_uf, state_idx, A)
    votes = A[:, None] * v3sh
    V = np.zeros((len(ufs), 3))
    for k in range(3):
        np.add.at(V[:, k], state_idx, votes[:, k])

    # crudo por estado
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
    live_total = np.zeros(n)
    for i, (_, r) in enumerate(df_base.iterrows()):
        lv = live.get((r["codigo_municipio"], r["zona_electoral"]))
        if lv:
            live_total[i] = lv["total"]
    escrutado_nat = _pct(float(live_total.sum()), nat_total)

    estados = []
    for uf, i in uf_idx.items():
        total = float(valid_uf[i])
        esc = _pct(float(live_total[state_idx == i].sum()), total)
        estados.append({
            "uf": uf,
            "nombre": NOMBRES_UF.get(uf, uf),
            "escrutado": esc,
            "electores_habilitados": int(H[state_idx == i].sum()),
            "crudo": _bloque_crudo(crudo_uf.get(uf, {
                "l": 0.0, "f": 0.0, "o": 0.0, "valid": 0.0,
                "total": 0.0, "blancos": 0.0, "nulos": 0.0})),
            "v3": _bloque(V[i, 0], V[i, 1], V[i, 2], total),
        })
    estados.sort(key=lambda e: -e["electores_habilitados"])

    return {
        "actualizado": datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"),
        "metodo": "v3",
        "escrutado_pct": escrutado_nat,
        "nacional": {"escrutado": escrutado_nat, "crudo": _bloque_crudo(crudo_nat),
                     "v3": _bloque(V[:, 0].sum(), V[:, 1].sum(), V[:, 2].sum(), nat_total)},
        "estados": estados,
    }


def main():
    resultado = proyectar_v3()
    if resultado is None:
        return
    with open(ARCHIVO_JSON_V3, "w", encoding="utf-8") as f:
        json.dump(resultado, f, ensure_ascii=False, indent=2)
    print(f"[✓] Proyección v3 (kNN zonas similares) escrita en {ARCHIVO_JSON_V3} "
          f"(escrutado {resultado['escrutado_pct']:.2f}%)")


if __name__ == "__main__":
    main()
