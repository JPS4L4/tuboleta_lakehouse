# Evidencia de ejecuciones del pipeline — Taller 4

Fecha de las salidas compartidas: 16-11-2026. Este documento separa las ejecuciones por fuente y hora; sus conteos no deben combinarse como si pertenecieran a una sola carga. Se añadió la repetición CockroachDB verificada a las 23:19 y la corrida final del 26-11-2026 a las 16:40, de la que provienen las cifras vigentes.

## 1. Escenario A — generación sintética directa

Configuración: `USE_SYNTHETIC=true`. El pipeline genera datos sintéticos con anomalías intencionales para demostrar la limpieza de Silver.

### Bronze

| Tabla | Filas |
|---|---:|
| canales | 3 |
| zonas | 6 |
| eventos | 5 |
| sillas | 45.000 |
| usuarios | 150.750 |
| compras_confirmadas | 210.358 |
| intentos_compra | 262.936 |

### Silver

| Tabla | Filas de salida | Tratamiento relevante |
|---|---:|---|
| usuarios | 150.000 | 750 duplicados eliminados; 99,50 % retenido |
| compras_confirmadas | 208.236 | 2.082 duplicados eliminados; 40 filas sin clave descartadas; 3.101 NULL de `canal_id` imputados como `DESCONOCIDO`; 98,99 % retenido |
| intentos_compra | 260.294 | 2.602 duplicados eliminados; 40 filas sin clave descartadas; 3.906 NULL de `canal_id` imputados como `DESCONOCIDO`; 99,00 % retenido |

La suma de `precio_pagado` de compras confirmadas pasa de 22.352.656.600 COP en Bronze a 22.126.123.800 COP en Silver, después de deduplicar y descartar registros sin clave. Los valores nulos de canal se resuelven en Silver, no se inventa el canal original.

### Gold y validaciones

| Tabla | Filas |
|---|---:|
| dim_tiempo | 5.656 |
| dim_evento | 5 |
| dim_zona | 6 |
| dim_silla | 45.000 |
| dim_usuario | 150.000 |
| dim_canal | 4 |
| fact_ventas_boletas | 208.236 |
| fact_intentos_compra | 260.294 |

Las validaciones reportadas para SCD2, no doble reserva, unicidad de compra, precio/descuento, relación venta-intento y estados ABANDONO/RECHAZO sin compra finalizaron correctamente.

## 2. Escenario B — CockroachDB como fuente OLTP

Configuración: `USE_SYNTHETIC=false`. Esta corrida anterior extrae el snapshot desde CockroachDB y reporta los siguientes conteos.

### Bronze y Silver

| Tabla | Bronze | Silver | Retención |
|---|---:|---:|---:|
| canales | 3 | 3 | 100 % |
| zonas | 6 | 6 | 100 % |
| eventos | 5 | 5 | 100 % |
| sillas | 45.000 | 45.000 | 100 % |
| usuarios | 150.000 | 150.000 | 100 % |
| compras_confirmadas | 208.236 | 208.236 | 100 % |
| intentos_compra | 260.294 | 260.294 | 100 % |

La salida informa cero duplicados, cero filas descartadas por ausencia de clave y cero NULL de `canal_id` resueltos en compras e intentos. La suma de precio de compras confirmadas es 22.126.123.800 COP tanto en Bronze como en Silver.

**Interpretación:** esta corrida anterior no demuestra imputación de NULL en Silver porque no había NULL que resolver en las tablas de hechos. Tampoco contradice el escenario sintético directo: las fuentes y sus volúmenes de entrada son distintos.

### Repetición CockroachDB verificada — 23:19

La corrida más reciente también usó `USE_SYNTHETIC=false` contra CockroachDB v25.4.0. La consulta SQL directa y Bronze coincidieron; las siete tablas Bronze tienen `_fuente=cockroachdb`.

| Tabla | Filas Bronze | NULL de `canal_id` en SQL/Bronze | NULL imputados en Silver |
|---|---:|---:|---:|
| compras_confirmadas | 208.236 | 3.101 | 3.101 |
| intentos_compra | 260.294 | 3.906 | 3.906 |

Silver convirtió esos valores a `DESCONOCIDO`. Esto valida el transporte CockroachDB → Bronze y la imputación Bronze → Silver. El contenido almacenado en CockroachDB provino del generador sintético del laboratorio; no son ventas reales de TuBoleta. El reporte de calidad de las 23:19 fue sobrescrito por el de la corrida final del 26-11-2026 (16:40), que está en [`../reporte_calidad_silver.txt`](../reporte_calidad_silver.txt) y repite las mismas cifras.

### Corrida final CockroachDB — 26-11-2026 16:40

