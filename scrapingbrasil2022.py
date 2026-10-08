# -*- coding: utf-8 -*-
"""
Descarga los resultados de las Elecciones Generales 2022 (Presidente) desde el
repositorio de datos abiertos del TSE y genera dos productos:

1) SERIE TEMPORAL NACIONAL (oficial, orden real de llegada de los votos)
   A partir de los archivos "Historico_Totalizacao_Presidente_BR_{1T,2T}_2022.zip".
   Cada fila es un instante DT_TOTALIZACAO con los acumulados y el
   PE_SECOES_TOT_ACUMULADO = % de secciones cargadas. Ideal para medir la
   evolucion de una proyeccion a medida que entra mas data.
   Salidas: historico_nacional_2022_1t.csv / historico_nacional_2022_2t.csv

2) BASE GEOGRAFICA FINAL (municipio + zona, 1er y 2do turno)
   A partir de votacao_candidato_munzona_2022.zip + detalhe_votacao_munzona_2022.zip.
   No tiene marcas de tiempo (es el resultado consolidado), pero sirve para
   simular ordenes de carga por region con simular_parciales_2022.py.
   Salidas: escrutinio_zonas_2022.csv / candidatos_2022.csv

La API JSON en vivo (resultados.tse.jus.br/oficial/ele2022/...) ya no existe:
el config actual del TSE solo sirve ele2024 y ele2026.
"""

import os
import io
import csv
import sys
import zipfile
import argparse
import requests
from datetime import datetime

BASE_CDN = "https://cdn.tse.jus.br/estatistica/sead"

URL_HIST = {
    "1T": f"{BASE_CDN}/eleicoes/eleicoes2022/Historico_Totalizacao_Presidente_BR_1T_2022.zip",
    "2T": f"{BASE_CDN}/eleicoes/eleicoes2022/Historico_Totalizacao_Presidente_BR_2T_2022.zip",
}
URL_CANDIDATOS = f"{BASE_CDN}/odsele/votacao_candidato_munzona/votacao_candidato_munzona_2022.zip"
URL_DETALHE    = f"{BASE_CDN}/odsele/detalhe_votacao_munzona/detalhe_votacao_munzona_2022.zip"

import rutas_datos as rd

ARCHIVO_ZONAS = rd.ruta("escrutinio_zonas_2022.csv")
ARCHIVO_CAND  = rd.ruta("candidatos_2022.csv")
CARPETA_DATOS = rd.ruta_dir("dados_tse_2022")
COD_CARGO_PRES = "1"

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                         "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}

# Posiciones (0-based) de detalhe_votacao_munzona (ver leiame.pdf oficial)
D_UF, D_MUN, D_ZONA, D_TURNO, D_CARGO = 10, 13, 15, 5, 16
D_APTO, D_COMP, D_BRANCOS, D_NULOS = 18, 23, 40, 41


def entero(valor):
    try:
        return int(str(valor).strip())
    except (TypeError, ValueError):
        return 0


def descargar(url, destino):
    """Descarga con reanudacion (Range) e indicador de progreso."""
    if os.path.exists(destino):
        print(f"[=] Ya existe {os.path.basename(destino)} ({os.path.getsize(destino)/1e6:.1f} MB)")
        return
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    parcial = destino + ".part"
    existente = os.path.getsize(parcial) if os.path.exists(parcial) else 0

    cabeceras = dict(HEADERS)
    modo = "wb"
    if existente:
        cabeceras["Range"] = f"bytes={existente}-"
        modo = "ab"

    print(f"[*] Descargando {os.path.basename(destino)}"
          + (f" (reanudando en {existente/1e6:.1f} MB)" if existente else ""))
    with requests.get(url, headers=cabeceras, stream=True, timeout=60) as r:
        if r.status_code not in (200, 206):
            r.raise_for_status()
        total = int(r.headers.get("Content-Length", 0)) + existente
        escritos = existente
        ultimo_print = 0
        with open(parcial, modo) as f:
            for bloque in r.iter_content(chunk_size=1024 * 256):
                if not bloque:
                    continue
                f.write(bloque)
                escritos += len(bloque)
                if total and (escritos - ultimo_print) > 50e6:
                    ultimo_print = escritos
                    print(f"    {escritos/1e6:7.1f} / {total/1e6:.1f} MB "
                          f"({100*escritos/total:5.1f}%)")

    os.replace(parcial, destino)
    print(f"[OK] {os.path.basename(destino)} listo ({os.path.getsize(destino)/1e6:.1f} MB)")


# ---------------------------------------------------------------------------
# 1) SERIE TEMPORAL NACIONAL (Historico de Totalizacao)
# ---------------------------------------------------------------------------
def nombre_desde_token(token):
    return token.replace("_", " ").title()


