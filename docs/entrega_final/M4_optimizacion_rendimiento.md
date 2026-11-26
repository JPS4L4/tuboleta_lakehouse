# M4 — Diagnóstico y optimización del rendimiento

## 1. Alcance y metodología

M4 evalúa por separado el acceso analítico sobre Parquet/DuckDB y el acceso transaccional sobre CockroachDB. No se presenta SQLite como si fuera CockroachDB: el benchmark SQLite/DuckDB del pipeline es una comparación OLAP independiente del experimento del índice OLTP.

El Gold original del M3 se conserva sin modificar. Las intervenciones analíticas escriben en `lakehouse/gold_t4/` y verifican mediante aserciones que las consultas antes y después devuelven el mismo resultado. Para DuckDB se utilizó la mediana de cinco ejecuciones después de tres calentamientos, salvo los controles complementarios identificados expresamente como mediana de quince. El experimento de tipos utiliza nueve ejecuciones. CockroachDB utiliza mediana de siete lecturas y mediana de tres lotes de inserción.

Entorno analítico documentado: DuckDB 2.0.0, Parquet, Windows 11 Pro, AMD Ryzen 5 9600X, 12 hilos lógicos, 15,1 GB RAM y Python 3.14.6. El experimento OLTP se ejecutó en CockroachDB CCL v25.4.0, nodo único Docker. Son mediciones locales, no SLO ni resultados de producción.

Las cifras de este documento provienen de la corrida final del 26-11-2026 en esta máquina (Python 3.14.6, DuckDB 2.0.0, CockroachDB v25.4.0 de un solo nodo en Docker, Windows 11, AMD64), con el pipeline extraído desde CockroachDB (`USE_SYNTHETIC=false`). Las medianas de corridas de desarrollo anteriores fueron distintas (por ejemplo, 2,08x en la lectura con índice y 3,98x en tipos); aquí solo se reportan las de esta corrida, con sus CSV.

## 2. Diagnóstico de consultas analíticas

### Q1 — Ingresos por evento en septiembre de 2026

```sql
SELECT e.nombre_evento, t.mes, COUNT(*) AS boletas,
       SUM(f.precio_pagado) AS ingresos
FROM fact_ventas_boletas f
JOIN dim_tiempo t ON t.tiempo_sk = f.tiempo_sk
JOIN dim_evento e ON e.evento_sk = f.evento_sk
WHERE t.anio = 2026 AND t.mes = 9
GROUP BY 1, 2;
```

Baseline: 4,97 ms. El `TABLE_SCAN` lee 208.236 filas para devolver dos grupos; la fact tiene un único row group y lee 261,1 kB. El filtro dinámico que llega desde `dim_tiempo` no puede descartar bloques porque el min/max del único row group cubre todo el período. Diagnóstico: acceso secuencial por ausencia de data skipping (indicadores 1 y 4). Como hallazgo secundario, la salida del join se estima en 1.651 filas frente a 34.039 reales (error 20,6x), pero no provoca una elección incorrecta del algoritmo de join.

### Q2 — Ingresos por zona en septiembre de 2026

```sql
SELECT zona_sk, COUNT(*) AS boletas, SUM(precio_pagado) AS ingresos
FROM fact_ventas_boletas
WHERE tiempo_sk BETWEEN 2026090100 AND 2026093023
GROUP BY 1;
```

Baseline: 2,44 ms. El filtro se empuja al scan, pero se lee el único archivo completo (246,3 kB) para retener el 16,3 % de las filas. Diagnóstico: acceso secuencial sobre un archivo sin particiones. Las estimaciones (41.647 frente a 34.039 reales) son razonables; no hay joins ni conversión de tipos en el predicado.

### Q3 — Embudo de conversión por evento

```sql
SELECT d.nombre_evento, COUNT(*) AS intentos,
       SUM(i.es_compra) AS compras,
       SUM(i.es_abandono) AS abandonos,
       SUM(i.es_rechazo_unique) AS rechazos
FROM fact_intentos_compra i
JOIN dim_evento d ON d.evento_sk = i.evento_sk
GROUP BY 1;
```

