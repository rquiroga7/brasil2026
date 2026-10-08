# Migración de votos en Brasil: 2022 → 2026 (Presidente, 1ª vuelta)

*Estimación ecológica por secciones electorales (EM). 5x5 bloques.*

## Cómo se hizo
Se emparejaron **461.219 secciones** entre 2022 y 2026 por (UF, municipio, zona,
sección). En cada sección se conoce el voto por bloque en ambos años y los
electores habilitados (aptos). Se estima la matriz de transición θ[j,k] =
P(votar k en 2026 | bloque j en 2022) por máxima verosimilitud (EM), con
intervalos por bootstrap. Los "No votó" son aptos − comparecimento.

## Resultado principal (2022 → 2026)
| Origen \ Destino | Lula | Flavio | Otros | Blanco/Nulo | No voto |
|---|---|---|---|---|---|
| **Lula** (57.3M) | 90.5% (51.8M) | 2.3% (1.3M) | 0.7% (0.4M) | 2.9% (1.6M) | 3.7% (2.1M) |
| **Bolsonaro** (51.1M) | 0.0% (0.0M) | 93.6% (47.8M) | 4.6% (2.4M) | 0.0% (0.0M) | 1.7% (0.9M) |
| **Otros** (9.9M) | 4.3% (0.4M) | 13.9% (1.4M) | 53.6% (5.3M) | 3.6% (0.4M) | 24.5% (2.4M) |
| **Blanco/Nulo** (5.5M) | 0.0% (0.0M) | 0.9% (0.0M) | 12.4% (0.7M) | 64.1% (3.5M) | 22.7% (1.2M) |
| **No voto** (32.7M) | 2.4% (0.8M) | 14.3% (4.7M) | 1.3% (0.4M) | 1.3% (0.4M) | 80.7% (26.4M) |

## Lectura
- **Lula retuvo el 90.5%** de su electorado; fugas: 2.3% a Flávio y 3.7% a la abstención.
- **Bolsonaro transfirió el 93.6% a Flávio**; casi nada a Lula (0.0%).
- Los **"Otros" 2022** (Ciro, Tebet, etc.) se repartieron: 13.9% a Flávio, 4.3% a Lula, 24.5% no votó.
- Entre quienes **no votaron en 2022**, 14.3% votó a Flávio y 2.4% a Lula en 2026.

## Balotaje 2022 (1ª → 2ª vuelta)
| Origen \ Destino | Lula | Bolsonaro | Blanco/Nulo | No voto |
|---|---|---|---|---|
| **Lula** (57.3M) | 96.5% (55.2M) | 0.0% (0.0M) | 1.3% (0.7M) | 2.2% (1.3M) |
| **Bolsonaro** (51.1M) | 0.0% (0.0M) | 100.0% (51.1M) | 0.0% (0.0M) | 0.0% (0.0M) |
| **Otros** (9.9M) | 29.5% (2.9M) | 51.2% (5.1M) | 14.7% (1.5M) | 4.5% (0.4M) |
| **Blanco/Nulo** (5.5M) | 21.0% (1.1M) | 15.8% (0.9M) | 63.1% (3.4M) | 0.0% (0.0M) |
| **No voto** (32.7M) | 3.3% (1.1M) | 2.6% (0.9M) | 0.2% (0.1M) | 93.8% (30.7M) |

## Contexto 2018 → 2022
| Origen \ Destino | Lula | Bolsonaro | Otros | Blanco/Nulo | No voto |
|---|---|---|---|---|---|
| **Haddad (PT)** (31.3M) | 88.3% (27.7M) | 4.1% (1.3M) | 0.1% (0.0M) | 0.3% (0.1M) | 7.1% (2.2M) |
| **Bolsonaro** (49.3M) | 0.0% (0.0M) | 87.5% (43.1M) | 5.0% (2.5M) | 0.6% (0.3M) | 7.0% (3.4M) |
| **Otros** (26.4M) | 65.5% (17.3M) | 4.0% (1.1M) | 23.8% (6.3M) | 2.6% (0.7M) | 4.1% (1.1M) |
| **Blanco/Nulo** (10.3M) | 52.0% (5.4M) | 2.6% (0.3M) | 0.9% (0.1M) | 34.5% (3.6M) | 10.1% (1.0M) |
| **No voto** (29.9M) | 10.7% (3.2M) | 8.2% (2.4M) | 1.5% (0.5M) | 1.7% (0.5M) | 77.9% (23.3M) |

## 2018 → 2026 (encadenado, supuesto de Markov)
| Origen \ Destino | Lula | Flavio | Otros | Blanco/Nulo | No voto |
|---|---|---|---|---|---|
| **Haddad (PT)** (31.3M) | 80.0% (25.1M) | 6.9% (2.2M) | 1.0% (0.3M) | 2.9% (0.9M) | 9.2% (2.9M) |
| **Bolsonaro** (49.3M) | 0.4% (0.2M) | 83.6% (41.2M) | 6.9% (3.4M) | 0.6% (0.3M) | 8.5% (4.2M) |
| **Otros** (26.4M) | 60.4% (16.0M) | 9.1% (2.4M) | 13.8% (3.6M) | 4.5% (1.2M) | 12.3% (3.2M) |
| **Blanco/Nulo** (10.3M) | 47.3% (4.9M) | 5.5% (0.6M) | 5.3% (0.6M) | 23.8% (2.4M) | 18.1% (1.9M) |
| **No voto** (29.9M) | 11.6% (3.5M) | 19.2% (5.8M) | 2.5% (0.7M) | 2.5% (0.7M) | 64.2% (19.2M) |

## Advertencias
Inferencia **ecológica**: son patrones agregados por sección, no seguimiento
individual. El encadenado 2018→2026 asume que 2026 depende de 2022 (Markov).
Cambios de padrón y de composición de las secciones introducen error.
Las celdas 0% o 100% son soluciones de frontera del EM (electorados muy rígidos):
léanse como «casi nulo» / «casi total», no como certeza.

---
*Por Rodrigo Quiroga. Trabajo realizado en colaboración con el Dr. Roberto Etchenique. Repositorio: https://github.com/rquiroga7/brasil2026*
