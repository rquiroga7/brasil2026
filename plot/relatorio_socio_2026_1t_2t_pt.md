# A economia e a sociedade mudam a migração de votos? (Brasil 2026 1T → 2T)

Fatores socioeconômicos municipais (Censo 2022) cruzados com 5570 municípios. Swing de Lula = % Lula destino − % Lula origen (2026 1T → 2T). Os quintis são cortados por eleitorado: cada um reúne ~20% dos votantes.

## Correlação com o swing de Lula

| Factor | Correlación | Intra-estado |
|---|---|---|
| Ingreso per cápita | +0.22 | +0.12 |
| % blancos | +0.12 | +0.02 |
| % evangélicos | +0.11 | +0.02 |
| % universitarios | +0.34 | +0.28 |
| log votos | +0.19 | +0.33 |

## Regressão (coef. em pontos por 1 desvio padrão; R²=0.51)

| Factor | Coef. | t |
|---|---|---|
| log votos | +0.57 | +25.4 |
| % universitarios | +0.10 | +3.4 |
| % blancos | -0.02 | -0.5 |
| Ingreso per cápita | -0.03 | -0.7 |
| % evangélicos | -0.09 | -4.0 |

## A inferência ecológica muda? Transições-chave por quintil

| Factor | Quintil | Flavio→Lula | Flavio→Flavio | Otros→Flavio |
|---|---|---|---|---|
| Ingreso per cápita | 1 | 0.0% | 91.8% | 40.5% |
| Ingreso per cápita | 2 | 0.0% | 91.8% | 44.1% |
| Ingreso per cápita | 3 | 0.0% | 96.2% | 43.1% |
| Ingreso per cápita | 4 | 0.0% | 98.7% | 39.7% |
| Ingreso per cápita | 5 | 0.0% | 99.3% | 42.3% |
| % universitarios | 1 | 0.0% | 96.9% | 41.2% |
| % universitarios | 2 | 0.0% | 97.8% | 50.8% |
| % universitarios | 3 | 0.0% | 97.7% | 41.7% |
| % universitarios | 4 | 0.0% | 97.4% | 47.8% |
| % universitarios | 5 | 0.1% | 95.8% | 58.7% |
| % evangélicos | 1 | 0.0% | 99.8% | 39.8% |
| % evangélicos | 2 | 0.0% | 98.0% | 52.3% |
| % evangélicos | 3 | 0.1% | 99.1% | 49.6% |
| % evangélicos | 4 | 0.0% | 97.5% | 49.4% |
| % evangélicos | 5 | 0.0% | 94.5% | 53.3% |

## Leitura
Se os coeficientes e as transições mudam fortemente entre quintis, os fatores socioeconômicos **sim** modificam a inferência: a matriz nacional mistura realidades muito distintas. A parte que sobrevive aos efeitos de estado é a relação mais limpa (não confundida pela geografia).

*Fonte socio: dschteingart/el-atlas-charts (Censo 2022). Inferência ecológica por seções (EM).*

---

*Por Rodrigo Quiroga. Trabajo realizado en colaboración con el Dr. Roberto Etchenique. Repositorio: https://github.com/rquiroga7/brasil2026*
