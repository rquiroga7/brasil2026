# Cómo proyectamos el resultado de Brasil 2026 a partir del escrutinio parcial

Daniel Schteingart · El Atlas / Cenital · elección presidencial del 4 de octubre de 2026

## 1. El problema

En Brasil el escrutinio es rapidísimo (en dos horas está casi todo contado), pero **las urnas no llegan en orden aleatorio**. En 2022 el Nordeste, donde Lula es mucho más fuerte, se contó más tarde. Por eso Bolsonaro arrancó adelante en el conteo y Lula recién lo pasó con **70% de las urnas escrutadas en la primera vuelta y con 67,8% en el balotaje**. Leer el conteo crudo en la primera hora es leer una muestra sesgada.

La proyección corrige ese sesgo: **lo ya contado se respeta y lo que falta se estima**, municipio por municipio, a partir de cuánto cambió el voto respecto de la elección anterior.

## 2. La idea en una frase

En cada municipio ya contado se mide el **cambio (swing) respecto de 2022**. Para lo que todavía no se contó, ese cambio se estima con el del mismo municipio (si ya contó una parte) y con el de municipios parecidos y cercanos. Al resultado de 2022 de cada lugar se le aplica ese cambio, y se suma todo ponderando por los votos que se esperan en cada uno.

¿Por qué el cambio y no directamente el nivel de los vecinos? Porque dos municipios vecinos pueden votar muy distinto (uno 40% Lula, el otro 70%), pero se **mueven** parecido de una elección a otra. En los datos de 2018→2022, dentro de una misma región inmediata del IBGE, el nivel del voto a Lula varía casi el doble que el cambio (desvío de 6,6 puntos contra 3,8), y eso con un salto enorme (Haddad 29% → Lula 48%).

## 3. El modelo, paso a paso (`proyeccion.py`, clase `Proyector`)

**Unidades.** Los 5.570 municipios más el exterior (una unidad aparte). Para cada una se conoce el resultado de la misma vuelta de 2022.

**Bloques.** Cada candidato de 2026 se asocia a uno de 2022: Lula ← Lula, Flávio Bolsonaro ← Jair Bolsonaro, todos los demás ← todos los demás de 2022. En el balotaje hay solo dos bloques.

**1. Cambio observado.** Para cada municipio *m* con al menos 20 votos contados y cada bloque *b*:

> y<sub>mb</sub> = logit(% hoy) − logit(% en 2022)

Se trabaja en *log-odds* y no en puntos para no proyectar más de 100% en los bastiones: +5 puntos en un municipio parejo equivale a mucho menos en uno donde Lula sacó 90%.

**2. Peso de cada municipio.** w<sub>m</sub> = 1 / (τ² + 1/(n<sub>m</sub>·p(1−p))), normalizado, con τ = 0,15. Un municipio grande pesa más que uno chico, pero con techo: la información sobre el cambio de una zona no crece infinitamente con los votos, porque los municipios difieren entre sí aunque sean enormes.

**3. Cambio esperado para cualquier municipio**, en dos capas:
- *Regresión ponderada* (con un poco de ridge para que no se dispare con pocos datos) del cambio contra el voto de 2022 de cada bloque (en logit) y el tamaño del municipio (log de votos). Captura, por ejemplo, que Lula pierda más donde había sacado más.
- *Efectos geográficos jerárquicos* sobre los residuos: región → estado → región intermedia → región inmediata del IBGE. Cada efecto es la media ponderada de los residuos del grupo, **encogida hacia cero** según cuántos municipios contados tenga: efecto = Σw·r / (Σw + κ), con κ = 2, 4, 6 y 6 "municipios equivalentes" para cada nivel. Con pocos datos en un estado, manda la región; con muchos, manda el estado.

**4. Efecto del propio municipio.** Si el municipio ya contó una parte, su propio residuo entra con peso f/(f + 0,15), donde *f* es la fracción de urnas contadas: 40% con 10% contado, 77% con 50%, 86% con 80%. Usarlo al 100% equivale a extrapolar el municipio, pero las primeras urnas de una ciudad pueden ser de un solo barrio.

**5. Votos esperados en cada municipio.** E = w·(n/f) + (1−w)·V<sub>2022</sub>·e<sup>ρ</sup>, con w = min(1, f/0,3). Con 30% contado o más, se extrapola lo contado; con menos, se usan los votos válidos de 2022 ajustados por la participación relativa ρ, que se estima con el mismo esquema jerárquico encogido.

