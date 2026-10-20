"""Orquestador del Mini-Lakehouse TuBoleta.

Ejecuta en orden: extracción (con generación sintética) -> Silver -> Gold -> análisis.
Imprime el tiempo de cada paso y el total; si un paso falla termina con código 1.

Uso:  python main.py
"""
from __future__ import annotations

import sys
import time
import traceback

from scripts import analyze, extract, transform_gold, transform_silver

PASOS = [
    ("1. Extracción: OLTP -> Bronze", extract.ejecutar),
    ("2. Transformación: Bronze -> Silver", transform_silver.ejecutar),
    ("3. Modelado: Silver -> Gold", transform_gold.ejecutar),
    ("4. Análisis: consultas y benchmark", analyze.ejecutar),
]


def main() -> int:
    """Corre todos los pasos y devuelve el código de salida (0 = éxito, 1 = falla)."""
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    tiempos: list[tuple[str, float]] = []
    inicio_total = time.perf_counter()
    for nombre, paso in PASOS:
        print(f"\n{'=' * 70}\n{nombre}\n{'=' * 70}")
        inicio = time.perf_counter()
        try:
            paso()
        except Exception:
            traceback.print_exc()
            print(f"\nERROR: falló el paso '{nombre}'. Pipeline detenido.")
            return 1
        tiempos.append((nombre, time.perf_counter() - inicio))
        print(f"-> {nombre}: {tiempos[-1][1]:.2f} s")

    print(f"\n{'=' * 70}\nResumen de tiempos\n{'=' * 70}")
    for nombre, segundos in tiempos:
        print(f"  {nombre:<40} {segundos:7.2f} s")
    print(f"  {'TOTAL':<40} {time.perf_counter() - inicio_total:7.2f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
