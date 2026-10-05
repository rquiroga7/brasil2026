# -*- coding: utf-8 -*-
"""
proyeccion_schteingart.py — Método "2026 Schteingart" (modelo de proyeccion.py).

Adapta el modelo logit-swing jerárquico (clase Proyector de proyeccion.py, de
Daniel Schteingart / El Atlas) a NUESTROS datos:
  * referencia 2022 por municipio IBGE (data/elecciones-2022.js)
  * jerarquía IBGE (data/mun-jerarquia.json)
  * escrutinio 2026 en vivo por ZONA (escrutinio_zonas_2026.csv) agregado a municipio
  * mapa TSE->IBGE desde el config del TSE (cdi)

Salida: datos_proyeccion_schteingart_2026.json (nacional + por estado).
"""

import os
import sys
import json
import requests
import numpy as np
from datetime import datetime

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from extrapolador10B_rodri import normalizar_codigo
from proyeccion_swing import cargar_vivo_2026, NOMBRES_UF
from proyeccion import Proyector

RAIZ = os.path.dirname(os.path.abspath(__file__))
ARCHIVO_JSON = "datos_proyeccion_schteingart_2026.json"
TURNO = 1
URL_CONFIG = ("https://resultados.tse.jus.br/oficial/ele2026/6257"
              "/config/mun-e006257-cm.json")

# Candidatos 2026 (número, nombre, partido) en el mismo orden que las columnas del CSV.
CANDS = [
    ("13", "Lula", "PT"), ("22", "Flavio Bolsonaro", "PL"), ("70", "Augusto Cury", "AVANTE"),
    ("55", "Ronaldo Caiado", "PSD"), ("30", "Romeu Zema", "NOVO"), ("14", "Renan Santos", "MISSAO"),
    ("16", "Hertz Dias", "PSTU"), ("21", "Edmilson Costa", "PCB"), ("27", "Clariana Barao", "DC"),
    ("29", "Rui Costa Pimenta", "PCO"), ("35", "Wilson Grassi", "DEMOCRATA"), ("80", "Samara", "UP"),
]
COLS = ["Lula", "Flavio_Bolsonaro", "Augusto_Cury", "Ronaldo_Caiado", "Romeu_Zema", "Renan_Santos",
        "Hertz_Dias", "Edmilson_Costa", "Clariana_Barao", "Rui_Costa_Pimenta", "Wilson_Grassi",
        "Samara_Martins"]


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


def cargar_ref(turno=TURNO):
    txt = open(os.path.join(RAIZ, "data", "elecciones-2022.js"), encoding="utf-8").read()
    for linea in txt.splitlines():
        if linea.startswith(f"window.ELEC['2022-{turno}']"):
            return json.loads(linea.split(" = ", 1)[1].rstrip(";"))
    return None


def construir_modelo():
    ref = cargar_ref()
    jer = json.load(open(os.path.join(RAIZ, "data", "mun-jerarquia.json"), encoding="utf-8"))
    jer["ZZ"] = ["EXT", "ZZ", "ZZ", "ZZ"]
    B = 3 if TURNO == 1 else 2
    blo = [0 if c["n"] == "13" else 1 if c["n"] == "22" else 2 for c in ref["cands"]]
    unidades = [k for k in ref["mun"] if k in jer] + (["ZZ"] if "ZZ" in ref.get("uf", {}) else [])
    base = np.zeros((len(unidades), B))
    for i, k in enumerate(unidades):
        v = ref["uf"]["ZZ"]["v"] if k == "ZZ" else ref["mun"][k][0]
        for j, x in enumerate(v):
            base[i, min(blo[j], B - 1)] += x
    return Proyector(unidades, jer, base, base.sum(1))


