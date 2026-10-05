# -*- coding: utf-8 -*-
"""
backtest.py — Compara métodos de proyección, robusto al sesgo de muestreo.

Dos análisis:
  A) Error NACIONAL por % escrutado, promediado sobre 3 raspados independientes
     del mismo escrutinio (main, maquinalabo, maquinarafa).
  B) Error por ESTADO, agrupado por el % escrutado DE CADA ESTADO. Así se evita
     el sesgo de que a un % nacional bajo unos estados estén más muestreados que
     otros. Se promedia sobre estados y sobre los 3 raspados.

Genera backtest_metodos_2026.png (panel A) y backtest_estados_2026.png (panel B).
"""

import os
import sys
import csv
import io
import tempfile
import contextlib
from collections import OrderedDict, defaultdict

import numpy as np

REPO = os.path.dirname(os.path.abspath(__file__))
os.chdir(REPO)
sys.path.insert(0, REPO)

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import extrapolador10B_rodri as e1
import proyeccion_swing as sw
import proyeccion_schteingart as sc
import proyeccion_v4 as v4

ARCHIVOS = ["escrutinio_zonas_2026.csv",
            "escrutinio_zonas_2026maquinalabo.csv",
            "escrutinio_zonas_2026maquinarafa.csv"]
OBJETIVOS_NAC = [1, 2.5, 5, 10, 20, 35, 50, 100]
BINS_ESTADO = [1, 2.5, 5, 10, 20, 35, 50, 100]
N_SNAPS_ESTADO = 8

METODOS = OrderedDict([
    ("crudo", ("#9AA0A6", "Conteo crudo TSE (muestra sesgada)")),
    ("v1",  ("#E11B22", "v1 Estratificado: media de lo contado")),
    ("v2",  ("#4C8DFF", "v2 Swing uniforme NACIONAL: 2022 + swing nacional")),
    ("scht", ("#2E7D32", "Schteingart (con gate): crudo hasta estar listo")),
    ("scht_ng", ("#8B5CF6", "Schteingart SIN gate: proyecta siempre")),
    ("v4",  ("#B8860B", "v4 Swing por ESTADO: 2022 + swing del estado")),
])

sw.N_SIM = 5
_BASE = e1.cargar_linea_base_2022()
_Z22 = sw.cargar_zonas_2022()
for _m in (e1, sw, sc, v4):
    if hasattr(_m, "cargar_linea_base_2022"):
        _m.cargar_linea_base_2022 = lambda: _BASE
    if hasattr(_m, "cargar_zonas_2022"):
        _m.cargar_zonas_2022 = lambda: _Z22

CANON = ['hora_local', 'hora_tse', 'estado_uf', 'codigo_municipio', 'municipio',
         'zona_electoral', 'secoes_totalizadas', 'electores', 'votos_totales',
         'Lula', 'Flavio_Bolsonaro', 'Augusto_Cury', 'Ronaldo_Caiado', 'Romeu_Zema',
         'Renan_Santos', 'Hertz_Dias', 'Edmilson_Costa', 'Clariana_Barao',
         'Rui_Costa_Pimenta', 'Wilson_Grassi', 'Samara_Martins', 'votos_blancos',
         'votos_nulos', 'numero_pasada']


def norm(x):
    x = str(x).strip()
    return str(int(x)) if x.isdigit() else x


def cargar(archivo):
    rows = list(csv.DictReader(open(archivo, encoding="utf-8")))
    for r in rows:
        if "electores" not in r:
            r["electores"] = r.get("electores_totales", "0")
        r.setdefault("secoes_totalizadas", "0")
        r.setdefault("municipio", "")
    return rows


