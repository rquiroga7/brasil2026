# ¿La economía y la sociedad cambian la migración de votos? (Brasil 2022 2T → 2026 2T)

Factores socioeconómicos municipales (Censo 2022) cruzados con 5570 municipios. Swing de Lula = % Lula destino − % Lula origen (2022 2T → 2026 2T).

## Correlación con el swing de Lula

| Factor | Correlación | Intra-estado |
|---|---|---|
| Ingreso per cápita | -0.06 | +0.17 |
| % blancos | -0.13 | -0.02 |
| % evangélicos | +0.24 | +0.25 |
| % universitarios | +0.26 | +0.36 |
| log votos | +0.28 | +0.36 |

## Regresión (coef. en puntos por 1 desvío estándar; R²=0.45)

| Factor | Coef. | t |
|---|---|---|
| log votos | +0.92 | +23.8 |
| % evangélicos | +0.55 | +13.8 |
| % universitarios | +0.45 | +8.6 |
| Ingreso per cápita | +0.08 | +0.9 |
| % blancos | -0.18 | -2.3 |

## ¿Modifica la inferencia ecológica? Transiciones clave por quintil

| Factor | Quintil | Bolsonaro→Lula | Bolsonaro→Flavio | Otros→Flavio |
|---|---|---|---|---|
| Ingreso per cápita | 1 | 0.0% | 92.9% | — |
| Ingreso per cápita | 2 | 1.9% | 88.7% | — |
| Ingreso per cápita | 3 | 2.3% | 93.4% | — |
| Ingreso per cápita | 4 | 0.0% | 97.4% | — |
| Ingreso per cápita | 5 | 0.0% | 97.4% | — |
| % universitarios | 1 | 0.0% | 94.1% | — |
| % universitarios | 2 | 0.0% | 94.0% | — |
| % universitarios | 3 | 0.0% | 94.9% | — |
| % universitarios | 4 | 0.0% | 96.6% | — |
| % universitarios | 5 | 0.0% | 96.3% | — |
| % evangélicos | 1 | 0.0% | 95.1% | — |
| % evangélicos | 2 | 0.0% | 94.5% | — |
| % evangélicos | 3 | 0.0% | 95.6% | — |
| % evangélicos | 4 | 0.2% | 93.6% | — |
| % evangélicos | 5 | 0.4% | 92.8% | — |

## Lectura
Si los coeficientes y las transiciones cambian marcadamente entre quintiles, los factores socioeconómicos **sí** modifican la inferencia: la matriz nacional promedia realidades muy distintas. La parte que sobrevive a los efectos de estado es la relación más limpia (no confundida por la geografía).

*Fuente socio: dschteingart/el-atlas-charts (Censo 2022). Inferencia ecológica por secciones (EM).*

---

*Por Rodrigo Quiroga. Trabajo realizado en colaboración con el Dr. Roberto Etchenique. Repositorio: https://github.com/rquiroga7/brasil2026*
