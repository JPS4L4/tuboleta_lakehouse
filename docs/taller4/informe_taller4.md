<div class="portada">

**Institución Universitaria ITM**

<h1 class="portada-titulo">Laboratorio de Optimización de Consultas</h1>

Diagnóstico, intervención y medición sobre el Mini-Lakehouse TuBoleta (DuckDB + Parquet)

**Informe técnico — Taller 4**

Curso: Tópicos Avanzados en Bases de Datos

**Integrantes**<br>
Luis Manuel Contreras<br>
Juan Pablo Salazar

**Docente**<br>
Roberto Carlos Rahamut Suteu

Medellín, 3 de noviembre de 2026

Repositorio: github.com/JPS4L4/tuboleta_lakehouse

</div>

<h1 class="salto">1. Resumen ejecutivo</h1>

Este taller partió del sistema analítico que construimos en el Taller 3: la información de venta de boletas de TuBoleta para el Estadio Atanasio Girardot, organizada en una zona "Gold" de archivos Parquet que consultamos con DuckDB. Elegimos tres preguntas de negocio representativas: **¿cuánto vendió cada evento en septiembre?** (Q1), **¿cuánto vendió cada zona del estadio en septiembre?** (Q2) y **¿cuántos intentos de compra terminaron en compra, abandono o rechazo?** (Q3).

En lugar de suponer por qué una consulta es lenta, le pedimos al motor que nos mostrara su plan de ejecución, es decir, el paso a paso de cómo resuelve cada pregunta. Encontramos lo siguiente:

- **Q1 y Q2 leían todos los datos de ventas para responder sobre un solo mes.** El archivo estaba guardado como un único bloque sin ordenar, así que el motor no tenía forma de saltarse los meses que no interesaban.
- **Q3 no tenía ningún problema.** Necesita mirar todos los intentos de compra, y eso es justo lo que hacía.

Aplicamos una corrección por consulta: ordenar el archivo por fecha en bloques pequeños (Q1), separar los datos en carpetas por mes (Q2) y actualizar las estadísticas del motor (Q3, como experimento de control). Las dos primeras funcionaron en lo que controlan: **el motor pasó a leer 1,8 y 4,2 veces menos datos**. Pero el tiempo no mejoró: Q1 quedó igual (0,99x), Q2 empeoró un 29 % y Q3 quedó igual (0,98x).

**Lo más valioso que aprendimos es por qué.** Con unas 200.000 ventas, cada consulta tarda entre 2 y 5,5 milisegundos, y más de la mitad de ese tiempo (en Q1, unos 2,5 de 4,5 ms) es un costo fijo del motor (preparar la consulta, abrir archivos) que no depende de cuántos datos se lean. Las optimizaciones de acceso atacan la otra mitad. A esta escala el beneficio existe y es medible, pero el tamaño de los datos lo limita. El aprendizaje para el diseño es que estas decisiones son baratas de tomar al construir el pipeline y su beneficio crece con el volumen. Por eso conviene incorporarlas desde el inicio, sin esperar que aceleren un sistema pequeño.

<h1 class="salto">2. Diagnóstico</h1>

**Alcance y motor.** Este documento conserva el diagnóstico de optimización OLAP del primer corte, con las cifras de la corrida final del 26-11-2026, y añade la corrección de tipos en DuckDB y el índice compuesto en CockroachDB. DuckDB + Parquet es el lakehouse analítico; CockroachDB es el motor OLTP. Las mediciones de CockroachDB son ejecuciones locales sobre filas experimentales reproducibles, no ventas reales ni resultados de producción.

**Entorno de medición.** DuckDB 2.0.0 sobre el Gold en Parquet del M3, sin modificar · AMD Ryzen 5 9600X (12 hilos lógicos) · 15,1 GB RAM · Windows 11 Pro · Python 3.14.6. Cada tiempo es la mediana de 5 ejecuciones, después de 3 ejecuciones de calentamiento. Los planes completos están en `docs/taller4/planes/` y se regeneran con `python -m scripts.taller4_optimizacion`.

