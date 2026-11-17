# Evidencia de ejecuciones del pipeline — Taller 4

Fecha de las salidas compartidas: 16-11-2026. Este documento separa dos ejecuciones que usan fuentes distintas. No deben combinarse sus conteos ni interpretarse como una misma carga.

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

Configuración: `USE_SYNTHETIC=false`. Esta ejecución extrae el snapshot desde CockroachDB. La salida compartida reporta los siguientes conteos.

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

**Interpretación:** esta ejecución no demuestra imputación de NULL en Silver porque no había NULL que resolver en las tablas de hechos. Tampoco contradice el escenario sintético directo: las fuentes y sus volúmenes de entrada son distintos. La evidencia de imputación efectiva es la del escenario A (3.101 NULL en compras y 3.906 en intentos).

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

Las cifras comparan el tiempo de consulta analítica sobre los conjuntos producidos por cada ruta; no miden el tiempo de carga de CockroachDB ni el costo de extracción. No deben presentarse como benchmark del índice OLTP.

## 4. Duración del pipeline

| Etapa | Sintético directo | CockroachDB como fuente |
|---|---:|---:|
| Extracción / generación Bronze | 2,29 s | 2,16 s |
| Bronze → Silver | 0,68 s | 0,55 s |
| Silver → Gold | 1,49 s | 1,62 s |
| Análisis | 5,92 s | 6,31 s |
| **Total** | **10,38 s** | **10,64 s** |

Son tiempos de las corridas compartidas en el entorno local, no garantías de rendimiento para otras máquinas.

## 5. Experimentos que esta evidencia no sustituye

Este archivo documenta el pipeline funcional y el benchmark analítico SQLite/DuckDB. No contiene los resultados del benchmark OLTP de CockroachDB (full scan frente a índice compuesto, planes `EXPLAIN ANALYZE` ni costo de INSERT), ni la comparación de VARCHAR + CAST frente a TIMESTAMP. Esos resultados deben generarse con:

```bash
python -m scripts.oltp.benchmark_cockroach
python -m scripts.taller4_tipos
```

No se incluyen cifras estimadas para esos experimentos. Las salidas esperadas son `docs/taller4/benchmarks_cockroach.md`, `docs/taller4/intervencion_tipos.md` y los planes asociados en `docs/taller4/planes/`.
