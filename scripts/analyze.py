"""Paso 5: consultas analíticas sobre Gold con DuckDB y benchmark.

Registra vistas DuckDB sobre los Parquet de Gold (`read_parquet`), ejecuta las
consultas de negocio de boletería, imprime los resultados, los guarda en
`docs/resultados_consultas.md` y corre el benchmark (`scripts/benchmark.py`).

Las consultas por zona agrupan por `zona_id` / `nombre_zona` y nunca por versión
de la zona (SCD Tipo 2); solo la consulta 6 compara versiones a propósito.
"""
from __future__ import annotations

from datetime import datetime

import pandas as pd

from scripts import benchmark, config

# Plantilla del embudo: se instancia por evento y por canal.
EMBUDO = """
WITH intentos AS (
    SELECT d.{etiqueta} AS {alias}, COUNT(*) AS intentos, CAST(SUM(i.es_compra) AS BIGINT) AS compras,
           CAST(SUM(i.es_abandono) AS BIGINT) AS abandonos, CAST(SUM(i.es_rechazo_unique) AS BIGINT) AS rechazos_unique
    FROM fact_intentos_compra i JOIN {dim} d ON d.{sk} = i.{sk}
    GROUP BY 1
), ventas AS (
    SELECT d.{etiqueta} AS {alias}, CAST(SUM(f.es_pago_tardio) AS BIGINT) AS pagos_tardios
    FROM fact_ventas_boletas f JOIN {dim} d ON d.{sk} = f.{sk}
    GROUP BY 1
)
SELECT i.{alias}, i.intentos, i.compras, i.abandonos, i.rechazos_unique,
       ROUND(100.0 * i.compras / i.intentos, 2) AS conversion_pct,
       ROUND(100.0 * i.abandonos / i.intentos, 2) AS abandono_pct,
       ROUND(100.0 * i.rechazos_unique / i.intentos, 2) AS rechazo_unique_pct,
       ROUND(100.0 * v.pagos_tardios / i.compras, 2) AS pago_tardio_pct
FROM intentos i JOIN ventas v USING ({alias})
ORDER BY i.intentos DESC
"""

