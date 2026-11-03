"""Taller 4 - Laboratorio de optimización sobre el Gold de TuBoleta (DuckDB + Parquet).

Ubicación sugerida: scripts/taller4_optimizacion.py  ->  python -m scripts.taller4_optimizacion
Si falta lakehouse/gold/*.parquet lo genera con los pasos del M3 (extract -> silver -> gold), sin correr analyze.py.

Qué hace (una intervención por problema):
  1. Captura EXPLAIN ANALYZE de 3 consultas ANTES y DESPUÉS  -> docs/taller4/planes/*.txt
  2. Mide baseline y resultado (warm-up x3, mediana de 5)      -> docs/taller4/benchmarks.md
  3. Intervenciones (no toca el Gold original, trabaja en lakehouse/gold_t4/):
       Q1 -> I-3  ordenar fact_ventas_boletas por tiempo_sk con row groups pequeños
       Q2 -> I-6  particionar la fact estilo Hive (year/month) y podar carpetas
       Q3 -> I-2  ANALYZE sobre tablas materializadas (experimento de control, se espera ~1.0x)
"""
from __future__ import annotations

import json
import platform
import re
import shutil
import statistics
import sys
import time
from pathlib import Path

import duckdb
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
GOLD = RAIZ / "lakehouse" / "gold"
T4 = RAIZ / "lakehouse" / "gold_t4"
OUT = RAIZ / "docs" / "taller4"
PLANES = OUT / "planes"
TABLAS = ["fact_ventas_boletas", "fact_intentos_compra", "dim_tiempo", "dim_evento", "dim_zona", "dim_canal"]

# ---------------------------------------------------------------- consultas
Q1 = ("Q1 - Ingresos por evento en septiembre 2026", """
    SELECT e.nombre_evento, t.mes, COUNT(*) AS boletas, SUM(f.precio_pagado) AS ingresos
    FROM fact_ventas_boletas f
    JOIN dim_tiempo t ON t.tiempo_sk = f.tiempo_sk
    JOIN dim_evento e ON e.evento_sk = f.evento_sk
    WHERE t.anio = 2026 AND t.mes = 9
    GROUP BY 1, 2""")

# Q2 filtra por rango de tiempo_sk (YYYYMMDDHH). En la versión particionada se usa year/month.
Q2_BASE = ("Q2 - Ingresos por zona en septiembre 2026 (filtro directo en la fact)", """
    SELECT zona_sk, COUNT(*) AS boletas, SUM(precio_pagado) AS ingresos
    FROM fact_ventas_boletas
    WHERE tiempo_sk BETWEEN 2026090100 AND 2026093023
    GROUP BY 1""")
Q2_PART = """
    SELECT zona_sk, COUNT(*) AS boletas, SUM(precio_pagado) AS ingresos
    FROM read_parquet('{ruta}/**/*.parquet', hive_partitioning=true)
    WHERE year = 2026 AND month = 9
    GROUP BY 1"""

Q3 = ("Q3 - Embudo de conversión por evento", """
    SELECT d.nombre_evento, COUNT(*) AS intentos, SUM(i.es_compra) AS compras,
           SUM(i.es_abandono) AS abandonos, SUM(i.es_rechazo_unique) AS rechazos
    FROM fact_intentos_compra i JOIN dim_evento d ON d.evento_sk = i.evento_sk
    GROUP BY 1""")


# ---------------------------------------------------------------- utilidades
def conectar(ruta_fact_ventas: str | None = None, materializar: bool = False) -> duckdb.DuckDBPyConnection:
    """Conexión con las tablas de Gold como vistas (o como tablas reales si materializar=True)."""
    con = duckdb.connect()
    for t in TABLAS:
        ruta = ruta_fact_ventas if (ruta_fact_ventas and t == "fact_ventas_boletas") else GOLD / f"{t}.parquet"
        objeto = "TABLE" if materializar else "VIEW"
        con.execute(f"CREATE {objeto} {t} AS SELECT * FROM read_parquet('{ruta}')")
    return con


def mediana_ms(con, sql: str, calentamiento: int = 3, corridas: int = 5) -> float:
    for _ in range(calentamiento):
        con.execute(sql).fetchall()
    tiempos = []
    for _ in range(corridas):
        t0 = time.perf_counter()
        con.execute(sql).fetchall()
        tiempos.append((time.perf_counter() - t0) * 1000)
    return statistics.median(tiempos)


