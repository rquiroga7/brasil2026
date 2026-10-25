# -*- coding: utf-8 -*-
"""
proyeccion_2t.py — Proyección de la 2ª vuelta 2026 (Lula vs Flávio).

Base del swing: los resultados de la 1ª vuelta 2026 (no 2022). Para cada zona,
el cambio (swing) se mide entre la 1T y la 2T ya escrutada y se extrapola a lo
que falta, con dos métodos:

  * Quiroga: swing logit de la participación relativa Lula/Flávio por zona,
    estimado por estado y encogido al nacional.
  * Schteingart: modelo logit-swing jerárquico (Proyector de proyeccion.py) con
    base municipal de la 1T.

Salida: datos_web_2t.json (mismo esquema que datos_web.json) + historico_2t.csv.
"""

import os
import sys
import json
from datetime import datetime

import numpy as np
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import rutas_datos as rd
from proyeccion import Proyector
from proyeccion_swing import NOMBRES_UF

BASE = rd.ruta("escrutinio_zonas_2026.csv")        # 1ª vuelta (base)
LIVE = rd.ruta("escrutinio_zonas_2026_2t.csv")     # 2ª vuelta (en vivo)
OUT = rd.ruta("datos_web_2t.json")
HIST = rd.ruta("historico_2t.json")
CAL = os.path.join(rd.REPO, "data", "error_model_1t.json")
RAIZ = rd.REPO
ESTADOS = ["ac", "al", "am", "ap", "ba", "ce", "df", "es", "go", "ma", "mg", "ms", "mt",
           "pa", "pb", "pe", "pi", "pr", "rj", "rn", "ro", "rr", "rs", "sc", "se", "sp",
           "to", "zz"]


def logit(p):
    p = np.clip(np.asarray(p, dtype=float), 1e-3, 1 - 1e-3)
    return np.log(p / (1 - p))


def expit(x):
    x = np.asarray(x, dtype=float)
    return 1.0 / (1.0 + np.exp(-x))


_MODELO = None


def modelo_error():
    """Tabla de error calibrada con el backtest 1T (data/error_model_1t.json)."""
    global _MODELO
    if _MODELO is None:
        try:
            d = json.load(open(CAL, encoding="utf-8"))
            xs = [p["esc"] / 100.0 for p in d["puntos"]]
            cs = [p["cand_p90"] for p in d["puntos"]]
            ms = [p["margen_p90"] for p in d["puntos"]]
            _MODELO = (xs, cs, ms)
        except (OSError, ValueError, KeyError):
            _MODELO = ([0.01, 1.0], [2.5, 0.03], [4.0, 0.01])
    return _MODELO


def cargar(path):
    if not os.path.exists(path):
        return None
    try:
        df = pd.read_csv(path, dtype={"codigo_municipio": str, "zona_electoral": str})
    except (pd.errors.ParserError, OSError, ValueError):
        return None
    df["uf"] = df["estado_uf"].astype(str).str.upper()
    df["mun"] = df["codigo_municipio"].astype(str).str.zfill(5)
    df["zona"] = df["zona_electoral"].astype(str).str.zfill(4)
    for c in ["secoes_totalizadas", "electores", "votos_totales", "votos_blancos",
              "votos_nulos", "Lula", "Flavio_Bolsonaro"]:
        df[c] = pd.to_numeric(df.get(c, 0), errors="coerce").fillna(0)
    return df


def tse_a_ibge():
    with open(os.path.join(RAIZ, "data", "tse_ibge.json"), encoding="utf-8") as f:
        return {int(k): str(v) for k, v in json.load(f).items()}


def bloque(l, f, valid):
    l, f = float(l), float(f)
    return {"lula": {"votos": int(l), "pct": round(100 * l / valid, 2) if valid else 0.0},
            "flavio": {"votos": int(f), "pct": round(100 * f / valid, 2) if valid else 0.0},
            "otros": {"votos": 0, "pct": 0.0}}


def crudo_bloque(l, f, valid, total, brancos, nulos):
    b = bloque(l, f, valid)
    b.update({"validos": int(valid), "total": int(total),
              "blancos": int(brancos), "nulos": int(nulos)})
    return b