def cargar_mapa_tse_ibge():
    cache = os.path.join(RAIZ, "data", "tse_ibge.json")
    if os.path.exists(cache):
        try:
            return json.load(open(cache, encoding="utf-8"))
        except (ValueError, OSError):
            pass
    H = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
    cfg = requests.get(URL_CONFIG, headers=H, timeout=30).json()
    mapa = {}
    for a in cfg.get("abr", []):
        for mu in a.get("mu", []):
            ibge = str(mu.get("cdi") or "")
            if ibge:
                mapa[normalizar_codigo(mu.get("cd"))] = ibge
    json.dump(mapa, open(cache, "w", encoding="utf-8"))
    return mapa


ESTADOS = ["ac", "al", "am", "ap", "ba", "ce", "df", "es", "go", "ma", "mg", "ms", "mt",
           "pa", "pb", "pe", "pi", "pr", "rj", "rn", "ro", "rr", "rs", "sc", "se", "sp", "to"]


def cargar_secciones_total():
    """Total de secciones por municipio (TSE) desde el avance -ab.json. Se cachea."""
    cache = os.path.join(RAIZ, "data", "secciones_total_2026.json")
    if os.path.exists(cache):
        try:
            return json.load(open(cache, encoding="utf-8"))
        except (ValueError, OSError):
            pass
    H = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
    out = {}
    for uf in ESTADOS:
        try:
            j = requests.get(f"{URL_CONFIG.rsplit('/config/', 1)[0]}/dados/{uf}/{uf}-e006257-ab.json",
                             headers=H, timeout=20).json()
        except Exception:
            continue
        for ab in j.get("abr", []):
            cd = normalizar_codigo(ab.get("cdabr"))
            ts = float(ab.get("s", {}).get("ts") or 0)
            if ts > 0:
                out[cd] = ts
    json.dump(out, open(cache, "w", encoding="utf-8"))
    return out


