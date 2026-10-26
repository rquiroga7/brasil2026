# -*- coding: utf-8 -*-
"""
inferencia_ecologica.py — Migración de votos en las presidenciales de Brasil.

Estima por máxima verosimilitud (EM) las MATRICES DE TRANSICIÓN entre bloques de
voto, a nivel de SECCIÓN electoral (la urna), incluyendo a quienes no votaron:

  2018 1T: Haddad (PT) | Bolsonaro | Otros | Blanco/Nulo | No votó
  2022 1T: Lula        | Bolsonaro | Otros | Blanco/Nulo | No votó
  2022 2T: Lula        | Bolsonaro |         Blanco/Nulo | No votó
  2026 1T: Lula        | Flávio    | Otros | Blanco/Nulo | No votó

Pares estimados: 2018→2022, 2022→2026 y 2022 1ª→2ª vuelta. Para los tres comicios
se ENCADENAN los pares (supuesto de Markov). No existe un método 3-vías
identificable solo con márgenes seccionales; el encadenado es el enfoque honesto.

Modelo (por par): en cada sección i, cada persona del año destino elige categoría
k con probabilidad p_ik = sum_j share_origen_ij * theta_jk. Se ajusta theta por EM
y se obtienen intervalos por bootstrap sobre secciones.

Salidas en <repo>\\plot\\ (formato 4:3):
  transicion_nacional_2018_2022.csv / _2022_2026.csv / _2022_1t_2t.csv
  transicion_2018_2026_markov.csv / transicion_por_region.csv
  heatmap_*.png, sankey_*.html|png
  informe_migracion_2022_2026_es.md, relatorio_migracao_2022_2026_pt.md
  resumen_ei.json
"""

import os
import sys
import json

import numpy as np
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import rutas_datos as rd
import estilo_plot as ep

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

SEC_DIR = rd.ruta_dir("secciones")
OUT_DIR = os.path.join(rd.REPO, "plot")
os.makedirs(OUT_DIR, exist_ok=True)

CATS = ["A", "B", "Otros", "Blanco/Nulo", "No voto"]
COLORES = {"A": "#E11B22", "B": "#2C5FBF", "Otros": "#9AA0A6",
           "Blanco/Nulo": "#CFCFCF", "No voto": "#4D4D4D"}
MIN_APTOS = 20
CLAVE = ["uf", "mun", "zona", "secao"]
CLAVE_ZONA = ["uf", "mun", "zona"]
COLS5 = ["blk_lula", "blk_bolso", "blk_otros", "blk_bn", "blk_novoto"]
COLS4 = ["blk_lula", "blk_bolso", "blk_bn", "blk_novoto"]

ANIOS = {
    2018: {"cands": ["12", "13", "15", "16", "17", "18", "19", "27", "30",
                     "45", "50", "51", "54"], "lula": "13", "bolso": "17",
           "labels": ["Haddad (PT)", "Bolsonaro", "Otros", "Blanco/Nulo", "No voto"]},
    2022: {"cands": ["12", "13", "14", "15", "16", "21", "22", "27", "30", "44", "80"],
           "lula": "13", "bolso": "22",
           "labels": ["Lula", "Bolsonaro", "Otros", "Blanco/Nulo", "No voto"]},
    2026: {"cands": ["13", "14", "16", "21", "22", "27", "28", "29", "30", "35",
                     "55", "70", "80"], "lula": "13", "bolso": "22",
           "labels": ["Lula", "Flavio", "Otros", "Blanco/Nulo", "No voto"]},
}
LABELS_2022_2T = ["Lula", "Bolsonaro", "Blanco/Nulo", "No voto"]
LABELS_2026_2T = ["Lula", "Flavio", "Blanco/Nulo", "No voto"]

# Configuración de los segundos turnos: solo Lula (13) y el candidato de la
# derecha (22). En 2022 el rival era Bolsonaro; en 2026, Flávio.
CFG_2T = {
    2022: {"cands": ["13", "22"], "lula": "13", "bolso": "22",
           "labels": LABELS_2022_2T},
    2026: {"cands": ["13", "22"], "lula": "13", "bolso": "22",
           "labels": LABELS_2026_2T},
}

REGION = {}
for uf in ["AC", "AP", "AM", "PA", "RO", "RR", "TO"]:
    REGION[uf] = "Norte"
for uf in ["AL", "BA", "CE", "MA", "PB", "PE", "PI", "RN", "SE"]:
    REGION[uf] = "Nordeste"
for uf in ["DF", "GO", "MT", "MS"]:
    REGION[uf] = "Centro-Oeste"
for uf in ["ES", "MG", "RJ", "SP"]:
    REGION[uf] = "Sudeste"
for uf in ["PR", "RS", "SC"]:
    REGION[uf] = "Sur"
REGION["ZZ"] = "Exterior"


def _nom_vot(y, turno):
    return f"secciones_presidente_{y}_{turno}t.csv"


def _nom_det(y, turno):
    return (f"secciones_detalle_{y}.csv" if turno == "1"
            else f"secciones_detalle_{y}_{turno}t.csv")


def _suma(df, cols):
    cols = [c for c in cols if c in df.columns]
    return df[cols].sum(axis=1) if cols else pd.Series(0.0, index=df.index)


