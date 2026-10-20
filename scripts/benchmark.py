"""Benchmark honesto: la misma agregación lógica en tres motores.

Agregación: boletas e ingresos por evento x zona x mes.

  (a) Fila (OLTP-like): SQLite cargado con las tablas operacionales normalizadas de
      Silver y los índices típicos de un sistema transaccional. La consulta une
      las tablas crudas (ventas, eventos, sillas, zonas).
  (b) DuckDB sobre los Parquet crudos de Bronze. La consulta debe limpiar al vuelo
      (TRIM, DISTINCT, filas sin clave, conversión de fechas) porque Bronze está sucio.
  (c) DuckDB sobre el esquema en estrella de Gold.

Reglas: el tiempo de carga NO se mide, se hace un calentamiento y luego N corridas;
se reporta la mediana. Se verifica que los tres motores devuelvan los mismos números.
"""
from __future__ import annotations

import os
import platform
import sqlite3
import statistics
import time
from datetime import datetime
from typing import Callable

import duckdb
import pandas as pd

from scripts import config
from scripts.transform_silver import archivo_bronze_mas_reciente

CORRIDAS = 5
Filas = list[tuple]

INDICES_OLTP = [
    "CREATE UNIQUE INDEX ux_compras_compra ON compras_confirmadas (compra_id)",
    "CREATE UNIQUE INDEX ux_compras_evento_silla ON compras_confirmadas (evento_id, silla_id)",
    "CREATE INDEX ix_compras_usuario ON compras_confirmadas (usuario_id)",
    "CREATE INDEX ix_compras_fecha ON compras_confirmadas (fecha_compra)",
    "CREATE UNIQUE INDEX ux_eventos_evento ON eventos (evento_id)",
    "CREATE UNIQUE INDEX ux_sillas_silla ON sillas (silla_id)",
    "CREATE INDEX ix_sillas_zona ON sillas (zona_id)",
    "CREATE INDEX ix_zonas_zona ON zonas (zona_id, valido_desde)",
    "CREATE UNIQUE INDEX ux_usuarios_usuario ON usuarios (usuario_id)",
    "CREATE INDEX ix_intentos_evento_silla ON intentos_compra (evento_id, silla_id)",
    "CREATE INDEX ix_intentos_fecha ON intentos_compra (fecha_intento)",
]
COLUMNAS_FECHA_DIA = {"zonas": ["valido_desde", "valido_hasta"], "eventos": ["fecha_evento", "inicio_ventas"]}

SQL_SQLITE = """
SELECT e.nombre_evento, z.nombre_zona,
       CAST(strftime('%Y', v.fecha_compra) AS INTEGER) AS anio,
       CAST(strftime('%m', v.fecha_compra) AS INTEGER) AS mes,
       COUNT(*) AS boletas, SUM(v.precio_pagado) AS ingresos
FROM compras_confirmadas v
JOIN eventos e ON e.evento_id = v.evento_id
JOIN sillas s ON s.silla_id = v.silla_id
JOIN zonas z ON z.zona_id = s.zona_id AND date(v.fecha_compra) BETWEEN z.valido_desde AND z.valido_hasta
GROUP BY e.evento_id, z.zona_id, anio, mes
"""

SQL_BRONZE = """
WITH v AS (
    SELECT DISTINCT TRIM(compra_id) AS compra_id, TRIM(silla_id) AS silla_id, TRIM(evento_id) AS evento_id,
           CAST(fecha_compra AS TIMESTAMP) AS fecha_compra, precio_pagado
    FROM read_parquet('{compras}')
    WHERE compra_id IS NOT NULL AND silla_id IS NOT NULL AND evento_id IS NOT NULL AND fecha_compra IS NOT NULL
)
SELECT e.nombre_evento, z.nombre_zona, year(v.fecha_compra) AS anio, month(v.fecha_compra) AS mes,
       COUNT(*) AS boletas, SUM(v.precio_pagado) AS ingresos
FROM v
JOIN read_parquet('{eventos}') e ON e.evento_id = v.evento_id
JOIN read_parquet('{sillas}') s ON s.silla_id = v.silla_id
JOIN read_parquet('{zonas}') z ON z.zona_id = s.zona_id
 AND CAST(v.fecha_compra AS DATE) BETWEEN CAST(z.valido_desde AS DATE) AND CAST(z.valido_hasta AS DATE)
GROUP BY e.evento_id, e.nombre_evento, z.zona_id, z.nombre_zona, anio, mes
"""

SQL_GOLD = """
SELECT e.nombre_evento, z.nombre_zona, t.anio, t.mes, COUNT(*) AS boletas, SUM(f.precio_pagado) AS ingresos
FROM fact_ventas_boletas f
JOIN dim_tiempo t ON t.tiempo_sk = f.tiempo_sk
JOIN dim_evento e ON e.evento_sk = f.evento_sk
JOIN dim_zona z ON z.zona_sk = f.zona_sk
GROUP BY e.evento_id, e.nombre_evento, z.zona_id, z.nombre_zona, t.anio, t.mes
"""


def preparar_sqlite() -> sqlite3.Connection:
    """Carga Silver en SQLite (en memoria) y crea los índices típicos de un OLTP."""
    conexion = sqlite3.connect(":memory:")
    for tabla in ("canales", "zonas", "eventos", "sillas", "usuarios", "compras_confirmadas", "intentos_compra"):
        df = pd.read_parquet(config.SILVER / f"{tabla}_silver.parquet")
        for col in COLUMNAS_FECHA_DIA.get(tabla, []):
            df[col] = df[col].map(str)
        df.to_sql(tabla, conexion, index=False)
    for sentencia in INDICES_OLTP:
        conexion.execute(sentencia)
    conexion.execute("ANALYZE")
    return conexion