Baseline sobre vistas Parquet: 5,49 ms. La consulta necesita recorrer todos los intentos porque no tiene filtro selectivo. Las estimaciones de 260.294 intentos y cinco eventos son exactas y el hash join utiliza la dimensión pequeña como build. Diagnóstico: no hay problema de acceso que deba corregirse; Q3 se conserva como control para evaluar `ANALYZE`.

## 3. Intervenciones y resultados

### 3.1. Ordenamiento y data skipping — Q1

Se reescribió la fact ordenada por `tiempo_sk`, con row groups de 20.000 filas. El número de row groups pasó de 1 a 11; el plan posterior escanea 3 de 11, en vez de 1 de 1. Los bytes leídos bajaron de 261,1 kB a 142,4 kB (1,8 veces menos). La mediana pasó de 4,97 ms a 5,02 ms: 0,99x, es decir, sin ganancia de tiempo (la diferencia de 0,05 ms es menor que las desviaciones estándar de 0,18 y 0,28 ms).

La reducción de lectura no se tradujo en una mejora proporcional de tiempo por el overhead fijo de planificación/apertura/metadatos, la caché del sistema operativo y el costo de paralelismo. En el control de una sola hebra (mediana de 15), la mediana fue 4,45 → 4,41 ms y la CPU sumada de operadores 1,82 → 1,61 ms. El resultado demuestra data skipping (menos row groups y bytes leídos), pero el conjunto de 208 mil ventas impide que eso se vea en el tiempo de pared.

### 3.2. Particionado Hive — Q2

Se derivaron las columnas `year` y `month` de `tiempo_sk` y se escribió la fact en carpetas Hive `year=YYYY/month=MM`. El plan abre 1 de 9 archivos y los bytes leídos bajan de 246,3 kB a 58,8 kB (4,2 veces menos). Sin embargo, la mediana empeora de 2,44 ms a 3,14 ms (0,78x, aproximadamente 29 % más lento).

El control complementario aisló el costo: archivo único con filtro, 1,81 ms; glob Hive con pruning, 2,76 ms; lectura directa del archivo de septiembre, 1,26 ms (mediana de 15, protocolo distinto del de la tabla principal). El costo de expandir el glob, listar carpetas y parsear las claves de partición supera el ahorro con archivos pequeños. Además, la estimación de cardinalidad cae a una fila frente a 34.039 reales y el agregado cambia de `PERFECT_HASH_GROUP_BY` a `HASH_GROUP_BY`. Con este volumen, el particionado reduce I/O lógico, pero no mejora el tiempo. Es más apropiado cuando las particiones contienen muchos más datos o se consulta almacenamiento remoto.

### 3.3. Corrección de tipos — VARCHAR a TIMESTAMP

Se compararon las mismas filas Silver: un control serializa `fecha_compra` como VARCHAR y convierte en la consulta, mientras que el escenario tipado conserva TIMESTAMP y filtra directamente. La mediana fue 14,338 ms con VARCHAR + CAST y 4,285 ms con TIMESTAMP, una mejora de 3,35x.

Ambos escenarios devolvieron exactamente 34.039 ventas y 3.689.715.500 COP. El beneficio proviene de evitar la conversión fila por fila y mantener el dato en su tipo temporal. Este experimento aísla el efecto del tipo en DuckDB; no es una comparación de extracción desde CockroachDB.

### 3.4. Índice compuesto en CockroachDB

Se evaluó el índice compuesto `(tiempo_sk, evento_sk)` sobre una tabla experimental de un millón de filas. La consulta de rango temporal se midió con calentamiento y mediana de siete ejecuciones. La lectura pasó de 426,217 ms sin índice a 210,591 ms con índice: mejora de 2,02x.

Los planes instrumentados muestran el mecanismo: sin índice, full scan de 1.000.000 filas, 73 MiB y 8 llamadas gRPC; con índice, 164.066 filas decodificadas, 9,7 MiB y una llamada gRPC. Los tiempos individuales de EXPLAIN ANALYZE (732 ms y 241 ms) son capturas instrumentadas y no deben confundirse con las medianas de la tabla.

