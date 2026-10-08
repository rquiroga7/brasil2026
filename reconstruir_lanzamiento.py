# -*- coding: utf-8 -*-
"""
reconstruir_lanzamiento.py — ¿Cuándo se publicó cada resultado del TSE 2026 y
con qué sesgo geográfico?

Usa el escrutinio en vivo por zona (escrutinio_zonas_2026.csv). Cada fila trae
dos relojes:
  * hora_local: cuándo lo descargamos nosotros.
  * hora_tse:   la hora de generación que el propio TSE pone en el archivo.

Para reconstruir el ORDEN DE PUBLICACIÓN usamos hora_tse (no depende de la
velocidad de nuestro raspado). Para medir cuánto distorsionaba nuestro raspado
comparamos con hora_local.

Productos (en D:\\brasil2026_data\\lanzamiento\\):
  zonas_primera_publicacion.csv   una fila por zona con primera/última vez vista
  municipios_publicacion.csv      agregado por municipio
  bias_por_decil.csv              % Lula 2026 y 2022 por decil de publicación
  resumen_lanzamiento.json        métricas de sesgo
  lanzamiento_2026.png            figura de 4 paneles
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

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ARCHIVO_VIVO = rd.ruta("escrutinio_zonas_2026.csv")
ARCHIVO_2022 = rd.ruta("escrutinio_zonas_2022.csv")
ARCHIVO_HIST_2022 = rd.ruta("historico_nacional_2022_1t.csv")
OUT_DIR = rd.ruta_dir("lanzamiento")

CAND26 = ["Lula", "Flavio_Bolsonaro", "Augusto_Cury", "Ronaldo_Caiado", "Romeu_Zema",
          "Renan_Santos", "Hertz_Dias", "Edmilson_Costa", "Clariana_Barao",
          "Rui_Costa_Pimenta", "Wilson_Grassi", "Samara_Martins"]

REGION = {}
for uf in ["ac", "ap", "am", "pa", "ro", "rr", "to"]:
    REGION[uf.upper()] = "Norte"
for uf in ["al", "ba", "ce", "ma", "pb", "pe", "pi", "rn", "se"]:
    REGION[uf.upper()] = "Nordeste"
for uf in ["df", "go", "mt", "ms"]:
    REGION[uf.upper()] = "Centro-Oeste"
for uf in ["es", "mg", "rj", "sp"]:
    REGION[uf.upper()] = "Sudeste"
for uf in ["pr", "rs", "sc"]:
    REGION[uf.upper()] = "Sur"
REGION["ZZ"] = "Exterior"


def _ts(serie):
    return pd.to_datetime(serie, format="%d/%m/%Y %H:%M:%S", errors="coerce")


def cargar():
    df = pd.read_csv(ARCHIVO_VIVO, dtype=str)
    for c in ["secoes_totalizadas", "electores", "votos_totales", "votos_blancos",
              "votos_nulos", "numero_pasada"] + CAND26:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)
    df["hl"] = pd.to_datetime(df["hora_local"], errors="coerce")
    df["ht"] = _ts(df["hora_tse"])
    df["uf"] = df["estado_uf"].str.upper()
    df["cod_mun"] = df["codigo_municipio"].astype(str).str.zfill(5)
    df["zona"] = df["zona_electoral"].astype(str).str.zfill(4)
    df["validos"] = df[CAND26].sum(axis=1)
    df["con_datos"] = (df["secoes_totalizadas"] > 0) | (df["votos_totales"] > 0)
    df["region"] = df["uf"].map(REGION).fillna("Otros")
    return df


def primeras_ultimas(df):
    clave = ["uf", "cod_mun", "zona"]
    con = df[df["con_datos"]].sort_values(clave + ["hl"])
    primera = con.drop_duplicates(subset=clave, keep="first").copy()
    ultima = df.sort_values(clave + ["hl"]).drop_duplicates(subset=clave, keep="last").copy()

    primera = primera.rename(columns={"hl": "primera_local", "ht": "primera_tse",
                                      "numero_pasada": "pasada_primera"})
    cols_p = clave + ["municipio", "region", "primera_local", "primera_tse",
                      "pasada_primera", "secoes_totalizadas", "votos_totales"]
    primera = primera[cols_p]

    ultima = ultima.rename(columns={"hl": "ultima_local", "ht": "ultima_tse",
                                    "numero_pasada": "pasada_ultima"})
    ultima["lula_pct"] = 100 * ultima["Lula"] / ultima["validos"].replace(0, np.nan)
    ultima["flavio_pct"] = 100 * ultima["Flavio_Bolsonaro"] / ultima["validos"].replace(0, np.nan)
    cols_u = clave + ["municipio", "electores", "votos_totales", "validos",
                      "Lula", "Flavio_Bolsonaro", "lula_pct", "flavio_pct",
                      "secoes_totalizadas", "ultima_local", "ultima_tse", "pasada_ultima"]
    ultima = ultima[cols_u]

    n_obs = df.groupby(clave).size().rename("n_obs").reset_index()
    out = primera.merge(ultima, on=clave, how="inner").merge(n_obs, on=clave, how="left")
    out = out.rename(columns={"municipio_x": "municipio"}).drop(columns=["municipio_y"], errors="ignore")
    return out


def enriquecer_2022(out):
    if not os.path.exists(ARCHIVO_2022):
        return out
    z = pd.read_csv(ARCHIVO_2022, dtype=str)
    z = z[z["turno"] == "1"].copy()
    cand22 = [c for c in z.columns if c not in
              ["ref", "uf", "codigo_municipio", "municipio", "zona", "turno",
               "electores", "votos_totales", "secciones_totalizadas",
               "votos_blancos", "votos_nulos"]]
    for c in cand22:
        z[c] = pd.to_numeric(z[c], errors="coerce").fillna(0)
    z["uf"] = z["uf"].str.upper()
    z["cod_mun"] = z["codigo_municipio"].astype(str).str.zfill(5)
    z["zona"] = z["zona"].astype(str).str.zfill(4)
    z["validos22"] = z[cand22].sum(axis=1)
    lula22 = [c for c in cand22 if c.startswith("13_")]
    z["lula22_pct"] = 100 * z[lula22[0]] / z["validos22"].replace(0, np.nan) if lula22 else np.nan
    z = z[["uf", "cod_mun", "zona", "validos22", "lula22_pct"]]
    return out.merge(z, on=["uf", "cod_mun", "zona"], how="left")


def _corr(x, y):
    m = x.notna() & y.notna()
    if m.sum() < 10:
        return float("nan")
    x2, y2 = x[m], y[m]
    if x2.std() == 0 or y2.std() == 0:
        return float("nan")
    return float(np.corrcoef(x2, y2)[0, 1])


def analizar(out):
    out = out[out["primera_tse"].notna() & out["lula_pct"].notna()].copy()
    out = out[out["primera_tse"] >= pd.Timestamp("2026-10-04")].copy()
    t0 = out["primera_tse"].min()
    out["min_tse"] = (out["primera_tse"] - t0).dt.total_seconds() / 60.0
    t0l = out["primera_local"].min()
    out["min_local"] = (out["primera_local"] - t0l).dt.total_seconds() / 60.0

    res = {}
    res["n_zonas"] = int(len(out))
    res["primera_tse"] = str(out["primera_tse"].min())
    res["ultima_tse"] = str(out["primera_tse"].max())
    res["corr_orden_lula_tse"] = _corr(out["min_tse"], out["lula_pct"])
    res["corr_orden_lula_local"] = _corr(out["min_local"], out["lula_pct"])

    # correlación intra-estado (quita el efecto fijo del estado)
    dem_t = out["min_tse"] - out.groupby("uf")["min_tse"].transform("mean")
    dem_l = out["lula_pct"] - out.groupby("uf")["lula_pct"].transform("mean")
    res["corr_intra_estado_tse"] = _corr(dem_t, dem_l)

    # deciles de tiempo de publicación
    out["decil"] = pd.qcut(out["min_tse"], 10, labels=False, duplicates="drop")
    dec = out.groupby("decil").agg(
        min_tse=("min_tse", "mean"),
        lula26=("lula_pct", "mean"),
        flavio26=("flavio_pct", "mean"),
        lula22=("lula22_pct", "mean") if "lula22_pct" in out.columns else ("lula_pct", "mean"),
        validos=("validos", "sum"),
        n=("lula_pct", "size"),
    ).reset_index()
    dec.to_csv(os.path.join(OUT_DIR, "bias_por_decil.csv"), index=False)

    q = pd.qcut(out["min_tse"], 4, labels=["Q1 temprano", "Q2", "Q3", "Q4 tardío"])
    res["cuartiles_lula26"] = out.groupby(q)["lula_pct"].mean().round(2).to_dict()
    if "lula22_pct" in out.columns:
        res["cuartiles_lula22"] = out.groupby(q)["lula22_pct"].mean().round(2).to_dict()
    res["cuartiles_region"] = out.groupby(q)["region"].agg(lambda s: s.value_counts().idxmax()).to_dict()
    return out, dec, res


def curva_nacional(out):
    """% de votos válidos finales ya publicados, minuto a minuto (reloj TSE)."""
    total = out["validos"].sum()
    orden = out.sort_values("min_tse")
    cum = orden["validos"].cumsum() / total * 100
    return orden["min_tse"].values, cum.values


def historico_2022():
    if not os.path.exists(ARCHIVO_HIST_2022):
        return None, None
    h = pd.read_csv(ARCHIVO_HIST_2022)
    col = "pe_secoes_acumulado" if "pe_secoes_acumulado" in h.columns else None
    if col is None:
        return None, None
    h = h.copy()
    h["pe"] = pd.to_numeric(h[col].astype(str).str.replace(",", "."), errors="coerce")
    h["ts"] = pd.to_datetime(h["ts"], errors="coerce")
    h = h.dropna(subset=["pe", "ts"]).sort_values("ts")
    h = h[h["pe"] > 0]
    if h.empty:
        return None, None
    t0 = h["ts"].min()
    return (h["ts"] - t0).dt.total_seconds().values / 60.0, h["pe"].values


def graficar(out, dec, res):
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))

    ax = axes[0, 0]
    x, y = curva_nacional(out)
    ax.plot(x, y, color="#1f77b4", linewidth=2, label="2026 (votos publicados)")
    hx, hy = historico_2022()
    if hx is not None:
        ax.plot(hx, hy, color="#888", linewidth=1.5, alpha=0.8,
                label="2022 TSE oficial (% secciones)")
    ax.set_xlabel("minutos desde la primera publicación")
    ax.set_ylabel("% del total final ya publicado")
    ax.set_title("A) Curva de publicación del escrutinio")
    ax.grid(alpha=0.4, linestyle="--")
    ax.legend(fontsize=8)

    ax = axes[0, 1]
    ax.bar(dec["decil"], dec["lula26"], color="#E11B22", alpha=0.8, label="Lula 2026")
    if "lula22_pct" in dec.columns:
        ax.plot(dec["decil"], dec["lula22"], "o-", color="#333", label="Lula 2022 (mismas zonas)")
    ax.set_xlabel("decil de tiempo de publicación (0=primero)")
    ax.set_ylabel("% de votos válidos")
    ax.set_title("B) Sesgo de publicación: % Lula por momento de carga")
    ax.grid(alpha=0.4, linestyle="--")
    ax.legend(fontsize=8)

    ax = axes[1, 0]
    dem_t = out["min_tse"] - out.groupby("uf")["min_tse"].transform("mean")
    dem_l = out["lula_pct"] - out.groupby("uf")["lula_pct"].transform("mean")
    ax.scatter(dem_t, dem_l, s=4, alpha=0.15, color="#444")
    ax.axhline(0, color="k", linewidth=0.6)
    ax.set_xlabel("tiempo de publicación, min (desviado por estado)")
    ax.set_ylabel("% Lula 2026 (desviado por estado)")
    ax.set_title(f"C) Dentro de cada estado: corr = {res['corr_intra_estado_tse']:.3f}")

    ax = axes[1, 1]
    orden_reg = ["Norte", "Nordeste", "Centro-Oeste", "Sudeste", "Sur", "Exterior"]
    datos = [out.loc[out["region"] == r, "min_tse"].dropna().values for r in orden_reg]
    ax.boxplot(datos, showfliers=False)
    ax.set_xticks(range(1, len(orden_reg) + 1))
    ax.set_xticklabels(orden_reg, fontsize=8)
    ax.set_ylabel("minutos hasta la publicación")
    ax.set_title("D) Momento de publicación por región")
    ax.grid(alpha=0.4, axis="y", linestyle="--")

    fig.tight_layout()
    fig.savefig(os.path.join(OUT_DIR, "lanzamiento_2026.png"), dpi=120, bbox_inches="tight")
    plt.close(fig)


def analizar_control(muni):
    """Timeline TSE-nativo: hora de finalización por municipio (abrangencia dt/ht
    guardada en control_versiones_2026.json). No depende de la velocidad de
    nuestro raspado (es la última versión que el TSE publicó)."""
    ruta = rd.ruta("control_versiones_2026.json")
    if not os.path.exists(ruta):
        return None, float("nan")
    with open(ruta, encoding="utf-8") as f:
        cv = json.load(f)
    filas = []
    for clave, v in cv.items():
        uf, cod = clave.split("/", 1)
        partes = (v.split("|") + ["", "", ""])[:3]
        ts = pd.to_datetime(f"{partes[0]} {partes[1]}",
                            format="%d/%m/%Y %H:%M:%S", errors="coerce")
        filas.append({"uf": uf.upper(), "cod_mun": cod.zfill(5), "fin_tse": ts,
                      "est_final": pd.to_numeric(partes[2], errors="coerce")})
    c = pd.DataFrame(filas).merge(
        muni[["uf", "cod_mun", "lula_pct", "validos", "primera_tse"]],
        on=["uf", "cod_mun"], how="inner")
    c = c[c["fin_tse"].notna()].copy()
    t0 = c["fin_tse"].min()
    c["min_fin"] = (c["fin_tse"] - t0).dt.total_seconds() / 60.0
    c.to_csv(os.path.join(OUT_DIR, "municipios_final_tse.csv"), index=False)
    corr = _corr(c["min_fin"], c["lula_pct"])
    return c, corr


def main():
    print("[*] Reconstruyendo la publicación del escrutinio 2026...")
    df = cargar()
    out = primeras_ultimas(df)
    out = enriquecer_2022(out)
    out = out.rename(columns={"municipio": "municipio"})
    out.to_csv(os.path.join(OUT_DIR, "zonas_primera_publicacion.csv"), index=False)

    muni = out.groupby(["uf", "cod_mun", "municipio"], as_index=False).agg(
        primera_tse=("primera_tse", "min"),
        primera_local=("primera_local", "min"),
        ultima_tse=("ultima_tse", "max"),
        validos=("validos", "sum"),
        Lula=("Lula", "sum"),
        Flavio=("Flavio_Bolsonaro", "sum"),
        n_zonas=("zona", "size"),
    )
    muni["lula_pct"] = 100 * muni["Lula"] / muni["validos"].replace(0, np.nan)
    muni.to_csv(os.path.join(OUT_DIR, "municipios_publicacion.csv"), index=False)

    out2, dec, res = analizar(out)
    print(f"[i] Zonas analizadas: {res['n_zonas']}  ({res['primera_tse']} -> {res['ultima_tse']})")
    print(f"[i] Correlación (tiempo publicación vs % Lula):")
    print(f"      hora TSE (orden real):   {res['corr_orden_lula_tse']:+.3f}")
    print(f"      hora local (nuestro):    {res['corr_orden_lula_local']:+.3f}")
    print(f"      intra-estado (hora TSE): {res['corr_intra_estado_tse']:+.3f}")
    print(f"[i] % Lula 2026 por cuartil de publicación: {res['cuartiles_lula26']}")
    if "cuartiles_lula22" in res:
        print(f"[i] % Lula 2022 por cuartil de publicación: {res['cuartiles_lula22']}")
    print(f"[i] Región dominante por cuartil: {res['cuartiles_region']}")

    cfin, corr_fin = analizar_control(muni)
    if cfin is not None:
        q = pd.qcut(cfin["min_fin"], 4, labels=["Q1", "Q2", "Q3", "Q4"])
        res["corr_fin_lula"] = corr_fin
        res["cuartiles_fin_lula"] = cfin.groupby(q)["lula_pct"].mean().round(2).to_dict()
        print(f"\n[i] Hora de FINALIZACIÓN TSE-nativa ({len(cfin)} municipios):")
        print(f"      corr (fin vs % Lula): {corr_fin:+.3f}")
        print(f"      % Lula por cuartil de finalización: {res['cuartiles_fin_lula']}")

    est = out2.groupby("uf").agg(min_tse=("min_tse", "mean"),
                                 lula=("lula_pct", "mean"),
                                 n=("lula_pct", "size")).sort_values("min_tse")
    est.to_csv(os.path.join(OUT_DIR, "por_estado.csv"))
    print("\n[i] Orden medio de publicación por estado (min desde la primera):")
    for uf, row in est.iterrows():
        print(f"      {uf:>3}: {row['min_tse']:6.1f} min   Lula {row['lula']:5.1f}%   n={int(row['n'])}")

    json.dump(res, open(os.path.join(OUT_DIR, "resumen_lanzamiento.json"), "w"),
              ensure_ascii=False, indent=2)
    graficar(out2, dec, res)
    print(f"\n[OK] Salidas en {OUT_DIR}")


if __name__ == "__main__":
    main()
