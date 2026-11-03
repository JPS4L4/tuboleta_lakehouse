# diagnostico_baseline.md — Taller 4

| Entorno | Valor |
|---|---|
| Motor | DuckDB 2.0.0 sobre Parquet (Gold del M3, sin modificar) |
| Máquina | AMD Ryzen 5 9600X (6 núcleos) · 15,1 GB RAM · Windows 11 Pro · Python 3.14.6 |
| Método | warm-up ×3, mediana de 5 ejecuciones (`scripts/taller4_optimizacion.py`) |
| Planes crudos | `docs/taller4/planes/Qn_antes.txt` (árbol `EXPLAIN ANALYZE`) |
| Tiempo por operador | `docs/taller4/planes/Qn_antes_perfil.txt` (profiling JSON de DuckDB) |
| Reproducir | `python -m scripts.taller4_optimizacion` |

> **Nota sobre DuckDB 2.0.** El árbol de `EXPLAIN ANALYZE` muestra filas reales, archivos y row groups, pero todos los operadores aparecen con `0µs`. El tiempo real de cada operador y la cardinalidad estimada solo se exponen en el profiling JSON (`profiling_mode='detailed'`). Por eso cada plan tiene un archivo `_perfil.txt` al lado.

> **Regla aplicada.** Primero se capturó el plan sin interpretar. Luego se buscaron los 5 indicadores en orden; el primero que aparece es el problema principal. También se documentan los indicadores descartados y por qué.

---

## Q1 — Ingresos por evento en septiembre 2026

```sql
SELECT e.nombre_evento, t.mes, COUNT(*) AS boletas, SUM(f.precio_pagado) AS ingresos
FROM fact_ventas_boletas f
JOIN dim_tiempo t ON t.tiempo_sk = f.tiempo_sk
JOIN dim_evento e ON e.evento_sk = f.evento_sk
WHERE t.anio = 2026 AND t.mes = 9
GROUP BY 1, 2
```

| Campo | Valor |
|---|---|
| Tiempo baseline (mediana) | **5,09 ms** |
| Motor usado | DuckDB 2.0.0 sobre Parquet |
| Operador más costoso | `TABLE_SCAN` sobre `fact_ventas_boletas`: 1,10 ms (el mayor del plan), `Row Groups Scanned: 1 / 1`, `Data Read: 640,9 kB`, cardinalidad estimada de entrada 208.236 filas, 34.039 filas emitidas, 2 filas devueltas por la consulta |
| Problema identificado | **Acceso secuencial (full scan) sin data skipping posible.** La fact se escribió en un único row group y sin orden por `tiempo_sk` (`is_monotonic_increasing = False`). El filtro por mes llega a la fact como filtro dinámico del join (`Dynamic Filters: tiempo_sk IN PRF(tiempo_sk)`), pero el único zonemap min/max del archivo cubre todo el rango (2026022310–2026101623). Por eso no se puede descartar ningún bloque: se decodifica la tabla completa para quedarse con el 16,3 % de las filas. |
| Indicador que lo revela | **Indicador 1, acceso secuencial:** 208.236 filas leídas frente a 2 devueltas. Su causa raíz es el **Indicador 4, data skipping ausente:** `Row Groups Scanned: 1 / 1` aunque se filtra un rango temporal. |
| Indicadores descartados | **3:** dos `HASH_JOIN` (`INNER`, condiciones `tiempo_sk = tiempo_sk` y `evento_sk = evento_sk`), sin `CROSS_JOIN` ni nested loop. El lado build son las dimensiones pequeñas (720 y 5 filas), que es lo correcto. **5:** `mes` es `INTEGER` y se compara con el literal entero `9` (`Filters: mes = 9`), sin `CAST` en el predicado. El `CAST(#1 AS TINYINT)` del plan está en una proyección interna del agrupamiento, no en el filtro. |
| Hallazgo secundario (Indicador 2) | La salida de los joins se **estimó en 1.651 filas y fueron 34.039 reales (20,6x)**. Supera el umbral de 10x del enunciado. Sin embargo, el error no produjo una decisión equivocada: el algoritmo (Hash Join) y la elección de la tabla build son los correctos para estas cardinalidades. Por eso no es el problema principal, pero se documenta como evidencia. |

**Lectura del plan.** El plan se lee de abajo hacia arriba:
1. DuckDB escanea `dim_tiempo` con `mes = 9` (720 horas de septiembre). Le aplica además un `FILTER` con el rango `tiempo_sk BETWEEN 2026022310 AND 2026101623`, que coincide exactamente con el min/max de la fact: es un filtro derivado de las estadísticas del archivo.
2. Con esas 720 filas construye la tabla hash.
3. Esa tabla hash genera el filtro dinámico (PRF) que se empuja al `TABLE_SCAN` de la fact.
4. El filtro dinámico solo puede saltarse bloques si los min/max del bloque lo permiten. Con 1 row group eso es imposible.

---

## Q2 — Ingresos por zona en septiembre 2026 (filtro directo en la fact)

```sql
SELECT zona_sk, COUNT(*) AS boletas, SUM(precio_pagado) AS ingresos
FROM fact_ventas_boletas
WHERE tiempo_sk BETWEEN 2026090100 AND 2026093023
GROUP BY 1
```

