# Brasil 2026 — Proyección y análisis electoral

Proyección y análisis de las elecciones presidenciales de **Brasil 2026** a partir del
escrutinio oficial del TSE (`resultados.tse.jus.br`) y de los datos abiertos del TSE.

**Autor:** Rodrigo Quiroga
**Colaboración:** este trabajo fue realizado en colaboración con el **Dr. Roberto Etchenique**.
**Repositorio:** https://github.com/rquiroga7/brasil2026

---

## Qué contiene

1. **Raspado en vivo del escrutinio** (por zona electoral). Raspador concurrente
   (`zonpasG_rodri.py`, `scrapingbrasil2026zonpasG_rverboseRAP2.py`) con límite de
   tráfico adaptativo (~80 req/s, el TSE tolera ~100), uso del índice de avance por
   municipio para no pedir zonas vacías, e intercalado de estados para no sesgar el
   orden de observación.
2. **Modelos de proyección** del resultado final a partir del conteo parcial
   (`proyeccion.py`, `proyeccion_swing.py`, `proyeccion_schteingart.py`, `proyeccion_v4.py`):
   swing uniforme nacional (v2), swing por estado (v4), y modelo logit-swing jerárquico
   (Schteingart).
3. **Backtest con la carga real** (`backtest_timestamped.py`): reconstruye el orden real
   de publicación a partir de las marcas de tiempo del TSE
   (`DT_RECEBIMENTO_BU_HOR_TSE` / `DT_PRIM_TOT_PARCIAL_HOR_TSE`) y mide el error de cada
   método por % escrutado. Recomendación: **Schteingart hasta ~10% escrutado, luego v2**.
4. **Inferencia ecológica** de la migración de votos (`inferencia_ecologica.py`) por
   secciones electorales (EM), incluyendo a quienes no votaron: matrices 2018→2022,
   2022→2026, 2022 1ª→2ª vuelta y el encadenado 2018→2026. Diagramas de Sankey
   (PNG + HTML) y heatmaps.
5. **Factores socioeconómicos** (`inferencia_ecologica_socio.py`): cruce del swing con
   Bolsa Família, ingreso, raza, religión y universitarios (Censo 2022), y transiciones
   de voto por quintil.

## Datos

- **Votos por sección electoral** (Presidente, 1ª vuelta, 2018/2022/2026) y **detalle por
  sección** (aptos, abstención, marcas de tiempo): datos abiertos del TSE
  (`cdn.tse.jus.br/estatistica/sead/odsele/...`). Se descargan y procesan con
  `descargar_secciones.py`.
- **Socioeconómicos municipales** (Censo 2022): de
  [`dschteingart/el-atlas-charts`](https://github.com/dschteingart/el-atlas-charts/tree/main/brasil-2026)
  (`data/socio.js`).
- **Referencia 2022 / jerarquía IBGE**: `data/elecciones-2022.js`, `data/mun-jerarquia.json`.

Los datos crudos y derivados se guardan en `D:\brasil2026_data` (ver `rutas_datos.py`),
porque el disco C: está lleno. Los gráficos e informes se escriben en `plot/`.

## Informes

- `plot/informe_migracion_2022_2026_es.md` y `plot/relatorio_migracao_2022_2026_pt.md`
  (migración de votos, español y portugués).
- `plot/informe_socio_es.md` y `plot/relatorio_socio_pt.md` (factores socioeconómicos).
- `COMO_PROYECTAMOS.md` (explicación metodológica de la proyección).

## Cómo correr (resumen)

```bash
python descargar_secciones.py            # datos por sección (D:)
python inferencia_ecologica.py           # migración de votos + gráficos
python inferencia_ecologica_socio.py     # cruce socioeconómico
python backtest_timestamped.py           # backtest con la carga real
```

## Créditos

Trabajo realizado por **Rodrigo Quiroga** en colaboración con el **Dr. Roberto Etchenique**.

Repositorio: https://github.com/rquiroga7/brasil2026