def cargar_zona_2026_2t():
    """2ª vuelta 2026 por zona (el TSE aún no publicó la base por sección).

    Los votos salen del escrutinio oficial por zona (`escrutinio_zonas_2026_2t.csv`,
    generado por el raspador). Los electores aptos vienen del mismo JSON oficial.
    """
    ruta = rd.ruta("escrutinio_zonas_2026_2t.csv")
    if not os.path.exists(ruta):
        raise FileNotFoundError(
            f"Falta {ruta}. Corre antes:\n"
            "  python scrapingbrasil2026zonpasG_rverboseRAP2_3X.py "
            "--turno 2 --una-pasada --silencioso")
    d = pd.read_csv(ruta, dtype={"codigo_municipio": str, "zona_electoral": str})
    z = pd.DataFrame({
        "uf": d["estado_uf"].str.upper(),
        "mun": d["codigo_municipio"].str.zfill(5),
        "zona": d["zona_electoral"].str.zfill(4),
        "blk_lula": pd.to_numeric(d["Lula"], errors="coerce").fillna(0),
        "blk_bolso": pd.to_numeric(d["Flavio_Bolsonaro"], errors="coerce").fillna(0),
        "blk_otros": 0.0,
        "blk_bn": (pd.to_numeric(d["votos_blancos"], errors="coerce").fillna(0)
                   + pd.to_numeric(d["votos_nulos"], errors="coerce").fillna(0)),
        "aptos": pd.to_numeric(d["electores"], errors="coerce").fillna(0),
    })
    z["comparecimento"] = z[["blk_lula", "blk_bolso", "blk_bn"]].sum(axis=1)
    z["blk_novoto"] = (z["aptos"] - z["comparecimento"]).clip(lower=0)
    # Si el raspador corrió varias pasadas, quedarse con la última por zona.
    z = z.drop_duplicates(subset=CLAVE_ZONA, keep="last")
    return z


def _cfg_anio(y, turno):
    return CFG_2T[y] if turno == "2" else ANIOS[y]


def cargar_anio(y, turno="1", nivel="secao"):
    """Carga los bloques de voto de un año/turno.

    nivel="secao" (default) usa la base por sección; nivel="zona" agrega a zona
    electoral (necesario para 2026 2T, que solo está disponible por zona).
    """
    if (y, turno) == (2026, "2"):
        if nivel != "zona":
            raise ValueError("2026 2T solo está disponible a nivel de zona "
                             "(usar nivel='zona').")
        return cargar_zona_2026_2t()

    cfg = _cfg_anio(y, turno)
    d = pd.read_csv(os.path.join(SEC_DIR, _nom_vot(y, turno)), dtype=str)
    det = pd.read_csv(os.path.join(SEC_DIR, _nom_det(y, turno)), dtype=str)
    for c in [c for c in d.columns if c not in CLAVE]:
        d[c] = pd.to_numeric(d[c], errors="coerce").fillna(0)
    otros = [c for c in cfg["cands"] if c not in (cfg["lula"], cfg["bolso"])]
    d["blk_lula"] = _suma(d, [cfg["lula"]])
    d["blk_bolso"] = _suma(d, [cfg["bolso"]])
    d["blk_otros"] = _suma(d, otros)
    d["blk_bn"] = _suma(d, ["branco", "nulo", "97"])
    d["comparecimento"] = d[["blk_lula", "blk_bolso", "blk_otros", "blk_bn"]].sum(axis=1)
    det = det.copy()
    det["aptos"] = pd.to_numeric(det["aptos"], errors="coerce").fillna(0)
    d = d.merge(det[CLAVE + ["aptos"]], on=CLAVE, how="left")
    d["aptos"] = d["aptos"].fillna(0)
    if nivel == "zona":
        d = d.groupby(CLAVE_ZONA, as_index=False).agg(
            {**{c: "sum" for c in COLS5[:4]}, "aptos": "sum"})
        d["comparecimento"] = d[COLS5[:4]].sum(axis=1)
    d["blk_novoto"] = (d["aptos"] - d["comparecimento"]).clip(lower=0)
    return d


def emparejar(da, db, claves=None):
    claves = CLAVE if claves is None else claves
    m = da[claves + COLS5].merge(db[claves + COLS5], on=claves,
                                 suffixes=("_o", "_d"))
    m["region"] = m["uf"].map(REGION).fillna("Otros")
    return m


def _mat(m, cols_o, cols_d):
    return m[cols_o].to_numpy(float), m[cols_d].to_numpy(float)


def em_transicion(X, Y, iters=800, tol=1e-10, theta0=None, alpha=0.0):
    """MLE rectangular de theta[j,k]=P(destino k | origen j) por EM."""
    Ko, Kd = X.shape[1], Y.shape[1]
    val = X.sum(1) > 0
    X, Y = X[val], Y[val]
    xs = X / X.sum(1, keepdims=True)
    theta = np.full((Ko, Kd), 1.0 / Kd) if theta0 is None else theta0.copy()
    for _ in range(iters):
        xp = np.where((xs @ theta) <= 1e-15, 1e-15, xs @ theta)
        w = Y / xp
        num = (xs[:, :, None] * theta[None, :, :]) * w[:, None, :]
        Z = num.sum(0)
        nueva = (Z + alpha) / (Z.sum(1, keepdims=True) + Kd * alpha)
        if np.max(np.abs(nueva - theta)) < tol:
            return nueva
        theta = nueva
    return theta


def goodman(X, Y):
    val = X.sum(1) > 0
    X, Y = X[val], Y[val]
    xs = X / X.sum(1, keepdims=True)
    ys = Y / Y.sum(1, keepdims=True)
    theta, *_ = np.linalg.lstsq(xs, ys, rcond=None)
    theta = np.clip(theta, 0, None)
    s = theta.sum(1, keepdims=True)
    return np.divide(theta, s, out=np.full_like(theta, 1.0 / theta.shape[1]), where=s > 0)


def bootstrap(X, Y, theta0, reps=60, seed=0, iters=60):
    rng = np.random.default_rng(seed)
    N = X.shape[0]
    out = np.empty((reps, X.shape[1], Y.shape[1]))
    for r in range(reps):
        idx = rng.integers(0, N, N)
        out[r] = em_transicion(X[idx], Y[idx], iters=iters, theta0=theta0)
    return out


