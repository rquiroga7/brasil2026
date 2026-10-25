# -*- coding: utf-8 -*-
"""
reconstruir_1t.py — Reconstruye la base de la 1ª vuelta 2026 por zona (y por
municipio) a partir de los datos abiertos del TSE ya descargados.

Salidas (D:\\brasil2026_data):
  escrutinio_zonas_2026.csv   (formato "vivo", por zona, para la 1ª vuelta y como
                               base del swing 1T->2T)
  base_1t_municipios.csv      (agregado por municipio TSE)
"""

import os
import numpy as np
import pandas as pd

import rutas_datos as rd

SEC = rd.ruta_dir("secciones")
OUT_ZONAS = rd.ruta("escrutinio_zonas_2026.csv")
OUT_MUN = rd.ruta("base_1t_municipios.csv")

CAND_NUM = {"13": "Lula", "22": "Flavio_Bolsonaro", "70": "Augusto_Cury",
            "55": "Ronaldo_Caiado", "30": "Romeu_Zema", "14": "Renan_Santos",
            "16": "Hertz_Dias", "21": "Edmilson_Costa", "27": "Clariana_Barao",
            "29": "Rui_Costa_Pimenta", "35": "Wilson_Grassi", "80": "Samara_Martins"}
HEADER = (["hora_local", "hora_tse", "estado_uf", "codigo_municipio", "municipio",
           "zona_electoral", "secoes_totalizadas", "electores", "votos_totales"]
          + list(CAND_NUM.values()) + ["votos_blancos", "votos_nulos", "numero_pasada"])


def main():
    clave = ["uf", "mun", "zona", "secao"]
    d = pd.read_csv(os.path.join(SEC, "secciones_presidente_2026_1t.csv"), dtype=str)
    det = pd.read_csv(os.path.join(SEC, "secciones_detalle_2026.csv"), dtype=str)
    for c in [c for c in d.columns if c not in clave]:
        d[c] = pd.to_numeric(d[c], errors="coerce").fillna(0)
    det["aptos"] = pd.to_numeric(det["aptos"], errors="coerce").fillna(0)
    det["ts"] = pd.to_datetime(det["prim_parcial"], format="%d/%m/%Y %H:%M:%S", errors="coerce")
    m = d.merge(det[clave + ["aptos", "ts"]], on=clave, how="left")

    agg = {name: (num, "sum") for num, name in CAND_NUM.items()}
    g = m.groupby(["uf", "mun", "zona"], as_index=False).agg(
        votos_totales=("total" if "total" in m.columns else "13", "sum"),
        votos_blancos=("branco", "sum"), votos_nulos=("nulo", "sum"),
        secoes_totalizadas=("secao", "size"), electores=("aptos", "sum"),
        hora=("ts", "max"), **agg)
    # votos_totales = suma de candidatos + blancos + nulos
    cands = list(CAND_NUM.values())
    g["votos_totales"] = g[cands].sum(axis=1) + g["votos_blancos"] + g["votos_nulos"]

    g["hora_local"] = g["hora"].dt.strftime("%Y-%m-%d %H:%M:%S")
    g["hora_tse"] = g["hora"].dt.strftime("%d/%m/%Y %H:%M:%S")
    g["estado_uf"] = g["uf"].str.upper()
    g["codigo_municipio"] = g["mun"]
    g["municipio"] = ""
    g["zona_electoral"] = g["zona"]
    g["numero_pasada"] = 1
    g[HEADER].to_csv(OUT_ZONAS, index=False)
    print(f"[OK] {len(g)} zonas -> {OUT_ZONAS}")

    gm = g.groupby(["uf", "mun"], as_index=False).agg(
        lula=("Lula", "sum"), flavio=("Flavio_Bolsonaro", "sum"),
        otros=("Augusto_Cury", "sum"), otros2=("Ronaldo_Caiado", "sum"),
        otros3=("Romeu_Zema", "sum"), otros4=("Renan_Santos", "sum"),
        otros5=("Hertz_Dias", "sum"), otros6=("Edmilson_Costa", "sum"),
        otros7=("Clariana_Barao", "sum"), otros8=("Rui_Costa_Pimenta", "sum"),
        otros9=("Wilson_Grassi", "sum"), otros10=("Samara_Martins", "sum"),
        blancos=("votos_blancos", "sum"), nulos=("votos_nulos", "sum"),
        aptos=("electores", "sum"))
    otros_cols = ["otros", "otros2", "otros3", "otros4", "otros5", "otros6",
                  "otros7", "otros8", "otros9", "otros10"]
    gm["validos"] = gm["lula"] + gm["flavio"] + gm[otros_cols].sum(axis=1)
    gm["comparecimento"] = gm["validos"] + gm["blancos"] + gm["nulos"]
    gm = gm.rename(columns={"otros": "otros_total"})
    gm[["uf", "mun", "lula", "flavio", "validos", "aptos", "comparecimento"]].to_csv(
        OUT_MUN, index=False)
    print(f"[OK] {len(gm)} municipios -> {OUT_MUN}")


if __name__ == "__main__":
    main()
