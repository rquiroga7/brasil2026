# -*- coding: utf-8 -*-
"""
backtest.py — Compara los métodos de proyección en distintos % de votos escrutados.

Reconstruye snapshots del CSV append-only y proyecta con cada método, midiendo el
error (|ΔLula| + |ΔFlavio| en puntos) frente al resultado final disponible.
Genera tabla en consola y backtest_metodos_2026.png.
"""

import os
import sys
import csv
import io
import tempfile
import contextlib
from collections import OrderedDict

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

CSV = "escrutinio_zonas_2026.csv"
OBJETIVOS = [0.5, 1, 2.5, 5, 7.5, 10, 20, 25, 36, 50]

# método -> (color, explicación breve)
METODOS = OrderedDict([
    ("crudo", ("#9AA0A6", "Conteo crudo TSE: lo escrutado tal cual (muestra sesgada)")),
    ("v1",  ("#E11B22", "v1 Estratificado: media de lo contado (municipio→estado→nacional)")),
    ("v2",  ("#4C8DFF", "v2 Swing uniforme: 2022 + swing del estado")),
    ("scht", ("#2E7D32", "Schteingart: swing logit jerárquico (IBGE: región→estado→inmediata)")),
    ("v4",  ("#B8860B", "v4 Swing diferencial: regresión 2026~2022 por estado")),
])

sw.N_SIM = 5   # MC reducido: el backtest solo usa el estimador puntual

# Cachear datos estáticos (base 2022 y resultados 2022) para acelerar.
_BASE = e1.cargar_linea_base_2022()
_Z22 = sw.cargar_zonas_2022()
for _m in (e1, sw, sc, v4):
    if hasattr(_m, "cargar_linea_base_2022"):
        _m.cargar_linea_base_2022 = lambda: _BASE
    if hasattr(_m, "cargar_zonas_2022"):
        _m.cargar_zonas_2022 = lambda: _Z22


def norm(x):
    x = str(x).strip()
    return str(int(x)) if x.isdigit() else x


def cargar_filas():
    with open(CSV, encoding="utf-8") as f:
        r = csv.DictReader(f)
        header = r.fieldnames
        rows = list(r)
    return header, rows


def escribir_snapshot(header, filas, path):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=header)
        w.writeheader()
        w.writerows(filas)


def proyectar(path):
    e1.ARCHIVO_VIVO_2026 = path
    e1.ARCHIVO_HISTORICO = tempfile.mktemp(suffix=".csv")
    e1.ARCHIVO_JSON = tempfile.mktemp(suffix=".json")
    sw.ARCHIVO_VIVO_2026 = path
    with contextlib.redirect_stdout(io.StringIO()):
        try:
            r1 = e1.ejecutar_extrapolacion()
        except Exception:
            r1 = None
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
    return r1, r2, r4, r5


def shares(r1, r2, r4, r5):
    out = {}
    if r2 and r2.get("nacional", {}).get("crudo"):
        b = r2["nacional"]["crudo"]
        out["crudo"] = (b["lula"]["pct"], b["flavio"]["pct"])
    if r1 and r1.get("proyectado"):
        out["v1"] = (r1["proyectado"]["lula"]["pct"], r1["proyectado"]["flavio"]["pct"])
    if r2 and r2.get("nacional", {}).get("swing"):
        b = r2["nacional"]["swing"]
        out["v2"] = (b["lula"]["pct"], b["flavio"]["pct"])
    if r4 and r4.get("nacional", {}).get("v4"):
        b = r4["nacional"]["v4"]
        out["v4"] = (b["lula"]["pct"], b["flavio"]["pct"])
    if r5 and r5.get("nacional", {}).get("schteingart"):
        b = r5["nacional"]["schteingart"]
        out["scht"] = (b["lula"]["pct"], b["flavio"]["pct"])
    return out


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