def guardar_plan(con, sql: str, nombre: str) -> str:
    """EXPLAIN ANALYZE completo a archivo de texto (se guarda sin interpretar, como pide el taller)."""
    texto = con.execute("EXPLAIN ANALYZE " + sql).fetchall()[0][1]
    PLANES.mkdir(parents=True, exist_ok=True)
    (PLANES / f"{nombre}.txt").write_text(texto, encoding="utf-8")
    guardar_perfil(con, sql, nombre)
    return texto


def guardar_perfil(con, sql: str, nombre: str) -> None:
    """Per-operator timing, real vs estimated rows. DuckDB 2.0 only exposes operator timing in the JSON profile."""
    ruta = PLANES / f"{nombre}_perfil.json"
    con = con.cursor()  # own client context: profiling settings must not leak into later EXPLAIN ANALYZE output
    con.execute("PRAGMA enable_profiling='json'")
    con.execute("SET profiling_mode='detailed'")
    con.execute(f"SET profiling_output='{ruta.as_posix()}'")
    con.execute(sql).fetchall()
    con.execute("PRAGMA disable_profiling")
    perfil = json.loads(ruta.read_text(encoding="utf-8"))
    ruta.unlink()
    q = perfil["query"]
    lineas = [f"total_time_ms={q['total_time'] * 1000:.3f}  bytes_read={perfil['io']['total_bytes_read']:,}  "
              f"row_groups={q['total_row_groups_scanned']}/{q['total_row_groups_to_scan']}", "",
              f"{'operador':<40}{'ms':>9}{'filas reales':>14}{'filas estimadas':>17}"]

    def recorrer(nodo: dict, nivel: int) -> None:
        info = nodo.get("extra_info", {})
        etiqueta = "  " * nivel + nodo["type"] + (f" [{Path(info['Filename(s)']).stem}]" if "Filename(s)" in info else "")
        lineas.append(f"{etiqueta:<40}{nodo['timing'] * 1000:>9.3f}{nodo['intermediate_rows']:>14,}"
                      f"{info.get('Estimated Cardinality', '-'):>17}")
        for hijo in nodo.get("children", []):
            recorrer(hijo, nivel + 1)

    for raiz in perfil["operator"]:
        recorrer(raiz, 0)
    (PLANES / f"{nombre}_perfil.txt").write_text("\n".join(lineas), encoding="utf-8")


def row_groups(ruta: str) -> int:
    con = duckdb.connect()
    return con.execute(f"SELECT COUNT(DISTINCT row_group_id) FROM parquet_metadata('{ruta}')").fetchone()[0]


def operadores(plan: str) -> list[str]:
    """Physical operator names in plan order (e.g. 'Hash Join', 'Table Scan')."""
    return [op for op in re.findall(r"╭─ ([A-Za-z ]+?) ─", plan) if op != "Summary"]


def asegurar_gold() -> None:
    """Build the M3 Gold layer if missing (Parquet is gitignored). Skips analyze.py so M3 docs stay untouched."""
    if (GOLD / "fact_ventas_boletas.parquet").exists():
        return
    from scripts import extract, transform_gold, transform_silver
    print("[setup] Gold no encontrado: generando Bronze -> Silver -> Gold del M3...")
    for paso in (extract.ejecutar, transform_silver.ejecutar, transform_gold.ejecutar):
        paso()


