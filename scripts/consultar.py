"""Consultas en vivo sobre Gold con DuckDB (para la exposición).

Uso:
    python -m scripts.consultar --lista               # lista las consultas listas
    python -m scripts.consultar ocupacion             # ejecuta una consulta lista
    python -m scripts.consultar "SELECT ..."          # ejecuta SQL libre

Abre DuckDB en memoria, registra una vista por cada Parquet de Gold (la misma
función que usa el análisis) e imprime el resultado y el tiempo en milisegundos.
Las vistas disponibles son las tablas de Gold: fact_ventas_boletas,
fact_intentos_compra, dim_tiempo, dim_evento, dim_zona, dim_silla, dim_usuario y dim_canal.
"""
from __future__ import annotations

import sys
import time

import duckdb

from scripts import analyze, benchmark, config

# Nombre corto -> título de la consulta en analyze.CONSULTAS (se reutiliza su SQL).
_TITULOS_LISTAS = {
    "ocupacion": "2. Ocupación e ingresos por evento y zona",
    "embudo": "5a. Embudo de conversión por evento",
    "vip": "6. SCD Tipo 2: ingresos VIP por versión de precio",
    "canales": "3. Volumen, ingresos y ticket promedio por canal",
}


def _consultas_listas() -> dict[str, tuple[str, str]]:
    """Devuelve {nombre_corto: (titulo, sql)} tomando el SQL de analyze.CONSULTAS."""
    por_titulo = {titulo: sql for titulo, _pregunta, sql in analyze.CONSULTAS}
    return {nombre: (titulo, por_titulo[titulo]) for nombre, titulo in _TITULOS_LISTAS.items()}


def _imprimir_lista(listas: dict[str, tuple[str, str]]) -> None:
    print("Consultas listas (python -m scripts.consultar <nombre>):")
    for nombre, (titulo, _sql) in listas.items():
        print(f"  {nombre:<10} {titulo}")


def _gold_existe() -> bool:
    return any(config.GOLD.glob("*.parquet"))


def ejecutar(argumentos: list[str]) -> int:
    """Ejecuta la consulta pedida. Devuelve 0 si salió bien y 1 si hubo un error."""
    listas = _consultas_listas()
    if not argumentos or argumentos[0] in {"-h", "--help"}:
        print(__doc__)
        _imprimir_lista(listas)
        return 0
    if argumentos[0] == "--lista":
        _imprimir_lista(listas)
        return 0

    peticion = " ".join(argumentos).strip()
    if peticion.lower() in listas:
        titulo, sql = listas[peticion.lower()]
        print(f"{titulo}")
    else:
        sql = peticion
        if " " not in sql:  # una sola palabra: probablemente un nombre mal escrito
            print(f"No existe la consulta '{sql}'. Usa --lista para ver las disponibles.")
            return 1

    if not _gold_existe():
        print("No hay Parquet de Gold en lakehouse/gold. Ejecuta primero: python main.py")
        return 1

    conexion = benchmark.conectar_gold()
    try:
        inicio = time.perf_counter()
        df = conexion.execute(sql).df()
        ms = (time.perf_counter() - inicio) * 1000
    except duckdb.Error as error:
        print(f"Error en la consulta: {error}")
        return 1

    print(df.to_string(index=False) if len(df) else "(sin filas)")
    print(f"\n{len(df)} filas en {ms:.1f} ms")
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(ejecutar(sys.argv[1:]))
