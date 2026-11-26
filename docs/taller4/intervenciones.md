# Intervenciones — Taller 4

**Regla:** una intervención por problema. La secuencia es: leer el plan antes → intervenir → leer el plan después → medir → comparar y argumentar.

| Fuente | Qué contiene |
|---|---|
| Tiempos y planes | `docs/taller4/benchmarks.md` y `docs/taller4/planes/*`, generados por `python -m scripts.taller4_optimizacion` (warm-up ×3, mediana de 5) |
| Análisis de resultados modestos | `docs/taller4/analisis_complementario.md`, generado por `python -m scripts.taller4_complementario` (mediana de 15). No es una intervención nueva: son controles de medición. |
| Entorno | DuckDB 2.0.0 · AMD Ryzen 5 9600X (12 hilos lógicos) · 15,1 GB RAM · Windows 11 Pro |

El Gold original del M3 **no se modifica**: cada intervención escribe en `lakehouse/gold_t4/`. En todos los casos el script verifica con `assert` que la consulta devuelve exactamente el mismo resultado antes y después.

Las cifras de estas fichas son las de la corrida final del 26-11-2026 en esta máquina (Python 3.14.6, DuckDB 2.0.0, pipeline extraído desde CockroachDB con `USE_SYNTHETIC=false`). Las medianas, mínimos, máximos y desviaciones estándar están en `estadisticas_duckdb.csv`; las observaciones individuales, en `mediciones_crudas_duckdb.csv`. Los rangos "de las 6 corridas" que se citan son de corridas previas del desarrollo y no forman parte de esta corrida.

---

## Ficha I-3 — Q1: ordenar la fact por `tiempo_sk` con row groups de 20.000 filas

| Campo | Contenido |
|---|---|
| Query afectada | Q1 — Ingresos por evento en septiembre 2026 |
| Problema (del diagnóstico) | Acceso secuencial sin data skipping posible (Indicador 1 → 4). La fact está en un único row group y sin orden por `tiempo_sk`, así que el zonemap min/max del archivo cubre todo el rango (2026022310–2026101623) y el filtro dinámico del join no puede descartar ningún bloque. |
| Intervención aplicada | I-3: reescribir la fact ordenada por `tiempo_sk`, en row groups de 20.000 filas |
| Código exacto | `df.sort_values("tiempo_sk").to_parquet(ordenado, index=False, row_group_size=20_000)` |
| Plan ANTES | `TABLE_SCAN fact_ventas_boletas` · `Row Groups Scanned: 1 / 1` · `Data Read: 261,1 kB` · 0,68 ms de CPU en el scan |
| Plan DESPUÉS | `TABLE_SCAN fact_ventas_boletas_ordenada` · **`Row Groups Scanned: 3 / 11`** · **`Data Read: 142,4 kB`** · el resto del árbol es idéntico (mismos 11 operadores, mismos `HASH_JOIN`) |
| ¿Cambió el plan? | **Sí, en el acceso:** se saltan 8 de 11 row groups y se lee 1,8x menos. Los operadores y el orden de los joins no cambian. |
| Tiempo antes / después | 4,97 ms / 5,02 ms (s = 0,18 / 0,28 ms) |
| Factor de mejora | **0,99x: sin ganancia de tiempo**, la diferencia (0,05 ms) está dentro de la dispersión (en 6 corridas previas del desarrollo el factor había oscilado entre 1,05x y 1,20x) |

**Justificación técnica: por qué funciona.**
- Parquet guarda min/max por columna y por row group (zonemaps). Si los datos están ordenados por `tiempo_sk`, cada row group cubre un rango contiguo y disjunto.
- El filtro `mes = 9` se aplica sobre `dim_tiempo`. Al construir la tabla hash del join, DuckDB genera un filtro dinámico (`Dynamic Filters: tiempo_sk IN PRF(tiempo_sk)`) y lo empuja al scan de la fact.
- Con la fact ordenada, ese filtro se compara contra los zonemaps de cada row group. Solo los row groups 7 (2026080615–2026090116), 8 (2026090116–2026091020) y 9 (2026091020–2026101211) intersectan septiembre. Esos son los 3 de 11 que reporta el plan.
- Se decodifican unas 60.000 filas en lugar de 208.236 (3,5x menos), mientras que los bytes leídos bajan 1,8x; no aislamos con una medición por qué ambas proporciones difieren.
- Con 1 solo row group no había nada que descartar. Ese era todo el problema.