def escribir(rows, path):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CANON, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def proyectar(path):
    e1.ARCHIVO_VIVO_2026 = path
    e1.ARCHIVO_HISTORICO = tempfile.mktemp(suffix=".csv")
    e1.ARCHIVO_JSON = tempfile.mktemp(suffix=".json")
    sw.ARCHIVO_VIVO_2026 = path
    with contextlib.redirect_stdout(io.StringIO()):
        try:
            r2 = sw.proyectar()
        except Exception:
            r2 = None
        try:
            r4 = v4.proyectar_v4()
        except Exception:
            r4 = None
        try:
            r5 = sc.proyectar()
        except Exception:
            r5 = None
    # nacional
    nac = {}
    if r2:
        c = r2.get("nacional", {}).get("crudo")
        if c:
            nac["crudo"] = (c["lula"]["pct"], c["flavio"]["pct"])
        b = r2.get("nacional", {}).get("v1")
        if b:
            nac["v1"] = (b["lula"]["pct"], b["flavio"]["pct"])
        b = r2.get("nacional", {}).get("swing")
        if b:
            nac["v2"] = (b["lula"]["pct"], b["flavio"]["pct"])
    if r4 and r4.get("nacional", {}).get("v4"):
        b = r4["nacional"]["v4"]
        nac["v4"] = (b["lula"]["pct"], b["flavio"]["pct"])
    if r5 and r5.get("nacional", {}).get("schteingart"):
        b = r5["nacional"]["schteingart"]
        nac["scht"] = (b["lula"]["pct"], b["flavio"]["pct"])
    if r5 and r5.get("nacional", {}).get("schteingart_nogate"):
        b = r5["nacional"]["schteingart_nogate"]
        nac["scht_ng"] = (b["lula"]["pct"], b["flavio"]["pct"])
    # estados
    est = {}
    if r2:
        for e in r2.get("estados", []):
            uf = e["uf"]
            est.setdefault(uf, {})["esc"] = e.get("escrutado")
            if e.get("crudo"):
                est[uf]["crudo"] = (e["crudo"]["lula"]["pct"], e["crudo"]["flavio"]["pct"])
            if e.get("v1"):
                est[uf]["v1"] = (e["v1"]["lula"]["pct"], e["v1"]["flavio"]["pct"])
            if e.get("swing"):
                est[uf]["v2"] = (e["swing"]["lula"]["pct"], e["swing"]["flavio"]["pct"])
    if r4:
        for e in r4.get("estados", []):
            if e.get("v4"):
                est.setdefault(e["uf"], {})["v4"] = (e["v4"]["lula"]["pct"], e["v4"]["flavio"]["pct"])
    if r5:
        for e in r5.get("estados", []):
            if e.get("schteingart"):
                est.setdefault(e["uf"], {})["scht"] = (e["schteingart"]["lula"]["pct"],
                                                       e["schteingart"]["flavio"]["pct"])
            if e.get("schteingart_nogate"):
                est.setdefault(e["uf"], {})["scht_ng"] = (e["schteingart_nogate"]["lula"]["pct"],
                                                          e["schteingart_nogate"]["flavio"]["pct"])
    return nac, est


def total_peso():
    df_base = e1.cargar_linea_base_2022()
    df_vivo = sw.cargar_vivo_2026()
    elec = e1.cargar_electores_habilitados_2026(df_vivo)
    tp = 0.0
    for _, r in df_base.iterrows():
        hab22 = int(r["electores_habilitados"])
        try:
            pct = float(r["porcentaje_asistencia"]) / 100.0
        except (TypeError, ValueError):
            pct = (int(r["electores_asistieron"]) / hab22) if hab22 else 0.0
        tp += elec.get((r["codigo_municipio"], r["zona_electoral"]), hab22) * pct
    return tp


