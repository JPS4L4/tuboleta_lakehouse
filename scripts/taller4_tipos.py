"""Intervencion de tipos: fecha texto en control VARCHAR frente a TIMESTAMP en Silver."""
from __future__ import annotations
import statistics, time
from pathlib import Path
import duckdb

ROOT=Path(__file__).resolve().parents[1]
SILVER=ROOT/"lakehouse"/"silver"
OUT=ROOT/"docs"/"taller4"
PLANES=OUT/"planes"

def median(con,sql):
    con.execute(sql).fetchall()
    values=[]
    for _ in range(9):
        start=time.perf_counter(); con.execute(sql).fetchall()
        values.append((time.perf_counter()-start)*1000)
    return statistics.median(values)

def main():
    silver=SILVER/"compras_confirmadas_silver.parquet"
    if not silver.exists(): raise FileNotFoundError("Silver no existe. Ejecuta python main.py.")
    con=duckdb.connect()
    con.execute(f"CREATE VIEW silver AS SELECT * FROM read_parquet('{silver.as_posix()}')")
    # Mismas filas y valores: solo se serializa la fecha como texto para aislar el tipo.
    con.execute("CREATE VIEW bronze AS SELECT * REPLACE (CAST(fecha_compra AS VARCHAR) AS fecha_compra) FROM silver")
    # Ambos escenarios aplican el mismo intervalo temporal y devuelven conteo/ingresos.
    q_text="""SELECT COUNT(*) AS ventas, SUM(precio_pagado) AS ingresos
              FROM bronze
              WHERE CAST(fecha_compra AS TIMESTAMP) >= TIMESTAMP '2026-09-01 00:00:00'
                AND CAST(fecha_compra AS TIMESTAMP) < TIMESTAMP '2026-10-01 00:00:00'"""
    q_typed="""SELECT COUNT(*) AS ventas, SUM(precio_pagado) AS ingresos
               FROM silver
               WHERE fecha_compra >= TIMESTAMP '2026-09-01 00:00:00'
                 AND fecha_compra < TIMESTAMP '2026-10-01 00:00:00'"""
    a=con.execute(q_text).fetchall(); b=con.execute(q_typed).fetchall()
    if a!=b: raise AssertionError(f"Resultados distintos: Bronze={a}, Silver={b}")
    pa=con.execute("EXPLAIN ANALYZE "+q_text).fetchall()
    pb=con.execute("EXPLAIN ANALYZE "+q_typed).fetchall()
    plan_a="\n".join(str(x[-1]) for x in pa); plan_b="\n".join(str(x[-1]) for x in pb)
    PLANES.mkdir(parents=True,exist_ok=True)
    (PLANES/"Q3_tipos_antes_texto.txt").write_text(plan_a,encoding="utf-8")
    (PLANES/"Q3_tipos_despues_timestamp.txt").write_text(plan_b,encoding="utf-8")
    before=median(con,q_text); after=median(con,q_typed)
    OUT.mkdir(parents=True,exist_ok=True)
    md=["# Intervención de tipos — texto frente a TIMESTAMP","",
        f"- Control: mismas filas Silver; fecha_compra se serializa como VARCHAR.",
        "- Antes: fecha serializada como VARCHAR; la consulta convierte con CAST para comparar.",
        "- Después: Silver conserva fecha_compra como TIMESTAMP; el predicado opera directamente sobre el tipo temporal.",
        "- Método: calentamiento y mediana de 9 ejecuciones en la misma conexión DuckDB.",
        f"- Resultado validado en ambos escenarios: {a[0][0]:,} ventas; ingresos {a[0][1]:,.2f} COP.","",
        "| Escenario | Mediana (ms) |",
        "|---|---:|",
        f"| Control VARCHAR + CAST | {before:.3f} |",
        f"| Silver TIMESTAMP | {after:.3f} |",
        f"| Factor antes/después | {before/after:.2f}x |","",
        "La conversión de tipo evita aplicar CAST fila por fila en la consulta y deja el dato tipado para filtros y operaciones temporales. El tiempo puede ser similar o incluso mayor por caché, costo de lectura, optimizaciones del motor y tamaño del conjunto; se reporta sin ocultar el resultado.",
        "","## Evidencia",
        "- planes/Q3_tipos_antes_texto.txt",
        "- planes/Q3_tipos_despues_timestamp.txt"]
    (OUT/"intervencion_tipos.md").write_text("\n".join(md),encoding="utf-8")
    print("\n".join(md))

if __name__=="__main__": main()