def ei_par(m, cols_o, cols_d, reps=60):
    X, Y = _mat(m, cols_o, cols_d)
    filtro = (X.sum(1) >= MIN_APTOS) & (Y.sum(1) >= MIN_APTOS)
    mf = m[filtro].copy()
    Xf, Yf = _mat(mf, cols_o, cols_d)
    theta = em_transicion(Xf, Yf)
    bs = bootstrap(Xf, Yf, theta, reps=reps)
    lo, hi = np.percentile(bs, 5, axis=0), np.percentile(bs, 95, axis=0)
    return theta, lo, hi, goodman(Xf, Yf), mf, Xf, Yf


def heatmap(theta, lo, hi, labels_o, labels_d, N_o, titulo, path):
    N_o = np.asarray(N_o, float)
    flujo = theta * N_o[:, None]
    tot_o, tot_d = N_o, flujo.sum(0)
    etiq_o = [f"{lab}\n({tot_o[i]/1e6:.1f}M)" for i, lab in enumerate(labels_o)]
    etiq_d = [f"{lab}\n({tot_d[j]/1e6:.1f}M)" for j, lab in enumerate(labels_d)]
    fig, ax = plt.subplots(figsize=(8, 6))          # 4:3
    im = ax.imshow(theta * 100, cmap="YlOrRd", vmin=0, vmax=100)
    for i in range(theta.shape[0]):
        for j in range(theta.shape[1]):
            txt = f"{theta[i, j]*100:.1f}%\n{flujo[i, j]/1e6:.1f}M"
            ax.text(j, i, txt, ha="center", va="center", fontsize=7.5,
                    color="black" if theta[i, j] < 0.6 else "white")
    ax.set_xticks(range(len(labels_d)))
    ax.set_yticks(range(len(labels_o)))
    ax.set_xticklabels(etiq_d, fontsize=8)
    ax.set_yticklabels(etiq_o, fontsize=8)
    ax.set_xlabel("Destino (millones de personas)")
    ax.set_ylabel("Origen (millones de personas)")
    ax.set_title(titulo, fontsize=11)
    fig.colorbar(im, ax=ax, fraction=0.046, label="% del bloque de origen")
    fig.tight_layout()
    ep.mpl(fig, "Inferencia ecológica por secciones electorales (EM): cada celda es el % "
                "del bloque de origen que va a cada destino; totales en millones.")
    fig.savefig(path, dpi=140, bbox_inches="tight")
    plt.close(fig)


def _rgba(hexcolor, alpha):
    h = hexcolor.lstrip("#")
    return f"rgba({int(h[0:2],16)},{int(h[2:4],16)},{int(h[4:6],16)},{alpha})"


def _plot_sankey(src, dst, val, cl, labels, color_nodo, titulo, path_html, path_png):
    import plotly.graph_objects as go
    fig = go.Figure(go.Sankey(
        arrangement="snap",
        node=dict(label=labels, color=color_nodo, pad=16, thickness=20,
                  line=dict(color="rgba(0,0,0,0.3)", width=0.5)),
        link=dict(source=src, target=dst, value=val, color=cl)))
    fig.update_layout(title_text=titulo, font_size=13, height=900, width=1200,
                      paper_bgcolor="white", margin=dict(b=150))
    ep.plotly(fig, "Sankey de migración de votos entre bloques (personas). "
                   "Inferencia ecológica por secciones electorales (EM).")
    fig.write_html(path_html, include_plotlyjs="cdn")
    print(f"[OK] {os.path.basename(path_html)}")
    try:
        fig.write_image(path_png, width=1200, height=900, scale=2)
        print(f"[OK] {os.path.basename(path_png)}")
    except Exception as exc:
        print(f"[!] PNG {os.path.basename(path_png)}: {exc}")


def sankey_par(theta, N_o, labels_o, labels_d, titulo, base):
    Ko, Kd = theta.shape
    labels = labels_o + labels_d
    color_nodo = [COLORES[CATS[i]] for i in range(Ko)] + \
                 [COLORES[CATS[i]] for i in range(Kd)]
    src, dst, val, cl = [], [], [], []
    for j in range(Ko):
        for k in range(Kd):
            v = float(theta[j, k] * N_o[j])
            if v < 0.5:
                continue
            src.append(j); dst.append(Ko + k); val.append(v)
            cl.append(_rgba(COLORES[CATS[j]], 0.5))
    _plot_sankey(src, dst, val, cl, labels, color_nodo, titulo,
                 os.path.join(OUT_DIR, base + ".html"),
                 os.path.join(OUT_DIR, base + ".png"))


def sankey_tres(thA, N18, thB, N22, labels18, labels22, labels26, base):
    K = len(labels18)
    labels = labels18 + labels22 + labels26
    color_nodo = [COLORES[CATS[i]] for i in range(K)] * 3
    src, dst, val, cl = [], [], [], []
    for j in range(K):
        for k in range(thA.shape[1]):
            v = float(thA[j, k] * N18[j])
            if v < 0.5:
                continue
            src.append(j); dst.append(K + k); val.append(v)
            cl.append(_rgba(COLORES[CATS[j]], 0.45))
    for k in range(K):
        for l in range(thB.shape[1]):
            v = float(thB[k, l] * N22[k])
            if v < 0.5:
                continue
            src.append(K + k); dst.append(2 * K + l); val.append(v)
            cl.append(_rgba(COLORES[CATS[k]], 0.45))
    _plot_sankey(src, dst, val, cl, labels, color_nodo,
                 "Migración de votos — Brasil 2018 → 2022 → 2026 (personas)",
                 os.path.join(OUT_DIR, base + ".html"),
                 os.path.join(OUT_DIR, base + ".png"))


