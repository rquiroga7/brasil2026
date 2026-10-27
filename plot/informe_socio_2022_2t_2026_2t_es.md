# ¿La economía y la sociedad cambian la migración de votos? (Brasil 2022 2T → 2026 2T)

Factores socioeconómicos municipales (Censo 2022) cruzados con 5570 municipios. Swing de Lula = % Lula destino − % Lula origen (2022 2T → 2026 2T). Los quintiles se cortan por electorado: cada uno reúne ~20% de los votantes.

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
| Ingreso per cápita | 1 | 0.0% | 93.2% | — |
| Ingreso per cápita | 2 | 4.4% | 89.3% | — |
| Ingreso per cápita | 3 | 0.6% | 94.6% | — |
| Ingreso per cápita | 4 | 0.0% | 98.0% | — |
| Ingreso per cápita | 5 | 0.0% | 97.8% | — |
| % universitarios | 1 | 0.0% | 93.7% | — |
| % universitarios | 2 | 0.0% | 95.7% | — |
| % universitarios | 3 | 0.0% | 96.0% | — |
| % universitarios | 4 | 0.0% | 97.2% | — |
| % universitarios | 5 | 1.1% | 93.5% | — |
| % evangélicos | 1 | 0.0% | 94.7% | — |
| % evangélicos | 2 | 0.0% | 95.5% | — |
| % evangélicos | 3 | 0.0% | 96.3% | — |
| % evangélicos | 4 | 0.8% | 92.5% | — |
| % evangélicos | 5 | 0.3% | 92.3% | — |

## Lectura
Si los coeficientes y las transiciones cambian marcadamente entre quintiles, los factores socioeconómicos **sí** modifican la inferencia: la matriz nacional promedia realidades muy distintas. La parte que sobrevive a los efectos de estado es la relación más limpia (no confundida por la geografía).

*Fuente socio: dschteingart/el-atlas-charts (Censo 2022). Inferencia ecológica por secciones (EM).*

---

*Por Rodrigo Quiroga. Trabajo realizado en colaboración con el Dr. Roberto Etchenique. Repositorio: https://github.com/rquiroga7/brasil2026*