# ---------------------------------------------------------------- experimento
def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    asegurar_gold()
    shutil.rmtree(T4, ignore_errors=True)
    T4.mkdir(parents=True)
    filas = []

    # ---- BASELINE ------------------------------------------------------
    con0 = conectar()
    base = {}
    for titulo, sql in (Q1, Q2_BASE, Q3):
        clave = titulo.split(" - ")[0]
        guardar_plan(con0, sql, f"{clave}_antes")
        base[clave] = mediana_ms(con0, sql)
        print(f"[baseline] {titulo}: {base[clave]:.2f} ms")
    rg_antes = row_groups(str(GOLD / "fact_ventas_boletas.parquet"))
    print(f"[baseline] row groups de fact_ventas_boletas: {rg_antes}")

    # ---- Q1: I-3 ordenar por tiempo_sk + row groups de 20K -------------
    df = pd.read_parquet(GOLD / "fact_ventas_boletas.parquet")
    ordenado = T4 / "fact_ventas_boletas_ordenada.parquet"
    df.sort_values("tiempo_sk").to_parquet(ordenado, index=False, row_group_size=20_000)
    con1 = conectar(str(ordenado))
    guardar_plan(con1, Q1[1], "Q1_despues")
    t1 = mediana_ms(con1, Q1[1])
    assert sorted(con0.execute(Q1[1]).fetchall()) == sorted(con1.execute(Q1[1]).fetchall()), "Q1: resultados distintos"
    filas.append(("Q1", "Sin data skipping: 1 row group, se lee toda la fact", "I-3 ordenar por tiempo_sk (rg=20K)",
                  base["Q1"], t1, f"row groups: {rg_antes} -> {row_groups(str(ordenado))}"))

    # ---- Q2: I-6 particionado Hive -------------------------------------
    df["year"] = df["tiempo_sk"] // 1_000_000
    df["month"] = (df["tiempo_sk"] // 10_000) % 100
    base_part = T4 / "fact_particionada"
    for (y, m), g in df.groupby(["year", "month"]):
        d = base_part / f"year={y}" / f"month={m:02d}"
        d.mkdir(parents=True)
        g.drop(columns=["year", "month"]).to_parquet(d / "data.parquet", index=False)
    con2 = duckdb.connect()
    sql_part = Q2_PART.format(ruta=base_part.as_posix())
    guardar_plan(con2, sql_part, "Q2_despues")
    t2 = mediana_ms(con2, sql_part)
    r_a = sorted(con0.execute(Q2_BASE[1]).fetchall())
    r_d = sorted(con2.execute(sql_part).fetchall())
    assert [(a, b, int(c)) for a, b, c in r_a] == [(a, b, int(c)) for a, b, c in r_d], "resultados distintos"
    n_part = len(list(base_part.glob("year=*/month=*")))
    filas.append(("Q2", "Filtro por mes sobre un único Parquet (full scan de la fact)", "I-6 particionar Hive year/month",
                  base["Q2"], t2, f"carpetas leídas: 1 de {n_part} (partition pruning)"))

    # ---- Q3: I-2 ANALYZE (control) -------------------------------------
    # Same materialized connection before and after, so ANALYZE is the only variable.
    con3 = conectar(materializar=True)          # tablas reales: aquí ANALYZE sí tiene objeto
    plan_a = guardar_plan(con3, Q3[1], "Q3_antes_analyze")
    t3_antes = mediana_ms(con3, Q3[1])
    r3_antes = sorted(con3.execute(Q3[1]).fetchall())
    con3.execute("ANALYZE")
    plan_d = guardar_plan(con3, Q3[1], "Q3_despues")
    t3 = mediana_ms(con3, Q3[1])
    assert r3_antes == sorted(con3.execute(Q3[1]).fetchall()), "Q3: resultados distintos"
    ops = operadores(plan_d)
    cambio = "No — plan idéntico: " + " + ".join(dict.fromkeys(ops)) if ops == operadores(plan_a) else "Sí — cambió el árbol de operadores"
    filas.append(("Q3", "Sin problema de acceso: agregación simple, join con dim de 5 filas", "I-2 ANALYZE (control)",
                  t3_antes, t3, cambio))

    # ---- Tabla de benchmarks (formato 4.1 del taller) -------------------
    md = ["# Benchmarks Taller 4", "",
          f"Motor: DuckDB {duckdb.__version__} sobre Parquet · Python {platform.python_version()} · "
          f"{platform.system()} {platform.release()} · CPU: {platform.processor() or 'n/d'}",
          "Método: warm-up ×3, mediana de 5 ejecuciones. Q3 antes/después medido sobre tablas materializadas.", "",
          "| Query | Problema (vocabulario M4) | Intervención | t antes (ms) | t después (ms) | Factor | ¿Cambió el plan? |",
          "|---|---|---|---:|---:|---:|---|"]
    for q, prob, interv, a, d, plan in filas:
        md.append(f"| {q} | {prob} | {interv} | {a:.2f} | {d:.2f} | {a / d:.2f}x | {plan} |")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "benchmarks.md").write_text("\n".join(md), encoding="utf-8")
    print("\n" + "\n".join(md))
    print(f"\nPlanes en {PLANES}")


if __name__ == "__main__":
    main()
