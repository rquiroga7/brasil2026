# -*- coding: utf-8 -*-
"""
proyeccion_v4.py — Proyección v4: swing uniforme POR ESTADO.

Para cada zona no escrutada: proj = % 2022 de la zona + swing del estado
(media de (cur − pri) de las zonas ya escrutadas del estado, ponderada por
tamaño × completitud). Si el estado tiene pocos datos, usa el swing nacional.

Salida: datos_proyeccion_v4_2026.json (nacional + por estado).
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
    normalizar_codigo,
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

import rutas_datos as rd

ARCHIVO_JSON_V4 = rd.ruta("datos_proyeccion_v4_2026.json")
MIN_N = 5   # zonas escrutadas mínimas para usar el swing propio del estado
T_SWING = 0.30   # % escrutado del estado a partir del cual manda su swing (antes: nacional)

ESTADOS = ["ac", "al", "am", "ap", "ba", "ce", "df", "es", "go", "ma", "mg", "ms", "mt",
           "pa", "pb", "pe", "pi", "pr", "rj", "rn", "ro", "rr", "rs", "sc", "se", "sp", "to"]
URL_BU = "https://resultados.tse.jus.br/oficial/ele2026/arquivo-urna/3220/config"


def cargar_secciones_zonas():
    """Total de secciones por zona (TSE) desde el config de urnas. Se cachea."""
    cache = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "data", "secciones_zonas_2026.json")
    if os.path.exists(cache):
        try:
            return json.load(open(cache, encoding="utf-8"))
        except (ValueError, OSError):
            pass
    import requests
    H = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
    out = {}
    for uf in ESTADOS:
        try:
            cfg = requests.get(f"{URL_BU}/{uf}/{uf}-p003220-cs.json", headers=H, timeout=20).json()
        except Exception:
            continue
        for a in cfg.get("abr", []):
            for mu in a.get("mu", []):
                for zon in mu.get("zon", []):
                    out[f'{normalizar_codigo(mu["cd"])}|{normalizar_codigo(zon["cd"])}'] = \
                        len(zon.get("sec", []))
    try:
        json.dump(out, open(cache, "w", encoding="utf-8"))
    except OSError:
        pass
    return out


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
    sec_zonas = cargar_secciones_zonas()

    # --- swing por estado (ponderado por tamaño 2022 x completitud) ---
    acc = {}   # uf -> [suma_w, suma_w*dl, suma_w*df, suma_w*do, n]
    nat = [0.0, 0.0, 0.0, 0.0, 0]
    for clave, lv in live.items():
        if lv["valid"] <= 0:
            continue
        p = dict22.get(clave)
        if not p or p["valid"] <= 0:
            continue
        uf = lv["uf"] or p["uf"]
        ts = sec_zonas.get(f"{clave[0]}|{clave[1]}", 0.0)
        st = lv.get("st", 0.0)
        comp = min(1.0, st / ts) if ts > 0 else min(1.0, lv["valid"] / p["valid"])
        w = p["valid"] * comp
        pri = [p["l"] / p["valid"], p["f"] / p["valid"], p["o"] / p["valid"]]
        cur = [lv["l"] / lv["valid"], lv["f"] / lv["valid"], lv["o"] / lv["valid"]]
        d = acc.setdefault(uf, [0.0, 0.0, 0.0, 0.0, 0])
        for c in range(3):
            d[1 + c] += w * (cur[c] - pri[c])
        d[0] += w
        d[4] += 1
        for c in range(3):
            nat[1 + c] += w * (cur[c] - pri[c])
        nat[0] += w
        nat[4] += 1

    swing_uf = {}
    for uf, d in acc.items():
        if d[0] > 0 and d[4] >= MIN_N:
            swing_uf[uf] = np.array([d[1] / d[0], d[2] / d[0], d[3] / d[0]])
    nat_swing = np.array([nat[1] / nat[0], nat[2] / nat[0], nat[3] / nat[0]]) if nat[0] > 0 else np.zeros(3)

    # --- arrays por zona base ---
    ufs = sorted(df_base["estado_uf"].unique())
    uf_idx = {u: i for i, u in enumerate(ufs)}

    # escrutado por estado = votos contados / votos esperados (umbral del swing)
    A_state = np.zeros(len(ufs))
    for _, r in df_base.iterrows():
        ii = uf_idx.get(r["estado_uf"], 0)
        hab22 = int(r["electores_habilitados"])
        try:
            pct22 = float(r["porcentaje_asistencia"]) / 100.0
        except (TypeError, ValueError):
            pct22 = (int(r["electores_asistieron"]) / hab22) if hab22 else 0.0
        A_state[ii] += electores_2026.get((r["codigo_municipio"], r["zona_electoral"]), hab22) * pct22
    counted_state = np.zeros(len(ufs))
    for lv in live.values():
        uf = lv["uf"]
        if uf in uf_idx:
            counted_state[uf_idx[uf]] += lv["total"]
    esc_s = counted_state / np.maximum(A_state, 1.0)

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
            if uf in swing_uf:
                # encoge el swing del estado hacia el nacional según su % escrutado
                lam = min(1.0, esc_s[state_idx[i]] / T_SWING)
                sw = lam * swing_uf[uf] + (1.0 - lam) * nat_swing
            else:
                sw = nat_swing
            v4sh[i] = normalizar((pri + sw)[None, :])[0]
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
    print(f"[✓] Proyección v4 (swing por estado) escrita en {ARCHIVO_JSON_V4} "
          f"(escrutado {resultado['escrutado_pct']:.2f}%)")


if __name__ == "__main__":
    main()
