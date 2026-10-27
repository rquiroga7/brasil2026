# ¿La economía y la sociedad cambian la migración de votos? (Brasil 2022 1T → 2026 2T)

Factores socioeconómicos municipales (Censo 2022) cruzados con 5570 municipios. Swing de Lula = % Lula destino − % Lula origen (2022 1T → 2026 2T). Los quintiles se cortan por electorado: cada uno reúne ~20% de los votantes.

## Correlación con el swing de Lula

| Factor | Correlación | Intra-estado |
|---|---|---|
| Ingreso per cápita | -0.19 | +0.15 |
| % blancos | -0.23 | -0.01 |
| % evangélicos | +0.13 | +0.17 |
| % universitarios | +0.20 | +0.39 |
| log votos | +0.25 | +0.38 |

## Regresión (coef. en puntos por 1 desvío estándar; R²=0.50)

| Factor | Coef. | t |
|---|---|---|
| log votos | +1.07 | +25.2 |
| % universitarios | +0.69 | +12.0 |
| % evangélicos | +0.34 | +7.8 |
| % blancos | -0.15 | -1.8 |
| Ingreso per cápita | -0.29 | -2.8 |

## ¿Modifica la inferencia ecológica? Transiciones clave por quintil

| Factor | Quintil | Bolsonaro→Lula | Bolsonaro→Flavio | Otros→Flavio |
|---|---|---|---|---|
| Ingreso per cápita | 1 | 0.0% | 89.3% | 61.1% |
| Ingreso per cápita | 2 | 0.0% | 90.8% | 22.6% |
| Ingreso per cápita | 3 | 0.0% | 97.2% | 7.1% |
| Ingreso per cápita | 4 | 0.0% | 99.9% | 11.6% |
| Ingreso per cápita | 5 | 0.0% | 100.0% | 2.4% |
| % universitarios | 1 | 0.0% | 96.8% | 57.5% |
| % universitarios | 2 | 0.0% | 99.4% | 43.0% |
| % universitarios | 3 | 0.0% | 99.0% | 12.6% |
| % universitarios | 4 | 0.0% | 99.2% | 39.8% |
| % universitarios | 5 | 0.2% | 96.4% | 35.5% |
| % evangélicos | 1 | 0.0% | 100.0% | 56.9% |
| % evangélicos | 2 | 0.0% | 100.0% | 17.5% |
| % evangélicos | 3 | 0.0% | 100.0% | 29.3% |
| % evangélicos | 4 | 0.0% | 99.0% | 5.1% |
| % evangélicos | 5 | 0.0% | 96.0% | 18.6% |

## Lectura
Si los coeficientes y las transiciones cambian marcadamente entre quintiles, los factores socioeconómicos **sí** modifican la inferencia: la matriz nacional promedia realidades muy distintas. La parte que sobrevive a los efectos de estado es la relación más limpia (no confundida por la geografía).

*Fuente socio: dschteingart/el-atlas-charts (Censo 2022). Inferencia ecológica por secciones (EM).*

---

*Por Rodrigo Quiroga. Trabajo realizado en colaboración con el Dr. Roberto Etchenique. Repositorio: https://github.com/rquiroga7/brasil2026*