**Por qué el factor de tiempo (0,99x) no acompaña al de datos (1,8x).** Lo explican tres razones medidas en `analisis_complementario.md`:
1. **Overhead fijo.** Con 1 hilo, unos 2,5 ms de cada ejecución (2,53 y 2,70 ms) ocurren fuera de los operadores: planificación, apertura de archivos y lectura de metadatos. Es más de la mitad del tiempo total, y ninguna intervención de acceso lo reduce, así que el techo de mejora a esta escala ronda 1,8x.
2. **Paralelismo.** El row group es la unidad de paralelismo de DuckDB sobre Parquet. Con 1 row group el scan es secuencial: la CPU es casi la misma con 1 que con 12 hilos. Con 11 row groups DuckDB reparte el trabajo y luego combina agregaciones parciales, y esa coordinación cuesta más de lo que ahorra con tan pocos datos: la CPU sumada sube de 1,61 ms a 7,25 ms. **Con `threads=1` el efecto aislado de I-3 es pequeño:** el tiempo casi no cambia (de 4,45 a 4,41 ms, 1,01x) y la CPU baja de 1,82 a 1,61 ms (−11,5 %).
3. **Caché.** Con el warm-up, el archivo ya está en la caché del sistema operativo, así que leer unos 119 kB menos ahorra decodificación pero no I/O de disco.

**Qué no cambió.** La estimación de cardinalidad del join (1.651 filas estimadas frente a 34.039 reales) sigue igual. Reordenar los datos no le da al planner estadísticas nuevas sobre la relación entre las tablas (ver la ficha I-2).

---

## Ficha I-6 — Q2: particionado Hive `year=/month=` de la fact

| Campo | Contenido |
|---|---|
| Query afectada | Q2 — Ingresos por zona en septiembre 2026 (filtro directo en la fact) |
| Problema (del diagnóstico) | Acceso secuencial sobre un archivo único (Indicador 1 → 4): se leen 246,3 kB (el 100 % de las columnas proyectadas) para un filtro que retiene el 16,3 % de las filas. |
| Intervención aplicada | I-6: dividir la fact en carpetas `year=YYYY/month=MM`, derivadas de `tiempo_sk` porque la fact no tiene una columna de fecha, y consultar con `hive_partitioning=true` |
| Código exacto | ```df["year"] = df["tiempo_sk"] // 1_000_000; df["month"] = (df["tiempo_sk"] // 10_000) % 100``` y, por grupo, ```g.drop(columns=["year","month"]).to_parquet(f"{base}/year={y}/month={m:02d}/data.parquet", index=False)```. La consulta: `read_parquet('.../**/*.parquet', hive_partitioning=true) WHERE year = 2026 AND month = 9` |
| Plan ANTES | `TABLE_SCAN fact_ventas_boletas` · 1 archivo · `Row Groups Scanned: 1 / 1` · `Data Read: 246,3 kB` · estimadas 41.647 filas · `PERFECT_HASH_GROUP_BY` |
| Plan DESPUÉS | `TABLE_SCAN` · **`Scanning Files: 1/9`** · **`Data Read: 58,8 kB`** · `Filters: CAST(month AS INTEGER) = 9` · **estimada 1 fila** (reales 34.039) · `HASH_GROUP_BY` |
| ¿Cambió el plan? | **Sí:** hay partition pruning (8 de 9 archivos descartados y 4,2x menos bytes), pero el agregado pasó de `PERFECT_HASH_GROUP_BY` a `HASH_GROUP_BY` y la estimación de cardinalidad se degradó a 1. |
| Tiempo antes / después | 2,44 ms / 3,14 ms (s = 0,39 / 0,26 ms) |
| Factor de mejora | **0,78x, es decir, empeoró un 29 %** (en 6 corridas previas del desarrollo el factor había oscilado entre 0,87x y 1,23x) |

