# Consultas SQL de negocio y resultados — entrega final

Este documento reúne consultas completas del modelo Gold para que puedan revisarse y ejecutarse de forma independiente. Los resultados de referencia provienen de `docs/resultados_consultas.md`, generado por `scripts/analyze.py` en la corrida final del **26-11-2026 a las 16:40**. Esa salida coincide con la de la ejecución del 16-11-2026 a las 23:19: los resultados de las consultas no cambiaron, solo la fecha de generación.

**Motor:** DuckDB sobre Parquet Gold.  
**Granularidad:** una fila de `fact_ventas_boletas` representa una silla vendida y pagada; una fila de `fact_intentos_compra` representa un intento.  
**Moneda:** COP.

## Consulta 1. Ingresos y boletas por evento y mes

**Pregunta:** ¿Cómo se distribuyen las ventas de cada evento durante su ventana de venta?

```sql
SELECT
    e.nombre_evento,
    t.anio,
    t.mes,
    t.mes_nombre,
    COUNT(*) AS boletas,
    CAST(SUM(f.precio_pagado) AS BIGINT) AS ingresos
FROM fact_ventas_boletas f
JOIN dim_tiempo t ON t.tiempo_sk = f.tiempo_sk
JOIN dim_evento e ON e.evento_sk = f.evento_sk
GROUP BY
    e.fecha_evento, e.nombre_evento,
    t.anio, t.mes, t.mes_nombre
ORDER BY e.fecha_evento, t.anio, t.mes;
```

**Resultado de referencia:** 15 grupos evento-mes. Ejemplos: Concierto Noche Latina registró 12.007 boletas y $1.210.903.000 COP en febrero; Final del Fútbol Colombiano registró 22.125 boletas y $2.402.970.800 COP en septiembre.

**Qué demuestra:** permite seguir el volumen y los ingresos en el tiempo sin consultar tablas operacionales normalizadas.

## Consulta 2. Ocupación e ingresos por evento y zona

**Pregunta:** ¿Qué porcentaje de la capacidad de cada zona se vendió y cuánto dinero generó?

```sql
SELECT
    e.nombre_evento,
    z.nombre_zona,
    MAX(z.capacidad_zona) AS capacidad_zona,
    COUNT(*) AS vendidas,
    ROUND(100.0 * COUNT(*) / MAX(z.capacidad_zona), 2) AS ocupacion_pct,
    CAST(SUM(f.precio_pagado) AS BIGINT) AS ingresos
FROM fact_ventas_boletas f
JOIN dim_zona z ON z.zona_sk = f.zona_sk
JOIN dim_evento e ON e.evento_sk = f.evento_sk
GROUP BY
    e.fecha_evento, e.nombre_evento,
    z.zona_id, z.nombre_zona
ORDER BY e.fecha_evento, ingresos DESC;
```

**Resultado de referencia:** 20 combinaciones evento-zona. El Clásico Paisa alcanzó 100 % de ocupación en Occidental (12.000/12.000) y VIP (3.000/3.000). La consulta agrupa por `zona_id`, no por versión SCD2, para no duplicar una zona lógica.

**Qué demuestra:** combina una métrica operativa (ocupación) con ingresos y capacidad de la dimensión.

## Consulta 3. Volumen, ingresos y ticket promedio por canal

**Pregunta:** ¿Qué canal vende más y cuál es el ticket promedio?

```sql
SELECT
    c.nombre AS canal,
    COUNT(*) AS boletas,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS boletas_pct,
    CAST(SUM(f.precio_pagado) AS BIGINT) AS ingresos,
    CAST(ROUND(AVG(f.precio_pagado), 0) AS BIGINT) AS ticket_promedio,
    CAST(ROUND(AVG(f.descuento_aplicado), 0) AS BIGINT) AS descuento_promedio
FROM fact_ventas_boletas f
JOIN dim_canal c ON c.canal_sk = f.canal_sk
GROUP BY c.nombre
ORDER BY ingresos DESC;
```

**Resultado de referencia:** app lidera con 92.066 boletas (44,21 %) y $9.779.126.100 COP; web registra 82.058 (39,41 %) y taquilla 31.011 (14,89 %). El miembro `DESCONOCIDO` concentra 3.101 ventas (1,49 %).