def parsear_historico(ruta_zip, turno):
    with zipfile.ZipFile(ruta_zip) as zf:
        nombre_csv = next(n for n in zf.namelist() if n.lower().endswith(".csv"))
        with zf.open(nombre_csv) as raw:
            texto = io.TextIOWrapper(raw, encoding="latin-1", newline="")
            lector = csv.reader(texto, delimiter=";")
            cabecera = [c.strip().lstrip("\ufeff") for c in next(lector)]
            ix = {c: i for i, c in enumerate(cabecera)}

            idx_dt = ix["DT_TOTALIZACAO"]
            idx_pe = ix.get("PE_SECOES_TOT_ACUMULADO")
            idx_sec_ac = ix.get("QT_SECOES_TOT_ACUMULADO")
            idx_sec_tot = ix.get("QT_SECOES_TOTAL")
            idx_aptos_tot = ix.get("QT_APTOS_TOTAL")
            idx_votos_ac = ix.get("QT_VOTOS_TOTAL_ACUMULADO")
            idx_conc_ac = ix.get("QT_VOTOS_CONCORRENTES_ACUMULADO")

            candidatos = []          # [(token, idx_votos, idx_pe)]
            for campo in cabecera:
                if campo.endswith("_QT_VOTOS_TOT_ACUMULADO") and not campo.startswith(("BRANCO", "NULO")):
                    token = campo[:-len("_QT_VOTOS_TOT_ACUMULADO")]
                    idx_pe_cand = ix.get(f"{token}_PE_VOTOS_TOT_ACUMULADO")
                    candidatos.append((token, ix[campo], idx_pe_cand))

            idx_branco = ix.get("BRANCO_QT_VOTOS_TOT_ACUMULADO")
            idx_nulo = ix.get("NULO_QT_VOTOS_TOT_ACUMULADO")
            idx_branco_pe = ix.get("BRANCO_PE_VOTOS_TOT_ACUMULADO")
            idx_nulo_pe = ix.get("NULO_PE_VOTOS_TOT_ACUMULADO")

            salida = rd.ruta(f"historico_nacional_2022_{turno.lower()}.csv")
            cab = (["dt_totalizacao", "ts", "pe_secoes_acumulado", "secoes_acumulado",
                    "secoes_total", "aptos_total", "votos_acumulado",
                    "votos_concorrentes_acumulado"]
                   + [f"{t}_votos" for t, _, _ in candidatos]
                   + [f"{t}_pe" for t, _, _ in candidatos]
                   + ["branco", "nulo", "branco_pe", "nulo_pe"])

            filas = 0
            with open(salida, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(cab)
                for fila in lector:
                    if len(fila) <= idx_dt:
                        continue
                    dt = fila[idx_dt].strip()
                    try:
                        ts = datetime.strptime(dt, "%d/%m/%Y %H:%M:%S").isoformat(sep=" ")
                    except ValueError:
                        ts = ""
                    def val(i):
                        return fila[i].strip() if i is not None and i < len(fila) else ""
                    linea = [dt, ts, val(idx_pe), val(idx_sec_ac), val(idx_sec_tot),
                             val(idx_aptos_tot), val(idx_votos_ac), val(idx_conc_ac)]
                    linea += [val(i) for _, i, _ in candidatos]
                    linea += [val(i) for _, _, i in candidatos]
                    linea += [val(idx_branco), val(idx_nulo), val(idx_branco_pe), val(idx_nulo_pe)]
                    w.writerow(linea)
                    filas += 1
    print(f"[OK] {filas} instantaneos -> {salida}")
    return salida


# ---------------------------------------------------------------------------
# 2) BASE GEOGRAFICA FINAL (municipio + zona)
# ---------------------------------------------------------------------------
def cargar_votos_candidatos(ruta_zip, solo_presidente=True):
    registro = {}
    municipios = {}
    candidatos = {}
    with zipfile.ZipFile(ruta_zip) as zf:
        for nombre in sorted(zf.namelist()):
            if not nombre.lower().endswith(".csv"):
                continue
            print(f" -> Procesando {nombre}")
            with zf.open(nombre) as raw:
                texto = io.TextIOWrapper(raw, encoding="latin-1", newline="")
                lector = csv.reader(texto, delimiter=";")
                try:
                    cabecera = [c.lstrip("\ufeff").strip('"') for c in next(lector)]
                except StopIteration:
                    continue
                ix = {col: i for i, col in enumerate(cabecera)}
                if "QT_VOTOS_NOMINAIS" not in ix:
                    continue

                for fila in lector:
                    if len(fila) < len(cabecera):
                        continue
                    if solo_presidente and fila[ix["CD_CARGO"]].strip('"') != COD_CARGO_PRES:
                        continue
                    uf = fila[ix["SG_UF"]].strip('"')
                    mun = fila[ix["CD_MUNICIPIO"]].strip('"')
                    zona = fila[ix["NR_ZONA"]].strip('"').zfill(4)
                    turno = fila[ix["NR_TURNO"]].strip('"')
                    num = fila[ix["NR_CANDIDATO"]].strip('"')
                    if not num.isdigit():
                        continue
                    candidatos[num] = (fila[ix["NM_URNA_CANDIDATO"]].strip('"'),
                                       fila[ix["SG_PARTIDO"]].strip('"'))
                    clave = (uf, mun, zona, turno)
                    votos = fila[ix["QT_VOTOS_NOMINAIS"]].strip('"')
                    datos = registro.setdefault(clave, {})
                    datos[num] = datos.get(num, 0) + entero(votos)
                    municipios[clave] = fila[ix["NM_MUNICIPIO"]].strip('"')
    return registro, municipios, candidatos


def cargar_detalle(ruta_zip):
    totales = {}
    with zipfile.ZipFile(ruta_zip) as zf:
        nombre = next((n for n in zf.namelist()
                       if n.endswith("detalhe_votacao_munzona_2022_BR.csv")), None)
        if not nombre:
            nombre = next((n for n in zf.namelist() if n.endswith("_BRASIL.csv")), None)
        if not nombre:
            return totales
        print(f" -> Totalizando desde {nombre}")
        with zf.open(nombre) as raw:
            texto = io.TextIOWrapper(raw, encoding="latin-1", newline="")
            for fila in csv.reader(texto, delimiter=";"):
                if len(fila) <= D_NULOS or fila[D_CARGO].strip('"') != COD_CARGO_PRES:
                    continue
                clave = (fila[D_UF].strip('"'), fila[D_MUN].strip('"'),
                         fila[D_ZONA].strip('"').zfill(4), fila[D_TURNO].strip('"'))
                t = totales.setdefault(clave, {"aptos": 0, "comp": 0, "brancos": 0, "nulos": 0})
                t["aptos"] += entero(fila[D_APTO])
                t["comp"] += entero(fila[D_COMP])
                t["brancos"] += entero(fila[D_BRANCOS])
                t["nulos"] += entero(fila[D_NULOS])
    return totales


def sanear(texto):
    return "".join(c if c.isalnum() else "_" for c in texto).strip("_")


def escribir_zonas(registro, municipios, candidatos, totales):
    numeros = sorted(candidatos.keys(), key=lambda n: int(n))
    columnas = [f"{n}_{sanear(candidatos[n][0])}" for n in numeros]
    cabecera = (["ref", "uf", "codigo_municipio", "municipio", "zona", "turno",
                 "electores", "votos_totales", "secciones_totalizadas"]
                + columnas + ["votos_blancos", "votos_nulos"])

    claves = sorted(registro.keys(), key=lambda k: (k[0], k[1], k[2], k[3]))
    with open(ARCHIVO_ZONAS, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cabecera)
        for clave in claves:
            uf, mun, zona, turno = clave
            votos = registro[clave]
            t = totales.get(clave, {})
            fila = [f"{uf}-{mun}-{zona}-{turno}", uf, mun, municipios.get(clave, ""),
                    zona, turno, t.get("aptos", 0), t.get("comp", 0), 0]
            fila += [votos.get(n, 0) for n in numeros]
            fila += [t.get("brancos", 0), t.get("nulos", 0)]
            w.writerow(fila)

    with open(ARCHIVO_CAND, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["numero", "nome_urna", "partido"])
        for n in numeros:
            w.writerow([n, candidatos[n][0], candidatos[n][1]])

    print(f"[OK] {len(claves)} filas -> {ARCHIVO_ZONAS}")
    print(f"[OK] {len(numeros)} candidatos -> {ARCHIVO_CAND}")


def main():
    parser = argparse.ArgumentParser(description="Datos Presidente 2022 (TSE).")
    parser.add_argument("--datos", default=CARPETA_DATOS, help="Carpeta de descarga.")
    parser.add_argument("--solo-historico", action="store_true", help="Solo serie temporal nacional.")
    parser.add_argument("--solo-zonas", action="store_true", help="Solo base geografica final.")
    parser.add_argument("--todos-cargos", action="store_true", help="Base final: todos los cargos.")
    args = parser.parse_args()

    hacer_hist = not args.solo_zonas
    hacer_zonas = not args.solo_historico

    try:
        if hacer_hist:
            print("\n=== SERIE TEMPORAL NACIONAL (Historico de Totalizacao) ===")
            for turno, url in URL_HIST.items():
                destino = os.path.join(args.datos, os.path.basename(url))
                descargar(url, destino)
                parsear_historico(destino, turno)

        if hacer_zonas:
            print("\n=== BASE GEOGRAFICA FINAL (municipio + zona) ===")
            zip_cand = os.path.join(args.datos, os.path.basename(URL_CANDIDATOS))
            zip_det = os.path.join(args.datos, os.path.basename(URL_DETALHE))
            descargar(URL_CANDIDATOS, zip_cand)
            descargar(URL_DETALHE, zip_det)
            print("[*] Leyendo votos por candidato...")
            registro, municipios, candidatos = cargar_votos_candidatos(
                zip_cand, solo_presidente=not args.todos_cargos)
            print(f"    Zonas-turno: {len(registro)}")
            print("[*] Leyendo totales (detalhe)...")
            totales = cargar_detalle(zip_det)
            print(f"    Zonas-turno con totales: {len(totales)}")
            escribir_zonas(registro, municipios, candidatos, totales)

    except KeyboardInterrupt:
        print("\n[!] Interrumpido por el usuario.")
        sys.exit(1)
    except (requests.RequestException, zipfile.BadZipFile, OSError, StopIteration) as exc:
        print(f"[x] Error: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