La corrida final de la entrega usó `USE_SYNTHETIC=false` contra CockroachDB v25.4.0 (la salida reporta `Fuente: CockroachDB`). Bronze y Silver conservaron todas las filas (100 % retenido, cero duplicados y cero filas sin clave) y Silver imputó los NULL de `canal_id` como `DESCONOCIDO`:

| Tabla | Filas Bronze | NULL imputados en Silver |
|---|---:|---:|
| compras_confirmadas | 208.236 | 3.101 |
| intentos_compra | 260.294 | 3.906 |

La suma de precio de compras confirmadas fue 22.126.123.800 COP en Bronze y en Silver, y Gold produjo 208.236 ventas y 260.294 intentos. El reporte de calidad de esa corrida es el actual [`../reporte_calidad_silver.txt`](../reporte_calidad_silver.txt) (16:40). Las cifras de rendimiento de esta corrida están en las secciones 3 a 5.

### Gold y validaciones

Los conteos Gold coinciden con Silver: 208.236 ventas y 260.294 intentos; dimensiones: tiempo 5.656, evento 5, zona 6, silla 45.000, usuario 150.000 y canal 4. Las validaciones de modelo reportadas finalizaron correctamente.

## 3. Comparación de rendimiento analítico

Cada fila corresponde a una ejecución independiente del benchmark SQLite frente a DuckDB. Los 60 grupos de resultados fueron idénticos en ambas comparaciones.

| Motor | Sintético directo (ms) | CockroachDB como fuente (ms) |
|---|---:|---:|
| SQLite | 447,10 | 441,25 |
| DuckDB Bronze | 112,30 | 155,67 |
| DuckDB Gold | 15,68 | 16,15 |
| DuckDB Bronze vs SQLite | 4,0x | 2,8x |
| DuckDB Gold vs SQLite | 28,5x | 27,3x |

Las cifras comparan el tiempo de consulta analítica sobre los conjuntos producidos por cada ruta; no miden el tiempo de carga de CockroachDB ni el costo de extracción. No deben presentarse como benchmark del índice OLTP. La corrida final (26-11-2026 16:40, CockroachDB como fuente) está en [`../benchmark.md`](../benchmark.md): SQLite 287,29 ms, DuckDB Bronze 112,38 ms y DuckDB Gold 10,12 ms (28,4x frente a SQLite). Para comparar, la ejecución del 16-11-2026 23:20 había medido SQLite 444,01 ms, DuckDB Bronze 169,22 ms y DuckDB Gold 16,97 ms (26,2x); la tabla de arriba y esa medición son históricas.

## 4. Duración del pipeline

| Etapa | Sintético directo | CockroachDB como fuente |
|---|---:|---:|
| Extracción / generación Bronze | 2,29 s | 2,16 s |
| Bronze → Silver | 0,68 s | 0,55 s |
| Silver → Gold | 1,49 s | 1,62 s |
| Análisis | 5,92 s | 6,31 s |
| **Total** | **10,38 s** | **10,64 s** |

Son tiempos de las corridas compartidas en el entorno local, no garantías de rendimiento para otras máquinas.
La repetición CockroachDB del 23:19 finalizó en 10,44 s. La corrida final del 26-11-2026 16:40 finalizó en 6,92 s (extracción 1,35 s; Bronze → Silver 0,34 s; Silver → Gold 1,08 s; análisis 4,15 s).

## 5. Experimentos OLTP y conversión de tipos

Los siguientes experimentos se midieron por separado del pipeline funcional (corrida final del 26-11-2026; mínimos, máximos y desviaciones estándar en los CSV `estadisticas_*.csv` de `docs/taller4/`):

| Experimento | Antes | Después | Resultado |
|---|---:|---:|---|
| Consulta OLTP CockroachDB | 426,217 ms sin índice | 210,591 ms con índice compuesto | 2,02x más rápida |
| Inserción OLTP (20.000 filas) | 308,35 ms sin índice | 358,24 ms con índice | 16,2 % más lenta |
| Fecha en DuckDB | 14,338 ms (`VARCHAR` + `CAST`) | 4,285 ms (`TIMESTAMP`) | 3,35x más rápida |

`EXPLAIN ANALYZE` registró 1.000.000 de filas / 73 MiB / 732 ms sin índice y 164.066 filas / 9,7 MiB / 241 ms con índice. Las medianas de consulta son siete ejecuciones; la inserción usa la mediana de tres lotes. La comparación de tipos usa las mismas filas Silver, y ambos casos devolvieron 34.039 ventas y 3.689.715.500 COP. Los resultados completos y sus limitaciones están en [`benchmarks_cockroach.md`](benchmarks_cockroach.md), [`intervencion_tipos.md`](intervencion_tipos.md) y los planes bajo `planes/`.

Comandos para repetir los experimentos:

```bash
python -m scripts.oltp.benchmark_cockroach
python -m scripts.taller4_tipos
```