**Origen de las cifras.** Los tiempos de este informe provienen de la corrida final del 26-11-2026 en esta máquina (Python 3.14.6, DuckDB 2.0.0, CockroachDB v25.4.0 de un solo nodo en Docker, Windows 11, AMD64), con el pipeline extraído desde CockroachDB (`USE_SYNTHETIC=false`). Las medianas de corridas de desarrollo anteriores fueron distintas (por ejemplo, 2,08x en la lectura con índice y 3,98x en tipos); aquí solo se reportan las de esta corrida, con sus CSV en `docs/taller4/`.

**Una particularidad de DuckDB 2.0.** El árbol de `EXPLAIN ANALYZE` informa filas reales, archivos y row groups, pero muestra `0µs` en todos los operadores. Para nombrar el operador más costoso con evidencia, el script captura además el profiling JSON del motor (`profiling_mode='detailed'`), que trae el tiempo y la cardinalidad estimada de cada operador. Ese tiempo es **CPU sumada entre hilos**, no tiempo de reloj, así que se usa para comparar operadores entre sí.

## 2.1 Tabla de diagnóstico

| Campo | Q1 — Ingresos por evento, sep-2026 | Q2 — Ingresos por zona, sep-2026 | Q3 — Embudo de conversión |
|---|---|---|---|
| Tiempo baseline (mediana) | 4,97 ms | 2,44 ms | 5,49 ms |
| Motor usado | DuckDB 2.0.0 / Parquet | DuckDB 2.0.0 / Parquet | DuckDB 2.0.0 / Parquet |
| Operador más costoso | `TABLE_SCAN` de la fact: 0,68 ms de CPU (32 %), `Row Groups Scanned: 1 / 1`, 261,1 kB | `TABLE_SCAN` de la fact: 0,51 ms de CPU (83 %), `1 / 1`, 246,3 kB | `TABLE_SCAN` de intentos: 1,87 ms de CPU (41 %), 260.294 filas; `HASH_GROUP_BY` 1,73 ms |
| Problema identificado | Acceso secuencial sin data skipping posible: 1 row group, fact sin ordenar por `tiempo_sk` | Acceso secuencial de un archivo único para un filtro que retiene el 16,3 % de las filas | Ninguno de acceso: agregación total sin filtro |
| Indicador que lo revela | 1 (208.236 filas leídas, 2 devueltas) → causa raíz 4 | 1 → causa raíz 4 | Ninguno |
| Indicadores descartados | 3 (dos `HASH_JOIN`, build en dims de 720 y 5 filas) · 5 (`mes INTEGER = 9`, sin `CAST`) · 2 presente pero inocuo (ver abajo) | 2 (estimadas 41.647 frente a 34.039 reales, 1,2x) · 3 (sin joins) · 5 (`tiempo_sk BIGINT` contra enteros) | 2 (estimaciones exactas) · 3 (`HASH_JOIN`, sin `CROSS_JOIN`) · 4 y 5 (sin predicado) |

## 2.2 Q1 — Ingresos por evento en septiembre 2026

```sql
SELECT e.nombre_evento, t.mes, COUNT(*) AS boletas, SUM(f.precio_pagado) AS ingresos
FROM fact_ventas_boletas f
JOIN dim_tiempo t ON t.tiempo_sk = f.tiempo_sk
JOIN dim_evento e ON e.evento_sk = f.evento_sk
WHERE t.anio = 2026 AND t.mes = 9
GROUP BY 1, 2
```

Fragmento del plan (`Q1_antes.txt`), leído de abajo hacia arriba:

```text
Summary:  Total Time: 0.0077s · Data Read: 261.1 kB
Hash Join (INNER)  tiempo_sk = tiempo_sk                         34,039 rows
├─ Table Scan  fact_ventas_boletas.parquet                        34,039 rows
│    Dynamic Filters: optional: tiempo_sk IN PRF(tiempo_sk)
│    Row Groups Scanned: 1 / 1
└─ Filter  tiempo_sk BETWEEN 2026022310 AND 2026101623                720 rows
   └─ Table Scan  dim_tiempo.parquet   Filters: mes = 9               720 rows
```