def _tab_md(theta, labels_o, labels_d, N_o, pct=True):
    N_o = np.asarray(N_o, float)
    flujo = theta * N_o[:, None]
    head = "| Origen \\ Destino | " + " | ".join(labels_d) + " |"
    sep = "|" + "---|" * (len(labels_d) + 1)
    filas = [head, sep]
    for i, lo in enumerate(labels_o):
        celdas = []
        for j in range(theta.shape[1]):
            if pct:
                celdas.append(f"{theta[i,j]*100:.1f}% ({flujo[i,j]/1e6:.1f}M)")
            else:
                celdas.append(f"{flujo[i,j]/1e6:.1f}M")
        filas.append(f"| **{lo}** ({N_o[i]/1e6:.1f}M) | " + " | ".join(celdas) + " |")
    return "\n".join(filas)


def reporte_es(thB, N22, thC, N22_1t, thA, N18, th_markov,
               thD=None, N26_1=None, thE=None, N22_2t=None,
               thF=None, N22_1t_2026=None):
    L22, L26, L22b = ANIOS[2022]["labels"], ANIOS[2026]["labels"], LABELS_2022_2T
    L26b = LABELS_2026_2T
    extra_2t = ""
    if thD is not None and thE is not None:
        extra_2t = f"""
## 2026 1ª → 2ª vuelta (nivel zona)
{_tab_md(thD, L26, L26b, N26_1)}

## 2022 1ª → 2026 2ª vuelta (nivel zona)
{_tab_md(thF, L22, L26b, N22_1t_2026)}

## 2022 2ª → 2026 2ª vuelta (nivel zona)
{_tab_md(thE, L22b, L26b, N22_2t)}
"""
    f = thB * N22[:, None]
    return f"""# Migración de votos en Brasil: 2022 → 2026 (Presidente, 1ª vuelta)

*Estimación ecológica por secciones electorales (EM). {f.shape[0]}x{f.shape[1]} bloques.*

## Cómo se hizo
Se emparejaron **461.219 secciones** entre 2022 y 2026 por (UF, municipio, zona,
sección). En cada sección se conoce el voto por bloque en ambos años y los
electores habilitados (aptos). Se estima la matriz de transición θ[j,k] =
P(votar k en 2026 | bloque j en 2022) por máxima verosimilitud (EM), con
intervalos por bootstrap. Los "No votó" son aptos − comparecimento.

## Resultado principal (2022 → 2026)
{_tab_md(thB, L22, L26, N22)}

## Lectura
- **Lula retuvo el {thB[0,0]*100:.1f}%** de su electorado; fugas: {thB[0,1]*100:.1f}% a Flávio y {thB[0,4]*100:.1f}% a la abstención.
- **Bolsonaro transfirió el {thB[1,1]*100:.1f}% a Flávio**; casi nada a Lula ({thB[1,0]*100:.1f}%).
- Los **"Otros" 2022** (Ciro, Tebet, etc.) se repartieron: {thB[2,1]*100:.1f}% a Flávio, {thB[2,0]*100:.1f}% a Lula, {thB[2,4]*100:.1f}% no votó.
- Entre quienes **no votaron en 2022**, {thB[4,1]*100:.1f}% votó a Flávio y {thB[4,0]*100:.1f}% a Lula en 2026.

## Balotaje 2022 (1ª → 2ª vuelta)
{_tab_md(thC, L22, L22b, N22_1t)}
{extra_2t}
## Contexto 2018 → 2022
{_tab_md(thA, ANIOS[2018]["labels"], L22, N18)}

## 2018 → 2026 (encadenado, supuesto de Markov)
{_tab_md(th_markov, ANIOS[2018]["labels"], L26, N18)}

## Advertencias
Inferencia **ecológica**: son patrones agregados por sección, no seguimiento
individual. El encadenado 2018→2026 asume que 2026 depende de 2022 (Markov).
Cambios de padrón y de composición de las secciones introducen error.
Las celdas 0% o 100% son soluciones de frontera del EM (electorados muy rígidos):
léanse como «casi nulo» / «casi total», no como certeza.

---
*{ep.CREDITO}*
"""


def reporte_pt(thB, N22, thC, N22_1t, thA, N18, th_markov,
               thD=None, N26_1=None, thE=None, N22_2t=None,
               thF=None, N22_1t_2026=None):
    L22, L26, L22b = ANIOS[2022]["labels"], ANIOS[2026]["labels"], LABELS_2022_2T
    L26b = LABELS_2026_2T
    extra_2t = ""
    if thD is not None and thE is not None:
        extra_2t = f"""
## 2026 1º → 2º turno (nível zona)
{_tab_md(thD, L26, L26b, N26_1)}

## 2022 1º → 2026 2º turno (nível zona)
{_tab_md(thF, L22, L26b, N22_1t_2026)}

## 2022 2º → 2026 2º turno (nível zona)
{_tab_md(thE, L22b, L26b, N22_2t)}
"""
    f = thB * N22[:, None]
    return f"""# Migração de votos no Brasil: 2022 → 2026 (Presidente, 1º turno)

*Inferência ecológica por seções eleitorais (EM). Blocos {f.shape[0]}x{f.shape[1]}.*

## Como foi feito
Foram pareadas **461.219 seções** entre 2022 e 2026 por (UF, município, zona,
seção). Em cada seção conhece-se o voto por bloco nos dois anos e os eleitores
aptos. Estima-se a matriz de transição θ[j,k] = P(votar k em 2026 | bloco j em
2022) por máxima verossimilhança (EM), com intervalos por bootstrap. Os "não
votou" são aptos − comparecimento.

## Resultado principal (2022 → 2026)
{_tab_md(thB, L22, L26, N22)}

## Leitura
- **Lula manteve {thB[0,0]*100:.1f}%** do seu eleitorado; fugas: {thB[0,1]*100:.1f}% para Flávio e {thB[0,4]*100:.1f}% para a abstenção.
- **Bolsonaro transferiu {thB[1,1]*100:.1f}% para Flávio**; quase nada para Lula ({thB[1,0]*100:.1f}%).
- Os **"Outros" de 2022** (Ciro, Tebet etc.) dividiram-se: {thB[2,1]*100:.1f}% para Flávio, {thB[2,0]*100:.1f}% para Lula, {thB[2,4]*100:.1f}% não votaram.
- Entre os que **não votaram em 2022**, {thB[4,1]*100:.1f}% votaram em Flávio e {thB[4,0]*100:.1f}% em Lula em 2026.

## 2º turno de 2022 (1º → 2º turno)
{_tab_md(thC, L22, L22b, N22_1t)}
{extra_2t}
## Contexto 2018 → 2022
{_tab_md(thA, ANIOS[2018]["labels"], L22, N18)}

## 2018 → 2026 (encadeado, suposto de Markov)
{_tab_md(th_markov, ANIOS[2018]["labels"], L26, N18)}

## Advertências
Inferência **ecológica**: são padrões agregados por seção, não acompanhamento
individual. O encadeamento 2018→2026 supõe que 2026 depende de 2022 (Markov).
Mudanças de eleitorado e de composição das seções introduzem erro.
As células 0% ou 100% são soluções de fronteira do EM (eleitorados muito rígidos):
leia-se como «quase nulo» / «quase total», não como certeza.

---
*{ep.CREDITO}*
"""