El índice tiene costo de escritura: insertar un lote aislado de 20.000 filas pasó de 308,35 ms a 358,24 ms, aproximadamente 16,2 % más lento (factor 1,16x). La decisión es favorable cuando el patrón de lectura selectiva justifica el mantenimiento adicional del índice. El benchmark es sintético y local; no mide producción ni afecta el Gold funcional.

## 4. Tabla consolidada de resultados

| Técnica / consulta | Antes | Después | Factor | Resultado físico |
|---|---:|---:|---:|---|
| Ordenamiento / Q1 | 4,97 ms | 5,02 ms | 0,99x | 1/1 → 3/11 row groups; 261,1 → 142,4 kB |
| Particionado Hive / Q2 | 2,44 ms | 3,14 ms | 0,78x | 1/9 archivos; 246,3 → 58,8 kB |
| TIMESTAMP / filtro temporal | 14,338 ms | 4,285 ms | 3,35x | Mismas 34.039 filas y COP 3.689.715.500 |
| Índice CockroachDB / rango | 426,217 ms | 210,591 ms | 2,02x | 1.000.000 → 164.066 filas decodificadas |
| Índice CockroachDB / INSERT 20.000 | 308,35 ms | 358,24 ms | 1,16x costo | Escritura ~16,2 % más lenta |

**Dispersión de la corrida final.** Mediana, mínimo, máximo y desviación estándar muestral copiados de `docs/taller4/estadisticas_duckdb.csv`, `estadisticas_tipos.csv` y `estadisticas_cockroach.csv`; las observaciones individuales están en los `mediciones_crudas_*.csv`. No se mezclan con los controles complementarios de 15 corridas.

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


## 5. Interpretación

Las intervenciones no tienen que mejorar todas las métricas para ser válidas. El ordenamiento y Hive demuestran reducción de datos leídos, pero el tamaño del dataset y el costo fijo del motor dominan el tiempo. El particionado incluso empeora el tiempo por el overhead de enumerar archivos y la pérdida de estadísticas. La conversión a TIMESTAMP presenta la mejora temporal más clara en el experimento DuckDB. El índice CockroachDB reduce el costo de lectura selectiva, a cambio de encarecer las inserciones.

La conclusión es que la optimización debe evaluarse con el plan, los datos leídos, el resultado lógico y el costo de escritura, no solo con un tiempo aislado. El benchmark SQLite/DuckDB del pipeline es una comparación OLAP distinta y no debe presentarse como benchmark CockroachDB contra DuckDB.

## 6. Evidencias y reproducibilidad

- Diagnóstico y SQL: `docs/taller4/diagnostico_baseline.md`.
- Intervenciones y explicación: `docs/taller4/intervenciones.md`.
- Medianas DuckDB: `docs/taller4/benchmarks.md`.
- Controles complementarios: `docs/taller4/analisis_complementario.md`.
- Tipos: `docs/taller4/intervencion_tipos.md`.
- Índice OLTP y planes: `docs/taller4/benchmarks_cockroach.md` y `docs/taller4/planes/cockroach_Q1_antes_full_scan.txt`, `docs/taller4/planes/cockroach_Q1_despues_index_scan.txt`.
- Planes DuckDB: `docs/taller4/planes/Q1_antes.txt`, `Q1_despues.txt`, `Q2_antes.txt`, `Q2_despues.txt`, `Q3_antes.txt`, `Q3_despues.txt` y los perfiles asociados.

Comandos principales:

```bash
python -m scripts.taller4_optimizacion
python -m scripts.taller4_complementario
python -m scripts.taller4_tipos
python -m scripts.oltp.benchmark_cockroach
```

CockroachDB se ejecuta en un nodo local Docker con configuración de laboratorio `--insecure`. Los registros experimentales son sintéticos. No se validan particiones, quórum, failover ni rendimiento multi-nodo.