**Lectura.** DuckDB filtra `dim_tiempo` por `mes = 9` y obtiene 720 filas, las horas de septiembre. A esa dimensión le aplica además un rango que coincide exactamente con el min/max de `tiempo_sk` en la fact: es un filtro derivado de las estadísticas del archivo. Con esas 720 filas construye la tabla hash del join, y de ella sale un **filtro dinámico** (`PRF`) que se empuja al scan de la fact. Ese filtro solo puede saltarse bloques si las estadísticas min/max de cada bloque (zonemaps) lo permiten. Como la fact tiene **un único row group** (`1 / 1`) cuyo rango cubre todo el período, no se puede descartar nada: se decodifica la tabla completa para quedarse con el 16,3 %.

**Por qué es el Indicador 1 con causa en el 4.** El motor lee 208.236 filas para devolver 2: es acceso secuencial. Lo que impide evitarlo es la ausencia de data skipping, porque la fact no está ordenada por `tiempo_sk` (`is_monotonic_increasing = False`) y se escribió sin `row_group_size`.

**Hallazgo secundario: Indicador 2.** El profiling muestra que la salida de los joins se estimó en **1.651 filas y fueron 34.039 (20,6x)**, por encima del umbral de 10x del enunciado. Lo documentamos, pero no es el problema principal: aun con esa estimación, el planner eligió el algoritmo correcto (Hash Join) y las tablas build correctas (las dimensiones pequeñas). Un error de estimación solo es un problema cuando lleva a una mala decisión, y aquí no la hubo.

## 2.3 Q2 — Ingresos por zona en septiembre 2026

```sql
SELECT zona_sk, COUNT(*) AS boletas, SUM(precio_pagado) AS ingresos
FROM fact_ventas_boletas
WHERE tiempo_sk BETWEEN 2026090100 AND 2026093023
GROUP BY 1
```

```text
Summary:  Total Time: 0.0021s · Data Read: 246.3 kB
Perfect Hash Group By                                                4 rows
└─ Table Scan  fact_ventas_boletas.parquet                      34,039 rows
     Filters: (tiempo_sk >= 2026090100) AND (tiempo_sk <= 2026093023)
     Row Groups Scanned: 1 / 1
```

**Lectura.** Este es el caso puro del problema. El filtro está directo sobre la fact y DuckDB lo empuja al scan (no hay `CAST`: `BIGINT` contra literales enteros, así que se descarta el Indicador 5). La estimación es razonable (41.647 frente a 34.039). Aun así se leen los 246,3 kB de las tres columnas proyectadas, porque el único row group contiene todos los meses. El scan concentra el 83 % de la CPU de la consulta. DuckDB elige `PERFECT_HASH_GROUP_BY` porque conoce el rango pequeño de `zona_sk`: un detalle que volverá a importar en la intervención.

## 2.4 Q3 — Embudo de conversión por evento

```sql
SELECT d.nombre_evento, COUNT(*) AS intentos, SUM(i.es_compra) AS compras,
       SUM(i.es_abandono) AS abandonos, SUM(i.es_rechazo_unique) AS rechazos
FROM fact_intentos_compra i JOIN dim_evento d ON d.evento_sk = i.evento_sk
GROUP BY 1
```

```text
Hash Group By                                                         5 rows
└─ Hash Join (INNER)  evento_sk = evento_sk                     260,294 rows
   ├─ Table Scan  fact_intentos_compra.parquet   1 / 1          260,294 rows
   └─ Table Scan  dim_evento.parquet                                  5 rows
```

**Lectura.** Las estimaciones son exactas en todos los nodos (260.294 = 260.294 y 5 = 5), el join es un `HASH_JOIN` con build en la dimensión de 5 filas, y no hay `WHERE`. Que se lean 260.294 filas para devolver 5 **no** es el Indicador 1: esa reducción la hace la agregación, no un filtro, y la consulta necesita todas las filas. No existe un subconjunto que un índice, un zonemap o una partición pudieran evitar. **Diagnóstico: no hay problema que resolver.** Por eso Q3 se usa como experimento de control.

<h1 class="salto">3. Intervenciones</h1>

Aplicamos una sola intervención por problema. El Gold original no se modifica: cada intervención escribe en `lakehouse/gold_t4/`, y el script verifica con `assert` que la consulta devuelve exactamente el mismo resultado antes y después. Para explicar los resultados modestos corrimos además controles de medición que **no son intervenciones**, en `scripts/taller4_complementario.py` (mediana de 15 corridas).