def zonas_estado(base, live):
    """Agrega 1T base y 2T live por zona, con totales de secciones de la 1T."""
    b = base.groupby(["uf", "mun", "zona"], as_index=False).agg(
        l1=("Lula", "sum"), f1=("Flavio_Bolsonaro", "sum"),
        val1=("votos_totales", "sum"), br1=("votos_blancos", "sum"),
        nu1=("votos_nulos", "sum"), sec_tot=("secoes_totalizadas", "sum"),
        aptos=("electores", "sum"))
    b["val1"] = b["val1"] - b["br1"] - b["nu1"]
    if live is None or live.empty:
        lv = pd.DataFrame(columns=["uf", "mun", "zona", "l2", "f2", "sec_cnt", "br2", "nu2"])
    else:
        lv = live.groupby(["uf", "mun", "zona"], as_index=False).agg(
            l2=("Lula", "sum"), f2=("Flavio_Bolsonaro", "sum"),
            sec_cnt=("secoes_totalizadas", "sum"),
            br2=("votos_blancos", "sum"), nu2=("votos_nulos", "sum"))
    m = b.merge(lv, on=["uf", "mun", "zona"], how="left")
    for c in ("l2", "f2", "sec_cnt", "br2", "nu2"):
        m[c] = m[c].fillna(0)
    m["f"] = np.clip(m["sec_cnt"] / m["sec_tot"].replace(0, np.nan), 0, 1).fillna(0)
    return m


def quiroga(m):
    """Swing 1T->2T de la razón Lula/Flávio, por estado, encogido al nacional."""
    cnt = m["f"] > 0
    q1 = m["l1"] / (m["l1"] + m["f1"]).replace(0, np.nan)
    q2 = m["l2"] / (m["l2"] + m["f2"]).replace(0, np.nan)
    sw = np.where(cnt, logit(q2) - logit(q1), np.nan)
    m = m.assign(sw=sw, w=np.where(cnt, m["l2"] + m["f2"], 0.0))
    nac = np.nansum(m["sw"] * m["w"]) / max(m["w"].sum(), 1)
    est = (m.groupby("uf").apply(lambda g: np.nansum(g["sw"] * g["w"]) /
                                  max(g["w"].sum(), 1) if g["w"].sum() else np.nan)
           .to_dict())
    # encoger el swing estatal al nacional si hay pocos votos contados
    w_uf = m.groupby("uf")["w"].sum().to_dict()
    k = 20000.0
    sw_uf = {u: (w_uf.get(u, 0) * est.get(u, np.nan) + k * nac) / (w_uf.get(u, 0) + k)
             if not np.isnan(est.get(u, np.nan)) else nac for u in m["uf"].unique()}
    m["sw_use"] = m["uf"].map(sw_uf).fillna(nac)
    # votos válidos esperados 2T: factor de participación observado
    factor = m.loc[cnt, "l2"].sum() + m.loc[cnt, "f2"].sum()
    factor = factor / max(m.loc[cnt, "val1"].sum(), 1) if cnt.any() else 0.0
    e = m["val1"] * (factor if factor > 0 else 1.0)
    q2p = expit(logit(q1) + m["sw_use"])
    l2p = np.where(cnt, m["l2"], e * q2p)
    f2p = np.where(cnt, m["f2"], e * (1 - q2p))
    # v1 (estratificada): media de lo contado por estado; fallback al base 1T
    est_q2 = {}
    for uf, g in m.groupby("uf"):
        gg = g[g["f"] > 0]
        tot = gg["l2"].sum() + gg["f2"].sum()
        if tot > 0:
            est_q2[uf] = float(gg["l2"].sum() / tot)
    q2v1 = m["uf"].map(est_q2).astype(float).to_numpy()
    cnta = np.asarray(cnt)
    q2v1 = np.where(cnta, np.asarray(q2, dtype=float), q2v1)
    q2v1 = np.where(np.isnan(q2v1), np.asarray(q1, dtype=float), q2v1)
    en = np.asarray(e, dtype=float)
    l1p = np.where(cnta, m["l2"].to_numpy(), en * q2v1)
    f1p = np.where(cnta, m["f2"].to_numpy(), en * (1 - q2v1))
    return (float(np.nansum(l2p)), float(np.nansum(f2p)),
            float(np.nansum(l1p)), float(np.nansum(f1p)))


