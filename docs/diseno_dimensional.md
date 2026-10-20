# Diseño dimensional — TuBoleta

Este documento responde las cinco preguntas del diseño dimensional para el proceso de venta de boletería de TuBoleta (Estadio Atanasio Girardot, Medellín) y justifica las decisiones del modelo. El diagrama se genera a partir de [`modelo_dimensional.dbml`](modelo_dimensional.dbml).

## Pregunta 1 — ¿Cuál es el proceso de negocio?

**Comportamiento de ventas de boletas (compras confirmadas) por evento, zona, canal y período**, junto con el embudo de intentos de compra que lo precede.

El sistema operacional (Redis + CockroachDB) atiende el flujo: fila virtual, lock temporal de la silla, pago y `INSERT` bajo `SERIALIZABLE`. Analíticamente nos interesan dos cosas distintas:

1. Lo que **se vendió** (dinero y boletas): `fact_ventas_boletas`.
2. Lo que **se intentó vender** y cómo terminó cada intento (compra, abandono o rechazo): `fact_intentos_compra`.

## Pregunta 2 — ¿Cuál es la granularidad?

| Tabla de hechos | Granularidad (una fila = ...) |
|---|---|
| `fact_ventas_boletas` | **una silla vendida y pagada en un evento** (compra confirmada). |
| `fact_intentos_compra` | **un intento de compra**: un usuario bloqueó una silla (lock) para un evento y el intento terminó en `COMPRA`, `ABANDONO` o `RECHAZO_UNIQUE`. |

**Los abandonos no son ventas.** Si se mezclaran en una sola tabla, cada `SUM(precio_pagado)` o `COUNT(*)` tendría que acordarse de filtrar, y bastaría un olvido para inflar los ingresos. Por eso la tabla de ventas contiene únicamente pagos confirmados, y los abandonos viven en su propia tabla.

Garantías que el pipeline verifica con `assert`:

- `UNIQUE(evento_sk, silla_sk)` en `fact_ventas_boletas`: **cero double-booking**, igual que la restricción `UNIQUE` en CockroachDB.
- Cada venta confirmada se enlaza con **exactamente un** intento de resultado `COMPRA` (`compra_id`).
- Cada fila de ambas tablas de hechos resolvió **exactamente una versión** de `dim_zona` (ver SCD Tipo 2).

## Pregunta 3 — ¿Cuáles son las dimensiones?

Las dimensiones son **conformadas**: las dos tablas de hechos comparten `dim_tiempo`, `dim_evento`, `dim_zona`, `dim_silla`, `dim_usuario` y `dim_canal`. Eso permite cruzar ventas y embudo con los mismos filtros.

| Dimensión | Atributos | Tipo SCD | Clave sustituta |
|---|---|---|---|
| `dim_tiempo` | tiempo_sk, fecha, anio, trimestre, mes, mes_nombre, dia, dia_semana, dia_nombre, es_fin_semana, hora, franja_horaria | Tipo 0 | `YYYYMMDDHH` (entero) |
| `dim_evento` | evento_sk, evento_id, nombre_evento, tipo_evento, recinto, ciudad, fecha_evento, inicio_ventas, aforo_total, organizador | Tipo 1 | secuencial |
| `dim_zona` | zona_sk, zona_id, nombre_zona, tipo_zona, capacidad_zona, precio_base, valido_desde, valido_hasta, activo | **Tipo 2** | secuencial |
| `dim_silla` | silla_sk, silla_id, zona_id, fila, numero, categoria | Tipo 1 | secuencial |
| `dim_usuario` | usuario_sk, usuario_id, segmento, canal_preferido | Tipo 1 | secuencial |
| `dim_canal` | canal_sk, canal_id, nombre, digital_flag | Tipo 1 | secuencial |

Notas:

