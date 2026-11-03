# Análisis complementario — Taller 4

DuckDB 2.0.0 · 12 hilos lógicos · mediana de 15 corridas con warm-up ×3.

## A. Q1 — paralelismo y overhead fijo

| Fact | threads | Mediana (ms) | CPU sumada de operadores (ms) | Wall del perfil (ms) | Overhead fuera de operadores (ms) |
|---|---:|---:|---:|---:|---:|
| original (1 row group) | 1 | 4.80 | 2.40 | 4.80 | 2.40 |
| original (1 row group) | 12 | 5.23 | 2.73 | 5.15 | n/a (CPU sumada entre hilos) |
| ordenada (11 row groups) | 1 | 4.09 | 1.56 | 3.91 | 2.35 |
| ordenada (11 row groups) | 12 | 4.70 | 5.75 | 4.58 | n/a (CPU sumada entre hilos) |

## B. Q2 — costo del particionado Hive

| Variante | Mediana (ms) |
|---|---:|
| archivo único, filtro por rango de tiempo_sk (baseline) | 2.26 |
| glob Hive + partition pruning (I-6) | 2.52 |
| lectura directa de la partición month=09 (sin glob ni Hive) | 1.08 |

## C. Q1 — ¿ANALYZE corrige la estimación de cardinalidad del join?

| Fuente de datos | Estimada antes de ANALYZE | Estimada después de ANALYZE | Real |
|---|---:|---:|---:|
| vistas sobre Parquet | 1,651 | 1,651 | 34,039 |
| tablas materializadas | 24,037 | 24,037 | 34,039 |