## 3.1 I-3 en Q1 — Ordenar la fact por `tiempo_sk` en row groups de 20.000 filas

```python
df.sort_values("tiempo_sk").to_parquet(ordenado, index=False, row_group_size=20_000)
```

| | Antes | Después |
|---|---|---|
| Row groups de la fact | 1 | 11 |
| `Row Groups Scanned` | 1 / 1 | **3 / 11** |
| `Data Read` | 261,1 kB | **142,4 kB (1,8x menos)** |
| Operadores del plan | 11 (2 `HASH_JOIN`, `HASH_GROUP_BY`) | los mismos 11 |
| Tiempo (mediana) | 4,97 ms | 5,02 ms → **0,99x (sin ganancia)** |

**Por qué funciona.** Parquet guarda min/max por columna en cada row group. Con la fact ordenada, cada row group cubre un rango contiguo de `tiempo_sk`, y el filtro dinámico que llega desde `dim_tiempo` se compara contra esos rangos. Revisando los metadatos del archivo, solo los row groups 7 (2026080615–2026090116), 8 (2026090116–2026091020) y 9 (2026091020–2026101211) intersectan septiembre: exactamente los 3 de 11 que reporta el plan. Se decodifican unas 60.000 filas en lugar de 208.236 (3,5x menos), mientras que los bytes leídos bajan 1,8x; no aislamos con una medición por qué ambas proporciones difieren.

**Por qué el tiempo no mejora.** Lo medimos en lugar de suponerlo (controles de 15 corridas, `analisis_complementario.md`):

| Fact | Hilos | Mediana (ms) | CPU de operadores (ms) | Fuera de los operadores (ms) |
|---|---:|---:|---:|---:|
| original (1 row group) | 1 | 4,45 | 1,82 | 2,53 |
| original (1 row group) | 12 | 4,80 | 1,78 | — |
| ordenada (11 row groups) | 1 | **4,41** | **1,61** | 2,70 |
| ordenada (11 row groups) | 12 | 5,01 | 7,25 | — |

1. **Overhead fijo.** Unos 2,5 ms por ejecución (2,53 y 2,70 ms) ocurren fuera de los operadores (planificación, apertura de archivos, metadatos). Es más de la mitad del tiempo, e I-3 no lo toca, así que el techo de mejora a esta escala ronda 1,8x.
2. **Paralelismo.** El row group es la unidad de paralelismo de DuckDB sobre Parquet. Con 1 row group, el scan es secuencial: la CPU casi no cambia entre 1 y 12 hilos (1,82 y 1,78 ms). Con 11, DuckDB reparte el trabajo y luego combina agregaciones parciales, y esa coordinación hace subir la CPU de 1,61 a 7,25 ms. **Aislando el efecto con 1 hilo, I-3 reduce la CPU un 11,5 % (1,82 → 1,61 ms), pero el tiempo casi no se mueve: 4,45 → 4,41 ms (1,01x).**
3. **Caché.** Después del calentamiento el archivo está en la caché del sistema operativo: leer unos 119 kB menos ahorra decodificación, no I/O de disco.

La estimación del join (1.651 frente a 34.039) no cambia: reordenar los datos no le da al planner estadísticas nuevas sobre la relación entre las tablas.

## 3.2 I-6 en Q2 — Particionado Hive `year=/month=`

```python
df["year"]  = df["tiempo_sk"] // 1_000_000        # la fact no tiene fecha: se deriva de YYYYMMDDHH
df["month"] = (df["tiempo_sk"] // 10_000) % 100
for (y, m), g in df.groupby(["year", "month"]):
    g.drop(columns=["year", "month"]).to_parquet(f"{base}/year={y}/month={m:02d}/data.parquet", index=False)
# consulta: read_parquet('.../**/*.parquet', hive_partitioning=true) WHERE year = 2026 AND month = 9
```

