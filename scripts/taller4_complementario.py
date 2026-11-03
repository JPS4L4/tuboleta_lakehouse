"""Taller 4 - Análisis complementario de resultados modestos (no es una intervención nueva).

Uso: python -m scripts.taller4_complementario   (requiere haber corrido antes scripts.taller4_optimizacion)
No reescribe los planes de docs/taller4/planes/; solo genera docs/taller4/analisis_complementario.md.

Responde las preguntas del enunciado sobre resultados modestos:
  A. Q1: ¿el paralelismo absorbe el beneficio de I-3? Se mide con threads=1 y con el valor por defecto.
  B. Q2: ¿cuánto del tiempo de I-6 es listar/parsear carpetas Hive y cuánto es leer datos?
  C. Q1: ¿ANALYZE corrige el error de estimación del join (vistas vs tablas materializadas)?
"""
from __future__ import annotations

import json
import os
import re
import sys

import duckdb

from scripts.taller4_optimizacion import OUT, Q1, Q2_BASE, Q2_PART, T4, conectar, mediana_ms

CORRIDAS = 15  # more runs than the baseline (5): these differences are sub-millisecond


def cpu_operadores_ms(con, sql: str) -> tuple[float, float]:
    """(sum of per-operator CPU time, wall time) in ms from DuckDB's JSON profile."""
    ruta = OUT / "_perfil_tmp.json"
    c = con.cursor()
    c.execute("PRAGMA enable_profiling='json'")
    c.execute(f"SET profiling_output='{ruta.as_posix()}'")
    c.execute(sql).fetchall()
    c.execute("PRAGMA disable_profiling")
    perfil = json.loads(ruta.read_text(encoding="utf-8"))
    ruta.unlink()

    def suma(nodo: dict) -> float:
        return nodo["timing"] + sum(suma(h) for h in nodo.get("children", []))

    return sum(suma(r) for r in perfil["operator"]) * 1000, perfil["query"]["total_time"] * 1000


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ordenada = T4 / "fact_ventas_boletas_ordenada.parquet"
    particion = T4 / "fact_particionada"
    if not ordenada.exists():
        raise SystemExit("Falta lakehouse/gold_t4: ejecuta primero `python -m scripts.taller4_optimizacion`.")

    md = ["# Análisis complementario — Taller 4", "",
          f"DuckDB {duckdb.__version__} · {os.cpu_count()} hilos lógicos · mediana de {CORRIDAS} corridas con warm-up ×3.", "",
          "## A. Q1 — paralelismo y overhead fijo", "",
          "| Fact | threads | Mediana (ms) | CPU sumada de operadores (ms) | Wall del perfil (ms) | Overhead fuera de operadores (ms) |",
          "|---|---:|---:|---:|---:|---:|"]
    for etiqueta, ruta in (("original (1 row group)", None), ("ordenada (11 row groups)", str(ordenada))):
        for hilos in (1, os.cpu_count()):
            con = conectar(ruta)
            con.execute(f"SET threads={hilos}")
            t = mediana_ms(con, Q1[1], corridas=CORRIDAS)
            cpu, wall = cpu_operadores_ms(con, Q1[1])
            # wall - cpu only means "fixed overhead" when operators run on one thread
            overhead = f"{wall - cpu:.2f}" if hilos == 1 else "n/a (CPU sumada entre hilos)"
            md.append(f"| {etiqueta} | {hilos} | {t:.2f} | {cpu:.2f} | {wall:.2f} | {overhead} |")

    md += ["", "## B. Q2 — costo del particionado Hive", "",
           "| Variante | Mediana (ms) |", "|---|---:|"]
    variantes = [
        ("archivo único, filtro por rango de tiempo_sk (baseline)", conectar(), Q2_BASE[1]),
        ("glob Hive + partition pruning (I-6)", duckdb.connect(), Q2_PART.format(ruta=particion.as_posix())),
        ("lectura directa de la partición month=09 (sin glob ni Hive)", duckdb.connect(),
         f"SELECT zona_sk, COUNT(*), SUM(precio_pagado) FROM read_parquet('{(particion / 'year=2026' / 'month=09' / 'data.parquet').as_posix()}') GROUP BY 1"),
    ]
    resultados = []
    for nombre, con, sql in variantes:
        resultados.append(sorted((a, b, int(c)) for a, b, c in con.execute(sql).fetchall()))
        md.append(f"| {nombre} | {mediana_ms(con, sql, corridas=CORRIDAS):.2f} |")
    assert resultados[0] == resultados[1] == resultados[2], "Q2: las variantes no devuelven lo mismo"

    md += ["", "## C. Q1 — ¿ANALYZE corrige la estimación de cardinalidad del join?", "",
           "| Fuente de datos | Estimada antes de ANALYZE | Estimada después de ANALYZE | Real |", "|---|---:|---:|---:|"]
    for nombre, materializar in (("vistas sobre Parquet", False), ("tablas materializadas", True)):
        con = conectar(materializar=materializar)
        estimada = lambda: re.findall(r"~([\d,]+) rows", con.execute("EXPLAIN " + Q1[1]).fetchall()[0][1])[2]  # noqa: E731
        antes = estimada()
        con.execute("ANALYZE")
        real = sum(fila[2] for fila in con.execute(Q1[1]).fetchall())  # sum of boletas = rows out of the joins
        md.append(f"| {nombre} | {antes} | {estimada()} | {real:,} |")

    (OUT / "analisis_complementario.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md))


if __name__ == "__main__":
    main()