**6. Lo que falta.** Para los E − n votos que faltan en cada municipio, el % de cada bloque es logit⁻¹(logit(% 2022) + cambio esperado), normalizado para que los bloques sumen 100%.

**7. Reparto dentro del bloque "resto".** Entre Caiado, Zema y los demás se reparte con la composición observada en el mismo municipio, región inmediata, intermedia, estado y región, encogida hacia el total nacional (κ = 20.000 votos). Así Caiado pesa donde efectivamente le va bien (Goiás) y Zema en Minas.

**8. Suma nacional.** Votos contados + votos proyectados de lo que falta, por candidato.

**Cuándo se muestra.** Cuando hay al menos 2% de los votos esperados contados y datos de 20 estados.

**Margen de error (±).** Sale de la prueba de la sección 4: el percentil 90 del error según la fracción de votos contada, con un piso prudente (0,1 + 0,3·(1 − contado) puntos por candidato y 0,15 + 0,5·(1 − contado) en la diferencia entre los dos primeros), porque la prueba no captura todo lo que puede ser distinto en 2026. Para candidatos chicos se achica en proporción a √(p(1−p)).

## 4. La prueba: proyectar 2022 a partir de 2018 (`scripts/probar_proyeccion.py`)

Es la misma tarea que hoy (2022 → 2026), pero con un cambio mucho más grande (Haddad 29% → Lula 48%), así que la prueba es exigente.

**Simulación del escrutinio.** Los votos de cada zona electoral de 2022 (~6.300) se reparten entre sus secciones, unas 470.000 urnas, con variación entre secciones (factores Gamma, κ = 12). Así, el conteo parcial de un municipio no es una copia a escala de su resultado final. Las urnas se van "contando" según cuatro escenarios:
- **Real:** cada zona termina a la hora en que terminó en 2022 (dato del TSE), y el Nordeste y el Norte llevan una demora calibrada para reproducir cuándo pasó Lula adelante (70% de las secciones en primera vuelta, 67,8% en el balotaje).
- **Azar:** secciones en orden aleatorio.
- **Sesgado:** el orden real, más un sesgo que el modelo no puede ver. Dentro de cada estado entran antes los municipios donde menos creció el PT.
- **Adverso:** ese mismo sesgo, fuerte. Es el peor caso razonable.

**Error en la diferencia Lula − Bolsonaro, en puntos** (mediana / percentil 90 de las simulaciones):

| Escrutado | Conteo crudo (real, 1ª) | Proyección real (1ª) | Proyección real (balotaje) | Sesgado (1ª / balotaje) | Adverso (1ª / balotaje) |
|---|---|---|---|---|---|
| 2% | 16,2 / 16,5 | 1,7 / 2,7 | 1,7 / 2,8 | 1,1 / 1,7 · 4,6 / 6,0 | 8,9 / 9,9 · 9,8 / 11,2 |
| 5% | 15,9 / 16,1 | 0,8 / 1,5 | 1,2 / 1,6 | 0,3 / 1,0 · 2,8 / 3,4 | 6,9 / 7,3 · 8,7 / 8,9 |
| 10% | 15,5 / 15,6 | 0,7 / 1,2 | 0,8 / 1,1 | 0,5 / 0,8 · 1,3 / 1,9 | 4,5 / 4,9 · 5,9 / 6,2 |
| 20% | 14,6 / 14,6 | 0,5 / 0,7 | 0,5 / 0,8 | 0,4 / 0,4 · 0,3 / 0,6 | 2,8 / 3,0 · 3,2 / 3,6 |
| 50% | 10,0 / 10,1 | 0,3 / 0,3 | 0,2 / 0,3 | 0,1 / 0,2 · 0,1 / 0,1 | 0,8 / 1,0 · 1,0 / 1,1 |

En orden aleatorio el error es mínimo desde el principio (menos de 0,6 puntos con 2% contado). El tercer puesto (Tebet sobre Ciro) se proyectó bien en el 100% de las simulaciones de todos los escenarios.

**Comparación con alternativas más simples** (`scripts/comparar_metodos.py`; escenario real, primera vuelta, mediana del error en la diferencia, en puntos; el signo menos es un error a favor de Bolsonaro):