| | Antes | Después |
|---|---|---|
| Archivos leídos | 1 (toda la fact) | **1 de 9** (`Scanning Files: 1/9`) |
| `Data Read` | 246,3 kB | **58,8 kB (4,2x menos)** |
| Filtro | `tiempo_sk` por rango, empujado al scan | `CAST(month AS INTEGER) = 9`, sobre la ruta |
| Filas estimadas / reales | 41.647 / 34.039 | **1** / 34.039 |
| Agregación | `PERFECT_HASH_GROUP_BY` | `HASH_GROUP_BY` |
| Tiempo (mediana) | 2,44 ms | 3,14 ms → **0,78x (empeoró un 29 %)** |

**Qué funcionó.** El partition pruning se resuelve sobre los nombres de carpeta antes de abrir ningún Parquet: de 9 archivos solo se abre `month=09`, y los bytes leídos caen 4,2x. El `CAST` sobre `month` es técnicamente un Indicador 5, pero inofensivo: se evalúa sobre 9 valores de partición, no sobre 208.236 filas.

**Por qué empeoró.** Separamos el costo del mecanismo del costo de los datos con un control:

| Variante (mediana de 15) | ms |
|---|---:|
| Archivo único, filtro por rango (baseline) | 1,81 |
| Glob Hive + partition pruning (I-6) | 2,76 |
| Lectura directa de `month=09/data.parquet` | **1,26** |

**Leer solo septiembre cuesta un 30 % menos que el baseline** (1,26 frente a 1,81 ms), así que la reducción de datos es real. Lo que se come la ganancia, unos 1,5 ms, es el mecanismo: expandir el glob `**/*.parquet`, listar 9 carpetas y parsear los valores `year=`/`month=` de cada ruta. Además, al leer por glob el planner **pierde las estadísticas**: estima 1 fila en lugar de 34.039 (la intervención introdujo un Indicador 2 que antes no existía) y abandona `PERFECT_HASH_GROUP_BY`, que necesita conocer el rango de `zona_sk`. Es el clásico problema de los archivos pequeños: el particionado conviene cuando cada partición es mucho más grande que el costo de listarla (millones de filas por mes, o almacenamiento de objetos donde cada archivo descartado ahorra una petición de red), no con 208.000 filas en 9 archivos. Los 1,81 ms del control no son los 2,44 ms de la tabla principal: son protocolos distintos (mediana de 15 frente a mediana de 5) y no se combinan.

## 3.3 I-2 en Q3 — `ANALYZE` (experimento de control)

Sobre vistas de Parquet `ANALYZE` no tiene estadísticas propias que actualizar, así que el control se hace sobre tablas materializadas en DuckDB. El plan y la mediana se toman antes y después de `ANALYZE` **en la misma conexión**, para que `ANALYZE` sea la única variable.

| | Antes | Después |
|---|---|---|
| Plan | `HASH_GROUP_BY` ← `PROJECTION` ← `HASH_JOIN` ← 2 × `TABLE_SCAN` | idéntico (verificado por el script) |
| Estimaciones | 260.294 / 5, exactas | 260.294 / 5 |
| Tiempo (mediana) | 2,65 ms | 2,69 ms → **0,98x (ruido)** |

**Justificación.** `ANALYZE` corrige estadísticas desactualizadas o ausentes, y aquí las estimaciones ya eran exactas: el resultado nulo era la predicción, y confirmarlo valida el diagnóstico.

**Experimento adicional.** ¿`ANALYZE` habría corregido el error de 20,6x de Q1? Lo probamos con las estimaciones de `EXPLAIN`:

| Fuente de datos | Estimada antes | Estimada después de `ANALYZE` | Real |
|---|---:|---:|---:|
| Vistas sobre Parquet | 1.651 | 1.651 | 34.039 |
| Tablas materializadas | 24.037 | 24.037 | 34.039 |

`ANALYZE` no mueve la estimación en ningún caso. Lo que la mejora, de 20,6x a 1,4x de error, es **materializar**: al cargar una tabla nativa, DuckDB recolecta estadísticas propias que una vista sobre Parquet no tiene. El Indicador 2 de Q1 nace de consultar Parquet a través de vistas, no de estadísticas viejas, y `ANALYZE` no es la herramienta que lo resuelve.

<h1>4. Tabla de benchmarks</h1>