def schteingart(base, live):
    """Proyector jerárquico con base municipal de la 1ª vuelta 2026."""
    t2i = tse_a_ibge()
    jer = json.load(open(os.path.join(RAIZ, "data", "mun-jerarquia.json"), encoding="utf-8"))
    jer["ZZ"] = ["EXT", "ZZ", "ZZ", "ZZ"]

    def unidad(uf, mun):
        return "ZZ" if uf == "ZZ" else t2i.get(int(mun))

    b = base.copy()
    b["ibge"] = [unidad(u, m) for u, m in zip(b["uf"], b["mun"])]
    lv = live.copy()
    lv["ibge"] = [unidad(u, m) for u, m in zip(lv["uf"], lv["mun"])]
    bg = b.groupby("ibge", as_index=False).agg(l1=("Lula", "sum"), f1=("Flavio_Bolsonaro", "sum"),
                                               val1=("votos_totales", "sum"),
                                               br=("votos_blancos", "sum"),
                                               nu=("votos_nulos", "sum"),
                                               sec_tot=("secoes_totalizadas", "sum"))
    bg["val1"] = bg["val1"] - bg["br"] - bg["nu"]
    lg = lv.groupby("ibge", as_index=False).agg(l2=("Lula", "sum"), f2=("Flavio_Bolsonaro", "sum"),
                                               sec_cnt=("secoes_totalizadas", "sum"))
    m = bg.merge(lg, on="ibge", how="left")
    for c in ("l2", "f2", "sec_cnt"):
        m[c] = m[c].fillna(0)

    unidades = [k for k in m["ibge"] if k and k in jer]
    m = m[m["ibge"].isin(unidades)]
    idx = {k: i for i, k in enumerate(unidades)}
    U = len(unidades)
    base_b = np.zeros((U, 2))
    base_val = np.zeros(U)
    O = np.zeros((U, 2))
    f = np.zeros(U)
    for _, r in m.iterrows():
        i = idx[r["ibge"]]
        base_b[i] = [r["l1"], r["f1"]]
        base_val[i] = r["val1"]
        O[i] = [r["l2"], r["f2"]]
        f[i] = min(1.0, r["sec_cnt"] / r["sec_tot"]) if r["sec_tot"] > 0 else 0.0
    modelo = Proyector(unidades, jer, base_b, np.maximum(base_val, 1.0))
    res = modelo.proyectar(O, f, np.array([0, 1]))
    if res is None:
        return None
    tot = res["final"].sum(0)
    return float(tot[0]), float(tot[1]), float(res["contado"])


def payload_ambito(base, live, nombre="BR"):
    m = zonas_estado(base, live)
    l_cnt, f_cnt = m["l2"].sum(), m["f2"].sum()
    val_cnt = l_cnt + f_cnt
    br, nu = m["br2"].sum(), m["nu2"].sum()
    total_cnt = val_cnt + br + nu
    ql, qf, l_v1, f_v1 = quiroga(m)
    scht = schteingart(base, live) if (live is not None and not live.empty) else None
    esc = 100 * m["sec_cnt"].sum() / max(m["sec_tot"].sum(), 1)
    b_swing = bloque(ql, qf, ql + qf)
    b_v1 = bloque(l_v1, f_v1, l_v1 + f_v1)
    b_scht = bloque(scht[0], scht[1], scht[0] + scht[1]) if scht else dict(b_swing)
    w = 0.5 * max(0.0, 1.0 - min(esc, 100) / 10.0)
    b_hyb = bloque(w * l_v1 + (1 - w) * ql, w * f_v1 + (1 - w) * qf,
                   w * (l_v1 + f_v1) + (1 - w) * (ql + qf))
    out = {
        "escrutado": round(esc, 2),
        "crudo": crudo_bloque(l_cnt, f_cnt, val_cnt, total_cnt, br, nu),
        "swing": b_swing,
        "v1": b_v1,
        "hybrid": b_hyb,
        "schteingart": b_scht,
    }
    out["scht_ng"] = b_scht
    # banda de incertidumbre calibrada con el error observado en la 1T
    xs, cs, ms = modelo_error()
    x = min(max(esc, 0.0), 100.0) / 100.0
    hw = max(float(np.interp(x, xs, cs)), 0.05 * (1 - x))
    mrg = float(np.interp(x, xs, ms))
    for blk in (out["crudo"], out["swing"], out["v1"], out["hybrid"], out["schteingart"]):
        blk["margen_p90"] = round(mrg, 2)
        for c in ("lula", "flavio"):
            p = blk[c]["pct"]
            blk[c]["p5"] = round(max(0.0, p - hw), 2)
            blk[c]["p95"] = round(min(100.0, p + hw), 2)
    return out, m