def conectar_gold() -> duckdb.DuckDBPyConnection:
    """Conexión DuckDB con una vista por cada Parquet de Gold (read_parquet)."""
    conexion = duckdb.connect()
    for archivo in sorted(config.GOLD.glob("*.parquet")):
        ruta = archivo.as_posix()
        conexion.execute(f"CREATE VIEW {archivo.stem} AS SELECT * FROM read_parquet('{ruta}')")
    return conexion


def _sql_bronze() -> str:
    """Completa la consulta de Bronze con los archivos más recientes."""
    rutas = {t: archivo_bronze_mas_reciente(t).as_posix() for t in ("compras_confirmadas", "eventos", "sillas", "zonas")}
    return SQL_BRONZE.format(compras=rutas["compras_confirmadas"], eventos=rutas["eventos"],
                             sillas=rutas["sillas"], zonas=rutas["zonas"])


def medir(consulta: Callable[[], Filas]) -> tuple[list[float], Filas]:
    """Calienta una vez y mide `CORRIDAS` ejecuciones (ms). Devuelve tiempos y resultado."""
    resultado = sorted(consulta())
    tiempos = []
    for _ in range(CORRIDAS):
        inicio = time.perf_counter()
        consulta()
        tiempos.append((time.perf_counter() - inicio) * 1000)
    return tiempos, resultado


def ejecutar() -> list[dict]:
    """Corre el benchmark, verifica que los tres motores coincidan y escribe docs/benchmark.md."""
    sqlite = preparar_sqlite()
    duck = conectar_gold()
    sql_bronze = _sql_bronze()
    motores = [
        ("(a) SQLite, almacén por filas (OLTP-like)", "Silver normalizado + índices",
         lambda: sqlite.execute(SQL_SQLITE).fetchall()),
        ("(b) DuckDB sobre Bronze crudo", "Parquet sucio, limpieza en la consulta",
         lambda: duck.execute(sql_bronze).fetchall()),
        ("(c) DuckDB sobre Gold (estrella)", "Parquet columnar modelado",
         lambda: duck.execute(SQL_GOLD).fetchall()),
    ]
    resultados = []
    for nombre, fuente, consulta in motores:
        tiempos, filas = medir(consulta)
        resultados.append({"motor": nombre, "fuente": fuente, "tiempos": tiempos,
                           "mediana": statistics.median(tiempos), "filas": filas})

    referencia = resultados[0]["filas"]
    for r in resultados:
        if r["filas"] != referencia:
            raise AssertionError(f"El benchmark no es válido: {r['motor']} devolvió números distintos")
        r["factor"] = resultados[0]["mediana"] / r["mediana"]
    print(f"  [OK] los tres motores devolvieron los mismos {len(referencia)} grupos (boletas e ingresos idénticos)")

    for r in resultados:
        print(f"  {r['motor']}: mediana {r['mediana']:.2f} ms | mejora vs (a): {r['factor']:.1f}x")
    escribir_markdown(resultados, len(referencia), sqlite)
    return resultados


def escribir_markdown(resultados: list[dict], grupos: int, sqlite: sqlite3.Connection) -> None:
    """Guarda docs/benchmark.md con la tabla medida y las condiciones del experimento."""
    ventas = sqlite.execute("SELECT COUNT(*) FROM compras_confirmadas").fetchone()[0]
    filas = [
        f"| {r['motor']} | {r['fuente']} | {r['mediana']:.2f} | {min(r['tiempos']):.2f} - {max(r['tiempos']):.2f} | {r['factor']:.1f}x |"
        for r in resultados
    ]
    texto = "\n".join([
        "# Benchmark: OLTP vs columnar",
        "",
        "Misma agregación lógica en tres motores: **boletas e ingresos por evento x zona x mes**.",
        "",
        f"- Ventas confirmadas: {ventas:,}".replace(",", "."),
        f"- Grupos devueltos (evento x zona x mes): {grupos}",
        f"- Corridas por motor: {CORRIDAS} (más un calentamiento previo); se reporta la mediana.",
        "- El tiempo de carga no se incluye: solo cuenta ejecutar la consulta y traer el resultado.",
        "- Los tres motores devuelven exactamente las mismas cifras (el pipeline lo verifica con una aserción).",
        f"- Máquina: {platform.platform()}, {os.cpu_count()} hilos lógicos; Python {platform.python_version()}, "
        f"DuckDB {duckdb.__version__}, SQLite {sqlite3.sqlite_version}.",
        f"- Ejecutado: {datetime.now():%Y-%m-%d %H:%M}.",
        "",
        "| Motor | Fuente | Mediana (ms) | Rango (ms) | Mejora vs (a) |",
        "|---|---|---:|---:|---:|",
        *filas,
        "",
        "## Cómo leer el resultado",
        "",
        "- **(a)** es un almacén por filas con índices típicos de OLTP (únicos por clave, índices de unión). "
        "Está pensado para buscar y modificar filas puntuales; aquí se le pide recorrer todas las ventas y unir cuatro tablas.",
        "- **(b)** lee Parquet columnar sin modelar, por lo que la consulta debe limpiar al vuelo; "
        "muestra cuánto aporta el formato columnar sin el modelado.",
        "- **(c)** lee solo las columnas necesarias de la tabla de hechos y de dimensiones pequeñas con claves enteras.",
        "- DuckDB usa varios hilos y SQLite solo uno; parte de la diferencia viene de ahí y no solo del formato de almacenamiento.",
        "- Con volúmenes menores de 100.000 filas las diferencias se reducen; este conjunto supera las 200.000 ventas.",
        "",
    ])
    config.DOCS.mkdir(parents=True, exist_ok=True)
    (config.DOCS / "benchmark.md").write_text(texto, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    ejecutar()