| Query | Problema (vocabulario M4) | Intervención | t antes (ms) | t después (ms) | Factor | ¿Cambió el plan? |
|---|---|---|---:|---:|---:|---|
| Q1 — Ingresos por evento, sep-2026 | Acceso secuencial sin data skipping: 1 row group, fact sin ordenar; 208.236 filas leídas, 2 devueltas | I-3: ordenar por `tiempo_sk`, `row_group_size=20_000` | 4,97 | 5,02 | 0,99x | Sí, en el acceso: row groups 1/1 → 3/11, 261,1 → 142,4 kB. Mismos operadores. |
| Q2 — Ingresos por zona, sep-2026 | Acceso secuencial de un archivo único para un 16,3 % de filas | I-6: particionado Hive `year/month` | 2,44 | 3,14 | 0,78x | Sí: archivos 1/9, 246,3 → 58,8 kB; `PERFECT_HASH` → `HASH_GROUP_BY`; estimación 41.647 → 1 |
| Q3 — Embudo de conversión | Ninguno: agregación total, estimaciones exactas | I-2: `ANALYZE` (control) | 2,65 | 2,69 | 0,98x | No: plan idéntico |

**Contexto de la medición.** DuckDB 2.0.0 · Ryzen 5 9600X · 15,1 GB · Windows 11 Pro. Calentamiento ×3, mediana de 5. Q3 se mide sobre tablas materializadas (por eso su "antes" es menor que su baseline de diagnóstico sobre Parquet, 5,49 ms).

**Variabilidad.** En la corrida final, las desviaciones estándar de las 5 repeticiones van de 0,09 a 0,39 ms (tabla de la sección 4.1), del mismo orden que la diferencia entre antes y después de Q1 (0,05 ms) y de Q3 (0,04 ms); por eso esos dos factores son indistinguibles de 1,0x. En Q2 la diferencia (0,70 ms) es mayor que la desviación, aunque los rangos de las repeticiones se solapan. Como referencia histórica, en 6 corridas completas del desarrollo (no son esta corrida) los factores de Q1 oscilaron entre 1,05x y 1,20x, los de Q2 entre 0,87x y 1,23x y los de Q3 entre 0,81x y 1,06x; la corrida final queda fuera de esos rangos en Q1 y Q2, lo que confirma que con consultas de 2 a 5 ms el factor de tiempo cambia de una corrida a otra. Por eso las conclusiones se apoyan en lo que el plan muestra de forma determinista (row groups, archivos y bytes leídos, operadores elegidos) y en controles con 15 corridas, no en un solo factor de tiempo.

**Lectura honesta.** Las dos intervenciones con diagnóstico real hicieron lo que la teoría predice sobre el acceso: 1,8x y 4,2x menos datos leídos. Ninguna se tradujo en una mejora de tiempo en esta corrida (Q1 0,99x; Q2 0,78x), por razones identificadas y medidas: el overhead fijo, el costo de coordinar el paralelismo y el costo del glob y las rutas Hive. El control (Q3, 0,98x) dio el resultado nulo esperado. La evidencia favorable de Q1 y Q2 es la reducción de lectura, no el tiempo.

## 4.1 Resultados medidos de tipos e índice

| Experimento | Antes | Después | Hallazgo |
|---|---:|---:|---|
| CockroachDB: mediana de consulta (7 ejecuciones) | 426,217 ms | 210,591 ms | 2,02x más rápida con el índice compuesto |
| CockroachDB: `EXPLAIN ANALYZE` (una ejecución) | Full scan: 1.000.000 filas, 73 MiB, 8 llamadas gRPC; 732 ms | Índice: 164.066 filas, 9,7 MiB, 1 llamada gRPC; 241 ms | El plan cambia a rango por `tiempo_sk` |
| CockroachDB: inserción de 20.000 filas (mediana de 3) | 308,35 ms | 358,24 ms | El índice añade 16,2 % al tiempo de inserción (1,16x) |
| DuckDB: filtro `VARCHAR` + `CAST` frente a `TIMESTAMP` | 14,338 ms | 4,285 ms | 3,35x más rápida; mismo resultado |

