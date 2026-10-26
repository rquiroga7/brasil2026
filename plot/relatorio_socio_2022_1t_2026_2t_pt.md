# A economia e a sociedade mudam a migração de votos? (Brasil 2022 1T → 2026 2T)

Fatores socioeconômicos municipais (Censo 2022) cruzados com 5570 municípios. Swing de Lula = % Lula destino − % Lula origen (2022 1T → 2026 2T).

## Correlação com o swing de Lula

| Factor | Correlación | Intra-estado |
|---|---|---|
| Ingreso per cápita | -0.19 | +0.15 |
| % blancos | -0.23 | -0.01 |
| % evangélicos | +0.13 | +0.17 |
| % universitarios | +0.20 | +0.39 |
| log votos | +0.25 | +0.38 |

## Regressão (coef. em pontos por 1 desvio padrão; R²=0.50)

| Factor | Coef. | t |
|---|---|---|
| log votos | +1.07 | +25.2 |
| % universitarios | +0.69 | +12.0 |
| % evangélicos | +0.34 | +7.8 |
| % blancos | -0.15 | -1.8 |
| Ingreso per cápita | -0.29 | -2.8 |

## A inferência ecológica muda? Transições-chave por quintil

| Factor | Quintil | Bolsonaro→Lula | Bolsonaro→Flavio | Otros→Flavio |
|---|---|---|---|---|
| Ingreso per cápita | 1 | 0.0% | 85.6% | 62.5% |
| Ingreso per cápita | 2 | 0.0% | 90.0% | 35.1% |
| Ingreso per cápita | 3 | 0.0% | 94.1% | 19.6% |
| Ingreso per cápita | 4 | 0.0% | 99.8% | 1.7% |
| Ingreso per cápita | 5 | 0.0% | 99.7% | 2.2% |
| % universitarios | 1 | 0.0% | 97.4% | 43.1% |
| % universitarios | 2 | 0.0% | 96.4% | 65.5% |
| % universitarios | 3 | 0.0% | 98.8% | 47.6% |
| % universitarios | 4 | 0.0% | 99.7% | 37.1% |
| % universitarios | 5 | 0.0% | 98.5% | 16.6% |
| % evangélicos | 1 | 0.0% | 100.0% | 58.4% |
| % evangélicos | 2 | 0.0% | 100.0% | 47.4% |
| % evangélicos | 3 | 0.0% | 100.0% | 22.6% |
| % evangélicos | 4 | 0.0% | 98.9% | 13.4% |
| % evangélicos | 5 | 0.0% | 96.7% | 18.2% |

## Leitura
Se os coeficientes e as transições mudam fortemente entre quintis, os fatores socioeconômicos **sim** modificam a inferência: a matriz nacional mistura realidades muito distintas. A parte que sobrevive aos efeitos de estado é a relação mais limpa (não confundida pela geografia).

*Fonte socio: dschteingart/el-atlas-charts (Censo 2022). Inferência ecológica por seções (EM).*

---

*Por Rodrigo Quiroga. Trabajo realizado en colaboración con el Dr. Roberto Etchenique. Repositorio: https://github.com/rquiroga7/brasil2026*
