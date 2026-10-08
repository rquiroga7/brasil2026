# -*- coding: utf-8 -*-
"""
descargar_secciones.py — Arma la base por SECCIÓN electoral (la urna) para
Presidente, 1er turno, 2022 y 2026, a partir de los datos abiertos del TSE.

Los zip 'votacao_secao_AAAA_BR.zip' contienen SOLO Presidente (todos los estados
+ exterior). Para cada sección se pivotea el voto por número de candidato, más
blanco (95) y nulo (96).

Salidas (D:\\brasil2026_data\\secciones\\):
  secciones_presidente_2022_1t.csv
  secciones_presidente_2026_1t.csv
  resumen_secciones.json

Requiere los zip ya descargados (o los baja si falta).
"""

import os
import io
import json
import sys
import zipfile

import requests
import pandas as pd

import rutas_datos as rd

SEC_DIR = rd.ruta_dir("secciones")
URL = "https://cdn.tse.jus.br/estatistica/sead/odsele/votacao_secao/votacao_secao_{y}_BR.zip"
URL_DETALLE = ("https://cdn.tse.jus.br/estatistica/sead/odsele/detalhe_votacao_secao/"
               "detalhe_votacao_secao_{y}.zip")
COLS = ["SG_UF", "CD_MUNICIPIO", "NR_ZONA", "NR_SECAO",
        "CD_CARGO", "NR_TURNO", "NR_VOTAVEL", "NM_VOTAVEL", "QT_VOTOS"]
COLS_DET = ["SG_UF", "CD_MUNICIPIO", "NR_ZONA", "NR_SECAO", "NR_TURNO",
            "QT_APTOS", "QT_COMPARECIMENTO", "QT_ABSTENCOES",
            "DT_RECEBIMENTO_BU_HOR_TSE", "DT_PRIM_TOT_PARCIAL_HOR_TSE"]
BRANCO, NULO = "95", "96"


def descargar(y):
    destino = os.path.join(SEC_DIR, f"votacao_secao_{y}_BR.zip")
    if os.path.exists(destino):
        print(f"[=] Ya existe {os.path.basename(destino)} "
              f"({os.path.getsize(destino)/1e6:.1f} MB)")
        return destino
    url = URL.format(y=y)
    print(f"[*] Descargando {url}")
    with requests.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(destino, "wb") as f:
            for bloque in r.iter_content(chunk_size=1024 * 512):
                f.write(bloque)
    return destino


def _nom_vot(y, turno):
    return f"secciones_presidente_{y}_{turno}t.csv"


def _nom_det(y, turno):
    return (f"secciones_detalle_{y}.csv" if turno == "1"
            else f"secciones_detalle_{y}_{turno}t.csv")


def construir(y, turno="1"):
    salida = os.path.join(SEC_DIR, _nom_vot(y, turno))
    if os.path.exists(salida):
        cols = list(pd.read_csv(salida, nrows=0).columns)
        cands = [c for c in cols if c not in ("uf", "mun", "zona", "secao",
                                              "branco", "nulo", "total")]
        n = sum(1 for _ in open(salida, encoding="utf-8")) - 1
        print(f"[=] Ya existe {os.path.basename(salida)} ({n} secciones)")
        return {"anio": y, "turno": turno, "n_secciones": int(n),
                "candidatos": {c: "" for c in cands}, "columnas": cols}

    zp = descargar(y)
    z = zipfile.ZipFile(zp)
    nombre = [n for n in z.namelist() if n.lower().endswith(".csv")][0]
    print(f"[*] Leyendo {nombre} de {os.path.basename(zp)}...")

    acum = None
    nombres = {}
    with z.open(nombre) as raw:
        for chunk in pd.read_csv(raw, sep=";", encoding="latin-1", dtype=str,
                                 usecols=COLS, chunksize=1_000_000,
                                 on_bad_lines="skip"):
            chunk = chunk[(chunk["CD_CARGO"] == "1") & (chunk["NR_TURNO"] == turno)]
            if chunk.empty:
                continue
            chunk["QT_VOTOS"] = pd.to_numeric(chunk["QT_VOTOS"], errors="coerce").fillna(0)
            for num, nm in chunk[["NR_VOTAVEL", "NM_VOTAVEL"]].drop_duplicates().itertuples(index=False):
                nombres.setdefault(num, nm)
            g = chunk.groupby(["SG_UF", "CD_MUNICIPIO", "NR_ZONA", "NR_SECAO",
                               "NR_VOTAVEL"])["QT_VOTOS"].sum()
            acum = g if acum is None else acum.add(g, fill_value=0)

    df = acum.reset_index()
    df["SG_UF"] = df["SG_UF"].str.upper()
    df["CD_MUNICIPIO"] = df["CD_MUNICIPIO"].str.zfill(5)
    df["NR_ZONA"] = df["NR_ZONA"].str.zfill(4)
    df["NR_SECAO"] = df["NR_SECAO"].str.zfill(4)

    wide = df.pivot_table(index=["SG_UF", "CD_MUNICIPIO", "NR_ZONA", "NR_SECAO"],
                          columns="NR_VOTAVEL", values="QT_VOTOS",
                          fill_value=0, aggfunc="sum").reset_index()
    wide.columns.name = None
    wide = wide.rename(columns={"SG_UF": "uf", "CD_MUNICIPIO": "mun",
                                "NR_ZONA": "zona", "NR_SECAO": "secao"})
    for c in [c for c in wide.columns if c not in ("uf", "mun", "zona", "secao")]:
        wide[c] = pd.to_numeric(wide[c], errors="coerce").fillna(0).astype("int64")

    cands = sorted([c for c in wide.columns if c not in ("uf", "mun", "zona", "secao")
                    and c not in (BRANCO, NULO)], key=lambda x: int(x))
    wide["branco"] = wide.get(BRANCO, 0)
    wide["nulo"] = wide.get(NULO, 0)
    wide = wide.drop(columns=[c for c in (BRANCO, NULO) if c in wide.columns])
    wide["total"] = wide[cands].sum(axis=1) + wide["branco"] + wide["nulo"]

    salida = os.path.join(SEC_DIR, _nom_vot(y, turno))
    wide.to_csv(salida, index=False)
    print(f"[OK] {len(wide)} secciones -> {salida}")
    print(f"     candidatos: {cands}")
    return {"anio": y, "turno": turno, "n_secciones": int(len(wide)),
            "candidatos": {n: nombres.get(n, "") for n in cands},
            "columnas": list(wide.columns)}