En CockroachDB, la mediana de consulta mide siete ejecuciones con el resultado consumido; los tiempos de los planes son ejecuciones instrumentadas independientes y no se comparan como medianas. El plan anterior lee la tabla completa; el posterior usa `idx_fact_ventas_tiempo_evento`. El costo de lectura menor tiene como contrapartida más trabajo al insertar. Los planes completos y la tabla de resultados están en `planes/cockroach_Q1_antes_full_scan.txt`, `planes/cockroach_Q1_despues_index_scan.txt` y `benchmarks_cockroach.md`.

**Estadística consolidada.** Mediana, mínimo, máximo y desviación estándar muestral de cada medición de la corrida final, copiados de `estadisticas_duckdb.csv`, `estadisticas_tipos.csv` y `estadisticas_cockroach.csv` (las observaciones individuales están en los `mediciones_crudas_*.csv`). Los controles complementarios de 15 corridas son otro protocolo y no se mezclan aquí.

| Medición | Escenario | n | Mediana (ms) | Mín (ms) | Máx (ms) | Desv. est. (ms) |
|---|---|---:|---:|---:|---:|---:|
| Q1 | antes (fact original) | 5 | 4,9685 | 4,7801 | 5,2538 | 0,1792 |
| Q1 | después (ordenada, I-3) | 5 | 5,0216 | 4,5836 | 5,2936 | 0,2823 |
| Q2 | antes (archivo único) | 5 | 2,4360 | 2,1812 | 3,1896 | 0,3907 |
| Q2 | después (Hive, I-6) | 5 | 3,1393 | 2,7268 | 3,3723 | 0,2582 |
| Q3 | baseline sobre Parquet | 5 | 5,4853 | 5,3407 | 5,7529 | 0,1890 |
| Q3 | antes de ANALYZE (tablas) | 5 | 2,6504 | 2,5614 | 2,7622 | 0,0866 |
| Q3 | después de ANALYZE (I-2) | 5 | 2,6927 | 2,6167 | 3,2044 | 0,2457 |
| Tipos | VARCHAR + CAST | 9 | 14,3377 | 14,0580 | 15,0341 | 0,3086 |
| Tipos | TIMESTAMP | 9 | 4,2851 | 3,8062 | 4,3746 | 0,2157 |
| CockroachDB lectura | sin índice | 7 | 426,2172 | 414,8571 | 443,1641 | 11,3913 |
| CockroachDB lectura | con índice | 7 | 210,5908 | 208,7586 | 211,9116 | 1,1191 |
| CockroachDB INSERT 20.000 | sin índice | 3 | 308,3453 | 306,7608 | 332,5851 | 14,4740 |
| CockroachDB INSERT 20.000 | con índice | 3 | 358,2443 | 348,7881 | 386,8234 | 19,8026 |

Factores antes/después calculados con las medianas: Q1 0,99x; Q2 0,78x; Q3 con `ANALYZE` 0,98x; tipos 3,35x; lectura CockroachDB 2,02x; costo de INSERT con índice 1,16x (+16,2 %).

La comparación de tipos usa las mismas 208.236 filas de Silver, serializando `fecha_compra` como texto solo en la vista de control. Ambos casos devuelven 34.039 ventas y 3.689.715.500 COP. Antes, el plan evalúa `CAST(fecha_compra AS TIMESTAMP)` en un filtro sobre el scan; después, el predicado temporal se empuja al `TABLE_SCAN` de Parquet. Los planes están en `planes/Q3_tipos_antes_texto.txt` y `planes/Q3_tipos_despues_timestamp.txt`; los tiempos son medianas de nueve ejecuciones, no los tiempos de una sola captura `EXPLAIN ANALYZE`.

**Alcance de los datos.** Los tiempos anteriores son mediciones reales de las ejecuciones locales guardadas en los artefactos. El benchmark CockroachDB expande determinísticamente filas del Gold hasta un millón y usa otra tabla aislada para medir inserciones; esas filas son sintéticas y no representan transacciones reales. La comparación VARCHAR/TIMESTAMP también usa Silver. En la ejecución final de `main.py` del 26-11-2026 16:40 se seleccionó `USE_SYNTHETIC=false` (la salida reporta `Fuente: CockroachDB`): Bronze y Silver conservaron 208.236 compras y 260.294 intentos, y Silver imputó 3.101 y 3.906 NULL de `canal_id` como `DESCONOCIDO`. La verificación con una consulta directa a CockroachDB v25.4.0 se hizo en la repetición anterior del 16-11-2026 23:19, con esos mismos conteos de NULL. Sin embargo, la base fue cargada con el snapshot sintético del laboratorio, por lo que esto valida la conexión y el flujo de calidad, no datos reales ni rendimiento de producción.