| Escrutado | Municipios con algún dato | Conteo crudo | Extrapolar cada municipio contado | Extrapolar + completar los que faltan con su voto anterior | Modelo (swing) |
|---|---|---|---|---|---|
| 2% | 41% | −16,3 | −9,8 | −4,4 | +1,7 |
| 5% | 61% | −16,0 | −6,8 | −2,1 | +0,8 |
| 10% | 77% | −15,5 | −4,2 | −0,9 | +0,7 |
| 20% | 89% | −14,6 | −2,2 | −0,4 | +0,4 |
| 50% | 98% | −10,0 | −0,4 | 0,0 | +0,2 |

Extrapolar solo lo que llega ya mejora muchísimo el conteo crudo, pero en la primera media hora ignora los municipios que todavía no informaron, que justamente son los que llegan tarde. El swing es lo que arregla los primeros minutos. Pasado el 20-30%, cualquier método razonable converge.

## 5. Limitaciones

- **Sesgo dentro de un mismo estado.** Si entran primero los lugares que cambiaron distinto de los que vienen después (escenarios "sesgado" y "adverso"), el modelo no tiene cómo verlo. En los primeros 15-20 minutos hay que leerlo con cuidado.
- **Candidatos nuevos.** Caiado y Zema no existían en 2022 y su voto está concentrado. Hasta que su zona tenga municipios contados, el reparto del "resto" puede estar corrido.
- **Supuesto de herencia.** Se supone que Flávio hereda la geografía de Jair. El modelo mide los desvíos, pero parte de ahí.
- **Votos esperados.** Con poco contado en un municipio, dependen de cómo se mueva la participación respecto de 2022.
- **Simplificaciones de la prueba.** En la simulación, las urnas dentro de una zona se cuentan sin un orden particular. En la realidad, el orden dentro de una ciudad también puede estar sesgado.

## 6. Cómo correrlo

Requiere Python 3 con `numpy` y `pandas` (`pip install -r requirements.txt`).

- **Ver la proyección funcionando, con un escrutinio ficticio:** `python vivo.py --simulacro`. La consola imprime cada ciclo el conteo y la proyección, y los datos quedan en `data/vivo/2026-1.json`. El simulacro parte de los resultados de 2022, le mete un cambio regional inventado y hace que el Nordeste se cuente más tarde.
- **Con el escrutinio real del TSE:** `python vivo.py` (primera vuelta) o `python vivo.py --turno 2`. Lee `resultados.tse.jus.br` cada 30 segundos.
- **La prueba 2018 → 2022:** `python scripts/probar_proyeccion.py <carpeta>`. La carpeta tiene que tener los datos abiertos del TSE (`cdn.tse.jus.br/estatistica/sead/odsele/`): `votacao_candidato_munzona_2018_BR.csv` y `votacao_candidato_munzona_2022_BR.csv` (miembros `_BR` de los zip `votacao_candidato_munzona_AAAA.zip`), `detalhe_votacao_munzona_2022_BR.csv`, la configuración de municipios del TSE (`ele2026_6257_config_mun-e006257-cm.json`, de `resultados.tse.jus.br/oficial/ele2026/6257/config/mun-e006257-cm.json`) y `mun_meta.json` (API de localidades del IBGE: `servicodados.ibge.gov.br/api/v1/localidades/municipios`). Escribe `data/proyeccion-calibracion.json`, que son los márgenes de error.

## 7. Archivos

| Archivo | Qué es |
|---|---|
| `proyeccion.py` | El modelo (`Proyector`) y su uso en vivo (`ProyeccionEnVivo`: referencia 2022, márgenes, historia) |
| `vivo.py` | Lector del escrutinio del TSE y simulacro; llama a la proyección en cada ciclo |
| `scripts/probar_proyeccion.py` | Prueba 2018 → 2022 por sección, con los cuatro escenarios de orden; calibra los márgenes |
| `scripts/comparar_metodos.py` | Comparación con el conteo crudo y con extrapolar municipio por municipio |
| `scripts/procesar_2022.py` | Arma `data/elecciones-2022.js` (resultados 2022 por municipio) desde los datos abiertos del TSE |
| `scripts/armar_jerarquia.py` | Arma `data/mun-jerarquia.json` (región, estado, región intermedia e inmediata de cada municipio) |
| `data/elecciones-2022.js` | Resultados de 2022 por municipio, 1ª y 2ª vuelta: la referencia |
| `data/mun-jerarquia.json` | Jerarquía geográfica del IBGE |
| `data/proyeccion-calibracion.json` | Márgenes de error por fracción contada, de la prueba |