def proyectar():
    modelo = construir_modelo()
    tse2ibge = cargar_mapa_tse_ibge()
    df = cargar_vivo_2026()
    if df is None or df.empty:
        print("[-] No hay escrutinio 2026 todavía.")
        return None

    U = len(modelo.keys)
    K = len(CANDS)
    idx = {k: i for i, k in enumerate(modelo.keys)}

    # --- agregar zonas -> municipio IBGE ---
    agg = {}
    crudo_uf = {}
    for _, r in df.iterrows():
        uf = str(r.get("estado_uf") or "").upper()
        tse = normalizar_codigo(r["codigo_municipio"])
        ibge = "ZZ" if uf == "ZZ" else tse2ibge.get(tse)
        tot = float(r.get("votos_totales") or 0)
        nu = float(r.get("votos_nulos") or 0)
        br = float(r.get("votos_blancos") or 0)
        valid = max(0.0, tot - nu - br)
        l = float(r.get("Lula") or 0)
        fl = float(r.get("Flavio_Bolsonaro") or 0)
        # crudo por estado
        cd = crudo_uf.setdefault(uf, {"l": 0.0, "f": 0.0, "o": 0.0, "valid": 0.0,
                                      "total": 0.0, "blancos": 0.0, "nulos": 0.0})
        cd["l"] += l; cd["f"] += fl; cd["o"] += max(0.0, valid - l - fl)
        cd["valid"] += valid; cd["total"] += tot; cd["blancos"] += br; cd["nulos"] += nu
        if ibge is None:
            continue
        d = agg.setdefault(ibge, {"v": [0.0] * K, "valid": 0.0, "bn": 0.0, "apt": 0.0,
                                      "com": 0.0, "st": 0.0, "tse": tse})
        for j, c in enumerate(COLS):
            d["v"][j] += float(r.get(c) or 0)
        d["valid"] += valid; d["bn"] += nu + br; d["com"] += tot
        d["apt"] += float(r.get("electores") or 0)
        d["st"] += float(r.get("secoes_totalizadas") or 0)

    # --- construir obs_votos y obs_f (f = secciones contadas / totales) ---
    O = np.zeros((U, K))
    f = np.zeros(U)
    extra = np.zeros(K)
    secciones = cargar_secciones_total()
    for k, d in agg.items():
        i = idx.get(k)
        if i is None:
            extra += np.asarray(d["v"][:K])
            continue
        O[i, :K] = d["v"][:K]
        ts = secciones.get(d["tse"], 0.0)
        f[i] = min(1.0, d["st"] / ts) if ts > 0 else 0.0

    bloque_de = np.array([0 if n == "13" else 1 if n == "22" else 2 for n, _, _ in CANDS])
    res = modelo.proyectar(O, f, bloque_de, extra)
    if res is None:
        print("[-] Schteingart: pocos datos para proyectar.")
        return None

    final = res["final"]  # [U, K]
    tot = final.sum(0)
    # --- por estado ---
    est_votos = {}
    for i, k in enumerate(modelo.keys):
        uf = str(modelo.uf[i])
        est_votos.setdefault(uf, np.zeros(K))
        est_votos[uf] += final[i]

    crudo_nat = {"l": 0.0, "f": 0.0, "o": 0.0, "valid": 0.0,
                 "total": 0.0, "blancos": 0.0, "nulos": 0.0}
    for d in crudo_uf.values():
        for key in crudo_nat:
            crudo_nat[key] += d[key]

    # electores habilitados 2026 por estado
    elec_uf = {}
    for _, r in df.iterrows():
        uf = str(r.get("estado_uf") or "").upper()
        elec_uf[uf] = elec_uf.get(uf, 0.0) + float(r.get("electores") or 0)

    escrutado_nat = round(res["contado"] * 100, 2)
    # Gate del modelo original (ProyeccionEnVivo): solo se muestra la proyección
    # con >=2% de votos esperados contados y >=20 estados con datos; si no, se
    # muestra el conteo crudo.
    ok = (res["contado"] >= 0.02) and (res["n_uf"] >= 20)

    estados = []
    for uf, vec in est_votos.items():
        if uf == "ZZ":
            nombre = "Exterior"
        else:
            nombre = NOMBRES_UF.get(uf, uf)
        total = float(vec.sum())
        cd = crudo_uf.get(uf, {"l": 0.0, "f": 0.0, "o": 0.0, "valid": 0.0,
                               "total": 0.0, "blancos": 0.0, "nulos": 0.0})
        esc = _pct(cd["total"], max(total, 1.0))  # aproximado
        crudo_blk = _bloque_crudo(cd)
        if ok:
            scht_blk = _bloque(vec[0], vec[1], vec[2:].sum(), total)
        else:
            scht_blk = {"lula": crudo_blk["lula"], "flavio": crudo_blk["flavio"],
                        "otros": crudo_blk["otros"]}
        estados.append({
            "uf": uf, "nombre": nombre, "escrutado": esc,
            "electores_habilitados": int(elec_uf.get(uf, 0)),
            "crudo": crudo_blk,
            "schteingart": scht_blk,
        })
    estados.sort(key=lambda e: -e["electores_habilitados"])

    crudo_nac_blk = _bloque_crudo(crudo_nat)
    if ok:
        nac_scht = _bloque(tot[0], tot[1], tot[2:].sum(), tot.sum())
    else:
        nac_scht = {"lula": crudo_nac_blk["lula"], "flavio": crudo_nac_blk["flavio"],
                    "otros": crudo_nac_blk["otros"]}

    return {
        "actualizado": datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"),
        "metodo": "schteingart",
        "ok": bool(ok),
        "n_uf": int(res["n_uf"]),
        "escrutado_pct": escrutado_nat,
        "nacional": {"escrutado": escrutado_nat, "crudo": crudo_nac_blk,
                     "schteingart": nac_scht},
        "estados": estados,
    }


def main():
    resultado = proyectar()
    if resultado is None:
        return
    with open(ARCHIVO_JSON, "w", encoding="utf-8") as fh:
        json.dump(resultado, fh, ensure_ascii=False, indent=2)
    print(f"[✓] Proyección 2026 Schteingart escrita en {ARCHIVO_JSON} "
          f"(escrutado {resultado['escrutado_pct']:.2f}%)")


if __name__ == "__main__":
    main()