<h1 class="salto">5. Reflexión arquitectural</h1>

*Si pudiéramos rediseñar el pipeline del M3 sabiendo lo que sabemos ahora, ¿qué cambiaríamos?*

**1. Diseñar el acceso según las consultas.** Ordenar Gold por `tiempo_sk` permite data skipping en Q1; filtrar directamente por esa clave evita depender de un join para seleccionar fechas. En la prueba, el orden redujo los bytes leídos 1,8x, aunque el tiempo no cambió (0,99x) por el tamaño del conjunto y el overhead fijo. Conviene particionar solo cuando el volumen por partición compense el costo de listar archivos; aquí el glob Hive incluso hizo que Q2 fuera 29 % más lento.

**2. Balancear lectura y escritura.** En CockroachDB, el índice compuesto hizo la consulta 2,02x más rápida, pero elevó 16,2 % el tiempo mediano de insertar 20.000 filas. El índice es útil cuando el beneficio de las lecturas selectivas compensa ese costo; el resultado es de un laboratorio local, no una predicción de producción.

**3. Tipar y agregar con propósito.** Comparar `TIMESTAMP` nativo con texto más `CAST` redujo la mediana de la consulta 3,35x, con resultados idénticos. En consultas que requieren recorrer todo el conjunto, como el embudo, un índice no evita el costo de agregación; para producción convendrían pre-agregaciones. Todas las conclusiones deben reevaluarse con el volumen, patrón de consultas y fuente de datos reales.

<h1>6. Anexos</h1>

**A. Planes `EXPLAIN ANALYZE` completos.** Están en el repositorio, en `docs/taller4/planes/`, porque sus árboles miden más de 200 columnas y no caben legibles en una página:

| Archivo | Contenido |
|---|---|
| `Q1_antes.txt` / `Q1_despues.txt` | Q1 sobre la fact original y sobre la ordenada (I-3) |
| `Q2_antes.txt` / `Q2_despues.txt` | Q2 sobre el archivo único y sobre la versión particionada (I-6) |
| `Q3_antes.txt` | Q3 sobre vistas de Parquet (diagnóstico) |
| `Q3_antes_analyze.txt` / `Q3_despues.txt` | Q3 sobre tablas materializadas, antes y después de `ANALYZE` (I-2) |
| `*_perfil.txt` | Tiempo de CPU y filas reales y estimadas por operador (profiling JSON de DuckDB) |
| `cockroach_Q1_antes_full_scan.txt` / `cockroach_Q1_despues_index_scan.txt` | CockroachDB: full scan frente al índice compuesto |
| `Q3_tipos_antes_texto.txt` / `Q3_tipos_despues_timestamp.txt` | DuckDB: predicado `VARCHAR` + `CAST` frente a `TIMESTAMP` |

**B. Documentos de trabajo.** `docs/taller4/diagnostico_baseline.md` (diagnóstico), `intervenciones.md` (fichas), `benchmarks.md` (DuckDB), `benchmarks_cockroach.md` (índice e inserciones), `intervencion_tipos.md` (tipos) y `analisis_complementario.md` (controles).

**C. Cómo reproducir.**

```bash
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
python -m scripts.taller4_optimizacion     # genera el Gold del M3 si falta; planes, perfiles y benchmarks
python -m scripts.taller4_complementario   # controles de paralelismo, Hive y ANALYZE
python -m scripts.taller4_tipos            # VARCHAR + CAST frente a TIMESTAMP
python -m scripts.oltp.benchmark_cockroach # índice y costo de INSERT en CockroachDB
```

Los tiempos absolutos varían según la máquina y la corrida. Los planes DuckDB y las filas experimentales CockroachDB son reproducibles; el benchmark CockroachDB modifica sus tablas de laboratorio y debe ejecutarse solo en la base desechable del proyecto.
