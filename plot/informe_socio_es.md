# ¿La economía y la sociedad cambian la migración de votos? (Brasil 2022→2026)

Factores socioeconómicos municipales (Censo 2022) cruzados con 5570 municipios. Swing de Lula = % Lula destino − % Lula origen (2022→2026). Los quintiles se cortan por electorado: cada uno reúne ~20% de los votantes.

## Correlación con el swing de Lula

| Factor | Correlación | Intra-estado |
|---|---|---|
| Ingreso per cápita | -0.30 | +0.09 |
| % blancos | -0.29 | -0.02 |
| % evangélicos | +0.07 | +0.17 |
| % universitarios | +0.02 | +0.26 |
| log votos | +0.15 | +0.22 |

## Regresión (coef. en puntos por 1 desvío estándar; R²=0.45)

| Factor | Coef. | t |
|---|---|---|
| % universitarios | +0.60 | +9.5 |
| log votos | +0.49 | +11.4 |
| % evangélicos | +0.43 | +9.1 |
| % blancos | -0.13 | -1.4 |
| Ingreso per cápita | -0.26 | -2.3 |

## ¿Modifica la inferencia ecológica? Transiciones clave por quintil

| Factor | Quintil | Bolsonaro→Lula | Bolsonaro→Flavio | Otros→Flavio |
|---|---|---|---|---|
| Ingreso per cápita | 1 | 0.0% | 92.2% | 47.4% |
| Ingreso per cápita | 2 | 0.0% | 91.5% | 16.8% |
| Ingreso per cápita | 3 | 0.0% | 94.4% | 1.7% |
| Ingreso per cápita | 4 | 0.0% | 96.4% | 1.5% |
| Ingreso per cápita | 5 | 0.0% | 95.9% | 0.4% |
| % universitarios | 1 | 0.0% | 92.0% | 38.7% |
| % universitarios | 2 | 0.0% | 94.1% | 20.9% |
| % universitarios | 3 | 0.0% | 94.7% | 10.0% |
| % universitarios | 4 | 0.0% | 93.3% | 23.5% |
| % universitarios | 5 | 0.1% | 91.1% | 17.3% |
| % evangélicos | 1 | 0.0% | 93.6% | 30.1% |
| % evangélicos | 2 | 0.0% | 95.4% | 2.5% |
| % evangélicos | 3 | 0.0% | 92.7% | 13.8% |
| % evangélicos | 4 | 0.0% | 92.1% | 3.8% |
| % evangélicos | 5 | 0.0% | 92.2% | 5.7% |

## Lectura
Si los coeficientes y las transiciones cambian marcadamente entre quintiles, los factores socioeconómicos **sí** modifican la inferencia: la matriz nacional promedia realidades muy distintas. La parte que sobrevive a los efectos de estado es la relación más limpia (no confundida por la geografía).

*Fuente socio: dschteingart/el-atlas-charts (Censo 2022). Inferencia ecológica por secciones (EM).*

---

*Por Rodrigo Quiroga. Trabajo realizado en colaboración con el Dr. Roberto Etchenique. Repositorio: https://github.com/rquiroga7/brasil2026*
