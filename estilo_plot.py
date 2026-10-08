# -*- coding: utf-8 -*-
"""
estilo_plot.py — Pie de figura común para todos los gráficos.

Añade una nota metodológica breve en español + autor + repositorio.
"""

REPO_URL = "https://github.com/rquiroga7/brasil2026"
AUTOR = "Por Rodrigo Quiroga"
COLABORACION = "Trabajo realizado en colaboración con el Dr. Roberto Etchenique"
CREDITO = f"{AUTOR}. {COLABORACION}. Repositorio: {REPO_URL}"


def pie(metodologia):
    return f"{metodologia}\n{AUTOR} · ver {REPO_URL}"


def mpl(fig, metodologia):
    """Pie para figuras matplotlib (usar con bbox_inches='tight')."""
    fig.text(0.5, -0.03, pie(metodologia), ha="center", va="top",
             fontsize=7, color="#555555")


def plotly(fig, metodologia):
    """Pie para figuras plotly (Sankey)."""
    fig.add_annotation(text=pie(metodologia), xref="paper", yref="paper",
                       x=0.5, y=-0.13, showarrow=False, align="center",
                       font=dict(size=10, color="#555555"))
