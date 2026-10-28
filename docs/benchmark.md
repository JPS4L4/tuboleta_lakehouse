# Benchmark: OLTP vs columnar

Misma agregación lógica en tres motores: **boletas e ingresos por evento x zona x mes**.

- Ventas confirmadas: 206.325
- Grupos devueltos (evento x zona x mes): 60
- Corridas por motor: 5 (más un calentamiento previo); se reporta la mediana.
- El tiempo de carga no se incluye: solo cuenta ejecutar la consulta y traer el resultado.
- Los tres motores devuelven exactamente las mismas cifras (el pipeline lo verifica con una aserción).
- Máquina: Windows-11-10.0.26200-SP0, 12 hilos lógicos; Python 3.12.10, DuckDB 2.0.0, SQLite 3.49.1.
- Ejecutado: 2026-10-28 11:16.

| Motor | Fuente | Mediana (ms) | Rango (ms) | Mejora vs (a) |
|---|---|---:|---:|---:|
| (a) SQLite, almacén por filas (OLTP-like) | Silver normalizado + índices | 303.96 | 300.42 - 306.89 | 1.0x |
| (b) DuckDB sobre Bronze crudo | Parquet sucio, limpieza en la consulta | 78.54 | 77.93 - 83.97 | 3.9x |
| (c) DuckDB sobre Gold (estrella) | Parquet columnar modelado | 11.58 | 11.17 - 11.74 | 26.2x |

## Cómo leer el resultado

- **(a)** es un almacén por filas con índices típicos de OLTP (únicos por clave, índices de unión). Está pensado para buscar y modificar filas puntuales; aquí se le pide recorrer todas las ventas y unir cuatro tablas.
- **(b)** lee Parquet columnar sin modelar, por lo que la consulta debe limpiar al vuelo; muestra cuánto aporta el formato columnar sin el modelado.
- **(c)** lee solo las columnas necesarias de la tabla de hechos y de dimensiones pequeñas con claves enteras.
- DuckDB usa varios hilos y SQLite solo uno; parte de la diferencia viene de ahí y no solo del formato de almacenamiento.
- Con volúmenes menores de 100.000 filas las diferencias se reducen; este conjunto supera las 200.000 ventas.