def main():
    base = cargar(BASE)
    if base is None:
        print("[x] Falta la base de la 1ª vuelta (escrutinio_zonas_2026.csv).")
        sys.exit(1)
    live = cargar(LIVE)

    nac, m = payload_ambito(base, live, "BR")
    estados = []
    for uf in ESTADOS:
        bu = base[base["uf"] == uf.upper()]
        lu = live[live["uf"] == uf.upper()] if live is not None else None
        if bu.empty:
            continue
        eu, _ = payload_ambito(bu, lu, uf.upper())
        val1 = (bu["votos_totales"].sum() - bu["votos_blancos"].sum()
                - bu["votos_nulos"].sum())
        l1, f1 = bu["Lula"].sum(), bu["Flavio_Bolsonaro"].sum()
        blk1 = {"lula": {"pct": round(100 * l1 / val1, 2) if val1 else 0.0},
                "flavio": {"pct": round(100 * f1 / val1, 2) if val1 else 0.0},
                "otros": {"pct": round(100 * (val1 - l1 - f1) / val1, 2) if val1 else 0.0}}
        estados.append({
            "uf": uf.upper(), "nombre": "Exterior" if uf == "zz" else NOMBRES_UF.get(uf.upper(), uf.upper()),
            "escrutado": eu["escrutado"],
            "electores": int(bu["electores"].sum()),
            "electores_habilitados": int(bu["electores"].sum()),
            "validos_proyectados": int(eu["swing"]["lula"]["votos"] + eu["swing"]["flavio"]["votos"]),
            "1t": blk1,
            "crudo": eu["crudo"], "swing": eu["swing"], "v1": eu["v1"],
            "hybrid": eu["hybrid"], "schteingart": eu["schteingart"],
            "scht_ng": eu["scht_ng"],
        })

    serie = []
    if os.path.exists(HIST):
        serie = json.load(open(HIST, encoding="utf-8"))

    def _punto(b, con_votos=False):
        p = {"lula": b["lula"]["pct"], "flavio": b["flavio"]["pct"],
             "otros": b.get("otros", {}).get("pct", 0.0)}
        if con_votos:
            p.update({"lula_votos": b["lula"]["votos"], "flavio_votos": b["flavio"]["votos"],
                      "otros_votos": b.get("otros", {}).get("votos", 0)})
        return p

    punto = {"t": datetime.now().astimezone().isoformat(),
             "escrutado": nac["escrutado"],
             "margen_p90": round(float(np.interp(nac["escrutado"] / 100.0, modelo_error()[0],
                                                  modelo_error()[2])), 2),
             "crudo": _punto(nac["crudo"], True),
             "swing": _punto(nac["swing"]),
             "v1": _punto(nac["v1"]),
             "hybrid": _punto(nac["hybrid"]),
             "proyectado": _punto(nac["schteingart"])}
    if not serie or serie[-1].get("escrutado") != punto["escrutado"]:
        serie.append(punto)
    json.dump(serie, open(HIST, "w", encoding="utf-8"), ensure_ascii=False)

    det = tipo_pct = 0
    total_zonas = int(len(m))
    directo = int((m["f"] > 0).sum())
    payload = {
        "actualizado": datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"),
        "escrutado_pct": nac["escrutado"],
        "estado_control": "",
        "swing_disponible": True,
        "metodo_principal": "swing",
        "crudo": nac["crudo"],
        "zonas": {"directo": directo, "municipio": 0, "estado": 0, "nacional": 0,
                  "total": total_zonas,
                  "pct_superiores": round(100 * directo / max(total_zonas, 1), 1)},
        "nacional": nac,
        "estados": estados,
        "serie": serie,
        "publicado": datetime.now().astimezone().isoformat(),
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
    print(f"[OK] 2ª vuelta escrita en {OUT} | escrutado {nac['escrutado']:.2f}% | "
          f"crudo {nac['crudo']['lula']['pct']:.1f}/{nac['crudo']['flavio']['pct']:.1f} | "
          f"swing {nac['swing']['lula']['pct']:.1f}/{nac['swing']['flavio']['pct']:.1f} | "
          f"scht {nac['schteingart']['lula']['pct']:.1f}/{nac['schteingart']['flavio']['pct']:.1f}")


if __name__ == "__main__":
    main()
