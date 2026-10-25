# -*- coding: utf-8 -*-
"""publicar_2t.py — Publica datos_web_2t.json en la rama `data2t`."""
import os
import sys

import rutas_datos as rd
import publicar_rodri as p


def main():
    archivo = rd.ruta("datos_web_2t.json")
    if not os.path.exists(archivo):
        print(f"[x] Falta {archivo}; corre proyeccion_2t.py primero.")
        sys.exit(1)
    branch = os.environ.get("GIT_DATA_BRANCH_2T", "data2t")
    ok = p.publicar_git(archivo, branch=branch, remote=os.environ.get("GIT_REMOTE", "origin"),
                        force=True)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
