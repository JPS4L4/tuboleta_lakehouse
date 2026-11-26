# Análisis complementario — Taller 4

DuckDB 2.0.0 · 12 hilos lógicos · mediana de 15 corridas con warm-up ×3.

## A. Q1 — paralelismo y overhead fijo

| Fact | threads | Mediana (ms) | CPU sumada de operadores (ms) | Wall del perfil (ms) | Overhead fuera de operadores (ms) |
|---|---:|---:|---:|---:|---:|
| original (1 row group) | 1 | 4.45 | 1.82 | 4.35 | 2.53 |
| original (1 row group) | 12 | 4.80 | 1.78 | 4.52 | n/a (CPU sumada entre hilos) |
| ordenada (11 row groups) | 1 | 4.41 | 1.61 | 4.31 | 2.70 |
| ordenada (11 row groups) | 12 | 5.01 | 7.25 | 4.63 | n/a (CPU sumada entre hilos) |

## B. Q2 — costo del particionado Hive

| Variante | Mediana (ms) |
|---|---:|
| archivo único, filtro por rango de tiempo_sk (baseline) | 1.81 |
| glob Hive + partition pruning (I-6) | 2.76 |
| lectura directa de la partición month=09 (sin glob ni Hive) | 1.26 |

## C. Q1 — ¿ANALYZE corrige la estimación de cardinalidad del join?

| Fuente de datos | Estimada antes de ANALYZE | Estimada después de ANALYZE | Real |
|---|---:|---:|---:|
| vistas sobre Parquet | 1,651 | 1,651 | 34,039 |
| tablas materializadas | 24,037 | 24,037 | 34,039 |