# (titulo, pregunta de negocio, SQL)
CONSULTAS: list[tuple[str, str, str]] = [
    ("1. Ingresos y boletas por evento y mes",
     "¿Cómo se reparten las ventas de cada evento a lo largo de los meses de su ventana de venta?",
     """
     SELECT e.nombre_evento, t.anio, t.mes, t.mes_nombre,
            COUNT(*) AS boletas, CAST(SUM(f.precio_pagado) AS BIGINT) AS ingresos
     FROM fact_ventas_boletas f
     JOIN dim_tiempo t ON t.tiempo_sk = f.tiempo_sk
     JOIN dim_evento e ON e.evento_sk = f.evento_sk
     GROUP BY e.fecha_evento, e.nombre_evento, t.anio, t.mes, t.mes_nombre
     ORDER BY e.fecha_evento, t.anio, t.mes
     """),
    ("2. Ocupación e ingresos por evento y zona",
     "¿Qué porcentaje de la capacidad de cada zona se vendió en cada evento y cuánto dinero generó?",
     """
     SELECT e.nombre_evento, z.nombre_zona, MAX(z.capacidad_zona) AS capacidad_zona,
            COUNT(*) AS vendidas,
            ROUND(100.0 * COUNT(*) / MAX(z.capacidad_zona), 2) AS ocupacion_pct,
            CAST(SUM(f.precio_pagado) AS BIGINT) AS ingresos
     FROM fact_ventas_boletas f
     JOIN dim_zona z ON z.zona_sk = f.zona_sk
     JOIN dim_evento e ON e.evento_sk = f.evento_sk
     GROUP BY e.fecha_evento, e.nombre_evento, z.zona_id, z.nombre_zona
     ORDER BY e.fecha_evento, ingresos DESC
     """),
    ("3. Volumen, ingresos y ticket promedio por canal",
     "¿Qué canal vende más y cuánto paga en promedio quien compra por cada uno?",
     """
     SELECT c.nombre AS canal, COUNT(*) AS boletas,
            ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS boletas_pct,
            CAST(SUM(f.precio_pagado) AS BIGINT) AS ingresos,
            CAST(ROUND(AVG(f.precio_pagado), 0) AS BIGINT) AS ticket_promedio,
            CAST(ROUND(AVG(f.descuento_aplicado), 0) AS BIGINT) AS descuento_promedio
     FROM fact_ventas_boletas f
     JOIN dim_canal c ON c.canal_sk = f.canal_sk
     GROUP BY c.nombre
     ORDER BY ingresos DESC
     """),
    ("4. Distribución por franja horaria y día de la semana",
     "¿A qué hora y en qué día compra la gente? Boletas por franja horaria, abiertas por día de la semana.",
     """
     SELECT t.franja_horaria, COUNT(*) AS boletas,
            ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS pct,
            COUNT(*) FILTER (WHERE t.dia_semana = 1) AS lunes,
            COUNT(*) FILTER (WHERE t.dia_semana = 2) AS martes,
            COUNT(*) FILTER (WHERE t.dia_semana = 3) AS miercoles,
            COUNT(*) FILTER (WHERE t.dia_semana = 4) AS jueves,
            COUNT(*) FILTER (WHERE t.dia_semana = 5) AS viernes,
            COUNT(*) FILTER (WHERE t.dia_semana = 6) AS sabado,
            COUNT(*) FILTER (WHERE t.dia_semana = 7) AS domingo
     FROM fact_ventas_boletas f
     JOIN dim_tiempo t ON t.tiempo_sk = f.tiempo_sk
     GROUP BY t.franja_horaria
     ORDER BY CASE t.franja_horaria WHEN 'madrugada' THEN 1 WHEN 'mañana' THEN 2 WHEN 'tarde' THEN 3 ELSE 4 END
     """),
    ("5a. Embudo de conversión por evento",
     "De cada 100 intentos de compra (lock de silla), ¿cuántos terminan en compra, abandono o rechazo UNIQUE? "
     "¿Qué porcentaje de las ventas se pagó en el último tramo del TTL?",
     EMBUDO.format(etiqueta="nombre_evento", alias="evento", dim="dim_evento", sk="evento_sk")),
    ("5b. Embudo de conversión por canal",
     "Misma lectura del embudo, ahora por canal de venta.",
     EMBUDO.format(etiqueta="nombre", alias="canal", dim="dim_canal", sk="canal_sk")),
    ("6. SCD Tipo 2: ingresos VIP por versión de precio",
     "El 2026-07-01 sube el precio VIP. ¿Cómo cambian boletas, ingresos y descuentos entre las dos versiones?",
     """
     SELECT z.zona_sk, z.nombre_zona, z.precio_base, z.valido_desde, z.valido_hasta,
            COUNT(*) AS boletas, CAST(SUM(f.precio_pagado) AS BIGINT) AS ingresos,
            CAST(ROUND(AVG(f.precio_pagado), 0) AS BIGINT) AS ticket_promedio,
            CAST(ROUND(AVG(f.descuento_aplicado), 0) AS BIGINT) AS descuento_promedio
     FROM fact_ventas_boletas f
     JOIN dim_zona z ON z.zona_sk = f.zona_sk
     WHERE z.zona_id = 'Z-VIP'
     GROUP BY z.zona_sk, z.nombre_zona, z.precio_base, z.valido_desde, z.valido_hasta
     ORDER BY z.valido_desde
     """),
    ("7. Tiempo hasta el pago por zona (promedio, mediana y p95)",
     "¿Cuánto tarda en pagar cada zona desde que bloquea la silla (TTL de 600 s)? ¿Cuántos pagan al límite?",
     """
     SELECT z.nombre_zona, COUNT(*) AS boletas,
            ROUND(AVG(f.tiempo_hasta_pago_seg), 1) AS promedio_seg,
            ROUND(quantile_cont(f.tiempo_hasta_pago_seg, 0.5), 1) AS mediana_seg,
            ROUND(quantile_cont(f.tiempo_hasta_pago_seg, 0.95), 1) AS p95_seg,
            ROUND(100.0 * CAST(SUM(f.es_pago_tardio) AS BIGINT) / COUNT(*), 2) AS pago_tardio_pct
     FROM fact_ventas_boletas f
     JOIN dim_zona z ON z.zona_sk = f.zona_sk
     GROUP BY z.zona_id, z.nombre_zona
     ORDER BY promedio_seg DESC
     """),
    ("8. Ventas en el día de apertura",
     "¿Qué parte de las boletas de cada evento se vende el primer día y en los tres primeros días de venta?",
     """
     SELECT e.nombre_evento, e.inicio_ventas, COUNT(*) AS boletas,
            COUNT(*) FILTER (WHERE t.fecha = e.inicio_ventas) AS primer_dia,
            ROUND(100.0 * COUNT(*) FILTER (WHERE t.fecha = e.inicio_ventas) / COUNT(*), 2) AS primer_dia_pct,
            ROUND(100.0 * COUNT(*) FILTER (WHERE t.fecha <= e.inicio_ventas + 2) / COUNT(*), 2) AS tres_dias_pct,
            CAST(SUM(f.precio_pagado) FILTER (WHERE t.fecha = e.inicio_ventas) AS BIGINT) AS ingresos_primer_dia
     FROM fact_ventas_boletas f
     JOIN dim_tiempo t ON t.tiempo_sk = f.tiempo_sk
     JOIN dim_evento e ON e.evento_sk = f.evento_sk
     GROUP BY e.evento_id, e.nombre_evento, e.inicio_ventas
     ORDER BY e.inicio_ventas
     """),
    ("9. Ingreso potencial perdido por abandono, por zona",
     "Cada abandono libera una silla que pudo venderse. ¿Cuánto dinero de lista se asocia a esos abandonos? "
     "Es una cota superior: parte de esas sillas se vendió después a otro usuario.",
     """
     SELECT z.nombre_zona, COUNT(*) AS intentos, CAST(SUM(i.es_abandono) AS BIGINT) AS abandonos,
            ROUND(100.0 * CAST(SUM(i.es_abandono) AS BIGINT) / COUNT(*), 2) AS abandono_pct,
            CAST(SUM(i.precio_lista) FILTER (WHERE i.es_abandono = 1) AS BIGINT) AS ingreso_potencial_perdido
     FROM fact_intentos_compra i
     JOIN dim_zona z ON z.zona_sk = i.zona_sk
     GROUP BY z.zona_id, z.nombre_zona
     ORDER BY ingreso_potencial_perdido DESC
     """),
]