def descargar_detalle(y):
    destino = os.path.join(SEC_DIR, f"detalhe_votacao_secao_{y}.zip")
    if os.path.exists(destino):
        print(f"[=] Ya existe {os.path.basename(destino)} "
              f"({os.path.getsize(destino)/1e6:.1f} MB)")
        return destino
    url = URL_DETALLE.format(y=y)
    print(f"[*] Descargando {url}")
    with requests.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(destino, "wb") as f:
            for bloque in r.iter_content(chunk_size=1024 * 512):
                f.write(bloque)
    return destino


def construir_detalle(y, turno="1"):
    """Aptos, comparecimento, abstención y marcas de tiempo por sección.

    Los CSV del zip vienen por UF (y un BRASIL que se ignora para no duplicar).
    El apto es el mismo para todos los cargos de una sección, así que se toma una
    fila por sección."""
    salida = os.path.join(SEC_DIR, _nom_det(y, turno))
    if os.path.exists(salida):
        n = sum(1 for _ in open(salida, encoding="utf-8")) - 1
        print(f"[=] Ya existe {os.path.basename(salida)} ({n} secciones)")
        return {"anio": y, "turno": turno, "n_secciones_detalle": int(n)}

    zp = descargar_detalle(y)
    z = zipfile.ZipFile(zp)
    clave = ["SG_UF", "CD_MUNICIPIO", "NR_ZONA", "NR_SECAO"]
    partes = []
    for nombre in z.namelist():
        if not nombre.lower().endswith(".csv") or "BRASIL" in nombre.upper():
            continue
        with z.open(nombre) as raw:
            for chunk in pd.read_csv(raw, sep=";", encoding="latin-1", dtype=str,
                                     usecols=COLS_DET, chunksize=1_000_000,
                                     on_bad_lines="skip"):
                chunk = chunk[chunk["NR_TURNO"] == turno].drop_duplicates(subset=clave)
                if not chunk.empty:
                    partes.append(chunk)
    df = pd.concat(partes, ignore_index=True).drop_duplicates(subset=clave)
    df["SG_UF"] = df["SG_UF"].str.upper()
    df["CD_MUNICIPIO"] = df["CD_MUNICIPIO"].str.zfill(5)
    df["NR_ZONA"] = df["NR_ZONA"].str.zfill(4)
    df["NR_SECAO"] = df["NR_SECAO"].str.zfill(4)
    for c in ["QT_APTOS", "QT_COMPARECIMENTO", "QT_ABSTENCOES"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).astype("int64")
    df = df.rename(columns={"SG_UF": "uf", "CD_MUNICIPIO": "mun",
                            "NR_ZONA": "zona", "NR_SECAO": "secao",
                            "QT_APTOS": "aptos", "QT_COMPARECIMENTO": "comparecimento",
                            "QT_ABSTENCOES": "abstencoes",
                            "DT_RECEBIMENTO_BU_HOR_TSE": "recebimento_bu",
                            "DT_PRIM_TOT_PARCIAL_HOR_TSE": "prim_parcial"})
    salida = os.path.join(SEC_DIR, _nom_det(y, turno))
    df.to_csv(salida, index=False)
    print(f"[OK] {len(df)} secciones (detalle) -> {salida}")
    return {"anio": y, "turno": turno, "n_secciones_detalle": int(len(df))}


def main():
    anios = (2018, 2022, 2026)
    solo_det = "--solo-detalle" in sys.argv
    resumen = []
    if solo_det:
        p = os.path.join(SEC_DIR, "resumen_secciones.json")
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                resumen = json.load(f)
    else:
        for y in anios:
            resumen.append(construir(y, "1"))
        resumen.append(construir(2022, "2"))
    for y in anios:
        construir_detalle(y, "1")
    construir_detalle(2022, "2")
    with open(os.path.join(SEC_DIR, "resumen_secciones.json"), "w", encoding="utf-8") as f:
        json.dump(resumen, f, ensure_ascii=False, indent=2)
    print("[OK] resumen_secciones.json")


if __name__ == "__main__":
    main()
