# ¿La economía y la sociedad cambian la migración de votos? (Brasil 2022→2026)

Factores socioeconómicos municipales (Censo 2022) cruzados con 5570 municipios. Swing de Lula = % Lula 2026 − % Lula 2022 (1ª vuelta).

## Correlación con el swing de Lula

| Factor | Correlación | Intra-estado |
|---|---|---|
| Bolsa Família (por 100 hog.) | +0.33 | +0.00 |
| Ingreso per cápita | -0.30 | +0.09 |
| % blancos | -0.29 | -0.02 |
| % evangélicos | +0.07 | +0.17 |
| % universitarios | +0.02 | +0.26 |
| log votos | +0.15 | +0.22 |

## Regresión (coef. en puntos por 1 desvío estándar; R²=0.46)

| Factor | Coef. | t |
|---|---|---|
| % universitarios | +0.60 | +9.7 |
| Bolsa Família (por 100 hog.) | +0.59 | +7.7 |
| log votos | +0.53 | +12.4 |
| % evangélicos | +0.44 | +9.3 |
| % blancos | +0.03 | +0.3 |
| Ingreso per cápita | -0.01 | -0.0 |

## ¿Modifica la inferencia ecológica? Transiciones clave por quintil

| Factor | Quintil | Bolsonaro→Lula | Bolsonaro→Flávio | Otros→Flávio |
|---|---|---|---|---|
| Ingreso per cápita | 1 | 0.0% | 92.1% | 49.2% |
| Ingreso per cápita | 2 | 0.0% | 91.0% | 19.9% |
| Ingreso per cápita | 3 | 0.0% | 94.2% | 4.0% |
| Ingreso per cápita | 4 | 0.0% | 96.2% | 1.7% |
| Ingreso per cápita | 5 | 0.0% | 95.7% | 0.5% |
| Bolsa Família (por 100 hog.) | 1 | 0.0% | 95.3% | 0.7% |
| Bolsa Família (por 100 hog.) | 2 | 0.0% | 94.3% | 0.3% |
| Bolsa Família (por 100 hog.) | 3 | 0.0% | 94.9% | 2.8% |
| Bolsa Família (por 100 hog.) | 4 | 0.0% | 89.7% | 25.1% |
| Bolsa Família (por 100 hog.) | 5 | 0.0% | 91.7% | 45.5% |
| % evangélicos | 1 | 0.0% | 93.0% | 33.5% |
| % evangélicos | 2 | 0.0% | 95.0% | 4.4% |
| % evangélicos | 3 | 0.0% | 92.8% | 15.1% |
| % evangélicos | 4 | 0.0% | 91.9% | 7.2% |
| % evangélicos | 5 | 0.0% | 92.1% | 8.9% |

## Lectura
Si los coeficientes y las transiciones cambian marcadamente entre quintiles, los factores socioeconómicos **sí** modifican la inferencia: la matriz nacional promedia realidades muy distintas. La parte que sobrevive a los efectos de estado es la relación más limpia (no confundida por la geografía).

*Fuente socio: dschteingart/el-atlas-charts (Censo 2022). Inferencia ecológica por secciones (EM).*

---

*Por Rodrigo Quiroga. Trabajo realizado en colaboración con el Dr. Roberto Etchenique. Repositorio: https://github.com/rquiroga7/brasil2026*