def err(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def parte_a(tp, final_nac):
    print("\n=== A) Error nacional promedio sobre 3 raspados ===")
    acum = {m: {o: [] for o in OBJETIVOS_NAC} for m in METODOS}
    for archivo in ARCHIVOS:
        rows = cargar(archivo)
        rows.sort(key=lambda r: r["hora_local"])
        by_time = OrderedDict()
        for r in rows:
            by_time.setdefault(r["hora_local"], []).append(r)
        ultimo = {}; suma = 0.0; ti = 0
        for t, ft in by_time.items():
            for r in ft:
                k = (norm(r["codigo_municipio"]), norm(r["zona_electoral"]))
                v = int(float(r["votos_totales"] or 0))
                old = ultimo.get(k)
                if old is not None:
                    suma -= old[0]
                ultimo[k] = (v, r); suma += v
            esc = suma / tp * 100 if tp else 0
            while ti < len(OBJETIVOS_NAC) and esc >= OBJETIVOS_NAC[ti]:
                snap = tempfile.mktemp(suffix=".csv")
                escribir([rr for _, rr in ultimo.values()], snap)
                nac, _ = proyectar(snap)
                for m in METODOS:
                    if m in nac:
                        acum[m][OBJETIVOS_NAC[ti]].append(err(nac[m], final_nac))
                ti += 1
            if ti >= len(OBJETIVOS_NAC):
                break
        print(f"  [{archivo}] listo", flush=True)

    cols = list(METODOS.keys())
    print(f'{"%esc":>6} | ' + " ".join(f'{m:>7}' for m in cols))
    for o in OBJETIVOS_NAC:
        fila = " ".join(f"{np.mean(acum[m][o]):7.2f}" if acum[m][o] else "    n/a" for m in cols)
        print(f"{o:6.1f} | {fila}")
    print("\nError medio (todos los cortes):")
    medias = {}
    for m in cols:
        vals = [x for o in OBJETIVOS_NAC for x in acum[m][o]]
        medias[m] = np.mean(vals) if vals else float("nan")
        print(f"  {m}: {medias[m]:.2f}   — {METODOS[m][1]}")
    return acum, medias


def parte_b(final_est):
    print("\n=== B) Error por estado, agrupado por % escrutado del propio estado ===")
    acum = {m: {b: [] for b in BINS_ESTADO} for m in METODOS}
    for archivo in ARCHIVOS:
        rows = cargar(archivo)
        rows.sort(key=lambda r: r["hora_local"])
        by_time = OrderedDict()
        for r in rows:
            by_time.setdefault(r["hora_local"], []).append(r)
        tiempos = list(by_time.keys())
        idxs = np.unique(np.linspace(0, len(tiempos) - 1, N_SNAPS_ESTADO).astype(int))
        for i in idxs:
            filas = [r for r in rows if r["hora_local"] <= tiempos[i]]
            snap = tempfile.mktemp(suffix=".csv")
            escribir(filas, snap)
            _, est = proyectar(snap)
            for uf, d in est.items():
                if uf == "ZZ" or "esc" not in d or d["esc"] is None:
                    continue
                fin = final_est.get(uf)
                if not fin:
                    continue
                b = min(BINS_ESTADO, key=lambda x: abs(x - d["esc"]))
                for m in METODOS:
                    if m in d:
                        acum[m][b].append(err(d[m], fin))
        print(f"  [{archivo}] listo", flush=True)

    cols = list(METODOS.keys())
    print(f'{"%esc UF":>7} | ' + " ".join(f'{m:>7}' for m in cols))
    for b in BINS_ESTADO:
        fila = " ".join(f"{np.mean(acum[m][b]):7.2f}" if acum[m][b] else "    n/a" for m in cols)
        print(f"{b:7.1f} | {fila}")
    print("\nError medio por estado (todos los bins):")
    for m in cols:
        vals = [x for b in BINS_ESTADO for x in acum[m][b]]
        print(f"  {m}: {np.mean(vals):.2f}" if vals else f"  {m}: n/a")
    return acum


def graficar(acum_a, acum_b):
    fig, ax = plt.subplots(figsize=(11, 7))
    for m, (color, explic) in METODOS.items():
        xs = [o for o in OBJETIVOS_NAC if acum_a[m][o]]
        ys = [np.mean(acum_a[m][o]) for o in OBJETIVOS_NAC if acum_a[m][o]]
        if xs:
            ax.plot(xs, ys, "o-", color=color, linewidth=2, label=f"{m}: {explic}")
    ax.set_xlabel("% de votos escrutados (nacional)", fontsize=10)
    ax.set_ylabel("Error |ΔLula| + |ΔFlavio| (puntos)", fontsize=10)
    ax.set_title("A) Error nacional por % escrutado (promedio de 3 raspados)",
                 fontsize=11, fontweight="bold")
    ax.grid(True, linestyle="--", alpha=0.5)
    ax.legend(fontsize=8, loc="upper right", title="Método", title_fontsize=9)
    fig.tight_layout()
    fig.savefig("backtest_metodos_2026.png", dpi=120, bbox_inches="tight")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(11, 7))
    for m, (color, explic) in METODOS.items():
        xs = [b for b in BINS_ESTADO if acum_b[m][b]]
        ys = [np.mean(acum_b[m][b]) for b in BINS_ESTADO if acum_b[m][b]]
        if xs:
            ax.plot(xs, ys, "o-", color=color, linewidth=2, label=f"{m}: {explic}")
    ax.set_xlabel("% escrutado del propio estado", fontsize=10)
    ax.set_ylabel("Error |ΔLula| + |ΔFlavio| (puntos)", fontsize=10)
    ax.set_ylim(0, 20)
    ax.set_title("B) Error por estado según su propio % escrutado (prom. estados × 3 raspados)",
                 fontsize=11, fontweight="bold")
    ax.grid(True, linestyle="--", alpha=0.5)
    ax.legend(fontsize=8, loc="upper right", title="Método", title_fontsize=9)
    fig.tight_layout()
    fig.savefig("backtest_estados_2026.png", dpi=120, bbox_inches="tight")
    plt.close(fig)
    print("\n[i] Gráficos: backtest_metodos_2026.png, backtest_estados_2026.png")


def main():
    tp = total_peso()
    # final nacional y por estado desde el raspado principal (último snapshot)
    rows = cargar(ARCHIVOS[0])
    full = tempfile.mktemp(suffix=".csv")
    escribir(rows, full)
    nac_f, est_f = proyectar(full)
    final_nac = nac_f["crudo"]
    final_est = {uf: d["crudo"] for uf, d in est_f.items() if "crudo" in d}
    print(f"Final nacional (crudo): Lula {final_nac[0]:.2f}% | Flavio {final_nac[1]:.2f}%")
    acum_a, _ = parte_a(tp, final_nac)
    acum_b = parte_b(final_est)
    graficar(acum_a, acum_b)


if __name__ == "__main__":
    main()
