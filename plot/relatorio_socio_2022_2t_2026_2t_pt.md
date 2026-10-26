# A economia e a sociedade mudam a migração de votos? (Brasil 2022 2T → 2026 2T)

Fatores socioeconômicos municipais (Censo 2022) cruzados com 5570 municípios. Swing de Lula = % Lula destino − % Lula origen (2022 2T → 2026 2T).

## Correlação com o swing de Lula

| Factor | Correlación | Intra-estado |
|---|---|---|
| Ingreso per cápita | -0.06 | +0.17 |
| % blancos | -0.13 | -0.02 |
| % evangélicos | +0.24 | +0.25 |
| % universitarios | +0.26 | +0.36 |
| log votos | +0.28 | +0.36 |

## Regressão (coef. em pontos por 1 desvio padrão; R²=0.45)

| Factor | Coef. | t |
|---|---|---|
| log votos | +0.92 | +23.8 |
| % evangélicos | +0.55 | +13.8 |
| % universitarios | +0.45 | +8.6 |
| Ingreso per cápita | +0.08 | +0.9 |
| % blancos | -0.18 | -2.3 |

## A inferência ecológica muda? Transições-chave por quintil

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

## Leitura
Se os coeficientes e as transições mudam fortemente entre quintis, os fatores socioeconômicos **sim** modificam a inferência: a matriz nacional mistura realidades muito distintas. A parte que sobrevive aos efeitos de estado é a relação mais limpa (não confundida pela geografia).

*Fonte socio: dschteingart/el-atlas-charts (Censo 2022). Inferência ecológica por seções (EM).*

---

*Por Rodrigo Quiroga. Trabajo realizado en colaboración con el Dr. Roberto Etchenique. Repositorio: https://github.com/rquiroga7/brasil2026*