**Justificación técnica: qué funcionó.** El partition pruning se resuelve sobre la ruta del archivo, antes de abrir ningún Parquet: el predicado `year = 2026 AND month = 9` se evalúa contra los nombres de carpeta y solo se abre `month=09`. El plan lo confirma con `Scanning Files: 1/9` y 58,8 kB leídos.

**Por qué no se tradujo en tiempo.** Lo medimos con un control en `analisis_complementario.md`, sección B:

| Variante | Mediana (ms) |
|---|---:|
| Archivo único con filtro por rango (baseline) | 1,81 |
| Glob Hive + partition pruning (I-6) | 2,76 |
| Lectura directa de `month=09/data.parquet`, sin glob ni Hive | **1,26** |

- **Leer solo los datos de septiembre cuesta un 30 % menos que el baseline** (1,26 frente a 1,81 ms; protocolo de 15 corridas, distinto del de 5 de la tabla principal), así que la reducción de datos es real. Lo que se come la ganancia, unos 1,5 ms, es el mecanismo de particionado: expandir el glob `**/*.parquet` (listar 9 carpetas en el sistema de archivos), parsear los valores `year=` / `month=` de cada ruta y evaluar el filtro sobre ellos.
- **Se perdieron estadísticas.** Al leer por glob con columnas Hive, el planner estima 1 fila en lugar de 34.039, lo que introduce un Indicador 2 que antes no existía. También deja de usar `PERFECT_HASH_GROUP_BY`, que necesita conocer el rango de `zona_sk`, y cae al `HASH_GROUP_BY` genérico. Aquí no cambia el algoritmo de join porque no hay joins, pero en una consulta con joins una estimación de 1 fila podría llevar a elegir mal el lado build.
- **El `CAST(month AS INTEGER)` (Indicador 5) es inofensivo aquí.** Se evalúa sobre los 9 valores de partición, no sobre 208.236 filas, así que no fuerza un acceso secuencial.

**Cuándo sí conviene particionar.** Cuando cada partición es mucho más grande que el costo de listarla: millones de filas por mes, o almacenamiento de objetos (S3, GCS), donde cada archivo descartado ahorra una petición de red. También cuando las consultas filtran casi siempre por la clave de partición. Con 208.000 filas repartidas en 9 archivos pequeños, el costo fijo por archivo domina, y ese es el clásico problema de los archivos pequeños.

---

## Ficha I-2 — Q3 (experimento de control): `ANALYZE`

| Campo | Contenido |
|---|---|
| Query afectada | Q3 — Embudo de conversión por evento |
| Problema (del diagnóstico) | Ninguno de acceso: es una agregación total sin filtro, y las estimaciones ya son exactas (260.294 = 260.294 y 5 = 5) |
| Intervención aplicada | I-2: `ANALYZE` sobre las tablas materializadas en DuckDB. Sobre vistas de Parquet no hay estadísticas propias que actualizar. |
| Código exacto | `con = conectar(materializar=True)` → plan + mediana → `con.execute("ANALYZE")` → plan + mediana, en la **misma conexión** |
| Plan ANTES | `Q3_antes_analyze.txt`: `HASH_GROUP_BY` ← `PROJECTION` ← `HASH_JOIN` ← 2 × `TABLE_SCAN` · estimaciones 260.294 / 5 |
| Plan DESPUÉS | `Q3_despues.txt`: el mismo árbol de 6 operadores, las mismas estimaciones |
| ¿Cambió el plan? | **No:** plan idéntico (verificado automáticamente por el script) |
| Tiempo antes / después | 2,65 ms / 2,69 ms (s = 0,09 / 0,25 ms) |
| Factor de mejora | **0,98x**, dentro del ruido (en 6 corridas previas del desarrollo el factor había oscilado entre 0,81x y 1,06x) |