def solo_graficos():
    """Regenera heatmaps y Sankeys desde resumen_ei.json (sin repetir el EM)."""
    res = json.load(open(os.path.join(OUT_DIR, "resumen_ei.json"), encoding="utf-8"))
    n_o = res.setdefault("N_o", {})
    if "2018" in n_o and "2022" in n_o:
        N18 = np.array(n_o["2018"])
        N22 = np.array(n_o["2022"])
    else:
        N18 = cargar_anio(2018, "1")[COLS5].sum().to_numpy()
        N22 = cargar_anio(2022, "1")[COLS5].sum().to_numpy()
        n_o["2018"] = N18.tolist()
        n_o["2022"] = N22.tolist()
    thA = np.array(res["transicion_2018_2022"])
    thB = np.array(res["transicion_2022_2026"])
    thC = np.array(res["transicion_2022_1t_2t"])
    thD = np.array(res["transicion_2026_1t_2t"])
    thE = np.array(res["transicion_2022_2t_2026_2t"])
    thF = np.array(res["transicion_2022_1t_2026_2t"])
    thM = np.array(res["transicion_2018_2026_markov"])
    N26_1t = np.array(res["N_o"]["2026_1t"])
    N22_2t = np.array(res["N_o"]["2022_2t"])
    N22_1t = np.array(res["N_o"]["2022_1t"])
    heatmap(thA, None, None, ANIOS[2018]["labels"], ANIOS[2022]["labels"], N18,
            "Transición de votos — Brasil 2018 → 2022 (%)", os.path.join(OUT_DIR, "heatmap_2018_2022.png"))
    heatmap(thB, None, None, ANIOS[2022]["labels"], ANIOS[2026]["labels"], N22,
            "Transición de votos — Brasil 2022 → 2026 (%)", os.path.join(OUT_DIR, "heatmap_2022_2026.png"))
    heatmap(thC, None, None, ANIOS[2022]["labels"], LABELS_2022_2T, N22,
            "Transición — Brasil 2022 1ª → 2ª vuelta (%)", os.path.join(OUT_DIR, "heatmap_2022_1t_2t.png"))
    heatmap(thD, None, None, ANIOS[2026]["labels"], LABELS_2026_2T, N26_1t,
            "Transición — Brasil 2026 1ª → 2ª vuelta (%)",
            os.path.join(OUT_DIR, "heatmap_2026_1t_2t.png"))
    heatmap(thE, None, None, LABELS_2022_2T, LABELS_2026_2T, N22_2t,
            "Transición — Brasil 2022 2ª → 2026 2ª vuelta (%)",
            os.path.join(OUT_DIR, "heatmap_2022_2t_2026_2t.png"))
    heatmap(thF, None, None, ANIOS[2022]["labels"], LABELS_2026_2T, N22_1t,
            "Transición — Brasil 2022 1ª → 2026 2ª vuelta (%)",
            os.path.join(OUT_DIR, "heatmap_2022_1t_2026_2t.png"))
    heatmap(thM, None, None, ANIOS[2018]["labels"], ANIOS[2026]["labels"], N18,
            "Transición encadenada — Brasil 2018 → 2026 (Markov, %)",
            os.path.join(OUT_DIR, "heatmap_2018_2026.png"))
    sankey_par(thA, N18, ANIOS[2018]["labels"], ANIOS[2022]["labels"],
               "Migración de votos — Brasil 2018 → 2022 (personas)", "sankey_2018_2022")
    sankey_par(thB, N22, ANIOS[2022]["labels"], ANIOS[2026]["labels"],
               "Migración de votos — Brasil 2022 → 2026 (personas)", "sankey_2022_2026")
    sankey_par(thC, N22, ANIOS[2022]["labels"], LABELS_2022_2T,
               "Migración de votos — Brasil 2022 1ª → 2ª vuelta (personas)", "sankey_2022_1t_2t")
    sankey_par(thD, N26_1t, ANIOS[2026]["labels"], LABELS_2026_2T,
               "Migración de votos — Brasil 2026 1ª → 2ª vuelta (personas, zonas)",
               "sankey_2026_1t_2t")
    sankey_par(thE, N22_2t, LABELS_2022_2T, LABELS_2026_2T,
               "Migración de votos — Brasil 2022 2ª → 2026 2ª vuelta (personas, zonas)",
               "sankey_2022_2t_2026_2t")
    sankey_par(thF, N22_1t, ANIOS[2022]["labels"], LABELS_2026_2T,
               "Migración de votos — Brasil 2022 1ª → 2026 2ª vuelta (personas, zonas)",
               "sankey_2022_1t_2026_2t")
    sankey_tres(thA, N18, thB, N22, ANIOS[2018]["labels"], ANIOS[2022]["labels"],
                ANIOS[2026]["labels"], "sankey_2018_2022_2026")
    open(os.path.join(OUT_DIR, "informe_migracion_2022_2026_es.md"), "w", encoding="utf-8").write(
        reporte_es(thB, N22, thC, N22, thA, N18, thM, thD, N26_1t, thE, N22_2t,
                   thF, N22_1t))
    open(os.path.join(OUT_DIR, "relatorio_migracao_2022_2026_pt.md"), "w", encoding="utf-8").write(
        reporte_pt(thB, N22, thC, N22, thA, N18, thM, thD, N26_1t, thE, N22_2t,
                   thF, N22_1t))
    json.dump(res, open(os.path.join(OUT_DIR, "resumen_ei.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print("[OK] Gráficos regenerados desde resumen_ei.json")


def solo_2t():
    """Calcula solo los pares nuevos con 2ª vuelta 2026 (nivel zona).

    Reutiliza los resultados ya guardados en resumen_ei.json para no repetir el
    EM pesado por sección de 2018→2022 y 2022→2026.
    """
    print("[*] Cargando zonas 2026 1T / 2022 1T / 2022 2T / 2026 2T ...", flush=True)
    d26z = cargar_anio(2026, "1", nivel="zona")
    d22z = cargar_anio(2022, "1", nivel="zona")
    d22bz = cargar_anio(2022, "2", nivel="zona")
    d26b = cargar_anio(2026, "2", nivel="zona")

    m_d = emparejar(d26z, d26b, CLAVE_ZONA)
    m_e = emparejar(d22bz, d26b, CLAVE_ZONA)
    m_f = emparejar(d22z, d26b, CLAVE_ZONA)
    print(f"    emparejadas 2026 1T-2T: {len(m_d)} | "
          f"2022 1T-2026 2T: {len(m_f)} | "
          f"2022 2T-2026 2T: {len(m_e)} (zonas)", flush=True)

    cols_o5 = [c + "_o" for c in COLS5]
    cols_d5 = [c + "_d" for c in COLS5]
    cols_o4 = [c + "_o" for c in COLS4]
    cols_d4 = [c + "_d" for c in COLS4]

    print("[*] EI 2026 1ª → 2ª vuelta (zonas) ...", flush=True)
    thD, loD, hiD, _, _, XD, _ = ei_par(m_d, cols_o5, cols_d4)
    print("[*] EI 2022 1ª → 2026 2ª vuelta (zonas) ...", flush=True)
    thF, loF, hiF, _, _, XF, _ = ei_par(m_f, cols_o5, cols_d4)
    print("[*] EI 2022 2ª → 2026 2ª vuelta (zonas) ...", flush=True)
    thE, loE, hiE, _, _, XE, _ = ei_par(m_e, cols_o4, cols_d4)

    for th, lo, ld, nombre in (
            (thD, ANIOS[2026]["labels"], LABELS_2026_2T, "2026_1t_2t"),
            (thF, ANIOS[2022]["labels"], LABELS_2026_2T, "2022_1t_2026_2t"),
            (thE, LABELS_2022_2T, LABELS_2026_2T, "2022_2t_2026_2t")):
        pd.DataFrame(th, index=lo, columns=ld).to_csv(
            os.path.join(OUT_DIR, f"transicion_nacional_{nombre}.csv"))
        print(f"\n=== Transición {nombre} ===", flush=True)
        print((pd.DataFrame(th, index=lo, columns=ld) * 100).round(1).to_string(),
              flush=True)

    heatmap(thD, loD, hiD, ANIOS[2026]["labels"], LABELS_2026_2T, XD.sum(0),
            "Transición — Brasil 2026 1ª → 2ª vuelta (%)",
            os.path.join(OUT_DIR, "heatmap_2026_1t_2t.png"))
    heatmap(thF, loF, hiF, ANIOS[2022]["labels"], LABELS_2026_2T, XF.sum(0),
            "Transición — Brasil 2022 1ª → 2026 2ª vuelta (%)",
            os.path.join(OUT_DIR, "heatmap_2022_1t_2026_2t.png"))
    heatmap(thE, loE, hiE, LABELS_2022_2T, LABELS_2026_2T, XE.sum(0),
            "Transición — Brasil 2022 2ª → 2026 2ª vuelta (%)",
            os.path.join(OUT_DIR, "heatmap_2022_2t_2026_2t.png"))
    sankey_par(thD, XD.sum(0), ANIOS[2026]["labels"], LABELS_2026_2T,
               "Migración de votos — Brasil 2026 1ª → 2ª vuelta (personas, zonas)",
               "sankey_2026_1t_2t")
    sankey_par(thF, XF.sum(0), ANIOS[2022]["labels"], LABELS_2026_2T,
               "Migración de votos — Brasil 2022 1ª → 2026 2ª vuelta "
               "(personas, zonas)", "sankey_2022_1t_2026_2t")
    sankey_par(thE, XE.sum(0), LABELS_2022_2T, LABELS_2026_2T,
               "Migración de votos — Brasil 2022 2ª → 2026 2ª vuelta "
               "(personas, zonas)", "sankey_2022_2t_2026_2t")

    p = os.path.join(OUT_DIR, "resumen_ei.json")
    res = json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}
    res.setdefault("n_emparejadas", {})
    res["n_emparejadas"]["2026_1t_2t_zonas"] = int(len(m_d))
    res["n_emparejadas"]["2022_1t_2026_2t_zonas"] = int(len(m_f))
    res["n_emparejadas"]["2022_2t_2026_2t_zonas"] = int(len(m_e))
    res.setdefault("labels", {})
    res["labels"]["2026_2t"] = LABELS_2026_2T
    res.setdefault("N_o", {})
    res["N_o"]["2026_1t"] = XD.sum(0).tolist()
    res["N_o"]["2022_1t"] = XF.sum(0).tolist()
    res["N_o"]["2022_2t"] = XE.sum(0).tolist()
    res["transicion_2026_1t_2t"] = thD.tolist()
    res["transicion_2022_1t_2026_2t"] = thF.tolist()
    res["transicion_2022_2t_2026_2t"] = thE.tolist()
    res["nota_2t"] = ("2026 1T->2T, 2022 1T->2026 2T y 2022 2T->2026 2T se "
                      "estiman por zona porque el TSE aún no publica la votación "
                      "por sección de la 2ª vuelta 2026.")
    json.dump(res, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"\n[OK] Salidas 2T en {OUT_DIR}", flush=True)


def main():
    if "--solo-2t" in sys.argv:
        solo_2t()
        return
    if "--solo-graficos" in sys.argv:
        solo_graficos()
        return
    print("[*] Cargando secciones 2018 / 2022 (1T y 2T) / 2026 1T y zonas 2T...")
    d18 = cargar_anio(2018, "1")
    d22 = cargar_anio(2022, "1")
    d22b = cargar_anio(2022, "2")
    d26 = cargar_anio(2026, "1")
    # Los pares con 2T 2026 se estiman a nivel de ZONA: el TSE todavía no
    # publica la votación por sección de la 2ª vuelta 2026.
    d26z = cargar_anio(2026, "1", nivel="zona")
    d22z = cargar_anio(2022, "1", nivel="zona")
    d22bz = cargar_anio(2022, "2", nivel="zona")
    d26b = cargar_anio(2026, "2", nivel="zona")

    m_a = emparejar(d18, d22)
    m_b = emparejar(d22, d26)
    m_c = emparejar(d22, d22b)
    m_d = emparejar(d26z, d26b, CLAVE_ZONA)
    m_e = emparejar(d22bz, d26b, CLAVE_ZONA)
    m_f = emparejar(d22z, d26b, CLAVE_ZONA)
    print(f"    emparejadas 2018-2022: {len(m_a)} | 2022-2026: {len(m_b)} | "
          f"2022 1T-2T: {len(m_c)}")
    print(f"    emparejadas 2026 1T-2T: {len(m_d)} | 2022 1T-2026 2T: {len(m_f)} | "
          f"2022 2T-2026 2T: {len(m_e)} (zonas)")

    cols_o5 = [c + "_o" for c in COLS5]
    cols_d5 = [c + "_d" for c in COLS5]
    cols_o4 = [c + "_o" for c in COLS4]
    cols_d4 = [c + "_d" for c in COLS4]

    print("[*] EI 2018 → 2022 ...")
    thA, loA, hiA, _, mfA, XA, _ = ei_par(m_a, cols_o5, cols_d5)
    print("[*] EI 2022 → 2026 ...")
    thB, loB, hiB, _, mfB, XB, _ = ei_par(m_b, cols_o5, cols_d5)
    print("[*] EI 2022 1ª → 2ª vuelta ...")
    thC, loC, hiC, _, mfC, XC, _ = ei_par(m_c, cols_o5, cols_d4)
    print("[*] EI 2026 1ª → 2ª vuelta (zonas) ...")
    thD, loD, hiD, _, mfD, XD, _ = ei_par(m_d, cols_o5, cols_d4)
    print("[*] EI 2022 1ª → 2026 2ª vuelta (zonas) ...")
    thF, loF, hiF, _, mfF, XF, _ = ei_par(m_f, cols_o5, cols_d4)
    print("[*] EI 2022 2ª → 2026 2ª vuelta (zonas) ...")
    thE, loE, hiE, _, mfE, XE, _ = ei_par(m_e, cols_o4, cols_d4)

    trans = (
        (thA, ANIOS[2018]["labels"], ANIOS[2022]["labels"], "2018_2022"),
        (thB, ANIOS[2022]["labels"], ANIOS[2026]["labels"], "2022_2026"),
        (thC, ANIOS[2022]["labels"], LABELS_2022_2T, "2022_1t_2t"),
        (thD, ANIOS[2026]["labels"], LABELS_2026_2T, "2026_1t_2t"),
        (thF, ANIOS[2022]["labels"], LABELS_2026_2T, "2022_1t_2026_2t"),
        (thE, LABELS_2022_2T, LABELS_2026_2T, "2022_2t_2026_2t"),
    )
    for th, lo, ld, nombre in trans:
        pd.DataFrame(th, index=lo, columns=ld).to_csv(
            os.path.join(OUT_DIR, f"transicion_nacional_{nombre}.csv"))
        print(f"\n=== Transición {nombre} ===")
        print((pd.DataFrame(th, index=lo, columns=ld) * 100).round(1).to_string())

    th_markov = thA @ thB
    pd.DataFrame(th_markov, index=ANIOS[2018]["labels"], columns=ANIOS[2026]["labels"]).to_csv(
        os.path.join(OUT_DIR, "transicion_2018_2026_markov.csv"))

    filas = []
    for reg, g in mfB.groupby("region"):
        if len(g) < 500:
            continue
        Xr, Yr = _mat(g, cols_o5, cols_d5)
        th = em_transicion(Xr, Yr)
        for j, oj in enumerate(ANIOS[2022]["labels"]):
            for k, dk in enumerate(ANIOS[2026]["labels"]):
                filas.append({"region": reg, "origen": oj, "destino": dk, "p": th[j, k]})
    pd.DataFrame(filas).to_csv(os.path.join(OUT_DIR, "transicion_por_region.csv"), index=False)

    # Gráficos 4:3 con absolutos (millones) por fila, columna y celda
    heatmap(thA, loA, hiA, ANIOS[2018]["labels"], ANIOS[2022]["labels"], XA.sum(0),
            "Transición de votos — Brasil 2018 → 2022 (%)", os.path.join(OUT_DIR, "heatmap_2018_2022.png"))
    heatmap(thB, loB, hiB, ANIOS[2022]["labels"], ANIOS[2026]["labels"], XB.sum(0),
            "Transición de votos — Brasil 2022 → 2026 (%)", os.path.join(OUT_DIR, "heatmap_2022_2026.png"))
    heatmap(thC, loC, hiC, ANIOS[2022]["labels"], LABELS_2022_2T, XC.sum(0),
            "Transición — Brasil 2022 1ª → 2ª vuelta (%)", os.path.join(OUT_DIR, "heatmap_2022_1t_2t.png"))
    heatmap(thD, loD, hiD, ANIOS[2026]["labels"], LABELS_2026_2T, XD.sum(0),
            "Transición — Brasil 2026 1ª → 2ª vuelta (%)",
            os.path.join(OUT_DIR, "heatmap_2026_1t_2t.png"))
    heatmap(thF, loF, hiF, ANIOS[2022]["labels"], LABELS_2026_2T, XF.sum(0),
            "Transición — Brasil 2022 1ª → 2026 2ª vuelta (%)",
            os.path.join(OUT_DIR, "heatmap_2022_1t_2026_2t.png"))
    heatmap(thE, loE, hiE, LABELS_2022_2T, LABELS_2026_2T, XE.sum(0),
            "Transición — Brasil 2022 2ª → 2026 2ª vuelta (%)",
            os.path.join(OUT_DIR, "heatmap_2022_2t_2026_2t.png"))
    heatmap(th_markov, None, None, ANIOS[2018]["labels"], ANIOS[2026]["labels"], XA.sum(0),
            "Transición encadenada — Brasil 2018 → 2026 (Markov, %)", os.path.join(OUT_DIR, "heatmap_2018_2026.png"))

    sankey_par(thA, XA.sum(0), ANIOS[2018]["labels"], ANIOS[2022]["labels"],
               "Migración de votos — Brasil 2018 → 2022 (personas)", "sankey_2018_2022")
    sankey_par(thB, XB.sum(0), ANIOS[2022]["labels"], ANIOS[2026]["labels"],
               "Migración de votos — Brasil 2022 → 2026 (personas)", "sankey_2022_2026")
    sankey_par(thC, XC.sum(0), ANIOS[2022]["labels"], LABELS_2022_2T,
               "Migración de votos — Brasil 2022 1ª → 2ª vuelta (personas)", "sankey_2022_1t_2t")
    sankey_par(thD, XD.sum(0), ANIOS[2026]["labels"], LABELS_2026_2T,
               "Migración de votos — Brasil 2026 1ª → 2ª vuelta (personas, zonas)",
               "sankey_2026_1t_2t")
    sankey_par(thF, XF.sum(0), ANIOS[2022]["labels"], LABELS_2026_2T,
               "Migración de votos — Brasil 2022 1ª → 2026 2ª vuelta (personas, zonas)",
               "sankey_2022_1t_2026_2t")
    sankey_par(thE, XE.sum(0), LABELS_2022_2T, LABELS_2026_2T,
               "Migración de votos — Brasil 2022 2ª → 2026 2ª vuelta (personas, zonas)",
               "sankey_2022_2t_2026_2t")
    sankey_tres(thA, XA.sum(0), thB, XB.sum(0), ANIOS[2018]["labels"],
                ANIOS[2022]["labels"], ANIOS[2026]["labels"], "sankey_2018_2022_2026")

    open(os.path.join(OUT_DIR, "informe_migracion_2022_2026_es.md"), "w", encoding="utf-8").write(
        reporte_es(thB, XB.sum(0), thC, XC.sum(0), thA, XA.sum(0), th_markov,
               thD, XD.sum(0), thE, XE.sum(0), thF, XF.sum(0)))
    open(os.path.join(OUT_DIR, "relatorio_migracao_2022_2026_pt.md"), "w", encoding="utf-8").write(
        reporte_pt(thB, XB.sum(0), thC, XC.sum(0), thA, XA.sum(0), th_markov,
               thD, XD.sum(0), thE, XE.sum(0), thF, XF.sum(0)))

    res = {
        "n_emparejadas": {"2018_2022": int(len(m_a)), "2022_2026": int(len(m_b)),
                          "2022_1t_2t": int(len(m_c)),
                          "2026_1t_2t_zonas": int(len(m_d)),
                          "2022_1t_2026_2t_zonas": int(len(m_f)),
                          "2022_2t_2026_2t_zonas": int(len(m_e))},
        "labels": {"2018": ANIOS[2018]["labels"], "2022": ANIOS[2022]["labels"],
                   "2022_2t": LABELS_2022_2T, "2026": ANIOS[2026]["labels"],
                   "2026_2t": LABELS_2026_2T},
        "N_o": {"2018": XA.sum(0).tolist(), "2022": XB.sum(0).tolist(),
                "2026_1t": XD.sum(0).tolist(), "2022_1t": XF.sum(0).tolist(),
                "2022_2t": XE.sum(0).tolist()},
        "transicion_2018_2022": thA.tolist(),
        "transicion_2022_2026": thB.tolist(),
        "transicion_2022_1t_2t": thC.tolist(),
        "transicion_2026_1t_2t": thD.tolist(),
        "transicion_2022_1t_2026_2t": thF.tolist(),
        "transicion_2022_2t_2026_2t": thE.tolist(),
        "transicion_2018_2026_markov": th_markov.tolist(),
        "nota_3vias": "2018->2026 es el encadenado de los pares (Markov).",
        "nota_2t": ("2026 1T->2T, 2022 1T->2026 2T y 2022 2T->2026 2T se estiman "
                    "por zona porque el TSE aún no publica la votación por sección "
                    "de la 2ª vuelta 2026."),
    }
    json.dump(res, open(os.path.join(OUT_DIR, "resumen_ei.json"), "w"),
              ensure_ascii=False, indent=2)
    print(f"\n[OK] Salidas en {OUT_DIR}")


if __name__ == "__main__":
    main()