- **`dim_tiempo` (Tipo 0)** tiene granularidad de **hora** porque en boletería importa la hora (pico de la noche, pico del día de apertura). Se construye con el mínimo y el máximo de las fechas de ambos hechos. Los valores no cambian nunca (Tipo 0). Las franjas son: madrugada (0-5), mañana (6-11), tarde (12-17) y noche (18-23).
- **`dim_canal`** incluye el miembro `DESCONOCIDO` para las filas cuyo canal llegó nulo desde el sistema operacional.
- **¿Por qué solo `dim_zona` es Tipo 2?** Porque es la única dimensión cuyos cambios **alteran el significado de las métricas**: el precio base de una zona cambia entre temporadas y esa diferencia explica los ingresos. En cambio, el segmento o el canal preferido de un usuario, o el nombre de un evento, son atributos descriptivos: si se corrigen, nos interesa el valor actual y no el historial (Tipo 1). Historizar a los usuarios con Tipo 2 sería una evolución futura (ver limitaciones).

## Pregunta 4 — ¿Cuáles son las métricas (hechos)?

### `fact_ventas_boletas`

| Métrica | Tipo | Uso |
|---|---|---|
| `precio_pagado` | Aditiva | Ingresos (`SUM`). Es el `precio_base` de la versión de zona vigente menos el descuento. |
| `cantidad` | Aditiva | Boletas (siempre 1 por la granularidad). |
| `descuento_aplicado` | Aditiva | Promociones otorgadas. |
| `tiempo_hasta_pago_seg` | **No aditiva** | Segundos entre el lock de la silla y el pago. Solo `AVG` o percentiles; sumarla no tiene sentido. |
| `es_pago_tardio` | Flag 0/1 | El pago ocurrió en el último 20 % del TTL del lock (600 s, es decir, desde el segundo 480). **Sigue siendo una venta válida.** |

### `fact_intentos_compra`

| Métrica | Tipo | Uso |
|---|---|---|
| `resultado` | Atributo degenerado | `COMPRA`, `ABANDONO` o `RECHAZO_UNIQUE`. |
| `es_compra`, `es_abandono`, `es_rechazo_unique` | Flags 0/1 | `SUM` para contar y `AVG` para tasas del embudo. |
| `tiempo_en_fila_seg` | No aditiva | Espera antes de ser admitido. Solo `AVG` o percentiles. |
| `precio_lista` | Aditiva | Precio de lista de la silla al momento del intento. Con `es_abandono = 1` permite estimar el ingreso potencial perdido. |

### Qué significa cada resultado

- **COMPRA**: el usuario pagó antes de que venciera el TTL y el `INSERT` fue aceptado.
- **ABANDONO**: el TTL del lock venció sin pago y la silla se liberó.
- **RECHAZO_UNIQUE**: el `INSERT` fue rechazado por la restricción `UNIQUE` porque la silla ya estaba vendida. Muestra que la garantía de consistencia la da CockroachDB y no el lock de Redis.

### Métricas semi-aditivas

Con esta granularidad (una silla vendida o un intento por fila) **ninguna métrica es semi-aditiva**: cada medida es aditiva, no aditiva o un flag, y no representa un saldo que se mida en un instante.

Una métrica semi-aditiva aparecería con una **tabla de hechos de instantánea periódica** del inventario, por ejemplo `fact_inventario_zona_dia` con `sillas_disponibles` por zona y día:

| Métrica (futura) | Por zona / evento | A lo largo del tiempo | Cómo agregarla en el tiempo |
|---|---|---|---|
| `sillas_disponibles` | Aditiva (se puede sumar) | **No aditiva** (sumar días no tiene sentido) | último valor del período o promedio |

Es una evolución futura: hoy el inventario se deriva de las ventas y no se persiste como instantánea.

## Pregunta 5 — ¿Cómo manejamos los cambios lentos? (SCD Tipo 2 en `dim_zona`)

Cuando cambia el `precio_base` (o la capacidad) de una zona:

1. Se **cierra** la versión anterior: se fija su `valido_hasta` y `activo = false`.
2. Se **inserta** una versión nueva con un `zona_sk` nuevo, `valido_hasta = 9999-12-31` y `activo = true`.
3. Cada hecho guarda el `zona_sk` de la versión **vigente en su fecha**: `fecha BETWEEN valido_desde AND valido_hasta`.

Ejemplo real de los datos sintéticos (el 2026-07-01 suben VIP y Occidental):