def _formatear_celda(columna: str, valor: object) -> str:
    """Formatea una celda para Markdown: miles con punto y decimales con coma (el año queda sin formato)."""
    if isinstance(valor, float):
        return f"{valor:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    if isinstance(valor, int) and not isinstance(valor, bool) and columna != "anio":
        return f"{valor:,}".replace(",", ".")
    return str(valor)


def a_markdown(df: pd.DataFrame) -> str:
    """Convierte un DataFrame en una tabla Markdown."""
    encabezado = "| " + " | ".join(df.columns) + " |"
    separador = "|" + "|".join("---" for _ in df.columns) + "|"
    filas = ["| " + " | ".join(_formatear_celda(c, v) for c, v in zip(df.columns, fila)) + " |"
             for fila in df.itertuples(index=False, name=None)]
    return "\n".join([encabezado, separador, *filas])


def escribir_resultados(resultados: list[tuple[str, str, pd.DataFrame]]) -> None:
    """Guarda las consultas y sus resultados en docs/resultados_consultas.md."""
    bloques = ["# Resultados de las consultas analíticas", "",
               f"Generado por `scripts/analyze.py` ({datetime.now():%Y-%m-%d %H:%M}) sobre el esquema en estrella de Gold.", ""]
    for titulo, pregunta, df in resultados:
        bloques += [f"## {titulo}", "", f"*{pregunta}*", "", a_markdown(df), ""]
    config.DOCS.mkdir(parents=True, exist_ok=True)
    (config.DOCS / "resultados_consultas.md").write_text("\n".join(bloques), encoding="utf-8", newline="\n")


def ejecutar() -> int:
    """Ejecuta las consultas de negocio, escribe sus resultados y corre el benchmark."""
    conexion = benchmark.conectar_gold()
    resultados = []
    for titulo, pregunta, sql in CONSULTAS:
        df = conexion.execute(sql).df()
        resultados.append((titulo, pregunta, df))
        print(f"\n{titulo}\n  {pregunta}")
        print(df.to_string(index=False))
    escribir_resultados(resultados)
    print("\nBenchmark (agregación evento x zona x mes):")
    benchmark.ejecutar()
    return len(CONSULTAS)


if __name__ == "__main__":
    ejecutar()