**Justificación técnica.** `ANALYZE` sirve cuando el planner trabaja con estadísticas desactualizadas o ausentes. Aquí no es el caso: DuckDB conoce el número exacto de filas de sus tablas y la estimación del join ya es exacta. Un resultado nulo era la predicción, y confirmarlo valida el diagnóstico de Q3.

**Experimento adicional: ¿`ANALYZE` habría corregido el error de 20,6x de Q1?** Lo probamos con las estimaciones de `EXPLAIN` para la salida de los joins de Q1 (`analisis_complementario.md`, sección C):

| Fuente de datos | Antes de `ANALYZE` | Después de `ANALYZE` | Real |
|---|---:|---:|---:|
| Vistas sobre Parquet | 1.651 | 1.651 | 34.039 |
| Tablas materializadas | 24.037 | 24.037 | 34.039 |

`ANALYZE` no movió la estimación en ningún caso. Lo que la mejora, de 20,6x a 1,4x de error, es **materializar**: al cargar una tabla nativa, DuckDB recolecta estadísticas propias (como los conteos de valores distintos) que una vista sobre Parquet no tiene. Conclusión: el Indicador 2 de Q1 se origina en leer Parquet a través de vistas, no en estadísticas viejas, y `ANALYZE` no es la intervención que lo resuelve.

---

## Preguntas del enunciado sobre resultados modestos

| Pregunta | Respuesta con evidencia |
|---|---|
| ¿El dataset es tan pequeño que el overhead supera el beneficio? | **Sí.** Unos 2,5 ms por ejecución son overhead fijo, más de la mitad del tiempo total (sección A). En Q2, el costo de listar y parsear las carpetas Hive (~1,5 ms) es mayor que lo que ahorra leer menos datos (sección B). |
| ¿La caché absorbió el efecto del ordenamiento? | **En parte.** Tras el warm-up los archivos están en la caché del sistema operativo, así que el ahorro de bytes no ahorra I/O de disco. Además, el paralelismo que habilitan los 11 row groups agrega coordinación entre hilos. Con 1 hilo, I-3 tampoco mejora el tiempo (1,01x) y solo baja la CPU un 11,5 %. |
| ¿La selectividad era tan baja que el scan completo ya era eficiente? | **En Q3, sí:** la selectividad es del 100 % y no hay nada que saltar. En Q1 y Q2 el filtro retiene el 16,3 % y las intervenciones sí redujeron los datos leídos 1,8x y 4,2x. A esta escala, eso no se traduce en tiempo. |


---

## Actualización de alcance: matriz de cuatro técnicas solicitadas

Las fichas anteriores documentan los experimentos históricos del primer corte. Para la entrega final, la intervención de `ANALYZE` queda como **control complementario**, no como sustituto de la corrección de tipos. La matriz que responde a la retroalimentación del docente es:

| Técnica | Tecnología | Evidencia y ejecución |
|---|---|---|
| Ordenamiento / data skipping | Parquet + DuckDB | Q1: `scripts/taller4_optimizacion.py`; planes y perfiles en `docs/taller4/planes/` |
| Particionado Hive | Parquet + DuckDB | Q2: `scripts/taller4_optimizacion.py`; carpetas year/month y pruning |
| Corrección de tipos VARCHAR → TIMESTAMP | DuckDB | Q3: `python -m scripts.taller4_tipos`; resultados en `intervencion_tipos.md` |
| Índice compuesto (tiempo_sk, evento_sk) | CockroachDB | Q4: `python -m scripts.oltp.benchmark_cockroach`; resultados en `benchmarks_cockroach.md` |

Los resultados medidos de las cuatro técnicas están en `benchmarks.md`, `benchmarks_cockroach.md` e `intervencion_tipos.md`; los planes completos están en `planes/`. Las mediciones CockroachDB provienen de filas experimentales sintéticas y no representan transacciones reales. La matriz, el método y los criterios de aceptación están en `experimentos_requeridos.md`.