| Campo | Valor |
|---|---|
| Tiempo baseline (mediana) | **2,31 ms** |
| Motor usado | DuckDB 2.0.0 sobre Parquet |
| Operador más costoso | `TABLE_SCAN` sobre `fact_ventas_boletas`: 1,04 ms de 2,26 ms totales (46 %), `Row Groups Scanned: 1 / 1`, `Data Read: 583,7 kB`, 34.039 filas emitidas de 208.236, 4 filas devueltas |
| Problema identificado | **Acceso secuencial sobre un único archivo.** El filtro sí se empuja al scan (`Filters: (tiempo_sk >= 2026090100) AND (tiempo_sk <= 2026093023)`), pero se aplica fila por fila después de leer el archivo completo. Septiembre representa el 16,3 % de la fact, y aun así se leen el 100 % de los datos de las 3 columnas proyectadas. |
| Indicador que lo revela | **Indicador 1, acceso secuencial:** el archivo se lee completo para devolver 4 filas. La causa es la misma que en Q1, el **Indicador 4** (`1 / 1` row groups), pero aquí el filtro está directo sobre la fact, lo que permite atacarlo con particionado por mes. |
| Indicadores descartados | **2:** se estimaron 41.647 filas y fueron 34.039 (1,2x), una estimación coherente. **3:** no aplica, la consulta no tiene joins. **5:** `tiempo_sk` es `BIGINT` y se compara con literales enteros; el predicado aparece en el plan sin conversión. |

**Lectura del plan.** El plan es lineal: `TABLE_SCAN` (con filtro empujado) → dos `PROJECTION` → `PERFECT_HASH_GROUP_BY`. DuckDB elige el *perfect* hash porque `zona_sk` tiene un dominio pequeño y conocido (estima 6 grupos, que son las versiones SCD2 de `dim_zona`; salen 4 zonas con ventas). Casi la mitad del tiempo se va en el scan; la agregación es barata (0,12 ms).

---

## Q3 — Embudo de conversión por evento

```sql
SELECT d.nombre_evento, COUNT(*) AS intentos, SUM(i.es_compra) AS compras,
       SUM(i.es_abandono) AS abandonos, SUM(i.es_rechazo_unique) AS rechazos
FROM fact_intentos_compra i JOIN dim_evento d ON d.evento_sk = i.evento_sk
GROUP BY 1
```

| Campo | Valor |
|---|---|
| Tiempo baseline (mediana) | **4,98 ms** (vistas sobre Parquet) |
| Motor usado | DuckDB 2.0.0 sobre Parquet |
| Operador más costoso | `TABLE_SCAN` sobre `fact_intentos_compra`: 1,23 ms, 260.294 filas, `Data Read: 232,3 kB`. Le sigue `HASH_GROUP_BY` con 0,98 ms (5 grupos). |
| Problema identificado | **Ninguno de acceso.** La consulta no tiene `WHERE`: agrega todos los intentos de compra. Leer las 260.294 filas no es un desperdicio, es lo que la consulta necesita. No existe un subconjunto que un índice, un zonemap o una partición pudieran evitar. Diagnóstico honesto: el plan ya es el adecuado para su selectividad (100 %). |
| Indicador que lo revela | **Ninguno.** Hay muchas más filas leídas (260.294) que devueltas (5), pero eso no es el Indicador 1: no hay filtro que haga selectiva la consulta, y la reducción la produce la agregación, no el acceso. |
| Indicadores descartados | **2:** las estimaciones son exactas (260.294 = 260.294 y 5 = 5). **3:** `HASH_JOIN` `INNER` con build en `dim_evento` (5 filas), sin `CROSS_JOIN`. **4 y 5:** no aplican porque no hay predicado. |

**Uso en el taller.** Q3 se usa como experimento de control con I-2 (`ANALYZE`). Si las estimaciones ya son exactas, actualizar estadísticas no debería cambiar ni el plan ni el tiempo. Para que `ANALYZE` tenga un objeto real, el control se mide sobre tablas materializadas (antes y después en la misma conexión; ver `Q3_antes_analyze.txt`). Por eso el "t antes" de Q3 en `benchmarks.md` (≈2,5 ms) es menor que este baseline sobre Parquet: materializar elimina la decodificación del archivo.

---

## Resumen del diagnóstico

| Query | Baseline | Operador más costoso | Problema | Indicador | Intervención prevista |
|---|---:|---|---|---|---|
| Q1 | 5,09 ms | `TABLE_SCAN` fact (1,10 ms, 1/1 row groups, 640,9 kB) | Full scan sin data skipping: 1 row group, fact sin ordenar | 1 → 4 (y 2 secundario: 20,6x) | I-3: ordenar por `tiempo_sk`, `row_group_size=20_000` |
| Q2 | 2,31 ms | `TABLE_SCAN` fact (1,04 ms, 46 %, 583,7 kB) | Full scan de un archivo único para un 16,3 % de filas | 1 → 4 | I-6: particionado Hive `year=/month=` |
| Q3 | 4,98 ms | `TABLE_SCAN` intentos (1,23 ms) + `HASH_GROUP_BY` (0,98 ms) | Ninguno: agregación total, sin filtro | Ninguno | I-2: `ANALYZE` (control, se espera ≈1,0x) |

**Advertencia de escala.** Las tres consultas tardan entre 2 y 5 ms. Con 208.000 y 260.000 filas, el overhead fijo del motor (planificación, abrir archivos y recolectar el resultado) pesa tanto como el scan. Por eso la reducción de datos leídos debe medirse en bytes y row groups, no solo en milisegundos.

## Lista de verificación del diagnóstico
- [x] Los planes están guardados completos en `docs/taller4/planes/`
- [x] Cada query tiene la mediana de 5 medidas con warm-up
- [x] Se nombra el operador más costoso con el nombre exacto del plan y su tiempo medido
- [x] Se citan filas leídas frente a devueltas y row groups escaneados
- [x] Se explican los indicadores descartados, no solo el que aplica
- [ ] Opcional: consulta 7 (`quantile_cont`) como candidata de costo inherente