| zona_sk | zona_id | nombre_zona | precio_base | valido_desde | valido_hasta | activo |
|---|---|---|---|---|---|---|
| 1 | Z-VIP | VIP | 250000 | 2026-01-01 | 2026-06-30 | false |
| 2 | Z-VIP | VIP | 280000 | 2026-07-01 | 9999-12-31 | true |
| 3 | Z-OCC | Occidental | 150000 | 2026-01-01 | 2026-06-30 | false |
| 4 | Z-OCC | Occidental | 165000 | 2026-07-01 | 9999-12-31 | true |

Una boleta VIP pagada el 2026-06-15 apunta a `zona_sk = 1` y una pagada el 2026-07-20 apunta a `zona_sk = 2`. Hay eventos cuya ventana de ventas cruza el 1 de julio, así que **un mismo evento vende boletas a dos precios**; sin SCD Tipo 2 ese cambio se perdería o, peor, se reescribiría la historia.

Reglas de uso:

- **Los análisis por zona agrupan por `zona_id` / `nombre_zona`, nunca por versión**, y no filtran `activo = true`. Si se filtrara por la versión activa, se descartarían todas las ventas hechas antes del cambio de precio.
- Para comparar precios se agrupa por `zona_sk` (consulta 6 de `analyze.py`).
- La capacidad de la zona se mantiene en cada versión para que `ocupación = vendidas / capacidad_zona` funcione en cualquier versión.

## Por qué el estado de Redis no es un hecho

La posición en la fila virtual (ZSET), los locks activos y los contadores de disponibilidad en RAM son **estado efímero**: existen para coordinar el flujo en tiempo real y desaparecen cuando el TTL vence o el usuario avanza. No describen un evento de negocio terminado, no son durables y no se pueden reconstruir con certeza.

Lo que sí es un hecho analítico es el **resultado de cada intento que el sistema operacional persiste** (compra, abandono, rechazo `UNIQUE`) y, por supuesto, la compra confirmada en CockroachDB. Por eso `fact_intentos_compra` modela resultados persistidos y no "la fila de Redis". Atributos como `tiempo_en_fila_seg` solo existen en el modelo porque el sistema operacional los registra junto con el resultado del intento.

## Decisiones de pipeline relacionadas

- **Bronze** conserva los datos tal cual llegan, con basura intencional (duplicados, IDs con espacios, fechas como texto, canales nulos y filas sin claves de negocio). **Silver** hace solo limpieza técnica y documenta el efecto en `reporte_calidad_silver.txt`. **Gold** modela y resuelve las claves sustitutas.
- `es_pago_tardio` se **deriva** en Gold a partir de `tiempo_hasta_pago_seg` y del TTL (columnas ya persistidas), sin leer nada de Redis.
- La versión de zona se resuelve con la fecha del hecho: fecha de pago en ventas y fecha del intento (momento del lock) en intentos.

## Limitaciones y evolución futura

- **Datos sintéticos.** Los datos se generan con una semilla fija para que el pipeline sea reproducible; los patrones (picos, descuentos, abandono) son plausibles pero no reales.
- **Carga completa.** Cada ejecución reconstruye Silver y Gold. A mayor volumen habría que pasar a **cargas incrementales** (por rango de fechas o por marca de agua).
- **Sin captura de cambios.** La extracción es por lote. Una evolución natural es **CDC con Kafka** (Debezium sobre CockroachDB, que ofrece *changefeeds*) para alimentar Bronze casi en tiempo real.
- **CockroachDB real.** La rama de extracción hacia CockroachDB existe (`USE_SYNTHETIC=false`), pero no se probó contra un clúster; habría que ajustar nombres de tablas y tipos al esquema real.
- **SCD Tipo 2 en `dim_usuario`.** Hoy el usuario es Tipo 1. Historizar segmento y canal preferido permitiría analizar cómo cambia el comportamiento de un mismo cliente.
- **Embudo parcial.** El embudo comienza en el lock de la silla. Las salidas de la fila virtual antes de lograr un lock no se persisten en el sistema operacional y por eso no se analizan.
- **Una compra = una silla.** No se modela la compra de varias sillas en una sola transacción (carrito).