def main():
    header, rows = cargar_filas()
    if not rows:
        print("CSV vacío")
        return
    tp = total_peso()

    full = tempfile.mktemp(suffix=".csv")
    escribir_snapshot(header, rows, full)
    _, r2f, _, _ = proyectar(full)
    fin = r2f["nacional"]["crudo"]
    final = (fin["lula"]["pct"], fin["flavio"]["pct"])
    print(f"Referencia final (crudo, {r2f['escrutado_pct']:.2f}% escrutado): "
          f"Lula {final[0]:.2f}% | Flavio {final[1]:.2f}%\n")

    by_time = OrderedDict()
    for r in rows:
        by_time.setdefault(r["hora_local"], []).append(r)

    ultimo = {}
    suma = 0.0
    ti = 0
    resultados = []
    for t, filas_t in by_time.items():
        for r in filas_t:
            clave = (norm(r["codigo_municipio"]), norm(r["zona_electoral"]))
            v = int(r["votos_totales"])
            old = ultimo.get(clave)
            if old is not None:
                suma -= old[0]
            ultimo[clave] = (v, r)
            suma += v
        esc = (suma / tp * 100.0) if tp else 0.0
        while ti < len(OBJETIVOS) and esc >= OBJETIVOS[ti]:
            snap = tempfile.mktemp(suffix=".csv")
            escribir_snapshot(header, [rr for _, rr in ultimo.values()], snap)
            r1, r2, r4, r5 = proyectar(snap)
            sh = shares(r1, r2, r4, r5)
            errs = {m: abs(l - final[0]) + abs(f - final[1]) for m, (l, f) in sh.items()}
            resultados.append((esc, sh, errs))
            ti += 1
            print(f"[backtest] objetivo {OBJETIVOS[ti-1]}% -> esc {esc:.2f}% ok", flush=True)
        if ti >= len(OBJETIVOS):
            break

    # --- tabla ---
    cols = list(METODOS.keys())
    cab = f'{"%esc":>6} | ' + " ".join(f'{m:>7}' for m in cols) + " | " + \
          " ".join(f'{m+" L/F":>11}' for m in cols)
    print("\nError = |ΔLula| + |ΔFlavio| (puntos) frente al final\n")
    print(cab)
    print("-" * len(cab))
    for esc, sh, errs in resultados:
        def e(m):
            return f"{errs[m]:7.2f}" if m in errs else "   n/a "
        def lf(m):
            return f"{sh[m][0]:5.1f}/{sh[m][1]:5.1f}" if m in sh else "   n/a   "
        print(f"{esc:6.2f} | " + " ".join(e(m) for m in cols) + " | " +
              " ".join(f'{lf(m):>11}' for m in cols))

    print("\nError medio en los cortes pedidos:")
    for m in cols:
        vals = [errs[m] for _, _, errs in resultados if m in errs]
        if vals:
            print(f"  {m}: {np.mean(vals):.2f}   — {METODOS[m][1]}")

    # --- gráfico ---
    fig, ax = plt.subplots(figsize=(11, 7))
    for m, (color, explic) in METODOS.items():
        xs = [esc for esc, _, errs in resultados if m in errs]
        ys = [errs[m] for _, _, errs in resultados if m in errs]
        if xs:
            ax.plot(xs, ys, "o-", color=color, linewidth=2,
                    label=f"{m}: {explic}")
    ax.set_xlabel("% de votos escrutados", fontsize=10)
    ax.set_ylabel("Error |ΔLula| + |ΔFlavio| (puntos)", fontsize=10)
    ax.set_title("Error de cada método vs % escrutado (menor = mejor)",
                 fontsize=11, fontweight="bold")
    ax.grid(True, linestyle="--", alpha=0.5)
    ax.legend(fontsize=8, loc="upper right", title="Método", title_fontsize=9)
    fig.tight_layout()
    fig.savefig("backtest_metodos_2026.png", dpi=120, bbox_inches="tight")
    plt.close(fig)
    print("\n[i] Gráfico: backtest_metodos_2026.png")


if __name__ == "__main__":
    main()