**Qué demuestra:** compara canales y mantiene visibles los registros cuyo canal no pudo identificarse en origen.

## Consulta 4. Embudo de conversión por evento

**Pregunta:** ¿Cuántos intentos terminan en compra, abandono o rechazo por unicidad?

```sql
WITH intentos AS (
    SELECT
        d.nombre_evento AS evento,
        COUNT(*) AS intentos,
        CAST(SUM(i.es_compra) AS BIGINT) AS compras,
        CAST(SUM(i.es_abandono) AS BIGINT) AS abandonos,
        CAST(SUM(i.es_rechazo_unique) AS BIGINT) AS rechazos_unique
    FROM fact_intentos_compra i
    JOIN dim_evento d ON d.evento_sk = i.evento_sk
    GROUP BY d.nombre_evento
),
ventas AS (
    SELECT
        d.nombre_evento AS evento,
        CAST(SUM(f.es_pago_tardio) AS BIGINT) AS pagos_tardios
    FROM fact_ventas_boletas f
    JOIN dim_evento d ON d.evento_sk = f.evento_sk
    GROUP BY d.nombre_evento
)
SELECT
    i.evento,
    i.intentos,
    i.compras,
    i.abandonos,
    i.rechazos_unique,
    ROUND(100.0 * i.compras / i.intentos, 2) AS conversion_pct,
    ROUND(100.0 * i.abandonos / i.intentos, 2) AS abandono_pct,
    ROUND(100.0 * i.rechazos_unique / i.intentos, 2) AS rechazo_unique_pct,
    ROUND(100.0 * v.pagos_tardios / i.compras, 2) AS pago_tardio_pct
FROM intentos i
JOIN ventas v USING (evento)
ORDER BY i.intentos DESC;
```

**Resultado de referencia:** los cinco eventos muestran una conversión cercana al 80 %. Por ejemplo, el Clásico Paisa tuvo 54.577 intentos: 43.625 compras, 7.468 abandonos y 3.484 rechazos UNIQUE; conversión 79,93 %.

**Qué demuestra:** separa intentos de ventas confirmadas y permite observar el efecto de abandono y de la restricción de unicidad.

## Consulta 5. SCD Tipo 2: ingresos VIP por versión de precio

**Pregunta:** ¿Cómo cambian las ventas y los ingresos entre las dos versiones del precio VIP?

```sql
SELECT
    z.zona_sk,
    z.nombre_zona,
    z.precio_base,
    z.valido_desde,
    z.valido_hasta,
    COUNT(*) AS boletas,
    CAST(SUM(f.precio_pagado) AS BIGINT) AS ingresos,
    CAST(ROUND(AVG(f.precio_pagado), 0) AS BIGINT) AS ticket_promedio,
    CAST(ROUND(AVG(f.descuento_aplicado), 0) AS BIGINT) AS descuento_promedio
FROM fact_ventas_boletas f
JOIN dim_zona z ON z.zona_sk = f.zona_sk
WHERE z.zona_id = 'Z-VIP'
GROUP BY
    z.zona_sk, z.nombre_zona, z.precio_base,
    z.valido_desde, z.valido_hasta
ORDER BY z.valido_desde;
```

**Resultado de referencia:**

| Versión | Precio base | Vigencia | Boletas | Ingresos |
|---|---:|---|---:|---:|
| VIP anterior | $250.000 | 2026-01-01 a 2026-06-30 | 5.834 | $1.411.662.500 |
| VIP nueva | $280.000 | Desde 2026-07-01 | 8.041 | $2.186.856.000 |

**Qué demuestra:** conserva el historial de precios y asigna cada venta a la versión vigente en su fecha, en lugar de sobrescribir el valor histórico.

## Ejecución y verificación

Desde la raíz del repositorio:

```bash
python main.py
```

El proceso ejecuta las nueve consultas de negocio y regenera `docs/resultados_consultas.md`. Para contrastar una consulta individual, abrir DuckDB sobre los Parquet de `lakehouse/gold/` y ejecutar el SQL correspondiente.

**Fuente de resultados:** `docs/resultados_consultas.md`. Las cifras anteriores son la salida registrada en la ejecución indicada al inicio; si se regenera Gold con otra ruta o conjunto de datos, los resultados pueden cambiar. No mezclar la ejecución sintética directa con la extracción desde CockroachDB.
