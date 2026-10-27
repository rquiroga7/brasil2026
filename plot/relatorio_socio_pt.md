# A economia e a sociedade mudam a migração de votos? (Brasil 2022→2026)

Fatores socioeconômicos municipais (Censo 2022) cruzados com 5570 municípios. Swing de Lula = % Lula destino − % Lula origen (2022→2026). Os quintis são cortados por eleitorado: cada um reúne ~20% dos votantes.

## Correlação com o swing de Lula

| Factor | Correlación | Intra-estado |
|---|---|---|
| Ingreso per cápita | -0.30 | +0.09 |
| % blancos | -0.29 | -0.02 |
| % evangélicos | +0.07 | +0.17 |
| % universitarios | +0.02 | +0.26 |
| log votos | +0.15 | +0.22 |

## Regressão (coef. em pontos por 1 desvio padrão; R²=0.45)

| Factor | Coef. | t |
|---|---|---|
| % universitarios | +0.60 | +9.5 |
| log votos | +0.49 | +11.4 |
| % evangélicos | +0.43 | +9.1 |
| % blancos | -0.13 | -1.4 |
| Ingreso per cápita | -0.26 | -2.3 |

## A inferência ecológica muda? Transições-chave por quintil

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

## Leitura
Se os coeficientes e as transições mudam fortemente entre quintis, os fatores socioeconômicos **sim** modificam a inferência: a matriz nacional mistura realidades muito distintas. A parte que sobrevive aos efeitos de estado é a relação mais limpa (não confundida pela geografia).

*Fonte socio: dschteingart/el-atlas-charts (Censo 2022). Inferência ecológica por seções (EM).*

---

*Por Rodrigo Quiroga. Trabajo realizado en colaboración con el Dr. Roberto Etchenique. Repositorio: https://github.com/rquiroga7/brasil2026*
